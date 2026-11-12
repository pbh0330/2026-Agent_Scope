"""저장된 MCP `resources/list`·`resources/templates/list`·`prompts/list` 응답에서 정의를 수집한다 (내부 개발용 초안).

    python -m asset_scanner.resources_prompts --capture <저장된 응답 묶음 JSON> --output <결과 JSON>

이 모듈이 하는 일은 **이미 저장된 응답 JSON을 읽는 것뿐**이다. MCP 서버를 실행하거나 접속하지 않고,
`resources/read`·`prompts/get`·`tools/call`도 하지 않는다. 목록에 적힌 항목을 "읽을 수 있다", "Agent에 노출된다",
"호출할 수 있다"고 해석하지 않는다.

근거 규격: MCP 2025-11-25 및 2026-07-28의 `schema/<버전>/schema.ts` (고정 커밋은 docs/field-mapping.md 10장).
- 세 목록은 모두 `PaginatedResult`이고, 2026-07-28에서는 `CacheableResult`와 `Result.resultType`을 더한다.
- 목록마다 배열 이름(`resources`·`resourceTemplates`·`prompts`)과 항목의 필수 필드(`uri`·`uriTemplate`·`name`)가 다르다.
  Tool 규칙(`inputSchema` 등)은 적용하지 않고 각 항목 형식의 규칙으로 따로 검사한다.
- `resources` 능력 하나가 `resources/list`와 `resources/templates/list`를 포괄한다. `prompts` 능력은 `prompts/list`다.

상태 용어 (목록마다 따로 기록한다)
- complete: 끝까지 읽음 (`empty_list`는 정상적인 빈 목록, 서버가 0개를 보고함)
- partial: 일부만 읽었거나 완료를 확인하지 못함
- failed: 읽지 못함 (오류 응답, 잘못된 구조, 응답 없음). 0개가 아니라 수집 실패다.
- unsupported: 저장된 응답이 JSON-RPC "Method not found"(-32601)였음. 서버가 그 메서드를 지원하지 않는다고 응답한 근거다.
- not_performed: 입력에 그 목록의 응답이 없음. 0개도, 미지원도 아니다.

종료 코드는 다른 수집 CLI와 같다: 0 완전, 1 부분, 2 인자 오류, 3 실패, 4 저장 실패.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .cli import _make_console_output_safe, _same_file
from .output import OutputError, normalize_for_output, write_json_atomic
from .redaction import Redactor, looks_like_secret_value
from .tools_catalog import (
    EXIT_BY_STATUS,
    EXIT_OUTPUT_ERROR,
    LEGACY_PROTOCOL_VERSION,
    MAX_CAPTURE_BYTES,
    SUPPORTED_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    _conformance_summary,
    _find_duplicates,
    _is_number,
    _join,
    _json_type_name,
    _MISSING,
    _read_capture,
    _safe_names,
    _safe_short,
    _sanitize,
    _seg,
    _short,
    _text,
)

FORMAT_NAME = "agent-scope.scanner.mcp-resources-prompts"
FORMAT_VERSION = "0.1.0-draft"
CAPTURE_FORMAT = "mcp-lists-capture"
MAX_ITEMS_PER_LIST = 5000
METHOD_NOT_FOUND = -32601

# 규격 근거의 고정 버전 (docs/field-mapping.md 10장). 내려받은 파일의 해시를 함께 기록한다.
SPEC_BASIS = {
    "repository": "modelcontextprotocol/modelcontextprotocol",
    "2025-11-25": {
        "commit": "c4c367f9f58296a7053f5c78a52fd02bfbb56a49",
        "schema": "schema/2025-11-25/schema.ts",
        "schema_git_blob": "850a083fa228bf40af6feca42e23fd26342d3c59",
        "docs": {"docs/specification/2025-11-25/server/resources.mdx": "8f8341c1b974de227a6380cdbaef2c79b1033912",
                 "docs/specification/2025-11-25/server/prompts.mdx": "354c6213b285f07824e990097ac6814d41f56b23"},
    },
    "2026-07-28": {
        "commit": "271ecc9accafdd9b83a3c869fa67c22953b2af80",
        "schema": "schema/2026-07-28/schema.ts",
        "schema_sha256": "742750af0bb8c716e7030c4977c992b55d1adc4407e9e66997db5846baedc2cd",
        "docs": {"docs/specification/2026-07-28/server/resources.mdx": "f49dd8e6be3fd8f13911788ae5f5d4c87d2c53cd",
                 "docs/specification/2026-07-28/server/prompts.mdx": "5a6574be3c16715aaafb1c7973025c1bc3669474"},
    },
}

NOT_VERIFIED = [
    "live_server_query",     # 입력은 저장된 응답이며 서버에 접속하지 않았다
    "current_server_state",  # 저장 시점 이후의 목록 변경
    "resources_read",        # 리소스 내용을 읽지 않았다
    "prompts_get",           # 프롬프트 본문을 가져오지 않았다
    "tools_call",
    "capabilities",          # 입력에 저장된 능력 선언을 옮길 뿐 확인하지 않았다
    "exposure",              # Agent 노출 여부
    "callability",           # 읽기·가져오기·호출 가능 여부
    "common_server_id",      # 팀 공통 server_id·asset_id 미확정
]

DEFINITION_VALIDATION = {
    "level": "limited_structure",
    "checked": [
        "식별 필드(resource.uri, resource_template.uriTemplate, prompt.name)가 비어 있지 않은 문자열인가",
        "name(resource·resource_template 필수)과 title·description·mimeType의 문자열 여부",
        "resource.size의 숫자 여부, annotations(audience·priority 0~1·lastModified), icons[].src, _meta의 기본 JSON 자료형",
        "prompt.arguments가 객체 배열이고 각 argument의 name(필수)·title·description·required(불리언)",
    ],
    "not_checked": [
        "uri가 RFC 3986 URI인지, uriTemplate이 RFC 6570 템플릿인지(문법 검증 없음)",
        "uri 스킴이 접근 가능한지, 템플릿이 실제 리소스로 확장되는지",
        "mimeType 형식, icons 접근 가능 여부, annotations 의미",
        "prompt가 실제로 가져와지는지(prompts/get), 인자 값이 유효한지",
    ],
    "note": ("passed_limited_checks는 위 제한된 검사를 통과했다는 뜻일 뿐 정상 사용 가능한 항목이라는 뜻이 아니다. "
             "failed_limited_checks 항목도 인벤토리 수집 대상이므로 오류 근거(definition_issues)와 함께 보존한다."),
    "redaction_note": ("비밀값 가림을 적용한 정의(definition_altered: true)는 서버가 보낸 원본과 다르다. "
                       "가려진 식별값(uri·uriTemplate·name)은 원본 식별값이 아니므로 identity.*.original_value를 비우고 "
                       "status를 withheld_by_redaction으로 표시하며, 같은 값 여부 비교·중복 판정에 쓰지 않는다. "
                       "가림 위치와 이유는 redactions에 있고 원문 값은 기록하지 않는다."),
}


@dataclass(frozen=True)
class _Kind:
    key: str            # capture의 lists 키이자 결과의 lists 키
    kind: str           # 항목 하위 유형
    method: str
    result_field: str   # 결과 배열 이름
    id_field: str       # 식별 필드
    capability: str     # 서버 능력 이름
    plural: str         # internal_ref에 쓰는 이름


KINDS = (
    _Kind("resources", "resource", "resources/list", "resources", "uri", "resources", "resources"),
    _Kind("resource_templates", "resource_template", "resources/templates/list", "resourceTemplates", "uriTemplate",
          "resources", "resource_templates"),
    _Kind("prompts", "prompt", "prompts/list", "prompts", "name", "prompts", "prompts"),
)

_OFFICIAL_KEYS = {
    "resource": frozenset({"uri", "name", "title", "description", "mimeType", "annotations", "size", "icons", "_meta"}),
    "resource_template": frozenset({"uriTemplate", "name", "title", "description", "mimeType", "annotations", "icons", "_meta"}),
    "prompt": frozenset({"name", "title", "description", "arguments", "icons", "_meta"}),
}

# 규격 적합성 이슈는 수집 완전성(status)을 바꾸지 않는다. 읽은 항목은 그대로 보존한다.
_CONFORMANCE = {
    "result_type_missing": "violation",
    "result_type_invalid": "violation",
    "cache_hint_missing": "violation",
    "cache_hint_invalid": "violation",
    "jsonrpc_version_unexpected": "violation",
    "required_field_missing": "violation",
    "field_type_invalid": "violation",
}


def _issue(severity: str, code: str, message: str, **where: Any) -> dict:
    category = "conformance" if code in _CONFORMANCE else "completeness"
    item = {"category": category, "severity": _CONFORMANCE.get(code, severity), "code": code, "message": message}
    item.update({k: v for k, v in where.items() if v is not None})
    return item


# ---- 가림: URI 템플릿 --------------------------------------------------------------

_TPL_EXPR_RE = re.compile(r"\{[^{}]*\}")


def _sanitize_template(value: str, path: str, red: Redactor) -> str:
    """RFC 6570 템플릿 문자열을 가린다. `{...}` 표현식은 비밀 값이 아니므로 URL 규칙이 망가뜨리지 않게 보호한다.

    표현식 안의 변수 이름이 토큰처럼 보이면 표현식 전체를 `{<redacted>}`로 바꾼다. 템플릿을 확장하거나 해석하지 않는다.
    """
    prefix = "tplx"
    while prefix in value:
        prefix += "q"
    exprs: list[str] = []

    def protect(m: re.Match) -> str:
        expr = m.group(0)
        if looks_like_secret_value(expr[1:-1]):
            red._note(path, "template_expression_looks_like_secret")
            expr = "{<redacted>}"
        exprs.append(expr)
        return f"{prefix}{len(exprs) - 1}x"

    guarded = _TPL_EXPR_RE.sub(protect, value)
    out = _text(red, guarded, path)
    for i, expr in enumerate(exprs):
        out = out.replace(f"{prefix}{i}x", expr)
    return out


def _sanitize_definition(item: dict, kind: _Kind, red: Redactor) -> dict:
    """항목을 구조를 유지한 채 복사하며 비밀값만 가린다 (기존 Tool 정의와 같은 `_sanitize`)."""
    tpl = item.get("uriTemplate")
    if kind.id_field == "uriTemplate" and isinstance(tpl, str):
        rest = {k: v for k, v in item.items() if k != "uriTemplate"}
        sanitized = _sanitize(rest, "", red)
        return {"uriTemplate": _sanitize_template(tpl, "uriTemplate", red), **sanitized}
    return _sanitize(item, "", red)


# ---- 항목 검사 ---------------------------------------------------------------------

def _definition_issues(kind: _Kind, item: dict) -> list[dict]:
    """공식 정의의 필드 형식 위반을 찾는다. 위반해도 항목은 버리지 않고 사유만 남긴다. field_path는 항목 기준 상대 경로."""
    found: list[dict] = []

    def bad(code: str, field: str, msg: str) -> None:
        found.append(_issue("error", code, msg, field_path=field))

    def need_str(field: str, required: bool, obj: dict = item, prefix: str = "") -> None:
        path = prefix + field
        if field not in obj:
            if required:
                bad("required_field_missing", path, f"필수 필드 {path}가 없습니다.")
        elif not isinstance(obj[field], str):
            bad("field_type_invalid", path, f"{path}가 문자열이 아닙니다.")

    need_str(kind.id_field, True)
    if kind.kind != "prompt":
        need_str("name", True)
    for f in ("title", "description"):
        need_str(f, False)
    if kind.kind != "prompt":
        need_str("mimeType", False)
    if kind.kind == "resource" and "size" in item and not _is_number(item["size"]):
        bad("field_type_invalid", "size", "size가 숫자가 아닙니다.")
    if "_meta" in item and not isinstance(item["_meta"], dict):
        bad("field_type_invalid", "_meta", "_meta가 객체가 아닙니다.")
    if kind.kind != "prompt" and "annotations" in item:
        ann = item["annotations"]
        if not isinstance(ann, dict):
            bad("field_type_invalid", "annotations", "annotations가 객체가 아닙니다.")
        else:
            aud = ann.get("audience", _MISSING)
            if aud is not _MISSING and not (isinstance(aud, list) and all(a in ("user", "assistant") for a in aud)):
                bad("field_type_invalid", "annotations.audience", 'annotations.audience가 "user"/"assistant" 배열이 아닙니다.')
            pri = ann.get("priority", _MISSING)
            if pri is not _MISSING and not (_is_number(pri) and 0 <= pri <= 1):
                bad("field_type_invalid", "annotations.priority", "annotations.priority가 0~1 숫자가 아닙니다.")
            if "lastModified" in ann and not isinstance(ann["lastModified"], str):
                bad("field_type_invalid", "annotations.lastModified", "annotations.lastModified가 문자열이 아닙니다.")
    if "icons" in item:
        icons = item["icons"]
        if not isinstance(icons, list):
            bad("field_type_invalid", "icons", "icons가 배열이 아닙니다.")
        else:
            for i, icon in enumerate(icons):
                if not isinstance(icon, dict) or not isinstance(icon.get("src"), str):
                    bad("field_type_invalid", f"icons[{i}]", "icons 항목에 문자열 src가 없습니다.")
    if kind.kind == "prompt" and "arguments" in item:
        args = item["arguments"]
        if not isinstance(args, list):
            bad("field_type_invalid", "arguments", "arguments가 배열이 아닙니다.")
        else:
            for i, arg in enumerate(args):
                p = f"arguments[{i}]"
                if not isinstance(arg, dict):
                    bad("field_type_invalid", p, "arguments 항목이 객체가 아닙니다.")
                    continue
                need_str("name", True, arg, p + ".")
                need_str("title", False, arg, p + ".")
                need_str("description", False, arg, p + ".")
                if "required" in arg and not isinstance(arg["required"], bool):
                    bad("field_type_invalid", p + ".required", "arguments[].required가 불리언이 아닙니다.")
    return found


def _identity_entry(item: dict, defn: dict, field: str, redacted_paths: set[str]) -> dict:
    """원본 식별값 기록. 가려졌거나 바뀐 값은 원본 식별값이 아니므로 비운다."""
    value = item.get(field, _MISSING)
    if value is _MISSING:
        return {"original_value": None, "status": "missing"}
    if not isinstance(value, str):
        return {"original_value": None, "status": "invalid_type", "actual": _json_type_name(value)}
    if field in redacted_paths or defn.get(field) != value:
        return {"original_value": None, "status": "withheld_by_redaction"}
    return {"original_value": value, "status": "as_reported"}


def _redacted_top_paths(redactions: list[dict]) -> set[str]:
    out: set[str] = set()
    for r in redactions:
        p = r.get("field_path")
        if isinstance(p, str):
            out.add(p.split(".")[0].split("[")[0])
    return out


# ---- 페이지 해석 ------------------------------------------------------------------

def _parse_page(raw: Any, page_index: int, version: str, kind: _Kind) -> dict:
    """응답 한 건을 해석한다. 반환: ok, issues, items(원본), has_next, stop, unsupported, record."""
    res: dict = {"ok": False, "issues": [], "items": [], "has_next": False, "stop": False,
                 "unsupported": False, "record": {"page_index": page_index}}
    issues: list[dict] = res["issues"]

    def fail(code: str, msg: str, **extra: Any) -> dict:
        issues.append(_issue("error", code, msg, page_index=page_index, **extra))
        res["stop"] = True
        return res

    if not isinstance(raw, dict):
        return fail("invalid_response_structure", "응답이 JSON 객체가 아닙니다.")
    has_result, has_error = "result" in raw, "error" in raw
    if (has_result or has_error or "jsonrpc" in raw) and getattr(raw, "duplicate_keys", None):
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
        code_ok = isinstance(code, int) and not isinstance(code, bool)
        red = Redactor()
        msg = err.get("message")
        extra: dict[str, Any] = {"error_code": code if code_ok else None}
        if isinstance(msg, str):
            extra["error_message"] = _safe_short(red, msg, "error.message")
        if red.redactions:
            extra["redactions"] = red.redactions
        if "data" in err:
            extra["error_data_omitted"] = True
        if page_index == 0 and code_ok and code == METHOD_NOT_FOUND:
            # 첫 응답이 "Method not found"면 서버가 이 메서드를 지원하지 않는다고 응답한 것이다.
            res["unsupported"] = True
            res["stop"] = True
            res["record"].update({k: v for k, v in extra.items() if k != "error_data_omitted"})
            return res
        return fail("error_response", "서버가 오류 응답을 반환했습니다. 항목 0개가 아니라 수집 실패입니다.", **extra)
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

    latest = version == SUPPORTED_PROTOCOL_VERSION
    if latest:  # 2026-07-28: Result.resultType 필수. 2025-11-25에는 없으므로 요구하지 않는다.
        rtype = result.get("resultType", _MISSING)
        if rtype is _MISSING or not isinstance(rtype, str):
            missing = rtype is _MISSING
            res["record"]["result_type_state"] = "missing" if missing else "invalid_type"
            issues.append(_issue("error", "result_type_missing" if missing else "result_type_invalid",
                                 "2026-07-28 규격에서 서버가 반드시 넣어야 하는 resultType이 없습니다." if missing
                                 else "resultType이 문자열이 아닙니다.", page_index=page_index))
            issues.append(_issue("error", "result_completion_unverified",
                                 "resultType을 해석할 수 없어 이 응답이 완료된 응답이라고 판단하지 않았습니다. 읽을 수 있는 항목은 보존합니다.",
                                 page_index=page_index))
        elif rtype == "input_required":
            res["record"]["result_type"] = rtype
            return fail("input_required_result", f"{kind.method} 응답이 추가 입력을 요구하는 결과(input_required)입니다. 목록으로 읽지 않습니다.")
        elif rtype != "complete":
            res["record"]["result_type"] = _safe_short(Redactor(), rtype, "resultType")
            return fail("unsupported_result_type", "해석할 수 없는 resultType입니다. 응답 구조를 추정하지 않고 읽지 않습니다.")
        else:
            res["record"]["result_type"] = rtype
            res["record"]["result_type_state"] = "complete"

    items = result.get(kind.result_field, _MISSING)
    if items is _MISSING:
        return fail("invalid_response_structure", f"필수 필드 {kind.result_field}가 없습니다.", field_path=kind.result_field)
    if not isinstance(items, list):
        return fail("invalid_response_structure", f"{kind.result_field}가 배열이 아닙니다.", field_path=kind.result_field)

    cursor = result.get("nextCursor", _MISSING)
    if cursor is not _MISSING and not isinstance(cursor, str):
        issues.append(_issue("error", "next_cursor_invalid", "nextCursor가 문자열이 아닙니다. 이후 페이지 상태를 알 수 없습니다.", page_index=page_index))
        res["stop"] = True
    elif isinstance(cursor, str):
        res["has_next"] = True  # 빈 문자열도 유효한 커서다. 커서 값은 저장하지 않는다.

    if latest:
        ttl, scope = result.get("ttlMs", _MISSING), result.get("cacheScope", _MISSING)
        missing_names = [n for n, v in (("ttlMs", ttl), ("cacheScope", scope)) if v is _MISSING]
        if missing_names:
            issues.append(_issue("warning", "cache_hint_missing", f"규격상 필요한 {', '.join(missing_names)}가 응답에 없습니다.", page_index=page_index))
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
    known = {kind.result_field, "nextCursor", "_meta"} | ({"resultType", "ttlMs", "cacheScope"} if latest else set())
    extra_keys = sorted(_seg(k) for k in result if k not in known)
    if extra_keys:
        res["record"]["other_result_fields"] = extra_keys

    dups: list[tuple[str, list[str]]] = []
    rpath = f"pages[{page_index}].result"
    if getattr(result, "duplicate_keys", None):
        dups.append((rpath, _safe_names(result.duplicate_keys)))
    for k, v in result.items():
        if k != kind.result_field:  # 항목 배열은 항목별로 따로 검사한다
            _find_duplicates(v, _join(rpath, k), dups)
    for path_, names in dups:
        issues.append(_issue("error", "duplicate_key", "같은 키가 중복돼 마지막 값만 남았습니다.", page_index=page_index,
                             field_path=path_, duplicate_keys=names))

    res["items"] = items
    res["ok"] = True
    res["record"]["item_count"] = len(items)
    res["record"]["has_next_cursor"] = res["has_next"]
    return res


# ---- 목록 하나 --------------------------------------------------------------------

def _not_performed(kind: _Kind, declared: str) -> dict:
    reason = "capability_not_declared" if declared == "not_declared" else "not_requested"
    return {"kind": kind.kind, "method": kind.method, "collection_status": "not_performed", "outcome": reason,
            "item_count": None, "declared_capability": declared, "pages": [], "issues": [],
            "spec_conformance": _conformance_summary([], False), "items": [],
            "note": "입력에 이 목록의 응답이 없습니다. 항목 0개도, 서버가 지원하지 않는다는 뜻도 아닙니다."}


def _failed_list(kind: _Kind, declared: str, code: str, message: str) -> dict:
    return {"kind": kind.kind, "method": kind.method, "collection_status": "failed", "outcome": code,
            "item_count": None, "declared_capability": declared, "pages": [], "issues": [_issue("error", code, message)],
            "spec_conformance": _conformance_summary([], False), "items": []}


def _collect_list(kind: _Kind, spec: Any, version: str, declared: str, server_index: int, server_ref: str,
                  extra_issues: list[dict]) -> dict:
    pages = spec.get("pages", _MISSING) if isinstance(spec, dict) else _MISSING
    if not isinstance(spec, dict):
        out = _failed_list(kind, declared, "invalid_list_entry", "lists 항목이 객체가 아닙니다.")
    elif not isinstance(pages, list) or not pages:
        out = _failed_list(kind, declared, "no_response", "저장된 응답이 없습니다. 응답이 없는 것은 항목 0개가 아닙니다.")
    else:
        out = None
    if out is not None:
        out["issues"].extend(extra_issues)
        return out

    issues: list[dict] = list(extra_issues)
    page_records: list[dict] = []
    items_out: list[dict] = []
    parsed_ok = 0
    last_has_next = False
    stopped = False
    processed = 0
    flat_index = 0
    identities: dict[str, list[int]] = {}
    unsupported_record: dict | None = None

    if declared == "not_declared":
        issues.append(_issue("warning", "list_without_declared_capability",
                             f"입력의 능력 선언에 {kind.capability}가 없는데 {kind.method} 응답이 저장돼 있습니다. 응답은 그대로 읽었습니다."))

    for page_index, raw in enumerate(pages):
        if page_index > 0 and not last_has_next:
            issues.append(_issue("error", "page_after_final_page",
                                 "nextCursor가 없는 마지막 페이지 뒤에 응답이 더 있습니다. 뒤의 응답은 읽지 않았습니다.",
                                 page_index=page_index, ignored_pages=len(pages) - page_index))
            break
        if stopped:
            break
        processed += 1
        page = _parse_page(raw, page_index, version, kind)
        issues.extend(page["issues"])
        if page["unsupported"]:
            unsupported_record = page["record"]
            page_records.append(page["record"])
            break
        page_records.append(page["record"])
        if not page["ok"]:
            stopped = True
            last_has_next = False
            break
        parsed_ok += 1
        last_has_next = page["has_next"]
        stopped = page["stop"]
        for idx_in_page, item in enumerate(page["items"]):
            if flat_index >= MAX_ITEMS_PER_LIST:
                issues.append(_issue("error", "item_limit_exceeded",
                                     f"목록당 항목 {MAX_ITEMS_PER_LIST}개 한도를 넘어 나머지를 읽지 않았습니다.", page_index=page_index))
                stopped = True
                last_has_next = False
                break
            item_index = flat_index
            flat_index += 1
            base = f"pages[{page_index}].result.{kind.result_field}[{idx_in_page}]"
            if not isinstance(item, dict):
                issues.append(_issue("error", "item_invalid", "목록 항목이 객체가 아닙니다. 이 항목은 제외했습니다.",
                                     page_index=page_index, item_index=item_index))
                continue
            ident = item.get(kind.id_field)
            if not isinstance(ident, str) or ident == "":
                issues.append(_issue("error", "required_field_missing",
                                     f"필수 필드 {kind.id_field}가 비어 있지 않은 문자열이 아닙니다.",
                                     page_index=page_index, item_index=item_index, field_path=_join(base, kind.id_field)))
                issues.append(_issue("error", "item_invalid", f"식별할 {kind.id_field}가 없어 이 항목은 제외했습니다.",
                                     page_index=page_index, item_index=item_index))
                continue
            def_issues = _definition_issues(kind, item)
            dups: list[tuple[str, list[str]]] = []
            _find_duplicates(item, "", dups)
            def_issues += [_issue("error", "duplicate_key", "같은 키가 중복돼 마지막 값만 남았습니다.",
                                  field_path="(definition)" if p == "(root)" else p, duplicate_keys=names)
                           for p, names in dups]
            red = Redactor()
            definition = _sanitize_definition(item, kind, red)
            touched = _redacted_top_paths(red.redactions)
            identity = {kind.id_field: _identity_entry(item, definition, kind.id_field, touched)}
            if kind.kind != "prompt":
                identity["name"] = _identity_entry(item, definition, "name", touched)
            if identity[kind.id_field]["status"] == "as_reported":
                identities.setdefault(ident, []).append(item_index)
            other = sorted(_seg(k) for k in item if k not in _OFFICIAL_KEYS[kind.kind])
            items_out.append({
                # 아래 값은 이 파일 안에서만 쓰는 내부 참조다. 공통 자산 ID가 아니며 실행마다 같다는 보장도 없다.
                "internal_ref": f"capture-server[{server_index}]/{kind.plural}[{item_index}]",
                "kind": kind.kind,
                "server_index": server_index,
                "server_ref": server_ref,
                "page_index": page_index,
                "index_in_page": idx_in_page,
                "identity": identity,
                "definition": definition,
                "definition_status": "failed_limited_checks" if def_issues else "passed_limited_checks",
                "definition_check_level": "limited_structure",
                "definition_issues": def_issues,
                "other_definition_fields": other,
                "redactions": red.redactions,
                "definition_altered": bool(red.redactions),
                "trust": "untrusted_server_provided",
            })
            for di in def_issues:
                rel = di["field_path"]
                absolute = base if rel == "(definition)" else _join(base, rel)
                issues.append({**di, "field_path": absolute, "page_index": page_index, "item_index": item_index})

    if unsupported_record is not None and parsed_ok == 0 and len(page_records) == 1 and not any(
            i["category"] == "completeness" and i["severity"] == "error" for i in issues):
        return {"kind": kind.kind, "method": kind.method, "collection_status": "unsupported", "outcome": "method_not_found",
                "item_count": None, "declared_capability": declared, "pages": page_records, "issues": issues,
                "spec_conformance": _conformance_summary([], False), "items": [],
                "evidence": {"error_code": METHOD_NOT_FOUND, "page_index": 0,
                             "meaning": "저장된 첫 응답이 JSON-RPC Method not found(-32601)입니다. 서버가 이 메서드를 지원하지 않는다고 응답한 근거이며 항목 0개와는 다릅니다."}}

    if parsed_ok and last_has_next:
        issues.append(_issue("error", "next_cursor_remaining",
                             "마지막으로 읽은 페이지에 nextCursor가 남아 있습니다. 목록이 끝까지 수집되지 않았습니다.",
                             page_index=processed - 1))
    for value, idxs in identities.items():
        if len(idxs) > 1:
            issues.append(_issue("warning", "duplicate_identifier_in_list",
                                 f"같은 목록 안에서 {kind.id_field} 값이 중복됩니다. 두 항목을 모두 유지했고 합치지 않았습니다.",
                                 item_indexes=idxs))

    errors = [i for i in issues if i["category"] == "completeness" and i["severity"] == "error"]
    if parsed_ok == 0:
        status, outcome = "failed", errors[0]["code"] if errors else "no_response"
        count: int | None = None
    elif errors:
        only_unverified = {i["code"] for i in errors} == {"result_completion_unverified"}
        status, outcome, count = "partial", ("completion_unverified" if only_unverified else "incomplete_list"), len(items_out)
    else:
        status, count = "complete", len(items_out)
        outcome = "items_listed" if count else "empty_list"
    return {"kind": kind.kind, "method": kind.method, "collection_status": status, "outcome": outcome,
            "item_count": count, "declared_capability": declared, "pages": page_records, "issues": issues,
            "spec_conformance": _conformance_summary(issues, parsed_ok > 0), "items": items_out if parsed_ok else []}


# ---- 서버 단위 수집 ----------------------------------------------------------------

def _declared_capabilities(raw: Any) -> tuple[dict[str, str], list[dict]]:
    """입력에 저장된 능력 선언에서 `resources`·`prompts` 존재만 옮긴다. 내용은 옮기지 않고 확인하지도 않는다."""
    names = ("resources", "prompts")
    if raw is _MISSING:
        return {n: "unknown" for n in names}, []
    if not isinstance(raw, dict):
        return {n: "unknown" for n in names}, [_issue("warning", "server_capabilities_invalid",
                                                       "server_capabilities가 객체가 아니어서 능력 선언을 읽지 않았습니다.")]
    out = {}
    for n in names:
        v = raw.get(n, _MISSING)
        out[n] = "not_declared" if v is _MISSING else ("declared" if isinstance(v, dict) else "unknown")
    return out, []


def _failed_server(index: int, label: str, code: str, message: str, **extra: Any) -> dict:
    return {"server_index": index, "server_ref": label, "collection_status": "failed", "outcome": code,
            "counts": {k.key: None for k in KINDS}, "lists": {}, "issues": [_issue("error", code, message, **extra)],
            "redactions": []}


def _aggregate(lists: dict[str, dict]) -> tuple[str, str]:
    statuses = [lst["collection_status"] for lst in lists.values()]
    if all(s in ("complete", "unsupported") for s in statuses):
        return "complete", "lists_collected"
    if all(s in ("failed", "not_performed") for s in statuses):
        failed = [lst for lst in lists.values() if lst["collection_status"] == "failed"]
        return "failed", (failed[0]["outcome"] if failed else "no_list_performed")
    return "partial", "some_lists_incomplete"


def _collect_server(index: int, entry: Any, seen_refs: set[str]) -> dict:
    if not isinstance(entry, dict):
        return _failed_server(index, "<invalid>", "invalid_server_entry", "servers 항목이 객체가 아닙니다.")
    ref = entry.get("server_ref")
    if not isinstance(ref, str) or not ref:
        return _failed_server(index, "<missing>", "invalid_server_entry", "server_ref가 비어 있지 않은 문자열이 아닙니다.")
    srv_red = Redactor()
    safe_ref = _text(srv_red, ref, "server_ref")
    if ref in seen_refs:
        return _failed_server(index, safe_ref, "duplicate_server_ref",
                              "같은 server_ref가 이미 있습니다. 서로 다른 서버를 합치지 않기 위해 이 항목은 읽지 않습니다.")
    seen_refs.add(ref)

    server: dict = {"server_index": index, "server_ref": safe_ref, "server_ref_kind": "capture_local_label"}
    link: dict[str, Any] = {}
    for key in ("registration_key", "registry_path"):
        v = entry.get(key)
        if isinstance(v, str):
            link[key] = _text(srv_red, v, key)
    cref = entry.get("config_scan_ref", _MISSING)
    if isinstance(cref, str):
        link["config_scan_ref"] = _text(srv_red, cref, "config_scan_ref")
    elif cref is not _MISSING:
        link["config_scan_ref_invalid_type"] = _json_type_name(cref)
    if link:
        link["verified_against_config_scan"] = False  # 입력에 적힌 값이며 설정 수집 결과와 대조하지 않았다
        server["config_link"] = link

    version = entry.get("protocol_version")
    server["declared_protocol_version"] = _safe_short(srv_red, version, "protocol_version") if isinstance(version, str) else None

    def done_failed(code: str, message: str, **extra: Any) -> dict:
        server.update(collection_status="failed", outcome=code, counts={k.key: None for k in KINDS}, lists={},
                      issues=[_issue("error", code, message, **extra)], redactions=srv_red.redactions)
        return server

    if not isinstance(version, str) or not version:
        return done_failed("protocol_version_not_declared",
                           "입력이 protocol_version을 선언하지 않았습니다. 응답 구조는 규격 버전에 따라 다르므로 읽지 않습니다.")
    if version not in SUPPORTED_PROTOCOL_VERSIONS:
        return done_failed("protocol_version_unsupported",
                           f"지원하는 MCP 버전은 {', '.join(SUPPORTED_PROTOCOL_VERSIONS)}입니다. 다른 버전은 추정하지 않습니다.",
                           declared=_safe_short(srv_red, version, "protocol_version"))
    lists_in = entry.get("lists", {})
    if not isinstance(lists_in, dict):
        return done_failed("invalid_lists", "lists가 객체가 아닙니다.")

    caps, cap_issues = _declared_capabilities(entry.get("server_capabilities", _MISSING))
    server["declared_capabilities"] = {**caps, "source": "stored_in_input_not_verified"}
    lists_dups = set(getattr(lists_in, "duplicate_keys", []))
    other_keys = sorted(_seg(k) for k in lists_in if k not in {kd.key for kd in KINDS})
    if other_keys:
        server["other_list_keys"] = other_keys  # 이 모듈이 읽지 않는 목록 키(이름만)

    lists_out: dict[str, dict] = {}
    for kd in KINDS:
        declared = caps[kd.capability]
        if kd.key not in lists_in:
            lists_out[kd.key] = _not_performed(kd, declared)
            continue
        extra = []
        if kd.key in lists_dups:
            extra.append(_issue("error", "duplicate_key", "lists에 같은 키가 중복돼 마지막 값만 남았습니다. 앞의 값은 읽지 못했습니다.",
                                field_path=f"lists.{kd.key}", duplicate_keys=[kd.key]))
        spec = lists_in[kd.key]
        if isinstance(spec, dict) and getattr(spec, "duplicate_keys", None):
            extra.append(_issue("error", "duplicate_key", "목록 항목에 같은 키가 중복돼 마지막 값만 남았습니다.",
                                field_path=f"lists.{kd.key}", duplicate_keys=_safe_names(spec.duplicate_keys)))
        lists_out[kd.key] = _collect_list(kd, spec, version, declared, index, safe_ref, extra)

    status, outcome = _aggregate(lists_out)
    server_issues = list(cap_issues)
    server.update(collection_status=status, outcome=outcome, issues=server_issues, redactions=srv_red.redactions,
                  counts={k: lists_out[k]["item_count"] for k in lists_out}, lists=lists_out)
    return server


def _flag_entry_duplicates(server: dict, keys: list[str], index: int) -> None:
    server["issues"].append(_issue("error", "duplicate_key",
                                   "서버 항목에 같은 키가 중복돼 마지막 값만 남았습니다. 앞의 값은 읽지 못했습니다.",
                                   field_path=f"servers[{index}]", duplicate_keys=keys))
    if server["collection_status"] == "complete":
        server["collection_status"] = "partial"
        server["outcome"] = "duplicate_keys"


# ---- 전체 -------------------------------------------------------------------------

def summarize_collection(servers: list[dict], failure: dict | None, root_duplicates: list[str]) -> dict:
    reasons: list[dict] = []
    totals: dict[str, int | None] = {k.key: None for k in KINDS}
    counts_complete = False
    if failure is not None:
        status, outcome, server_count = "failed", failure["code"], None
        reasons.append(failure)
    else:
        statuses = [s["collection_status"] for s in servers]
        status = ("complete" if all(s == "complete" for s in statuses)
                  else "failed" if all(s == "failed" for s in statuses) else "partial")
        outcome = {"complete": "all_servers_collected", "partial": "some_servers_incomplete", "failed": "no_server_collected"}[status]
        server_count = len(servers)
        totals = {k.key: sum((s["counts"].get(k.key) or 0) for s in servers) for k in KINDS}
        # complete는 모든 서버의 모든 목록이 complete 또는 unsupported(응답으로 확인된 미지원)라는 뜻이다.
        counts_complete = status == "complete"
        for s in servers:
            for key, lst in s["lists"].items():
                if lst["collection_status"] in ("partial", "failed", "not_performed"):
                    reasons.append({"code": "list_incomplete", "server_index": s["server_index"], "list": key,
                                    "list_status": lst["collection_status"], "list_outcome": lst["outcome"],
                                    "message": "이 목록의 수집이 완전하지 않습니다. 항목 수는 읽은 항목 수일 뿐 서버의 전체 항목 수가 아닙니다."})
            if s["collection_status"] == "failed" and not s["lists"]:
                reasons.append({"code": "server_not_collected", "server_index": s["server_index"], "server_outcome": s["outcome"],
                                "message": "이 서버의 응답을 읽지 못했습니다."})
    if failure is None and root_duplicates:
        reasons.append({"code": "duplicate_key_in_capture", "field_path": "(root)", "duplicate_keys": root_duplicates,
                        "message": "입력 최상위에 같은 키가 중복돼 마지막 값만 읽었습니다. 앞의 값(서버 등)이 빠졌을 수 있어 완전 수집으로 보지 않습니다."})
        if status == "complete":
            status, outcome, counts_complete = "partial", "duplicate_keys_in_capture", False
    return {"status": status, "outcome": outcome, "server_count": server_count, "item_counts": totals,
            "item_counts_complete": counts_complete, "reasons": reasons}


def collect_resources_prompts(capture_path: Path) -> dict:
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
        origin = _safe_short(Redactor(), o, "origin") if isinstance(o, str) else None
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
    return {"capture_path": str(capture_path), "origin": origin,
            "collection": summarize_collection(servers, failure, root_duplicates), "servers": servers}


def build_report(collected: dict) -> dict:
    return {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "format_status": (
            "스캐너 내부 개발용 초안입니다. 팀 공통 스키마가 아니며 필드명과 구조는 협의 후 변경될 수 있습니다. "
            "공통 server_id·asset_id는 정하지 않았고 server_ref·internal_ref는 이 파일 안에서만 쓰는 이름입니다."
        ),
        "producer": {"name": "agent-scope-asset-scanner", "version": __version__},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "protocol": {"supported_versions": [LEGACY_PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSION], "spec_basis": SPEC_BASIS},
        "source": {
            "capture_path": collected["capture_path"],
            "source_kind": "stored_list_responses",
            "evidence_type": "stored_protocol_response",
            "live_server_query": False,
            "origin_declared_by_input": collected["origin"],
        },
        "scope": {
            "method": "저장된 resources/list · resources/templates/list · prompts/list 응답 JSON 읽기",
            "not_verified": NOT_VERIFIED,
            "list_status_meaning": {
                "complete": "끝까지 읽음. empty_list는 서버가 0개를 보고한 정상 빈 목록",
                "partial": "일부만 읽었거나 완료를 확인하지 못함",
                "failed": "읽지 못함. 항목 0개가 아님",
                "unsupported": "저장된 첫 응답이 JSON-RPC Method not found(-32601)",
                "not_performed": "입력에 응답이 없음. 0개도 미지원도 아님",
            },
            "definition_validation": DEFINITION_VALIDATION,
            "note": ("lists.*.items[]는 입력 파일의 응답에 적힌 정의를 옮긴 것입니다. 서버에 접속하지 않았으므로 실제 서버가 지금 "
                     "이 목록을 반환하는지, 리소스를 읽을 수 있는지, 프롬프트를 가져올 수 있는지, Agent에 노출되는지는 확인하지 않았습니다. "
                     "서버가 제공한 URI·설명·인자·메타데이터는 비신뢰 데이터로만 저장하며 접속·확장·실행하지 않습니다."),
        },
        "collection": collected["collection"],
        "servers": collected["servers"],
    }


# ---- CLI --------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m asset_scanner.resources_prompts",
        description="저장된 MCP resources/list · resources/templates/list · prompts/list 응답(capture JSON)을 읽어 정의를 저장합니다 "
                    "(내부 개발용 초안, 서버에 접속하지 않음).",
    )
    p.add_argument("--capture", required=True, type=Path, help="저장된 목록 응답을 담은 capture JSON")
    p.add_argument("--output", required=True, type=Path, help="결과 JSON을 저장할 경로")
    return p


def main(argv: list[str] | None = None) -> int:
    _make_console_output_safe()
    args = _parser().parse_args(argv)
    if _same_file(args.capture, args.output):
        print("오류: --output이 --capture와 같은 파일입니다. 입력을 덮어쓰지 않습니다.", file=sys.stderr)
        return EXIT_OUTPUT_ERROR

    report = build_report(collect_resources_prompts(args.capture))
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
        c = col["item_counts"]
        print(f"서버: {col['server_count']}개, 읽은 항목: resources {c['resources']}, templates {c['resource_templates']}, "
              f"prompts {c['prompts']}" + ("" if col["item_counts_complete"] else " (전체 수가 아님)"))
    for s in report["servers"]:
        print(f"  - server[{s['server_index']}] {json.dumps(_short(s['server_ref']))}  [{s['collection_status']}/{s['outcome']}]")
        for key, lst in s["lists"].items():
            n = "미확인" if lst["item_count"] is None else f"{lst['item_count']}개"
            print(f"      {key}: {lst['collection_status']}/{lst['outcome']} ({n})")
    for r in col["reasons"]:
        print(f"  사유: {r['code']}")
    print(f"결과 저장: {args.output}")
    return EXIT_BY_STATUS[col["status"]]


if __name__ == "__main__":
    sys.exit(main())
