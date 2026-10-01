"""OpenClaw 설정 파일(JSON/JSON5)에서 `mcp.servers` 등록 항목을 수집한다.

이 모듈은 설정 파일을 읽기 전용으로 열어 파싱만 한다.
설정 속 명령 실행, 서버 접속, 도구 조회, 환경변수 값 해석, $include 파일 읽기는 하지 않는다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import json5

from .redaction import ENV_REF_RE, REDACTED, Redactor, classify_secret_ref, looks_like_secret_value

REGISTRY_PATH = ("mcp", "servers")

# OpenClaw `mcp.servers.<key>` 항목에서 값을 (가림 처리 후) 보존하는 원천 필드.
STRING_FIELDS = ("transport", "command", "cwd", "workingDirectory", "url")
# 값은 남기지 않고 존재 여부와 참조 이름만 남기는 인증·자격증명 관련 필드.
NAME_MAP_FIELDS = ("env", "headers")
PRESENCE_ONLY_FIELDS = ("auth", "oauth", "clientCert", "clientKey")

# 서버 항목을 부분 수집(partial)으로 만드는 문제 코드.
INCOMPLETE_ISSUE_CODES = frozenset({
    "field_type_invalid", "duplicate_key", "invalid_secret_ref", "collector_internal_error",
})
# 등록 영역이 없어도 수집 결과를 불완전하게 만드는 상위 사유 코드.
INCOMPLETE_REASON_CODES = frozenset({"duplicate_key"})


class _Obj(dict):
    """JSON5 객체.

    - duplicate_keys: 같은 키가 두 번 나오면 마지막 값만 남으므로 중복 키 이름을 따로 기록한다.
    - masked_keys: 비밀값처럼 보여 자리표시자(`<redacted-key-N>`)로 바꾼 키.
    """

    duplicate_keys: list[str]
    masked_keys: list[str]


def _assign_placeholders(keys: list[str]) -> dict[str, str]:
    """한 객체 안에서 비밀값처럼 보이는 키마다 자리표시자(`<redacted-key-N>`)를 정한다.

    - 같은 원래 키는 같은 자리표시자를 받는다. 따라서 원래 키의 실제 중복은 중복으로 남는다.
    - 서로 다른 원래 키는 서로 다른 번호를 받는다.
    - 같은 객체에 이미 있는 일반 키(예: 설정에 직접 적힌 `<redacted-key-1>`)와 같은 이름은 건너뛴다.
      그래서 가림 때문에 생기는 이름 충돌은 만들어지지 않는다.
    - 번호는 이 객체 안의 등장 순서이며 원래 키나 그 해시를 쓰지 않는다.
    """
    plain = {k for k in keys if not looks_like_secret_value(k)}
    mapping: dict[str, str] = {}
    n = 0
    for k in keys:
        if k in plain or k in mapping:
            continue
        while True:
            n += 1
            candidate = f"<redacted-key-{n}>"
            if candidate not in plain:
                break
        mapping[k] = candidate
    return mapping


def _object_pairs_hook(pairs: list[tuple[str, Any]]) -> _Obj:
    mapping = _assign_placeholders([k for k, _ in pairs])
    obj = _Obj()
    dups: list[str] = []
    masked: list[str] = []
    for k, v in pairs:
        safe = mapping.get(k, k)
        if safe != k and safe not in masked:
            masked.append(safe)
        if safe in obj and safe not in dups:
            dups.append(safe)  # 자리표시자는 겹치지 않으므로 여기 오는 것은 원래 키의 실제 중복뿐
        obj[safe] = v
    obj.duplicate_keys = dups
    obj.masked_keys = masked
    return obj


# ---- 경로 표기 ------------------------------------------------------------------

_SIMPLE_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def dotted_path(parts: tuple[str | int, ...]) -> str:
    out = ""
    for p in parts:
        if isinstance(p, int):
            out += f"[{p}]"
        elif _SIMPLE_KEY_RE.match(p):
            out += ("." if out else "") + p
        else:
            out += f"[{json.dumps(p, ensure_ascii=False)}]"
    return out or "(root)"


def json_pointer(parts: tuple[str | int, ...]) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


# ---- 파일 읽기·파싱 -------------------------------------------------------------

class CollectionFailure(Exception):
    """설정 파일 전체를 처리할 수 없는 경우 (파일 없음, 읽기 실패, 파싱 실패, 잘못된 구조)."""

    def __init__(self, outcome: str, code: str, message: str, **detail: Any):
        super().__init__(message)
        self.outcome = outcome
        self.reason = {"code": code, "message": message, **detail}


def read_config(path: Path) -> str:
    if not path.exists():
        raise CollectionFailure("file_not_found", "file_not_found", "설정 파일이 존재하지 않습니다.")
    if not path.is_file():
        raise CollectionFailure("read_error", "not_a_file", "설정 경로가 일반 파일이 아닙니다.")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CollectionFailure(
            "read_error", "read_failed", "설정 파일을 읽지 못했습니다.", os_error=type(exc).__name__
        ) from None
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CollectionFailure(
            "read_error", "decode_failed", "설정 파일이 UTF-8 텍스트가 아닙니다.", byte_offset=exc.start
        ) from None


_JSON5_POS_RE = re.compile(r":(\d+) .* at column (\d+)")


def parse_config(text: str) -> Any:
    try:
        return json5.loads(text, object_pairs_hook=_object_pairs_hook)
    except ValueError as exc:
        # 파서 메시지에는 원문 문자가 섞일 수 있으므로 줄·열 번호만 남긴다.
        detail: dict[str, int] = {}
        m = _JSON5_POS_RE.search(str(exc))
        if m:
            detail = {"line": int(m.group(1)), "column": int(m.group(2))}
        raise CollectionFailure("parse_error", "json5_syntax_error", "JSON5 구문을 해석하지 못했습니다.", **detail) from None
    except RecursionError:
        raise CollectionFailure("parse_error", "nesting_too_deep", "설정의 중첩 깊이가 너무 깊습니다.") from None


# ---- $include 감지 --------------------------------------------------------------

def _find_includes(node: Any, parts: tuple = ()) -> list[tuple[tuple, Any]]:
    found: list[tuple[tuple, Any]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$include":
                found.append((parts, v))
            else:
                found.extend(_find_includes(v, parts + (k,)))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            found.extend(_find_includes(v, parts + (i,)))
    return found


def _affects_registry(container: tuple) -> bool:
    """이 위치의 $include가 mcp.servers 내용을 바꿀 수 있는가 (조상 또는 하위 위치)."""
    n = min(len(container), len(REGISTRY_PATH))
    return tuple(container[:n]) == REGISTRY_PATH[:n]


def _include_record(container: tuple, value: Any, reason: str) -> dict:
    """$include 위치와 대상 경로를 기록한다. 대상 문자열도 결과로 나가므로 가림 처리한다."""
    path = dotted_path(container) if container else "(root)"
    redactor = Redactor()
    if isinstance(value, str):
        targets: Any = [redactor.sanitize_string(value, path)]
    elif isinstance(value, list) and all(isinstance(v, str) for v in value):
        targets = [redactor.sanitize_string(v, f"{path}[{i}]") for i, v in enumerate(value)]
    else:
        targets = {"type": _type_name(value)}
    record = {"kind": "include", "field_path": path, "targets": targets, "reason": reason}
    if redactor.redactions:
        record["redactions"] = redactor.redactions
    return record


def _find_masked_keys(node: Any, parts: tuple = ()) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for k in getattr(node, "masked_keys", []):
            found.append(dotted_path(parts + (k,)))
        for k, v in node.items():
            found.extend(_find_masked_keys(v, parts + (k,)))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            found.extend(_find_masked_keys(v, parts + (i,)))
    return found


def _safe_source_path(config_path: Path) -> tuple[str, bool]:
    """경로 조각 중 비밀값처럼 보이는 부분을 가린다 (일반 경로는 그대로 둔다)."""
    parts = config_path.resolve().parts
    masked = [REDACTED if looks_like_secret_value(p) else p for p in parts]
    return str(Path(*masked)), masked != list(parts)


# ---- 서버 항목 ------------------------------------------------------------------

def _walk_refs(node: Any, parts: tuple, redactor: Redactor, secret_refs: list[dict]) -> None:
    """항목 하위의 환경변수 참조와 SecretRef 객체를 이름만 기록한다 (값은 읽지 않음).

    형식이 틀린 SecretRef 모양 객체는 여기서 참조로 기록하지 않는다. 인증정보 위치의 잘못된
    참조는 collect_server가 issues로 남기고, 그 밖의 위치에서는 일반 설정 객체로 본다.
    """
    kind, ref = classify_secret_ref(node)
    if kind == "valid":
        secret_refs.append({"kind": "secret_ref", **ref, "field_path": dotted_path(parts)})
        return
    if isinstance(node, str):
        redactor.collect_env_refs(node, dotted_path(parts))
    elif isinstance(node, dict):
        for k, v in node.items():
            _walk_refs(v, parts + (k,), redactor, secret_refs)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk_refs(v, parts + (i,), redactor, secret_refs)


def _invalid_ref_issue(field_path: str, problems: Any) -> dict:
    return {
        "code": "invalid_secret_ref", "field_path": field_path, "problems": problems,
        "message": "인증정보 위치의 SecretRef 형식이 올바르지 않아 참조를 확인하지 못했습니다.",
    }


def _value_kind(value: Any) -> dict:
    kind, detail = classify_secret_ref(value)
    if kind == "valid":
        return {"value_kind": "secret_ref", "ref": detail}
    if kind == "invalid":
        return {"value_kind": "invalid_secret_ref", "problems": detail}
    if isinstance(value, str):
        matches = list(ENV_REF_RE.finditer(value))
        if not matches:
            return {"value_kind": "literal"}
        kind = "env_ref" if len(matches) == 1 and ENV_REF_RE.sub("", value) == "" else "literal_with_env_ref"
        names = [REDACTED if looks_like_secret_value(m.group(1)) else m.group(1) for m in matches]
        out: dict[str, Any] = {"value_kind": kind, "ref_names": names}
        if any(m.group(2) for m in matches):
            out["default_value_withheld"] = True
        return out
    return {"value_kind": "non_string", "type": _type_name(value)}


def _name_map_summary(value: Any, parts: tuple, issues: list[dict]) -> dict:
    if not isinstance(value, dict):
        issues.append({
            "code": "field_type_invalid", "field_path": dotted_path(parts),
            "expected": "object", "actual": _type_name(value),
            "message": "이름-값 목록(object)이어야 하는 필드입니다.",
        })
        return {"present": True, "value_withheld": True}
    entries = []
    for k, v in value.items():
        entry = {"name": k, **_value_kind(v)}
        if entry["value_kind"] == "invalid_secret_ref":
            issues.append(_invalid_ref_issue(dotted_path(parts + (k,)), entry["problems"]))
        entries.append(entry)
    return {
        "present": True,
        "names": list(value.keys()),
        "entries": entries,
        "values_withheld": True,
    }


def _base_record(key: str, source_path: str, key_masked: bool) -> dict:
    parts = REGISTRY_PATH + (key,)
    record: dict[str, Any] = {
        "registration_key": key,
        "source_path": source_path,
        "declaration_path": dotted_path(parts),
        "declaration_pointer": json_pointer(parts),
    }
    if key_masked:
        # 원래 등록키가 토큰처럼 보여 자리표시자로 바꿨다. 다른 서버와는 번호로 구분된다.
        record["registration_key_redacted"] = True
    return record


def _invalid_record(record: dict, issues: list[dict], redactions: list[dict]) -> dict:
    record.update({"collection_status": "invalid", "declared": {}, "declared_keys": [],
                   "issues": issues, "unresolved": [], "redactions": redactions})
    return record


def collect_server(key: str, entry: Any, source_path: str, key_masked: bool = False) -> dict:
    parts = REGISTRY_PATH + (key,)
    record = _base_record(key, source_path, key_masked)
    issues: list[dict] = []
    redactor = Redactor()
    if key_masked:
        redactor._note(dotted_path(parts), "key_looks_like_secret")

    if not isinstance(entry, dict):
        issues.append({
            "code": "entry_not_object", "field_path": dotted_path(parts),
            "expected": "object", "actual": _type_name(entry),
            "message": "등록 항목이 객체가 아니어서 필드를 읽지 못했습니다.",
        })
        return _invalid_record(record, issues, redactor.redactions)

    secret_refs: list[dict] = []
    unresolved: list[dict] = []
    declared: dict[str, Any] = {}
    credentials: dict[str, Any] = {}
    other_keys: list[str] = []

    for dup in getattr(entry, "duplicate_keys", []):
        issues.append({
            "code": "duplicate_key", "field_path": dotted_path(parts + (dup,)),
            "message": "같은 키가 여러 번 선언되어 마지막 값만 읽었습니다.",
        })

    for field_name, value in entry.items():
        fpath = dotted_path(parts + (field_name,))
        if field_name == "$include":
            continue  # 아래에서 하위 위치까지 한 번에 기록
        elif field_name == "enabled":
            if isinstance(value, bool):
                declared["enabled"] = value
            else:
                issues.append({"code": "field_type_invalid", "field_path": fpath, "expected": "boolean",
                               "actual": _type_name(value), "message": "enabled 값이 true/false가 아닙니다."})
        elif field_name in STRING_FIELDS:
            if isinstance(value, str):
                declared[field_name] = redactor.sanitize_string(value, fpath)
            else:
                issues.append({"code": "field_type_invalid", "field_path": fpath, "expected": "string",
                               "actual": _type_name(value), "message": f"{field_name} 값이 문자열이 아닙니다."})
        elif field_name == "args":
            if isinstance(value, list) and all(isinstance(a, str) for a in value):
                declared["args"] = redactor.sanitize_args(value, fpath)
            else:
                issues.append({"code": "field_type_invalid", "field_path": fpath,
                               "expected": "array of string", "actual": _type_name(value),
                               "message": "args 값이 문자열 배열이 아닙니다."})
        elif field_name in NAME_MAP_FIELDS:
            credentials[field_name] = _name_map_summary(value, parts + (field_name,), issues)
        elif field_name in PRESENCE_ONLY_FIELDS:
            summary: dict[str, Any] = {"present": True, "value_withheld": True}
            kind, detail = classify_secret_ref(value)
            if kind == "invalid":
                issues.append(_invalid_ref_issue(fpath, detail))
                summary["value_kind"] = "invalid_secret_ref"
            elif kind == "valid":
                summary["value_kind"] = "secret_ref"
            elif isinstance(value, dict):
                summary["keys"] = list(value.keys())
            credentials[field_name] = summary
        else:
            other_keys.append(field_name)

    for container, value in _find_includes(entry, parts):
        unresolved.append(_include_record(container, value, "이번 단계는 $include 파일을 읽지 않습니다."))
    _walk_refs({k: v for k, v in entry.items() if k != "$include"}, parts, redactor, secret_refs)
    unresolved.extend(redactor.env_refs)
    unresolved.extend(secret_refs)

    if "command" not in entry and "url" not in entry:
        issues.append({"code": "no_connection_target_declared", "field_path": dotted_path(parts),
                       "message": "command와 url이 모두 선언되지 않았습니다."})

    if any(i["code"] in INCOMPLETE_ISSUE_CODES for i in issues) or unresolved:
        status = "partial"
    else:
        status = "complete"

    record.update({
        "collection_status": status,
        "declared": declared,
        "declared_keys": list(entry.keys()),
        "credentials": credentials,
        "other_declared_keys": other_keys,
        "unresolved": unresolved,
        "redactions": redactor.redactions,
        "issues": issues,
    })
    return record


# ---- 설정 파일 전체 ------------------------------------------------------------

def collect(config_path: Path) -> dict:
    """설정 파일 하나를 수집해 `collection`과 `servers`를 돌려준다."""
    source_path, source_path_redacted = _safe_source_path(config_path)
    try:
        text = read_config(config_path)
        root = parse_config(text)
        result = _collect_from_root(root, source_path)
        result["source_path_redacted"] = source_path_redacted
        return result
    except CollectionFailure as failure:
        return {
            "source_path": source_path,
            "source_path_redacted": source_path_redacted,
            "collection": {
                "status": "failed",
                "outcome": failure.outcome,
                "server_count": None,
                "reasons": [failure.reason],
                "unresolved": [],
            },
            "servers": [],
        }


def _collect_from_root(root: Any, source_path: str) -> dict:
    reasons: list[dict] = []
    unresolved: list[dict] = []

    if not isinstance(root, dict):
        raise CollectionFailure("invalid_structure", "root_not_object",
                                "설정 최상위가 객체가 아닙니다.", actual=_type_name(root))

    for container, value in _find_includes(root):
        if _affects_registry(container) and len(container) <= len(REGISTRY_PATH):
            unresolved.append(_include_record(
                container, value, "등록 영역에 영향을 줄 수 있는 $include를 해석하지 않았습니다."))

    for p in [(), ("mcp",)]:
        node = root
        for k in p:
            node = node.get(k) if isinstance(node, dict) else None
        if isinstance(node, dict):
            nxt = REGISTRY_PATH[len(p)]
            if nxt in getattr(node, "duplicate_keys", []):
                reasons.append({"code": "duplicate_key", "field_path": dotted_path(p + (nxt,)),
                                "message": "등록 영역 키가 여러 번 선언되어 마지막 값만 읽었습니다."})

    mcp = root.get("mcp", None)
    if "mcp" not in root:
        return _result_without_registry(source_path, "mcp", reasons, unresolved)
    if not isinstance(mcp, dict):
        raise CollectionFailure("invalid_structure", "mcp_not_object", "mcp 값이 객체가 아닙니다.",
                                field_path="mcp", actual=_type_name(mcp))
    if "servers" not in mcp:
        return _result_without_registry(source_path, "mcp.servers", reasons, unresolved)
    servers = mcp["servers"]
    if not isinstance(servers, dict):
        raise CollectionFailure("invalid_structure", "servers_not_object", "mcp.servers 값이 객체가 아닙니다.",
                                field_path="mcp.servers", actual=_type_name(servers))

    for dup in getattr(servers, "duplicate_keys", []):
        reasons.append({"code": "duplicate_registration_key", "field_path": dotted_path(REGISTRY_PATH + (dup,)),
                        "message": "같은 등록키가 여러 번 선언되어 마지막 항목만 수집했습니다."})

    masked_keys = set(getattr(servers, "masked_keys", []))
    records = [_collect_server_safely(k, v, source_path, k in masked_keys)
               for k, v in servers.items() if k != "$include"]

    if any(r["collection_status"] != "complete" for r in records):
        reasons.append({"code": "server_entries_incomplete",
                        "message": "일부 등록 항목을 완전히 수집하지 못했습니다. servers[].issues/unresolved를 확인하세요.",
                        "registration_keys": [r["registration_key"] for r in records
                                              if r["collection_status"] != "complete"]})
    if unresolved:
        reasons.append({"code": "unresolved_include",
                        "message": "해석하지 않은 $include가 있어 등록 항목이 더 있거나 다를 수 있습니다."})

    status = "partial" if reasons else "complete"
    return {
        "source_path": source_path,
        "collection": {
            "status": status,
            "outcome": "servers_found" if records else "empty_registry",
            "server_count": len(records),
            "reasons": reasons,
            "unresolved": unresolved,
            "key_redactions": _find_masked_keys(root),
        },
        "servers": records,
    }


def _collect_server_safely(key: str, entry: Any, source_path: str, key_masked: bool) -> dict:
    """한 항목에서 예상하지 못한 오류가 나도 다른 항목은 계속 수집한다.

    오류 항목은 버리지 않고 `invalid`와 이슈로 남긴다. 예외 메시지에는 원문 값이 섞일 수 있어
    예외 종류만 기록한다.
    """
    try:
        return collect_server(key, entry, source_path, key_masked)
    except Exception as exc:  # noqa: BLE001 - 항목 단위 격리가 목적
        parts = REGISTRY_PATH + (key,)
        issue = {"code": "collector_internal_error", "field_path": dotted_path(parts),
                 "error_type": type(exc).__name__,
                 "message": "이 항목을 처리하는 중 스캐너 내부 오류가 발생했습니다."}
        redactions = ([{"field_path": dotted_path(parts), "reason": "key_looks_like_secret"}]
                      if key_masked else [])
        return _invalid_record(_base_record(key, source_path, key_masked), [issue], redactions)


def _result_without_registry(source_path: str, missing: str, reasons: list, unresolved: list) -> dict:
    # 앞서 기록된 중복 키 등은 수집을 불완전하게 만든다. `registry_absent` 안내 자체는 불완전 사유가 아니다.
    incomplete = bool(unresolved) or any(r["code"] in INCOMPLETE_REASON_CODES for r in reasons)
    reasons = list(reasons)
    reasons.insert(0, {"code": "registry_absent", "field_path": missing,
                       "message": f"설정에 {missing} 영역이 없습니다. 등록 항목이 0개라는 뜻과는 다릅니다."})
    if unresolved:
        reasons.append({"code": "unresolved_include",
                        "message": "해석하지 않은 $include에 등록 영역이 있을 수 있습니다."})
    return {
        "source_path": source_path,
        "collection": {
            # 파일은 정상적으로 읽었지만 등록 영역 자체가 없다.
            # include나 중복 키가 있으면 영역이 정말 없는지 확정할 수 없다.
            "status": "partial" if incomplete else "complete",
            "outcome": "registry_absent",
            "server_count": None,
            "reasons": reasons,
            "unresolved": unresolved,
        },
        "servers": [],
    }
