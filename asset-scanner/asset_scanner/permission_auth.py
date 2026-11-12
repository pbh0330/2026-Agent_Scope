"""OpenClaw 설정에서 Permission/Auth 선언을 원천 항목 단위로 수집한다 (자산 수집 확대 ③, 내부 개발용 초안).

    python -m asset_scanner.permission_auth --config <openclaw.json5> --output <결과 JSON>

설정 파일을 읽기만 한다. 실행·접속·`$include` 읽기·환경변수 해석을 하지 않는다. 수집 대상은 OpenClaw 2026.9.6 패키지 문서에서
확인한 설정 경로의 **선언된 값**뿐이며(표 `SPEC`, 근거 문서는 항목마다 `doc_basis`), 문서에 없는 키는 값을 읽지 않는다.

- 원천 항목을 합치거나 집계하지 않는다. "실제로 적용되는 정책", 허용/거부의 최종 결과, 기본값은 계산하지 않는다.
  (집계 단위는 팀 협의 중이므로 공통 규칙으로 확정하지 않는다.)
- 각 항목은 설정 위치(`config_path`·`config_pointer`)와 적용 대상(`applies_to`: 전역, Provider, Agent, 발신자 종류, Gateway, Node,
  플러그인, MCP 서버 선언 위치)을 함께 가진다. MCP 서버 항목은 설정 수집기의 `declaration_path`와 같은 표기를 쓴다.
- 인증정보(`token`·`password`)는 종류(`secret_ref`/`env_ref`/`literal_withheld`)와 참조 이름만 남기고 원문·길이·해시를 저장하지 않는다.
- 발신자 키(`tools.toolsBySender`의 키)와 `elevated.allowFrom` 값은 개인 식별정보일 수 있어 종류·개수만 남기고 값은 저장하지 않는다.
종료 코드: 0 완전, 1 부분, 2 인자 오류, 3 실패, 4 저장 실패.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .cli import _make_console_output_safe, _same_file
from .collector import (CollectionFailure, SUPPORTED_REGISTRY_PATHS, _find_duplicate_keys, _find_includes, _include_record, _type_name,
                        _value_kind, dotted_path, json_pointer, parse_config, read_config)
from .output import OutputError, normalize_for_output, write_json_atomic
from .redaction import REDACTED, Redactor, looks_like_secret_value
from .tools_catalog import _short

FORMAT_NAME = "agent-scope.scanner.openclaw-permission-auth"
FORMAT_VERSION = "0.1.0-draft"
EXIT_BY_STATUS = {"complete": 0, "partial": 1, "failed": 3}
EXIT_OUTPUT_ERROR = 4
MAX_LIST = 200

D_TOOLS = "docs/gateway/config-tools/tool-policy.md"
D_GATEWAY = "docs/gateway/config-gateway.md"
D_NODEMCP = "docs/nodes/mcp-and-skills.md; docs/gateway/config-extensions.md"
D_EXT = "docs/gateway/config-extensions.md"
D_SKILLS = "docs/tools/skills-config.md"
D_MCP = "docs/gateway/config-extensions.md (mcp.servers.<name>.auth/oauth)"

# (경로 패턴, 값 형식, 분류, 근거 문서). "*"는 그 단계의 모든 키. 형식:
# bool | str | str:<허용값,...> | list | args | number | cred | count | keys | path
_TOOL_KEYS = (("profile", "str"), ("allow", "list"), ("alsoAllow", "list"), ("deny", "list"))
SPEC: list[tuple[tuple[str, ...], str, str, str]] = []
for _k, _t in _TOOL_KEYS:
    SPEC.append((("tools", _k), _t, "tool_policy", D_TOOLS))
    SPEC.append((("tools", "byProvider", "*", _k), _t, "tool_policy", D_TOOLS))
    SPEC.append((("agents", "entries", "*", "tools", _k), _t, "tool_policy", D_TOOLS))
for _k in ("allow", "alsoAllow", "deny"):
    SPEC.append((("tools", "toolsBySender", "*", _k), "list", "tool_policy", D_TOOLS))
SPEC += [
    (("tools", "elevated", "enabled"), "bool", "tool_policy", D_TOOLS),
    (("tools", "elevated", "allowFrom", "*"), "count", "tool_policy", D_TOOLS),
    (("agents", "entries", "*", "tools", "elevated", "enabled"), "bool", "tool_policy", D_TOOLS),
    (("agents", "defaults", "skills"), "list", "skill_policy", D_SKILLS),
    (("agents", "entries", "*", "skills"), "list", "skill_policy", D_SKILLS),
    (("skills", "allowBundled"), "list", "skill_policy", D_SKILLS),
    (("gateway", "auth", "mode"), "str:none,token,password,trusted-proxy", "gateway_auth", D_GATEWAY),
    (("gateway", "auth", "allowTailscale"), "bool", "gateway_auth", D_GATEWAY),
    (("gateway", "auth", "token"), "cred", "gateway_auth", D_GATEWAY),
    (("gateway", "auth", "password"), "cred", "gateway_auth", D_GATEWAY),
    (("gateway", "auth", "trustedProxy", "userHeader"), "str", "gateway_auth", D_GATEWAY),
    (("gateway", "trustedProxies"), "list", "gateway_auth", D_GATEWAY),
    (("gateway", "remote", "token"), "cred", "gateway_remote_client_auth", D_GATEWAY),
    (("gateway", "remote", "password"), "cred", "gateway_remote_client_auth", D_GATEWAY),
    (("gateway", "nodes", "commands", "allow"), "list", "node_policy", D_GATEWAY),
    (("gateway", "nodes", "commands", "deny"), "list", "node_policy", D_GATEWAY),
    (("gateway", "nodes", "pluginTools", "enabled"), "bool", "node_policy", D_NODEMCP),
    (("gateway", "nodes", "allowSkills"), "bool", "node_policy", D_NODEMCP),
    (("gateway", "nodes", "pairing", "autoApproveLocal"), "bool", "node_policy", D_GATEWAY),
    (("nodeHost", "skills", "enabled"), "bool", "node_policy", D_NODEMCP),
    (("plugins", "enabled"), "bool", "plugin_policy", D_EXT),
    (("plugins", "allow"), "list", "plugin_policy", D_EXT),
    (("plugins", "deny"), "list", "plugin_policy", D_EXT),
    (("security", "installPolicy", "enabled"), "bool", "install_policy", D_SKILLS),
    (("security", "installPolicy", "targets"), "list", "install_policy", D_SKILLS),
    (("security", "installPolicy", "exec", "command"), "str", "install_policy", D_SKILLS),
    (("security", "installPolicy", "exec", "args"), "args", "install_policy", D_SKILLS),
    (("security", "installPolicy", "exec", "timeoutMs"), "number", "install_policy", D_SKILLS),
    (("security", "installPolicy", "exec", "noOutputTimeoutMs"), "number", "install_policy", D_SKILLS),
    (("security", "installPolicy", "exec", "maxOutputBytes"), "number", "install_policy", D_SKILLS),
    (("security", "installPolicy", "exec", "passEnv"), "list", "install_policy", D_SKILLS),
    (("security", "installPolicy", "exec", "env"), "keys", "install_policy", D_SKILLS),
    (("security", "installPolicy", "exec", "trustedDirs"), "list", "install_policy", D_SKILLS),
]
# MCP 서버 항목의 인증 관련 필드. 등록 영역(mcp.servers·nodeHost.mcp.servers)마다 같은 형식으로 읽는다.
MCP_AUTH_SPEC: list[tuple[tuple[str, ...], str]] = [
    (("auth",), "str"), (("oauth", "identity"), "str:shared,per-requester"), (("oauth", "scope"), "str"), (("oauth", "authProfileId"), "str"),
    (("oauth", "redirectUrl"), "str"), (("oauth", "clientMetadataUrl"), "str"), (("clientCert",), "path"), (("clientKey",), "path"),
]

NOT_COLLECTED = [
    "effective_policy",            # 허용/거부의 최종 결과·기본값·우선순위 계산
    "tool_groups_and_profiles_expansion",   # group:fs, profile 이름이 가리키는 Tool 목록 펼치기
    "runtime_approvals_and_pairing_state",  # 승인·페어링 상태(런타임 상태)
    "secret_values",               # 인증정보 원문·길이·해시
    "channel_access_control",      # 채널별 허용 목록 등 이 표에 없는 정책 영역
    "sandbox_settings",
    "exec_approvals_file",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _issue(severity: str, code: str, message: str, **where: Any) -> dict:
    item = {"severity": severity, "code": code, "message": message}
    item.update({k: v for k, v in where.items() if v is not None})
    return item


def _walk(node: Any, pattern: tuple[str, ...], real: tuple, shown: tuple) -> list[tuple[tuple, tuple, Any]]:
    """패턴을 따라 내려가며 (실제 키 경로, 표시용 경로, 값)을 모은다. `*`는 그 단계의 모든 키."""
    if not pattern:
        return [(real, shown, node)]
    if not isinstance(node, dict):
        return []
    head, rest = pattern[0], pattern[1:]
    out: list[tuple[tuple, tuple, Any]] = []
    if head == "*":
        for k, v in node.items():
            if k != "$include":
                out.extend(_walk(v, rest, real + (k,), shown + (k,)))
    elif head in node:
        out.extend(_walk(node[head], rest, real + (head,), shown + (head,)))
    return out


def _sender_kind(key: str) -> str:
    if key == "*":
        return "any"
    prefix = key.split(":", 1)[0]
    return prefix if prefix in ("channel", "id", "e164", "username", "name") else "unknown_form"


def _applies_to(category: str, real: tuple, pattern: tuple[str, ...]) -> dict:
    if real[:1] == ("tools",) and len(real) > 2 and real[1] == "byProvider":
        return {"scope": "provider", "provider": real[2]}
    if real[:1] == ("tools",) and len(real) > 2 and real[1] == "toolsBySender":
        return {"scope": "sender_group", "sender_key_kind": _sender_kind(real[2]), "sender_key": "<withheld>" if real[2] != "*" else "*"}
    if real[:2] == ("agents", "entries"):
        return {"scope": "agent", "agent_key": real[2]}
    if real[:2] == ("agents", "defaults"):
        return {"scope": "agent_defaults"}
    if real[:1] == ("tools",):
        return {"scope": "global_tools"}
    if real[:1] == ("gateway",) and real[1:2] == ("nodes",):
        return {"scope": "gateway_nodes"}
    if real[:1] == ("gateway",):
        return {"scope": "gateway"}
    if real[:1] == ("nodeHost",):
        return {"scope": "node_host"}
    if real[:1] == ("plugins",):
        return {"scope": "plugins_global"}
    if real[:1] == ("skills",):
        return {"scope": "skills_global"}
    if real[:1] == ("security",):
        return {"scope": "install_policy"}
    return {"scope": "unspecified"}


def _display_parts(real: tuple, shown_extra: dict[int, str]) -> tuple:
    return tuple(shown_extra.get(i, p) for i, p in enumerate(real))


def _value(vtype: str, v: Any, path_str: str, red: Redactor) -> tuple[dict | None, dict | None]:
    """(값 필드들, 문제). 문제가 있으면 값은 저장하지 않고 자료형만 남긴다."""
    base, _, allowed = vtype.partition(":")
    if base == "bool":
        return ({"value_kind": "bool", "value": v}, None) if isinstance(v, bool) else (None, ("boolean", v))
    if base == "number":
        ok = isinstance(v, (int, float)) and not isinstance(v, bool)
        return ({"value_kind": "number", "value": v}, None) if ok else (None, ("number", v))
    if base == "str":
        if not isinstance(v, str):
            return None, ("string", v)
        rec = {"value_kind": "string", "value": red.sanitize_string(v, path_str)}
        if allowed:
            rec["documented_values"] = allowed.split(",")
            rec["value_documented"] = v in allowed.split(",")
        return rec, None
    if base == "list":
        if not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
            return None, ("array of string", v)
        items = [red.sanitize_string(x, f"{path_str}[{i}]") for i, x in enumerate(v[:MAX_LIST])]
        rec = {"value_kind": "string_list", "value": items, "count": len(v)}
        if len(v) > MAX_LIST:
            rec["truncated_at"] = MAX_LIST
        return rec, None
    if base == "args":
        if not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
            return None, ("array of string", v)
        return {"value_kind": "string_list", "value": red.sanitize_args(v[:MAX_LIST], path_str), "count": len(v)}, None
    if base == "count":   # 값이 개인 식별정보일 수 있어 개수만 남긴다
        if not (isinstance(v, list) and all(isinstance(x, (str, int)) for x in v)):
            return None, ("array of string", v)
        return {"value_kind": "count_only", "count": len(v), "values_withheld": True}, None
    if base == "keys":
        if not isinstance(v, dict):
            return None, ("object", v)
        return {"value_kind": "names_only", "names": [REDACTED if looks_like_secret_value(k) else k for k in list(v)[:MAX_LIST]], "values_withheld": True}, None
    if base == "path":   # 인증서·키 파일 경로: 선언 여부만 남긴다 (경로 문자열은 저장하지 않는다)
        return ({"value_kind": "path_declared", "value_withheld": True}, None) if isinstance(v, str) else (None, ("string", v))
    if base == "cred":
        kv = _value_kind(v)
        kind = kv["value_kind"]
        if kind == "literal":
            return {"value_kind": "credential", "credential": {"kind": "literal_withheld"}}, None   # 원문·길이·해시 없음
        if kind == "invalid_secret_ref":
            return {"value_kind": "credential", "credential": {"kind": "invalid_secret_ref", "problems": kv.get("problems")}}, ("secret_ref", v)
        if kind == "non_string":
            return None, ("string or SecretRef", v)
        cred: dict[str, Any] = {"kind": kind}
        if "ref" in kv:
            cred["ref"] = kv["ref"]
        if "ref_names" in kv:
            cred["ref_names"] = kv["ref_names"]
        if kv.get("default_value_withheld"):
            cred["default_value_withheld"] = True
        return {"value_kind": "credential", "credential": cred}, None
    return None, ("unsupported", v)


def collect_permission_auth(config_path: Path) -> dict:
    out: dict[str, Any] = {"source_path": str(config_path), "items": [], "issues": [], "unresolved": []}
    try:
        root = parse_config(read_config(config_path))
    except CollectionFailure as fail:
        out.update(status="failed", outcome=fail.outcome)
        out["issues"].append(_issue("error", fail.reason["code"], fail.reason["message"]))
        return out
    if not isinstance(root, dict):
        out.update(status="failed", outcome="root_not_object")
        out["issues"].append(_issue("error", "root_not_object", "설정 최상위가 객체가 아닙니다."))
        return out
    items: list[dict] = out["items"]
    issues: list[dict] = out["issues"]
    red = Redactor()

    def emit(category: str, real: tuple, shown: tuple, vtype: str, v: Any, doc: str, applies: dict) -> None:
        path_str = dotted_path(shown)
        fields, problem = _value(vtype, v, path_str, red)
        item: dict[str, Any] = {
            "ref": f"policy-item[{len(items)}]", "category": category, "origin": "config_declared",
            "config_path": path_str, "config_pointer": json_pointer(shown), "applies_to": applies, "doc_basis": doc,
        }
        if fields is not None:
            item.update(fields)
        else:
            item["value_kind"] = "invalid_type"
        if problem is not None:
            expected, bad = problem
            issues.append(_issue("warning", "field_type_invalid", f"{path_str}의 자료형이 {expected}가 아닙니다. 값은 저장하지 않았습니다.",
                                 field_path=path_str, expected=expected, actual=_type_name(bad)))
        # 인증정보 위치의 SecretRef 형식 오류가 아닌 SecretRef는 미해석 참조로 남긴다 (값은 읽지 않음)
        if vtype == "cred" and item.get("credential", {}).get("kind") == "secret_ref":
            out["unresolved"].append({"kind": "secret_ref", **item["credential"]["ref"], "field_path": path_str})
        if vtype == "cred" and item.get("credential", {}).get("ref_names"):
            for n in item["credential"]["ref_names"]:
                out["unresolved"].append({"kind": "env_var", "name": n, "field_path": path_str})
        items.append(item)

    for pattern, vtype, category, doc in SPEC:
        for real, shown, v in _walk(root, pattern, (), ()):
            extra: dict[int, str] = {}
            if pattern[:2] == ("tools", "toolsBySender"):
                extra[2] = f"<sender-key:{_sender_kind(real[2])}>"
            if pattern[:3] == ("tools", "elevated", "allowFrom"):
                pass  # 키는 채널 이름이다
            applies = _applies_to(category, real, pattern)
            emit(category, real, _display_parts(real, extra) if extra else shown, vtype, v, doc, applies)

    # MCP 서버의 인증 관련 선언: 설정 수집기와 같은 등록 영역·선언 위치 표기로 적용 대상을 연결한다.
    for label, reg in SUPPORTED_REGISTRY_PATHS.items():
        node: Any = root
        for p in reg:
            node = node.get(p) if isinstance(node, dict) else None
        if not isinstance(node, dict):
            continue
        masked = set(getattr(node, "masked_keys", []))
        for key, entry in node.items():
            if key == "$include" or not isinstance(entry, dict):
                continue
            decl = reg + (key,)
            applies = {"scope": "mcp_server", "registry_path": label, "registration_key": key,
                       "registration_key_redacted": key in masked, "declaration_path": dotted_path(decl), "declaration_pointer": json_pointer(decl),
                       "link_basis": "same_declaration_path_as_config_scan"}
            for sub, vtype in MCP_AUTH_SPEC:
                for real, shown, v in _walk(entry, sub, decl, decl):
                    emit("mcp_server_auth", real, shown, vtype, v, D_MCP, applies)

    # 이 모듈이 읽는 최상위 영역의 중복 키·$include만 문제로 본다 (채널 등 무관한 영역은 보고하지 않는다).
    areas = {p[0] for p, *_ in SPEC} | {r[0] for r in SUPPORTED_REGISTRY_PATHS.values()}

    def relevant(parts: tuple) -> bool:
        return not parts or parts[0] in areas

    for dup in _find_duplicate_keys(root, ()):
        head = dup.replace("[", ".").split(".")[0].strip('"')
        if not dup or dup == "(root)" or head in areas:
            issues.append(_issue("error", "duplicate_key", "같은 키가 여러 번 선언되어 마지막 값만 읽었습니다.", field_path=dup))
    for container, v in _find_includes(root):
        if relevant(container):
            out["unresolved"].append(_include_record(container, v, "이번 단계는 $include 파일을 읽지 않습니다. 정책이 다른 파일에 있을 수 있습니다."))
    for r in red.env_refs:
        out["unresolved"].append(r)
    out["redactions"] = red.redactions
    incomplete = any(i["severity"] == "error" for i in issues) or bool(out["unresolved"]) or any(i["code"] == "field_type_invalid" for i in issues)
    out["status"] = "partial" if incomplete else "complete"
    out["outcome"] = "items_read" if items else "no_declared_items"
    return out


def build_report(collected: dict) -> dict:
    items = collected["items"]
    by_cat: dict[str, int] = {}
    for i in items:
        by_cat[i["category"]] = by_cat.get(i["category"], 0) + 1
    return {
        "format": FORMAT_NAME, "format_version": FORMAT_VERSION,
        "format_status": ("스캐너 내부 개발용 초안입니다. 팀 공통 스키마가 아니며 집계 단위(Permission/Auth 자산의 묶음 기준)는 팀 협의 중이라 "
                          "확정하지 않았습니다. 원천 항목을 그대로 보존합니다. ref는 이 파일 안에서만 쓰는 이름입니다."),
        "producer": {"name": "agent-scope-asset-scanner", "version": __version__}, "generated_at": _now(),
        "basis": {"openclaw_version": "2026.9.6", "evidence": "패키지 문서(정적 읽기). docs/asset-collection.md 3장"},
        "source": {"source_path": collected["source_path"], "evidence_type": "static_file", "provided_by": "operator_selected_file"},
        "scope": {
            "method": "설정 파일의 문서화된 정책·인증 경로를 선언 값 그대로 수집 (해석·집계·실행 없음)",
            "not_collected": NOT_COLLECTED, "aggregation": "none",
            "note": ("items[]는 설정에 적힌 선언입니다. 허용/거부의 최종 결과, 기본값, 승인 상태는 계산하지 않았으며 선언이 없다는 것은 "
                     "정책이 없다는 뜻이 아닙니다(문서의 기본 동작이 적용될 수 있음). 인증정보 원문·길이·해시는 저장하지 않습니다."),
        },
        "collection": {"status": collected["status"], "outcome": collected["outcome"], "item_count": len(items), "by_category": by_cat},
        "items": items, "unresolved": collected["unresolved"], "issues": collected["issues"], "redactions": collected.get("redactions", []),
    }


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m asset_scanner.permission_auth",
                                description="OpenClaw 설정에서 Permission/Auth 선언을 원천 항목 단위로 수집합니다 (읽기 전용, 내부 개발용 초안).")
    p.add_argument("--config", required=True, type=Path, help="OpenClaw 설정 파일(JSON5)")
    p.add_argument("--output", required=True, type=Path, help="결과 JSON을 저장할 경로")
    return p


def main(argv: list[str] | None = None) -> int:
    _make_console_output_safe()
    args = _parser().parse_args(argv)
    if _same_file(args.config, args.output):
        print("오류: --output이 --config와 같은 파일입니다. 입력을 덮어쓰지 않습니다.", file=sys.stderr)
        return EXIT_OUTPUT_ERROR
    report = build_report(collect_permission_auth(args.config))
    report, normalized = normalize_for_output(report)
    if normalized:
        report["collection"]["output_text_normalizations"] = normalized
    try:
        write_json_atomic(args.output, report)
    except OutputError as exc:
        print(f"오류: 결과 파일을 저장하지 못했습니다 ({exc.kind}). 기존 결과 파일은 바꾸지 않았습니다.", file=sys.stderr)
        return EXIT_OUTPUT_ERROR
    c = report["collection"]
    print("Permission/Auth 선언 수집 결과 (설정 파일 읽기 전용, 값 해석·집계 없음)")
    print(f"수집 상태: {c['status']} ({c['outcome']}), 항목 {c['item_count']}개")
    for cat, n in sorted(c["by_category"].items()):
        print(f"  - {cat}: {n}")
    for u in report["unresolved"]:
        print(f"  미해석: {u.get('kind')}")
    print(f"결과 저장: {args.output}")
    return EXIT_BY_STATUS[c["status"]]


if __name__ == "__main__":
    sys.exit(main())
