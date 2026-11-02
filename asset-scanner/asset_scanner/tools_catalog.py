"""저장된 MCP `tools/list` 응답을 읽어 Tool 정의 목록으로 정리한다 (Tool 카탈로그 1단계, 내부 개발용 초안).

    python -m asset_scanner.tools_catalog --capture <저장된 응답 묶음 JSON> --output <결과 JSON>

이 모듈이 하는 일은 **이미 저장된 응답 JSON을 읽는 것뿐**이다. MCP 서버에 접속·실행하지 않고 `tools/call`도
하지 않으며, 그 결과를 "실제 서버 조회 성공", "Agent에 노출됨", "호출 가능"으로 해석하지 않는다.

근거 규격: MCP 2026-07-28 — `server/tools`, `server/utilities/pagination`, 스키마 `schema/2026-07-28/schema.ts`
(`ListToolsResult`, `Tool`, `ToolAnnotations`, `Icon`, `PaginatedResult`, `CacheableResult`, `Result.resultType`).
다른 버전의 응답은 같은 구조로 가정하지 않는다. 입력이 `protocol_version`으로 2026-07-28을 선언하지 않으면
Tool을 읽지 않고 실패로 기록한다. 자세한 근거는 docs/field-mapping.md를 본다.

종료 코드는 설정 수집 CLI와 같다: 0 완전, 1 부분, 2 인자 오류, 3 실패(Tool을 하나도 읽지 못함), 4 저장 실패.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .cli import _make_console_output_safe, _same_file
from .output import OutputError, normalize_for_output, write_json_atomic
from .redaction import REDACTED, Redactor, is_env_ref_only, is_secret_name, looks_like_secret_value

FORMAT_NAME = "agent-scope.scanner.mcp-tools-catalog"
FORMAT_VERSION = "0.1.0-draft"
CAPTURE_FORMAT = "tools-list-capture"
SUPPORTED_PROTOCOL_VERSION = "2026-07-28"
MAX_CAPTURE_BYTES = 16 * 1024 * 1024
MAX_TOOLS_PER_SERVER = 5000
MAX_MESSAGE_CHARS = 200

EXIT_BY_STATUS = {"complete": 0, "partial": 1, "failed": 3}
EXIT_OUTPUT_ERROR = 4

# Tool 정의에 대해 실제로 수행하는 검사의 범위. 전체 JSON Schema 검증이 아니다.
DEFINITION_VALIDATION = {
    "level": "limited_structure",
    "checked": [
        "name이 비어 있지 않은 문자열인가",
        "inputSchema가 객체이고 루트 type이 \"object\"인가",
        "title·description·outputSchema·annotations(및 힌트 자료형)·icons[].src·_meta의 기본 JSON 자료형",
    ],
    "not_checked": [
        "inputSchema·outputSchema 전체의 JSON Schema 유효성 (2020-12·draft-07 키워드, 형식)",
        "$ref·$defs·$anchor 해석",
        "x-mcp-header 제약",
        "outputSchema 내부 구조, annotations 의미, icons 접근 가능 여부",
    ],
    "note": ("passed_limited_checks는 위 제한된 검사를 통과했다는 뜻일 뿐 정상 사용 가능한 Tool이라는 뜻이 아니다. "
             "failed_limited_checks 항목도 인벤토리 수집 대상이므로 오류 근거(definition_issues)와 함께 보존한다."),
    "redaction_note": ("비밀값 가림과 입력 정규화(토큰 모양·고립된 surrogate 키 이름, 인증정보가 있는 URL, 인증 이름 필드 값, "
                       "고립된 surrogate, 비유한 숫자)를 적용한 정의(definition_altered: true)는 서버가 보낸 원본과 달라질 수 있다. "
                       "키 이름이 바뀌면 이름을 가리키는 참조가 어긋날 수 있다(required는 같은 자리표시자로 맞추지만 그 밖의 참조는 "
                       "맞추지 않는다). 가린 정의를 실행 가능한 원본 스키마로 보증하지 않으며 $ref는 문자열로만 저장하고 "
                       "실행·조회하지 않고 접속하지 않는다. 가림 위치와 이유는 tools[].redactions에 있고 원문 값은 기록하지 않는다."),
}

NOT_VERIFIED = [
    "live_server_query",     # 입력은 저장된 응답이며 서버에 접속하지 않았다
    "current_server_state",  # 저장 시점 이후의 목록 변경
    "tools_call",
    "resources_prompts",
    "capabilities",
    "exposure",              # Agent 노출 여부
    "callability",           # 호출 가능 여부
    "common_server_id",      # 팀 공통 server_id·asset_id 미확정
]

# 구조 키워드·형식 값은 문장이 아니므로 가림 검사에서 제외한다.
_STRUCTURAL_KEYS = frozenset({
    "$schema", "$ref", "$id", "$anchor", "$dynamicRef", "$dynamicAnchor",
    "type", "format", "pattern", "mimeType", "contentEncoding", "contentMediaType",
})
_VALUE_KEYS = frozenset({"default", "const", "examples", "enum"})
_HINT_KEYS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")
_NAME_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-.")
_TOOL_OFFICIAL_KEYS = frozenset({
    "name", "title", "description", "icons", "inputSchema", "outputSchema", "annotations", "_meta",
})


class _Obj(dict):
    """JSON 객체. 같은 키가 두 번 나오면 마지막 값만 남으므로 중복 사실을 따로 기록한다."""
    duplicate_keys: list[str]


def _pairs_hook(pairs: list[tuple[str, Any]]) -> _Obj:
    obj = _Obj()
    dups: list[str] = []
    for k, v in pairs:
        if k in obj and k not in dups:
            dups.append(k)
        obj[k] = v
    obj.duplicate_keys = dups
    return obj


class _NonFinite:
    """입력에 있던 NaN·Infinity·-Infinity 또는 float로 바꾸면 무한대가 되는 값(1e400 등)의 표식.

    숫자로 취급하지 않으며 결과에 그대로 쓰지 않는다. 한 값의 문제 때문에 파일 전체를 버리지 않으려고
    파싱 단계에서 거부하지 않고 표식으로 남긴다.
    """
    __slots__ = ()


def _parse_constant(_name: str) -> _NonFinite:
    return _NonFinite()


def _parse_float(text: str) -> Any:
    value = float(text)
    return value if math.isfinite(value) else _NonFinite()


NON_FINITE_PLACEHOLDER = "<non-finite-number>"
_LONE_SURROGATE_RE = re.compile("[\ud800-\udfff]")


def _scrub(text: str) -> str:
    return _LONE_SURROGATE_RE.sub("\ufffd", text)


def _seg(key: object) -> str:
    text = _scrub(str(key))
    return REDACTED if looks_like_secret_value(text) else text


def _join(path: str, key: object) -> str:
    return f"{path}.{_seg(key)}" if path else _seg(key)


def _safe_names(keys: list[str]) -> list[str]:
    return [_seg(k) for k in keys][:20]


def _text(red: Redactor, value: str, path: str) -> str:
    """입력에서 온 짧은 문자열(서버 이름·오류 메시지 등)을 결과에 쓰기 전에 정리한다."""
    if _LONE_SURROGATE_RE.search(value):
        value = _scrub(value)
        red._note(path, "lone_surrogate_replaced")
    return red.sanitize_text(value, path)


def _find_duplicates(node: Any, path: str, out: list[tuple[str, list[str]]]) -> None:
    if isinstance(node, dict):
        if getattr(node, "duplicate_keys", None):
            out.append((path or "(root)", _safe_names(node.duplicate_keys)))
        for k, v in node.items():
            _find_duplicates(v, _join(path, k), out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _find_duplicates(v, f"{path}[{i}]", out)


def _short(text: object) -> str:
    s = str(text)
    return s if len(s) <= MAX_MESSAGE_CHARS else s[:MAX_MESSAGE_CHARS] + "…"


def _is_number(v: object) -> bool:
    """유한한 숫자인가. bool·NaN·Infinity·표현할 수 없을 만큼 큰 정수는 숫자로 인정하지 않는다."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(float(v))
    except OverflowError:
        return False


# 규격 적합성 이슈(category "conformance")는 수집 완전성(status)을 바꾸지 않는다. 읽은 Tool은 그대로 보존한다.
#   violation              규격의 필수 필드·MUST 위반 (schema.ts의 필수 필드, Result.resultType 등)
#   recommendation_not_met 규격의 SHOULD 권장 사항 미충족
# 여기에 없는 코드는 category "completeness"이며, severity "error"가 있으면 서버 상태를 partial/failed로 만든다.
_CONFORMANCE = {
    "result_type_missing": "violation",
    "result_type_invalid": "violation",
    "cache_hint_missing": "violation",
    "cache_hint_invalid": "violation",
    "jsonrpc_version_unexpected": "violation",
    "tool_name_missing": "violation",
    "input_schema_missing": "violation",
    "input_schema_invalid_type": "violation",
    "input_schema_type_not_object": "violation",
    "field_type_invalid": "violation",
    "tool_name_nonconforming": "recommendation_not_met",
    "duplicate_tool_name_in_server": "recommendation_not_met",
}


def _issue(severity: str, code: str, message: str, **where: Any) -> dict:
    category = "conformance" if code in _CONFORMANCE else "completeness"
    item = {"category": category, "severity": _CONFORMANCE.get(code, severity), "code": code, "message": message}
    item.update({k: v for k, v in where.items() if v is not None})
    return item


# ---- 가림 -----------------------------------------------------------------------

# 이름만 보고 인증정보를 담는다고 판단하는 필드 이름 (임의 메타데이터용). `author`·`token_budget` 같은 일반 이름이
# 걸리지 않도록 이름을 단어로 나눠 비교한다. 문자열 값만 가리며 숫자·불리언은 건드리지 않는다.
_STRONG_WORDS = frozenset({"token", "secret", "password", "passwd", "pwd", "apikey", "authorization",
                           "credential", "credentials", "cookie", "bearer"})
_STRONG_PAIRS = frozenset({("api", "key"), ("access", "key"), ("private", "key"), ("client", "secret"),
                           ("secret", "key"), ("auth", "token"), ("session", "token")})
_WORD_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")


def _strong_secret_name(key: str) -> bool:
    words = [w.lower() for w in _WORD_RE.findall(key)]
    return any(w in _STRONG_WORDS for w in words) or any(pair in _STRONG_PAIRS for pair in zip(words, words[1:]))


def _needs_key_mask(key: str) -> bool:
    return bool(_LONE_SURROGATE_RE.search(key)) or looks_like_secret_value(key)


def _key_mapping(keys: list[str]) -> dict[str, str]:
    """한 객체 안에서 가려야 할 키마다 자리표시자(`<redacted-key-N>`)를 정한다.

    같은 객체의 일반 키와 이름이 겹치지 않게 번호를 건너뛴다. 따라서 가림 때문에 다른 항목이 덮어써지지 않는다.
    번호는 이 객체 안의 등장 순서이며 원래 키나 그 해시를 쓰지 않는다.
    """
    plain = {k for k in keys if not _needs_key_mask(k)}
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


# mode: "normal" 일반 / "prop_secret" 비밀 이름 속성의 하위 스키마(default·const·examples·enum 값을 가림) /
#       "all" 인증 이름 필드 아래(문자열 값을 모두 가림)
def _sanitize(node: Any, path: str, red: Redactor, mode: str = "normal", under_key: str = "",
              is_properties_map: bool = False) -> Any:
    """서버가 제공한 값을 구조를 유지한 채 복사하며 비밀값·무효 값만 가린다.

    - 문장은 해석·실행하지 않는다. `$ref`·`$id`는 문자열로만 다루며 해석·조회·접속하지 않는다.
    - 토큰 모양 키·properties 이름은 자리표시자로 바꾸고(`required`의 같은 이름도 맞춘다) 위치와 이유를 `red`에 남긴다.
    - 구조 키($ref, $id, $schema, pattern 등) 아래 문자열도 알려진 토큰·URL 자격증명은 가린다.
    - 고립된 surrogate는 U+FFFD로, NaN·Infinity 등은 자리표시자로 바꾼다 (이유를 기록).
    """
    if isinstance(node, _NonFinite):
        red._note(path, "non_finite_number_replaced")
        return NON_FINITE_PLACEHOLDER
    if isinstance(node, dict):
        keys = list(node.keys())
        mapping = _key_mapping(keys)
        prop_map: dict[str, str] = {}
        props = node.get("properties")
        if not is_properties_map and isinstance(props, dict):
            prop_map = _key_mapping(list(props.keys()))
        out: dict = {}
        for k, v in node.items():
            new_key = mapping.get(k, k)
            child_path = _join(path, new_key)
            if new_key != k:
                red._note(child_path, "lone_surrogate_in_key" if _LONE_SURROGATE_RE.search(k) else "key_looks_like_secret")
            if is_properties_map:
                out[new_key] = _sanitize(v, child_path, red, "prop_secret" if is_secret_name(k) else "normal", "")
            elif k == "properties" and isinstance(v, dict):
                out[new_key] = _sanitize(v, child_path, red, mode, "properties", is_properties_map=True)
            elif k == "required" and isinstance(v, list) and prop_map:
                items = []
                for i, s in enumerate(v):
                    if isinstance(s, str) and s in prop_map:
                        red._note(f"{child_path}[{i}]", "reference_to_masked_key")
                        items.append(prop_map[s])
                    else:
                        items.append(_sanitize(s, f"{child_path}[{i}]", red, mode, "required"))
                out[new_key] = items
            else:
                child_mode = "all" if (mode == "all" or _strong_secret_name(k)) else mode
                out[new_key] = _sanitize(v, child_path, red, child_mode, str(k))
        return out
    if isinstance(node, list):
        return [_sanitize(v, f"{path}[{i}]", red, mode, under_key) for i, v in enumerate(node)]
    if isinstance(node, str):
        text = node
        if _LONE_SURROGATE_RE.search(text):
            text = _scrub(text)
            red._note(path, "lone_surrogate_replaced")
        if mode == "all":
            if text != "" and not is_env_ref_only(text):
                red._note(path, "secret_named_field_value")
                return REDACTED
            return text
        if mode == "prop_secret" and under_key in _VALUE_KEYS and text != "":
            red._note(path, "secret_named_property_value")
            return REDACTED
        # 구조 키 아래 문자열은 긴 식별자처럼 보인다는 이유로 지우지 않되, 알려진 토큰과 URL 자격증명은 가린다.
        return red.sanitize_text(text, path, check_entropy=under_key not in _STRUCTURAL_KEYS)
    return node


# ---- 입력 읽기 -------------------------------------------------------------------

def _read_capture(path: Path) -> tuple[Any | None, dict | None]:
    """(JSON 값, 실패 사유). 실패 사유에는 파일 내용을 넣지 않는다."""
    try:
        size = path.stat().st_size
        if size > MAX_CAPTURE_BYTES:
            return None, {"code": "capture_too_large", "message": f"입력 파일이 {MAX_CAPTURE_BYTES}바이트 한도를 넘습니다."}
        text = path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return None, {"code": "capture_not_found", "message": "입력 파일을 찾지 못했습니다."}
    except UnicodeDecodeError:
        return None, {"code": "capture_not_utf8", "message": "입력 파일이 UTF-8이 아닙니다."}
    except OSError as exc:
        return None, {"code": "capture_read_failed", "message": f"입력 파일을 읽지 못했습니다 ({type(exc).__name__})."}
    try:
        return json.loads(text, object_pairs_hook=_pairs_hook, parse_constant=_parse_constant, parse_float=_parse_float), None
    except (ValueError, RecursionError) as exc:
        return None, {"code": "capture_invalid_json", "message": f"입력이 올바른 JSON이 아닙니다 ({type(exc).__name__})."}


# ---- Tool 정의 검증 ---------------------------------------------------------------

def _definition_issues(tool: dict, base: str) -> list[dict]:
    """공식 `Tool` 필드 형식 위반을 찾는다. 위반해도 정의는 버리지 않고 사유만 남긴다."""
    found: list[dict] = []

    def bad(code: str, field: str, msg: str) -> None:
        found.append(_issue("error", code, msg, field_path=_join(base, field)))

    schema = tool.get("inputSchema", _MISSING)
    if schema is _MISSING:
        bad("input_schema_missing", "inputSchema", "필수 필드 inputSchema가 없습니다.")
    elif not isinstance(schema, dict):
        bad("input_schema_invalid_type", "inputSchema", "inputSchema가 객체가 아닙니다.")
    elif schema.get("type") != "object":
        bad("input_schema_type_not_object", "inputSchema.type", 'inputSchema의 루트 type이 "object"가 아닙니다.')
    for key in ("title", "description"):
        if key in tool and not isinstance(tool[key], str):
            bad("field_type_invalid", key, f"{key}가 문자열이 아닙니다.")
    if "outputSchema" in tool and not isinstance(tool["outputSchema"], dict):
        bad("field_type_invalid", "outputSchema", "outputSchema가 객체가 아닙니다.")
    if "_meta" in tool and not isinstance(tool["_meta"], dict):
        bad("field_type_invalid", "_meta", "_meta가 객체가 아닙니다.")
    ann = tool.get("annotations", _MISSING)
    if ann is not _MISSING:
        if not isinstance(ann, dict):
            bad("field_type_invalid", "annotations", "annotations가 객체가 아닙니다.")
        else:
            if "title" in ann and not isinstance(ann["title"], str):
                bad("field_type_invalid", "annotations.title", "annotations.title이 문자열이 아닙니다.")
            for hint in _HINT_KEYS:
                if hint in ann and not isinstance(ann[hint], bool):
                    bad("field_type_invalid", f"annotations.{hint}", f"annotations.{hint}가 불리언이 아닙니다.")
    icons = tool.get("icons", _MISSING)
    if icons is not _MISSING:
        if not isinstance(icons, list):
            bad("field_type_invalid", "icons", "icons가 배열이 아닙니다.")
        else:
            for i, icon in enumerate(icons):
                if not isinstance(icon, dict) or not isinstance(icon.get("src"), str):
                    bad("field_type_invalid", f"icons[{i}]", "icons 항목에 문자열 src가 없습니다.")
    return found


_MISSING = object()


def _name_is_conventional(name: str) -> bool:
    return 1 <= len(name) <= 128 and all(c in _NAME_CHARS for c in name)


# ---- 페이지 해석 ------------------------------------------------------------------

def _parse_page(raw: Any, page_index: int) -> dict:
    """응답 한 건을 해석한다. 반환: ok, issues, tools(원본 객체), has_next, record."""
    res: dict = {"ok": False, "issues": [], "tools": [], "has_next": False, "stop": False, "record": {"page_index": page_index}}
    issues: list[dict] = res["issues"]

    def fail(code: str, msg: str, **extra: Any) -> dict:
        issues.append(_issue("error", code, msg, page_index=page_index, **extra))
        res["stop"] = True
        return res

    if not isinstance(raw, dict):
        return fail("invalid_response_structure", "응답이 JSON 객체가 아닙니다.")
    has_result, has_error = "result" in raw, "error" in raw
    if (has_result or has_error or "jsonrpc" in raw) and getattr(raw, "duplicate_keys", None):
        # 응답 외피(`result`·`error`·`jsonrpc`·`id`)의 중복: 마지막 값만 남아 앞의 값은 읽지 못했다.
        issues.append(_issue("error", "duplicate_key", "같은 키가 중복돼 마지막 값만 남았습니다. 앞의 값은 읽지 못했습니다.",
                             page_index=page_index, field_path=f"pages[{page_index}]",
                             duplicate_keys=_safe_names(raw.duplicate_keys)))
    if has_result and has_error:
        return fail("invalid_response_structure", "응답에 result와 error가 함께 있습니다.")
    if has_error:
        err = raw["error"]
        res["record"]["wrapper"] = "jsonrpc_error_response"
        if not isinstance(err, dict):
            return fail("invalid_response_structure", "error가 객체가 아닙니다.")
        code = err.get("code")
        msg = err.get("message")
        red = Redactor()
        safe_msg = _text(red, _short(msg), "error.message") if isinstance(msg, str) else None
        extra: dict[str, Any] = {"error_code": code if isinstance(code, int) and not isinstance(code, bool) else None}
        if safe_msg is not None:
            extra["error_message"] = safe_msg
        if red.redactions:
            extra["redactions"] = red.redactions
        if "data" in err:
            extra["error_data_omitted"] = True  # 서버가 정한 임의 값이라 저장하지 않는다
        return fail("error_response", "서버가 오류 응답을 반환했습니다. Tool 0개가 아니라 수집 실패입니다.", **extra)
    if has_result:
        result = raw["result"]
        res["record"]["wrapper"] = "jsonrpc_result_response"
        if raw.get("jsonrpc") != "2.0":
            issues.append(_issue("warning", "jsonrpc_version_unexpected", 'jsonrpc 값이 "2.0"이 아닙니다.', page_index=page_index))
    elif "jsonrpc" in raw:
        return fail("invalid_response_structure", "jsonrpc 메시지에 result와 error가 모두 없습니다.")
    else:
        result = raw
        res["record"]["wrapper"] = "bare_result"
    if not isinstance(result, dict):
        return fail("invalid_response_structure", "result가 객체가 아닙니다.")

    rtype = result.get("resultType", _MISSING)
    if rtype is _MISSING or not isinstance(rtype, str):
        # 규격 위반이다. 응답이 완료됐는지 알 수 없으므로 완료를 추정하지 않는다(서버는 partial).
        # 다만 tools 배열을 읽을 수 있으면 Tool 정의는 버리지 않고 보존한다.
        missing = rtype is _MISSING
        res["record"]["result_type_state"] = "missing" if missing else "invalid_type"
        issues.append(_issue("error", "result_type_missing" if missing else "result_type_invalid",
                             "2026-07-28 규격에서 서버가 반드시 넣어야 하는 resultType이 없습니다." if missing
                             else "resultType이 문자열이 아닙니다.", page_index=page_index))
        issues.append(_issue("error", "result_completion_unverified",
                             "resultType을 해석할 수 없어 이 응답이 완료된 응답이라고 판단하지 않았습니다. 읽을 수 있는 Tool 정의는 보존합니다.",
                             page_index=page_index))
    elif rtype == "input_required":
        res["record"]["result_type"] = rtype
        return fail("input_required_result", "tools/list 응답이 추가 입력을 요구하는 결과(input_required)입니다. Tool 목록으로 읽지 않습니다.")
    elif rtype != "complete":
        res["record"]["result_type"] = _text(Redactor(), _short(rtype), "resultType")
        return fail("unsupported_result_type", "해석할 수 없는 resultType입니다. 응답 구조를 추정하지 않고 읽지 않습니다.")
    else:
        res["record"]["result_type"] = rtype
        res["record"]["result_type_state"] = "complete"

    tools = result.get("tools", _MISSING)
    if tools is _MISSING:
        return fail("invalid_response_structure", "필수 필드 tools가 없습니다.", field_path="tools")
    if not isinstance(tools, list):
        return fail("invalid_response_structure", "tools가 배열이 아닙니다.", field_path="tools")

    cursor = result.get("nextCursor")
    if cursor is not None and not isinstance(cursor, str):
        issues.append(_issue("error", "next_cursor_invalid", "nextCursor가 문자열이 아닙니다. 이후 페이지 상태를 알 수 없습니다.", page_index=page_index))
        res["stop"] = True
    elif isinstance(cursor, str):
        res["has_next"] = True  # 빈 문자열도 유효한 커서다 (종료로 해석하지 않는다). 커서 값은 저장하지 않는다.

    ttl, scope = result.get("ttlMs", _MISSING), result.get("cacheScope", _MISSING)
    missing = [n for n, v in (("ttlMs", ttl), ("cacheScope", scope)) if v is _MISSING]
    if missing:
        issues.append(_issue("warning", "cache_hint_missing", f"규격상 필요한 {', '.join(missing)}가 응답에 없습니다.", page_index=page_index))
    if ttl is not _MISSING:
        if _is_number(ttl) and ttl >= 0:
            res["record"]["ttl_ms"] = ttl
        else:
            issues.append(_issue("warning", "cache_hint_invalid", "ttlMs가 0 이상의 숫자가 아닙니다.", page_index=page_index))
    if scope is not _MISSING:
        if scope in ("public", "private"):
            res["record"]["cache_scope"] = scope
        else:
            issues.append(_issue("warning", "cache_hint_invalid", 'cacheScope가 "public"/"private"가 아닙니다.', page_index=page_index))

    meta = result.get("_meta", _MISSING)
    if meta is not _MISSING:
        if isinstance(meta, dict):
            red = Redactor()
            res["record"]["result_meta"] = _sanitize(meta, f"pages[{page_index}].result._meta", red)
            if red.redactions:
                res["record"]["result_meta_redactions"] = red.redactions
        else:
            issues.append(_issue("warning", "field_type_invalid", "result._meta가 객체가 아닙니다.", page_index=page_index))
    known = {"resultType", "tools", "nextCursor", "ttlMs", "cacheScope", "_meta"}
    extra_keys = sorted(_seg(k) for k in result if k not in known)
    if extra_keys:
        res["record"]["other_result_fields"] = extra_keys

    dups: list[tuple[str, list[str]]] = []
    rpath = f"pages[{page_index}].result"
    if getattr(result, "duplicate_keys", None):
        dups.append((rpath, _safe_names(result.duplicate_keys)))
    for k, v in result.items():
        if k != "tools":  # tools[]는 항목별로 따로 검사한다
            _find_duplicates(v, _join(rpath, k), dups)
    for path_, names in dups:
        issues.append(_issue("error", "duplicate_key", "같은 키가 중복돼 마지막 값만 남았습니다.", page_index=page_index,
                             field_path=path_, duplicate_keys=names))

    res["tools"] = tools
    res["ok"] = True
    res["record"]["tool_count"] = len(tools)
    res["record"]["has_next_cursor"] = res["has_next"]
    return res


# ---- 서버 단위 수집 ----------------------------------------------------------------

def _conformance_summary(issues: list[dict], evaluated: bool) -> dict:
    """규격 적합성 요약. 제한된 구조 검사 결과이며 전체 규격 적합성 인증이 아니다."""
    if not evaluated:
        return {"status": "not_evaluated", "checks": "limited", "violation_count": 0,
                "violations": [], "recommendations_not_met": []}
    viol = [i for i in issues if i["category"] == "conformance" and i["severity"] == "violation"]
    rec = [i for i in issues if i["category"] == "conformance" and i["severity"] == "recommendation_not_met"]
    return {"status": "violations_found" if viol else "no_violations_found", "checks": "limited",
            "violation_count": len(viol), "violations": sorted({i["code"] for i in viol}),
            "recommendations_not_met": sorted({i["code"] for i in rec})}


def _failed_server(index: int, label: str, code: str, message: str, **extra: Any) -> dict:
    return {
        "server_index": index, "server_ref": label, "collection_status": "failed", "outcome": code,
        "tool_count": None, "pages": [], "issues": [_issue("error", code, message, **extra)],
        "spec_conformance": _conformance_summary([], False), "redactions": [], "tools": [],
    }


def _collect_server(index: int, entry: Any, seen_refs: set[str]) -> dict:
    if not isinstance(entry, dict):
        return _failed_server(index, "<invalid>", "invalid_server_entry", "servers 항목이 객체가 아닙니다.")
    ref = entry.get("server_ref")
    if not isinstance(ref, str) or not ref:
        return _failed_server(index, "<missing>", "invalid_server_entry", "server_ref가 비어 있지 않은 문자열이 아닙니다.")
    srv_red = Redactor()
    safe_ref = _text(srv_red, ref, "server_ref")
    if ref in seen_refs:
        return _failed_server(index, safe_ref, "duplicate_server_ref", "같은 server_ref가 이미 있습니다. 서로 다른 서버를 합치지 않기 위해 이 항목은 읽지 않습니다.")
    seen_refs.add(ref)

    server: dict = {
        "server_index": index,
        "server_ref": safe_ref,
        "server_ref_kind": "capture_local_label",  # 입력 파일 안에서만 쓰는 이름. 팀 공통 server_id가 아니다.
    }
    link: dict[str, Any] = {}
    for key in ("registration_key", "registry_path"):
        v = entry.get(key)
        if isinstance(v, str):
            link[key] = _text(srv_red, v, key)
    if link:
        link["verified_against_config_scan"] = False  # 입력에 적힌 값이며 설정 수집 결과와 대조하지 않았다
        server["config_link"] = link

    version = entry.get("protocol_version")
    server["declared_protocol_version"] = _text(srv_red, _short(version), "protocol_version") if isinstance(version, str) else None
    pages = entry.get("pages", _MISSING)

    def done_failed(code: str, message: str, **extra: Any) -> dict:
        server.update(collection_status="failed", outcome=code, tool_count=None, pages=[],
                      issues=[_issue("error", code, message, **extra)], tools=[], redactions=srv_red.redactions,
                      spec_conformance=_conformance_summary([], False))
        return server

    if not isinstance(version, str) or not version:
        return done_failed("protocol_version_not_declared",
                           "입력이 protocol_version을 선언하지 않았습니다. 응답 구조는 규격 버전에 따라 다르므로 읽지 않습니다.")
    if version != SUPPORTED_PROTOCOL_VERSION:
        return done_failed("protocol_version_unsupported",
                           f"이 모듈은 MCP {SUPPORTED_PROTOCOL_VERSION} 응답만 읽습니다. 다른 버전의 응답을 같은 구조로 가정하지 않습니다.",
                           declared=_text(srv_red, _short(version), "protocol_version"))
    if not isinstance(pages, list) or not pages:
        return done_failed("no_response", "저장된 응답이 없습니다. 응답이 없는 것은 Tool 0개가 아닙니다.")

    issues: list[dict] = []
    page_records: list[dict] = []
    tools_out: list[dict] = []
    parsed_ok = 0
    last_has_next = False
    stopped = False
    processed = 0
    flat_index = 0
    original_names: dict[str, list[int]] = {}

    for page_index, raw in enumerate(pages):
        if page_index > 0 and not last_has_next:
            issues.append(_issue("error", "page_after_final_page",
                                 "nextCursor가 없는 마지막 페이지 뒤에 응답이 더 있습니다. 뒤의 응답은 읽지 않았습니다.",
                                 page_index=page_index, ignored_pages=len(pages) - page_index))
            break
        if stopped:
            break
        processed += 1
        page = _parse_page(raw, page_index)
        issues.extend(page["issues"])
        page_records.append(page["record"])
        if not page["ok"]:
            stopped = True
            last_has_next = False
            break
        parsed_ok += 1
        last_has_next = page["has_next"]
        stopped = page["stop"]
        for idx_in_page, tool in enumerate(page["tools"]):
            if flat_index >= MAX_TOOLS_PER_SERVER:
                issues.append(_issue("error", "tool_limit_exceeded", f"서버당 Tool {MAX_TOOLS_PER_SERVER}개 한도를 넘어 나머지를 읽지 않았습니다.", page_index=page_index))
                stopped = True
                last_has_next = False
                break
            tool_index = flat_index
            flat_index += 1
            base = f"pages[{page_index}].result.tools[{idx_in_page}]"
            if not isinstance(tool, dict):
                issues.append(_issue("error", "tool_item_invalid", "tools 항목이 객체가 아닙니다. 이 항목은 제외했습니다.",
                                     page_index=page_index, tool_index=tool_index))
                continue
            name = tool.get("name")
            if not isinstance(name, str) or name == "":
                issues.append(_issue("error", "tool_name_missing", "필수 필드 name이 비어 있지 않은 문자열이 아닙니다.",
                                     page_index=page_index, tool_index=tool_index))
                issues.append(_issue("error", "tool_item_invalid", "식별할 name이 없어 이 항목은 제외했습니다.",
                                     page_index=page_index, tool_index=tool_index))
                continue
            original_names.setdefault(name, []).append(tool_index)
            if not _name_is_conventional(name):
                issues.append(_issue("warning", "tool_name_nonconforming",
                                     "Tool 이름이 규격 권장 형식(1~128자, A-Z a-z 0-9 _ - .)이 아닙니다.",
                                     page_index=page_index, tool_index=tool_index))
            def_issues = _definition_issues(tool, "")  # entry 안의 field_path는 Tool 정의 기준 상대 경로
            dups: list[tuple[str, list[str]]] = []
            _find_duplicates(tool, "", dups)
            def_issues += [_issue("error", "duplicate_key", "같은 키가 중복돼 마지막 값만 남았습니다.",
                                  field_path="(definition)" if p == "(root)" else p, duplicate_keys=names)
                           for p, names in dups]
            red = Redactor()
            definition = _sanitize(tool, "", red)
            other = sorted(_seg(k) for k in tool if k not in _TOOL_OFFICIAL_KEYS)
            entry_out = {
                # 아래 두 값은 이 파일 안에서만 쓰는 내부 참조다. 공통 자산 ID가 아니며 실행마다 같다는 보장도 없다.
                "internal_ref": f"capture-server[{index}]/tools[{tool_index}]",
                "server_index": index,
                "server_ref": safe_ref,
                "page_index": page_index,
                "index_in_page": idx_in_page,
                "definition": definition,
                # 제한된 구조 검사(`scope.definition_validation`)의 결과이며 전체 JSON Schema 검증이나
                # "정상 사용 가능한 Tool"이라는 뜻이 아니다. 실패한 항목도 인벤토리로 보존한다.
                "definition_status": "failed_limited_checks" if def_issues else "passed_limited_checks",
                "definition_check_level": "limited_structure",
                "definition_issues": def_issues,
                "other_definition_fields": other,
                "redactions": red.redactions,
                # 가림·정규화가 적용돼 서버가 보낸 원본과 다를 수 있는 정의인가 (`scope.definition_validation.redaction_note`)
                "definition_altered": bool(red.redactions),
                "trust": "untrusted_server_provided",
            }
            tools_out.append(entry_out)
            for di in def_issues:  # 서버 issues에는 응답 기준 절대 경로로 올린다
                rel = di["field_path"]
                absolute = base if rel == "(definition)" else _join(base, rel)
                issues.append({**di, "field_path": absolute, "page_index": page_index, "tool_index": tool_index})

    if parsed_ok and last_has_next:
        issues.append(_issue("error", "next_cursor_remaining",
                             "마지막으로 읽은 페이지에 nextCursor가 남아 있습니다. 목록이 끝까지 수집되지 않았습니다.",
                             page_index=processed - 1))
    for name, idxs in original_names.items():
        if len(idxs) > 1:
            issues.append(_issue("warning", "duplicate_tool_name_in_server",
                                 "같은 서버의 Tool 이름이 중복됩니다(규격은 서버 안 유일을 권장). 두 항목을 모두 유지했습니다.",
                                 tool_indexes=idxs))

    # 서버 상태는 수집 완전성만 나타낸다. 규격 적합성(category "conformance")은 상태를 바꾸지 않는다.
    errors = [i for i in issues if i["category"] == "completeness" and i["severity"] == "error"]
    if parsed_ok == 0:
        status, outcome = "failed", errors[0]["code"] if errors else "no_response"
        tool_count: int | None = None
    elif errors:
        only_unverified = {i["code"] for i in errors} == {"result_completion_unverified"}
        status, outcome, tool_count = "partial", ("completion_unverified" if only_unverified else "incomplete_list"), len(tools_out)
    else:
        status = "complete"
        tool_count = len(tools_out)
        outcome = "tools_listed" if tool_count else "empty_list"

    server.update(collection_status=status, outcome=outcome, tool_count=tool_count, pages=page_records,
                  issues=issues, spec_conformance=_conformance_summary(issues, parsed_ok > 0),
                  redactions=srv_red.redactions, tools=tools_out if parsed_ok else [])
    return server


# ---- 전체 -------------------------------------------------------------------------

def _flag_entry_duplicates(server: dict, keys: list[str], index: int) -> None:
    """서버 항목 객체의 중복 키(`pages` 등)를 그 서버의 수집 완전성에 반영한다."""
    server["issues"].append(_issue("error", "duplicate_key",
                                   "서버 항목에 같은 키가 중복돼 마지막 값만 남았습니다. 앞의 값은 읽지 못했습니다.",
                                   field_path=f"servers[{index}]", duplicate_keys=keys))
    if server["collection_status"] == "complete":
        server["collection_status"] = "partial"
        server["outcome"] = "duplicate_keys"


def summarize_collection(servers: list[dict], failure: dict | None, root_duplicates: list[str]) -> dict:
    """서버별 결과를 파일 전체의 수집 상태(`collection`)로 집계한다. 저장된 응답 읽기와 실제 조회가 함께 쓴다."""
    reasons: list[dict] = []
    conformance_total: dict | None = None
    if failure is not None:
        status, outcome, server_count, tool_count, complete = "failed", failure["code"], None, None, False
        reasons.append(failure)
    else:
        statuses = [s["collection_status"] for s in servers]
        if all(s == "complete" for s in statuses):
            status = "complete"
        elif all(s == "failed" for s in statuses):
            status = "failed"
        else:
            status = "partial"
        outcome = {"complete": "all_servers_listed", "partial": "some_servers_incomplete", "failed": "no_server_listed"}[status]
        server_count = len(servers)
        tool_count = sum(s["tool_count"] or 0 for s in servers)
        complete = status == "complete"
        sc = [s["spec_conformance"]["status"] for s in servers]
        conformance_total = {
            "checks": "limited",
            "servers_with_violations": sc.count("violations_found"),
            "servers_no_violations_found": sc.count("no_violations_found"),
            "servers_not_evaluated": sc.count("not_evaluated"),
            "violation_count": sum(s["spec_conformance"]["violation_count"] for s in servers),
        }
        for s in servers:
            if s["collection_status"] != "complete":
                reasons.append({"code": "server_list_incomplete", "server_index": s["server_index"],
                                "server_outcome": s["outcome"],
                                "message": "이 서버의 tools/list 수집이 완전하지 않습니다. tool_count는 읽은 항목 수일 뿐 서버의 전체 Tool 수가 아닙니다."})

    if failure is None and root_duplicates:
        # 입력 최상위의 중복: 마지막 값만 남았으므로 파일 전체가 빠짐없이 읽혔다고 확인할 수 없다.
        reasons.append({"code": "duplicate_key_in_capture", "field_path": "(root)", "duplicate_keys": root_duplicates,
                        "message": "입력 최상위에 같은 키가 중복돼 마지막 값만 읽었습니다. 앞의 값(서버 등)이 빠졌을 수 있어 완전 수집으로 보지 않습니다."})
        if status == "complete":
            status, outcome, complete = "partial", "duplicate_keys_in_capture", False
    return {
        "status": status, "outcome": outcome, "server_count": server_count,
        "tool_count": tool_count, "tool_count_complete": complete, "reasons": reasons,
        "spec_conformance": conformance_total,
    }


def collect_tools_catalog(capture_path: Path) -> dict:
    data, failure = _read_capture(capture_path)
    servers: list[dict] = []
    origin = None
    root_duplicates: list[str] = []
    if failure is None:
        if not isinstance(data, dict) or not isinstance(data.get("servers"), list):
            failure = {"code": "capture_invalid_structure", "message": "입력 최상위가 servers 배열을 가진 객체가 아닙니다."}
        elif data.get("format", CAPTURE_FORMAT) != CAPTURE_FORMAT:
            failure = {"code": "capture_invalid_structure", "message": f'format이 "{CAPTURE_FORMAT}"가 아닙니다.'}
        elif not data["servers"]:
            failure = {"code": "no_servers_in_capture", "message": "servers가 비어 있습니다. 서버가 없다는 뜻이 아니라 입력할 응답이 없다는 뜻입니다."}
    if failure is None:
        o = data.get("origin")
        origin = _text(Redactor(), _short(o), "origin") if isinstance(o, str) else None
        root_duplicates = _safe_names(getattr(data, "duplicate_keys", []))
        seen: set[str] = set()
        try:
            for i, e in enumerate(data["servers"]):
                srv = _collect_server(i, e, seen)
                if isinstance(e, dict) and getattr(e, "duplicate_keys", None):
                    _flag_entry_duplicates(srv, _safe_names(e.duplicate_keys), i)
                servers.append(srv)
        except RecursionError:
            failure = {"code": "capture_invalid_json", "message": "입력 JSON의 중첩이 너무 깊어 처리하지 못했습니다."}
            servers = []

    return {
        "capture_path": str(capture_path),
        "origin": origin,
        "collection": summarize_collection(servers, failure, root_duplicates),
        "servers": servers,
    }


def build_catalog_report(collected: dict) -> dict:
    return {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "format_status": (
            "스캐너 내부 개발용 초안입니다. 팀 공통 스키마가 아니며 필드명과 구조는 협의 후 변경될 수 있습니다. "
            "공통 server_id·asset_id는 정하지 않았고 server_ref·internal_ref는 이 파일 안에서만 쓰는 이름입니다."
        ),
        "producer": {"name": "agent-scope-asset-scanner", "version": __version__},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "protocol": {
            "supported_version": SUPPORTED_PROTOCOL_VERSION,
            "basis": "MCP 2026-07-28 server/tools, utilities/pagination, schema.ts (ListToolsResult, Tool, ToolAnnotations)",
        },
        "source": collected.get("source") or {
            "capture_path": collected["capture_path"],
            "source_kind": "stored_tools_list_response",
            "evidence_type": "stored_protocol_response",
            "live_server_query": False,
            "origin_declared_by_input": collected["origin"],
        },
        "scope": {
            "method": "저장된 tools/list 응답 JSON 읽기",
            "not_verified": NOT_VERIFIED,
            "status_meaning": {
                "collection_status": "수집 완전성: 응답 전체를 끝까지 읽었는가 (complete/partial/failed)",
                "spec_conformance": "규격 적합성: 읽은 응답이 2026-07-28 규격의 필수·권장 사항을 지키는가. 수집 완전성과 별개이며 상태를 바꾸지 않음",
            },
            "definition_validation": DEFINITION_VALIDATION,
            "note": ("tools[]는 입력 파일의 응답에 적힌 Tool 정의를 옮긴 것입니다. 서버에 접속하지 않았으므로 실제 서버가 지금 "
                     "이 목록을 반환하는지, Agent에 노출되는지, 호출할 수 있는지는 확인하지 않았습니다. "
                     "서버가 제공한 설명·메타데이터는 비신뢰 데이터로만 저장하며 실행하지 않습니다."),
            **collected.get("scope_overrides", {}),
        },
        "collection": collected["collection"],
        "servers": collected["servers"],
    }


# ---- CLI --------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m asset_scanner.tools_catalog",
        description="저장된 MCP tools/list 응답(capture JSON)을 읽어 Tool 정의 목록으로 저장합니다 "
                    "(내부 개발용 초안, 서버에 접속하지 않음).",
    )
    p.add_argument("--capture", required=True, type=Path, help="저장된 tools/list 응답을 담은 capture JSON")
    p.add_argument("--output", required=True, type=Path, help="결과 JSON을 저장할 경로")
    return p


def main(argv: list[str] | None = None) -> int:
    _make_console_output_safe()
    args = _parser().parse_args(argv)
    if _same_file(args.capture, args.output):
        print("오류: --output이 --capture와 같은 파일입니다. 입력을 덮어쓰지 않습니다.", file=sys.stderr)
        return EXIT_OUTPUT_ERROR

    report = build_catalog_report(collect_tools_catalog(args.capture))
    # 저장 전에 직렬화할 수 없는 문자(고립된 surrogate)를 정리한다. 정리한 건수는 결과에 남긴다.
    report, normalized = normalize_for_output(report)
    if normalized:
        report["collection"]["output_text_normalizations"] = normalized
    try:
        write_json_atomic(args.output, report)
    except OutputError as exc:
        print(f"오류: 결과 파일을 저장하지 못했습니다 ({exc.kind}). 기존 결과 파일은 바꾸지 않았습니다.", file=sys.stderr)
        return EXIT_OUTPUT_ERROR

    col = report["collection"]
    print("저장된 응답 읽기 결과 (실제 서버 조회가 아님)")
    print(f"수집 상태: {col['status']} ({col['outcome']})")
    if normalized:
        print(f"출력 문자열 정규화: {normalized}건 (고립된 surrogate를 U+FFFD로 대체)")
    if col["server_count"] is not None:
        print(f"서버: {col['server_count']}개, 읽은 Tool: {col['tool_count']}개" + ("" if col["tool_count_complete"] else " (전체 수가 아님)"))
    for s in report["servers"]:
        count = "미확인" if s["tool_count"] is None else f"{s['tool_count']}개"
        # 서버가 제공한 문자열이므로 이스케이프한 짧은 형태로만 출력한다. 설명·메타데이터는 출력하지 않는다.
        print(f"  - server[{s['server_index']}] {json.dumps(_short(s['server_ref']))}  [{s['collection_status']}/{s['outcome']}, Tool {count}]")
    for r in col["reasons"]:
        print(f"  사유: {r['code']}")
    print(f"결과 저장: {args.output}")
    return EXIT_BY_STATUS[col["status"]]


if __name__ == "__main__":
    sys.exit(main())
