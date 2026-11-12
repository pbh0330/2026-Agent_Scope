"""저장된 설정 수집 결과와 저장된 Tool 카탈로그 결과를 서버 단위로 연결한다 (내부 개발용 초안).

    python -m asset_scanner.linking \
        --config-scan gw=<설정 수집 결과 JSON> [--config-scan node1=<...>] \
        --catalog obs1=<Tool 카탈로그 결과 JSON> [--catalog obs2=<...>] \
        [--subject gw=gateway,id=<식별값>] --output <연결 결과 JSON>

이 모듈이 하는 일은 **이미 저장된 스캐너 결과 JSON을 읽는 것뿐**이다. 설정 속 명령 실행, 서버 접속,
tools/list·tools/call 요청, 환경변수 해석, $include 읽기를 하지 않는다. 입력 파일 외의 파일도 읽지 않는다.

연결 규칙 (보수적)
- 연결 근거는 카탈로그 서버 항목의 `config_link` 세 값이 **모두** 설정 수집 결과와 맞을 때뿐이다:
  `config_scan_ref`(실행 때 `--config-scan 라벨=경로`로 붙인 라벨 중 하나), `registry_path`, `registration_key`.
  참조가 가리킨 설정 수집 결과 안에서 같은 등록 영역·같은 등록키의 선언이 정확히 하나여야 `linked`다.
  등록키와 등록 영역이 우연히 같은 다른 설정 수집 결과는 후보(`key_region_matches`)로만 보여 주고 연결하지 않는다.
- 참조 누락·잘못된 형식·알 수 없는 라벨·중복 라벨·영역 불일치는 각각 사유를 남기고 추측하지 않는다.
- 물리 파일 경로는 연결 근거도, 자산 식별값도 아니다. 속성으로만 기록한다.
- 선언 주체의 종류·식별값은 `--subject`로 사용자가 입력한 것만 `user_provided`로 보존한다. 스캐너는 그 값을
  확인하지 않으며(`verified_by_scanner: false`), 입력이 없으면 식별값은 `not_collected`로 남기고 만들지 않는다.
- 같은 선언을 가리키는 관측이 **서로 다른 카탈로그 입력**에 있으면 각각 별개의 관측으로 보존한다(합치지 않음).
  **같은 카탈로그 입력 안에서** 두 서버가 같은 선언을 가리키면 같은 서버의 중복인지 다른 서버인지 알 수 없어 모두 보류한다.
- 같은 이름의 서버·Tool은 어떤 경우에도 합치지 않는다.
- `linked`는 입력 자료 사이의 연결이다. 서버 기동·Agent 노출·호출 가능을 뜻하지 않는다.
- 공통 자산 ID·해시·공통 스키마는 만들지 않는다. 출력의 `*_ref`는 이 파일 안에서만 쓰는 이름이다.
- 설정 대조·수집률·누락 계산은 하지 않는다. 선언에 Tool 근거가 없다는 것은 Tool 0개가 아니다.

종료 코드: 0 모든 카탈로그 서버가 모호함 없이 연결됨, 1 부분(모호·미연결·입력 불완전), 2 인자 오류, 3 실패, 4 저장 실패.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .cli import _make_console_output_safe, _same_file
from .output import OutputError, normalize_for_output, write_json_atomic
from .redaction import Redactor, looks_like_secret_value
from .report import FORMAT_NAME as CONFIG_FORMAT_NAME
from .tools_catalog import FORMAT_NAME as CATALOG_FORMAT_NAME
from .tools_catalog import _find_duplicates, _read_capture, _safe_short, _seg, _text

IDENTITY_FORMAT_NAME = "agent-scope.scanner.gateway-node-identity"   # node_gateway_identity 모듈의 결과 형식
IDENTITY_ORIGINS = ("observed_from_stored_command_output", "observed_from_direct_query")
FORMAT_NAME = "agent-scope.scanner.server-tool-links"
FORMAT_VERSION = "0.1.0-draft"

EXIT_BY_STATUS = {"complete": 0, "partial": 1, "failed": 3}
EXIT_OUTPUT_ERROR = 4
MAX_INPUTS = 20
MAX_SUBJECT_ID_CHARS = 200
SUBJECT_KINDS = ("gateway", "node", "plugin")
_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_REDACTED_NAME_RE = re.compile(r"^<redacted")

NOT_VERIFIED = [
    "live_server_query",            # 서버에 접속하지 않았다
    "runtime_registration",         # 선언이 실제 런타임에 등록됐는지
    "declaring_subject_identity",   # 사용자가 입력한 주체 종류·식별값을 스캐너가 확인하지 않았다
    "exposure",
    "callability",
    "config_vs_tools_comparison",   # 설정 대조·수집률·누락 계산은 보류
    "common_asset_id",
    "common_schema",
]

# 입력이 없을 때만 쓰는 추정 힌트. 사용자 입력이 있으면 입력이 우선하고 추정과 다르면 충돌로 표시한다.
_SUBJECT_HINTS = {
    "mcp.servers": ("gateway", "registry_path=mcp.servers (README·field-mapping의 Gateway 설정 영역)"),
    "nodeHost.mcp.servers": ("node", "registry_path=nodeHost.mcp.servers (OpenClaw 2026.9.6 docs/nodes/mcp-and-skills.md)"),
}
_PLUGIN_HINT = ("plugin", "source_kind=openclaw_plugin_manifest (Issue #10 의견: 플러그인 등록 서버의 선언 주체는 Plugin)")


class _InputFailure(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---- 입력 읽기 -------------------------------------------------------------------

def _load(path: Path, expected_format: str, label: str) -> dict:
    data, failure = _read_capture(path)
    if failure is not None:
        raise _InputFailure(f"{label}_{failure['code']}", failure["message"])
    if not isinstance(data, dict) or data.get("format") != expected_format:
        raise _InputFailure(f"{label}_format_mismatch", f'{label} 입력의 format이 "{expected_format}"가 아닙니다.')
    if not isinstance(data.get("servers"), list) or not isinstance(data.get("collection"), dict):
        raise _InputFailure(f"{label}_invalid_structure", f"{label} 입력에 servers 배열 또는 collection 객체가 없습니다.")
    return data


def _input_duplicates(data: dict) -> list[str]:
    """입력 파일 안의 중복 키 위치. 스캐너가 쓴 결과에는 없어야 하므로, 있으면 손으로 바뀐 입력으로 본다."""
    found: list[tuple[str, list[str]]] = []
    try:
        _find_duplicates(data, "", found)
    except RecursionError:
        return ["(nesting_too_deep)"]
    return [p for p, _ in found][:20]


def _is_redacted_name(value: str) -> bool:
    return bool(_REDACTED_NAME_RE.match(value))


def _norm_inputs(items: Any) -> list[tuple[str | None, Path]]:
    """`Path`, `(라벨, Path)` 또는 그 목록을 (라벨 또는 None, Path) 목록으로 만든다."""
    if isinstance(items, (str, Path)) or (isinstance(items, tuple) and len(items) == 2 and not isinstance(items[0], (tuple, list))
                                          and isinstance(items[1], (str, Path))):
        items = [items]
    out: list[tuple[str | None, Path]] = []
    for it in items:
        if isinstance(it, tuple):
            out.append((it[0], Path(it[1])))
        else:
            out.append((None, Path(it)))
    return out


def _label_ok(label: Any) -> bool:
    """라벨로 쓸 수 있는가. 형식을 통과해도 비밀값처럼 보이면(토큰 패턴·URL 자격증명·엔트로피) 거부한다.

    라벨은 입력을 잇는 이름이지 결과에 복사할 값이 아니다. 거부한 라벨은 원문을 출력하지 않고 어떤 연결에도 쓰지 않는다.
    """
    if not isinstance(label, str) or not _LABEL_RE.match(label):
        return False
    red = Redactor()
    return _text(red, label, "label") == label and not red.redactions and not looks_like_secret_value(label)


def _label_status(label: str | None, counts: dict[str, int]) -> str:
    if label is None:
        return "not_assigned"
    if not _label_ok(label):
        return "invalid"
    return "duplicate" if counts.get(label, 0) > 1 else "ok"


def _label_counts(labels: list[str | None]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for lb in labels:
        if _label_ok(lb):
            counts[lb] = counts.get(lb, 0) + 1
    return counts


def _out_label(label: Any, status: str) -> str | None:
    """결과에 쓸 라벨(출력용 값). 유효한 라벨만 내보내고 거부·미부여 라벨은 None이다. 내부 매칭용 원문과 분리돼 있다."""
    return label if status in ("ok", "duplicate") and isinstance(label, str) else None


# ---- 선언 주체 입력 --------------------------------------------------------------------

def _process_subject_inputs(subjects: list[dict], scan_labels: list[str | None], red: Redactor) -> tuple[list[dict], dict[str, dict]]:
    """사용자가 입력한 선언 주체 정보를 검사한다. (입력별 결과, 적용 가능한 라벨 → 입력) 을 돌려준다.

    같은 라벨에 입력이 둘 이상이면 어느 쪽도 쓰지 않는다. 식별값은 어떤 규칙으로도 만들거나 바꾸지 않는다.
    """
    counts = _label_counts(scan_labels)
    per_label: dict[str, int] = {}
    for s in subjects:
        lb = s.get("scan_label")
        if isinstance(lb, str):
            per_label[lb] = per_label.get(lb, 0) + 1
    records: list[dict] = []
    applicable: dict[str, dict] = {}
    for i, s in enumerate(subjects):
        lb, kind, sid = s.get("scan_label"), s.get("kind"), s.get("id")
        problems: list[str] = []
        if not _label_ok(lb):
            problems.append("scan_label_invalid")
        elif counts.get(lb, 0) == 0:
            problems.append("unknown_scan_label")
        elif counts[lb] > 1:
            problems.append("scan_label_duplicate")
        if isinstance(lb, str) and per_label.get(lb, 0) > 1:
            problems.append("duplicate_subject_input")
        if kind is not None and kind not in SUBJECT_KINDS:
            problems.append("kind_invalid")
        if sid is not None and (not isinstance(sid, str) or sid.strip() == "" or len(sid) > MAX_SUBJECT_ID_CHARS):
            problems.append("id_invalid")
        if kind is None and sid is None:
            problems.append("empty_subject_input")
        rec: dict[str, Any] = {
            "input_index": i,
            "scan_label": lb if _label_ok(lb) else None,  # 거부한 라벨은 원문을 내보내지 않는다
            "kind": kind if kind in SUBJECT_KINDS else None,
            "id_provided": isinstance(sid, str) and sid.strip() != "",
            "status": "applied" if not problems else "ignored",
            "problems": problems,
        }
        records.append(rec)
        if not problems:
            # 식별값은 정규화·해시하지 않는다. 알려진 토큰·URL 자격증명만 가린다(deviceId 같은 긴 hex는 엔트로피로 가리지 않는다).
            safe_id = red.sanitize_text(sid, "subject.id", check_entropy=False) if isinstance(sid, str) else None
            applicable[lb] = {"kind": kind, "id": safe_id}
    return records, applicable


def _process_observed_identities(items: list[dict], scan_labels: list[str | None]) -> tuple[list[dict], dict[str, dict]]:
    """`node_gateway_identity`가 저장한 관측 identity를 설정 수집 결과(라벨)에 붙일 수 있는지 검사한다.

    사용자 입력(--subject)과 다른 출처의 값이다. 한 파일에 identity가 정확히 하나이고 deviceId를 원본으로 읽은 경우만 쓴다.
    같은 라벨에 둘 이상이면 어느 쪽도 쓰지 않는다. 값은 만들거나 바꾸지 않는다.
    """
    counts = _label_counts(scan_labels)
    per_label: dict[str, int] = {}
    for it in items:
        lb = it.get("scan_label")
        if isinstance(lb, str):
            per_label[lb] = per_label.get(lb, 0) + 1
    records: list[dict] = []
    applicable: dict[str, dict] = {}
    for i, it in enumerate(items):
        lb = it.get("scan_label")
        problems: list[str] = []
        if not _label_ok(lb):
            problems.append("scan_label_invalid")
        elif counts.get(lb, 0) == 0:
            problems.append("unknown_scan_label")
        elif counts[lb] > 1:
            problems.append("scan_label_duplicate")
        if isinstance(lb, str) and per_label.get(lb, 0) > 1:
            problems.append("duplicate_observed_identity_input")
        data, failure = _read_capture(it["path"])
        chosen: dict | None = None
        if failure is not None:
            problems.append(f"identity_{failure['code']}")
        elif not isinstance(data, dict) or data.get("format") != IDENTITY_FORMAT_NAME:
            problems.append("identity_format_mismatch")
        else:
            ids = data.get("identities")
            if not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], dict):
                problems.append("identity_report_not_single")
            else:
                chosen = ids[0]
                did = chosen.get("device_id") if isinstance(chosen.get("device_id"), dict) else {}
                if chosen.get("kind") not in ("gateway", "node") or did.get("status") != "as_reported" or not isinstance(did.get("original_value"), str):
                    problems.append("device_id_not_read")
                elif chosen.get("origin") not in IDENTITY_ORIGINS:
                    problems.append("identity_origin_invalid")      # 손으로 바뀐 파일: 출처를 알 수 없는 값은 쓰지 않는다
        records.append({"input_index": i, "scan_label": lb if _label_ok(lb) else None,
                        "status": "applied" if not problems else "ignored", "problems": problems})
        if not problems and chosen is not None:
            obs = chosen.get("observation") if isinstance(chosen.get("observation"), dict) else {}
            pk = chosen.get("public_key") if isinstance(chosen.get("public_key"), dict) else {}
            applicable[lb] = {
                "origin": chosen["origin"],      # observed_from_stored_command_output | observed_from_direct_query (입력 파일에 적힌 출처 그대로)
                "kind": chosen["kind"],
                "device_id": {"original_value": chosen["device_id"]["original_value"], "status": "as_reported"},
                "public_key_status": pk.get("status") if isinstance(pk.get("status"), str) else None,
                "command": obs.get("command") if isinstance(obs.get("command"), str) else None,
                "observed_at": obs.get("observed_at") if isinstance(obs.get("observed_at"), str) else None,
                "observed_at_origin": obs.get("observed_at_origin") if isinstance(obs.get("observed_at_origin"), str) else None,
                "file_modified_at": obs.get("file_modified_at") if isinstance(obs.get("file_modified_at"), str) else None,
                "source_kind": obs.get("source_kind") if isinstance(obs.get("source_kind"), str) else None,
                "installed_version": ((obs.get("installed_version") or {}).get("version")
                                      if isinstance(obs.get("installed_version"), dict) else None),
                "verified_by_scanner": False,
            }
    return records, applicable


def _subject_for(source: dict, provided: dict | None, observed: dict | None = None) -> dict:
    kind_hint, basis = (_PLUGIN_HINT if source.get("source_kind") == "openclaw_plugin_manifest"
                        else _SUBJECT_HINTS.get(source.get("registry_path"), (None, "등록 영역으로 주체를 추정할 수 없음")))
    provided = provided or {}
    p_kind, p_id = provided.get("kind"), provided.get("id")
    if p_kind:
        kind, origin, conflict = p_kind, "user_provided", bool(kind_hint and kind_hint != p_kind)
        k_basis = "사용자 입력(--subject). 스캐너는 확인하지 않음"
    elif kind_hint:
        kind, origin, conflict, k_basis = kind_hint, "inferred_unverified", False, basis
    else:
        kind, origin, conflict, k_basis = None, "unknown", False, basis
    subject = {
        "kind": kind,
        "kind_origin": origin,
        "kind_basis": k_basis,
        "inferred_kind_from_source": kind_hint,
        "kind_conflicts_with_inference": conflict,
        "id": p_id if p_id else None,
        "id_origin": "user_provided" if p_id else "not_collected",
        "verified_by_scanner": False,
    }
    if observed is not None:
        # 저장된 명령 출력에서 관측한 identity. 사용자 입력(id, id_origin)을 덮어쓰지 않고 별도 필드에 둔다.
        subject["observed_identity"] = {
            **observed,
            "id_conflicts_with_user_provided": (p_id != observed["device_id"]["original_value"]) if p_id else None,
            "kind_conflicts_with_subject_kind": (kind != observed["kind"]) if kind else None,
        }
    return subject


# ---- 선언 목록 ---------------------------------------------------------------------

def _pointer_segments(pointer: Any) -> list[str] | None:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        return None
    return [s.replace("~1", "/").replace("~0", "~") for s in pointer[1:].split("/")]


def _build_declarations(scans: list[dict], labels: list[str | None], label_counts: dict[str, int],
                        subjects: dict[str, dict], red: Redactor,
                        observed: dict[str, dict] | None = None) -> tuple[list[dict], list[dict]]:
    """(선언 목록, 입력별 요약). 같은 이름의 선언도 합치지 않고 입력·위치별로 따로 둔다."""
    declarations: list[dict] = []
    summaries: list[dict] = []
    for i, scan in enumerate(scans):
        source = scan.get("source") if isinstance(scan.get("source"), dict) else {}
        col = scan["collection"]
        label = labels[i]
        lstatus = _label_status(label, label_counts)
        registry_path = source.get("registry_path") if isinstance(source.get("registry_path"), str) else None
        dup_registration_keys = {r.get("field_path") for r in col.get("reasons", [])
                                 if isinstance(r, dict) and r.get("code") == "duplicate_registration_key"}
        provided = subjects.get(label) if lstatus == "ok" else None
        subject = _subject_for(source, provided, (observed or {}).get(label) if lstatus == "ok" else None)
        summary = {
            "input_index": i,
            "label": _out_label(label, lstatus),
            "label_status": lstatus,
            "source_kind": _text(red, source["source_kind"], "source_kind") if isinstance(source.get("source_kind"), str) else None,
            "registry_path": _text(red, registry_path, "registry_path") if registry_path else None,
            # 물리 경로는 속성일 뿐 연결 근거·식별값이 아니다.
            "physical_source_path": _text(red, source["source_path"], "source_path") if isinstance(source.get("source_path"), str) else None,
            "collection_status": col.get("status"),
            "collection_outcome": col.get("outcome"),
            "declaring_subject": subject,
            "declaration_count": 0,
            "input_duplicate_keys": _input_duplicates(scan),
        }
        for j, srv in enumerate(scan["servers"]):
            if not isinstance(srv, dict):
                continue
            key = srv.get("registration_key")
            if not isinstance(key, str):
                continue
            seg = _pointer_segments(srv.get("declaration_pointer"))
            decl_path = srv.get("declaration_path")
            key_redacted = bool(srv.get("registration_key_redacted")) or _is_redacted_name(key)
            declared = srv.get("declared") if isinstance(srv.get("declared"), dict) else {}
            declarations.append({
                "declaration_ref": f"config-scan[{i}]/servers[{j}]",  # 이 파일 안에서만 쓰는 참조. 공통 ID가 아니다.
                "input_index": i,
                "config_scan_label": summary["label"],
                "registry_path": summary["registry_path"],
                "registration_key": _text(red, key, "registration_key"),
                "registration_key_redacted": key_redacted,
                "declaring_subject": subject,
                "logical_location": {
                    "source_kind": summary["source_kind"],
                    "registry_path": summary["registry_path"],
                    "key_path": [_seg(s) for s in seg] if seg else None,
                    "declaration_path": _safe_short(red, decl_path, "declaration_path") if isinstance(decl_path, str) else None,
                },
                "physical_source_path": summary["physical_source_path"],
                "declaration_collection_status": srv.get("collection_status"),
                "declared_enabled": declared.get("enabled") if isinstance(declared.get("enabled"), bool) else None,
                "key_declared_more_than_once_in_source": isinstance(decl_path, str) and decl_path in dup_registration_keys,
                "tool_evidence": "not_supplied",  # Tool 근거를 받지 못한 것이며 Tool 0개라는 뜻이 아니다
                "linked_observations": [],        # 같은 선언에 대한 관측(카탈로그 입력별)을 합치지 않고 나열한다
            })
            summary["declaration_count"] += 1
        summaries.append(summary)
    return declarations, summaries


# ---- 연결 ----------------------------------------------------------------------------

def _has_name_alteration(tool: Any) -> bool:
    red = tool.get("redactions") if isinstance(tool, dict) and isinstance(tool.get("redactions"), list) else []
    return any(isinstance(r, dict) and r.get("field_path") == "name" for r in red)


def _tool_trace(tool: Any, index_in_server: int, collision_indexes: set[int], other_servers: dict[str, set[int]],
                server_index: int, red: Redactor) -> dict:
    definition = tool.get("definition") if isinstance(tool, dict) and isinstance(tool.get("definition"), dict) else {}
    name = definition.get("name")
    entry: dict[str, Any] = {
        "internal_ref": tool.get("internal_ref") if isinstance(tool, dict) else None,
        "tool_index": index_in_server,
    }
    if not isinstance(name, str) or name == "":
        entry.update(original_name=None, original_name_status="missing")
    elif _has_name_alteration(tool) or _is_redacted_name(name):
        # 가림 처리된 이름은 원래 이름이 아니다. 다른 Tool과 같은 이름으로 취급하지 않는다.
        entry.update(original_name=None, original_name_status="withheld_by_redaction")
    else:
        entry.update(original_name=_safe_short(red, name, "tool.name"), original_name_status="as_reported")
        if index_in_server in collision_indexes:
            entry["name_repeated_in_server"] = True
        elsewhere = sorted(other_servers.get(name, set()) - {server_index})
        if elsewhere:
            entry["same_name_in_other_catalog_servers"] = elsewhere
    entry["definition_altered"] = bool(tool.get("definition_altered")) if isinstance(tool, dict) else None
    return entry


def _collision_indexes(server: dict) -> set[int]:
    out: set[int] = set()
    for issue in server.get("issues", []):
        if isinstance(issue, dict) and issue.get("code") == "duplicate_tool_name_in_server":
            idxs = issue.get("tool_indexes")
            if isinstance(idxs, list):
                out.update(i for i in idxs if isinstance(i, int))
    return out


def _tool_names_by_server(catalog_servers: list[dict]) -> dict[str, set[int]]:
    names: dict[str, set[int]] = {}
    for s in catalog_servers:
        for t in s.get("tools", []) if isinstance(s.get("tools"), list) else []:
            d = t.get("definition") if isinstance(t, dict) else None
            n = d.get("name") if isinstance(d, dict) else None
            if isinstance(n, str) and n and not _is_redacted_name(n) and not _has_name_alteration(t):
                names.setdefault(n, set()).add(s.get("server_index"))
    return names


def _resolve(link_in: dict, declarations: list[dict], scans: list[dict]) -> dict:
    """연결 판정. 근거가 모자라면 후보를 고르지 않고 사유만 돌려준다.

    반환: {"link_status", "reason", "declaration_ref", "candidates", ["key_region_matches"]}
    """
    def out(status: str, reason: str, decl: str | None = None, candidates: list[str] | None = None, **extra: Any) -> dict:
        return {"link_status": status, "reason": reason, "declaration_ref": decl, "candidates": candidates or [], **extra}

    key, reg = link_in.get("registration_key"), link_in.get("registry_path")
    if not isinstance(key, str) or key == "":
        return out("unlinked", "no_link_basis")
    if _is_redacted_name(key):
        return out("unlinked", "registration_key_redacted")
    if not isinstance(reg, str) or reg == "":
        return out("unlinked", "registry_path_missing")

    by_key_region = [d["declaration_ref"] for d in declarations
                     if d["registration_key"] == key and d["registry_path"] == reg and not d["registration_key_redacted"]]
    if "config_scan_ref_invalid_type" in link_in or (isinstance(link_in.get("config_scan_ref"), str) and link_in["config_scan_ref"] == ""):
        return out("unlinked", "config_scan_ref_invalid", key_region_matches=by_key_region)
    ref = link_in.get("config_scan_ref")
    if ref is None:
        # 같은 등록키·등록 영역이 우연히 일치하는 것만으로는 잇지 않는다.
        return out("unlinked", "config_scan_ref_missing", key_region_matches=by_key_region)

    holders = [s for s in scans if s["match_label"] is not None and s["match_label"] == ref]
    if not holders:
        return out("unlinked", "config_scan_ref_unknown", key_region_matches=by_key_region)
    if len(holders) > 1:
        return out("ambiguous", "config_scan_ref_duplicate", candidates=[f"config-scan[{s['input_index']}]" for s in holders])
    scan = holders[0]
    if scan["registry_path"] != reg:
        return out("unlinked", "registry_path_mismatch_with_referenced_scan")
    matches = [d for d in declarations
               if d["input_index"] == scan["input_index"] and d["registration_key"] == key
               and d["registry_path"] == reg and not d["registration_key_redacted"]]
    if not matches:
        return out("unlinked", "no_matching_declaration", referenced_scan_status=scan["collection_status"])
    if len(matches) > 1:
        return out("ambiguous", "multiple_matching_declarations", candidates=[m["declaration_ref"] for m in matches])
    m = matches[0]
    if m["key_declared_more_than_once_in_source"]:
        # 설정 수집기는 같은 등록키가 여러 번 선언되면 마지막 항목만 남긴다. 입력이 가리킨 선언이 그것인지 알 수 없다.
        return out("ambiguous", "declaration_key_duplicated_in_source", candidates=[m["declaration_ref"]])
    return out("linked", "config_scan_ref_registration_key_and_registry_path_match", m["declaration_ref"], [m["declaration_ref"]],
               basis=["config_scan_ref", "registry_path", "registration_key"])


def _link_server(server: dict, cat_index: int, cat_label: str | None, declarations: list[dict], scans: list[dict],
                 names: dict[str, set[int]], red: Redactor) -> dict:
    idx = server.get("server_index")
    link_in = server.get("config_link") if isinstance(server.get("config_link"), dict) else {}
    ref = server.get("server_ref")
    claimed = {k: (_text(red, link_in[k], k) if isinstance(link_in.get(k), str) else None)
               for k in ("registration_key", "registry_path", "config_scan_ref")}
    if "config_scan_ref_invalid_type" in link_in:
        claimed["config_scan_ref_invalid_type"] = _text(red, str(link_in["config_scan_ref_invalid_type"]), "config_scan_ref_invalid_type")
    safe_link_in = {**link_in, **{k: v for k, v in claimed.items() if k in ("registration_key", "registry_path", "config_scan_ref")}}
    entry: dict[str, Any] = {
        "catalog_input_index": cat_index,
        "catalog_label": cat_label,
        "catalog_server_index": idx,
        "server_ref": _text(red, ref, "server_ref") if isinstance(ref, str) else None,
        "server_ref_kind": server.get("server_ref_kind"),
        "catalog_collection_status": server.get("collection_status"),
        "catalog_outcome": server.get("outcome"),
        "claimed_link": claimed,
    }
    entry.update(_resolve(safe_link_in, declarations, scans))
    tools = server.get("tools") if isinstance(server.get("tools"), list) else []
    collisions = _collision_indexes(server)
    entry["tool_count_reported"] = server.get("tool_count")
    entry["tools"] = [_tool_trace(t, i, collisions, names, idx, red) for i, t in enumerate(tools)]
    return entry


def _apply_trace(link: dict, declarations_by_ref: dict[str, dict], scans: list[dict]) -> None:
    """연결된 항목에는 선언 주체·논리 위치·등록키·참조한 설정 수집 결과를 한곳에 모아 Tool 이름까지 추적하게 한다."""
    decl = declarations_by_ref.get(link.get("declaration_ref") or "")
    if decl is None:
        link["trace"] = None
        return
    scan = scans[decl["input_index"]]
    link["trace"] = {
        "config_scan": {"input_index": scan["input_index"], "label": scan["label"]},
        "declaring_subject": decl["declaring_subject"],
        "logical_location": decl["logical_location"],
        "registration_key": decl["registration_key"],
        "declared_enabled": decl["declared_enabled"],
        "declaration_collection_status": decl["declaration_collection_status"],
        "physical_source_path": decl["physical_source_path"],
        "physical_path_is_identity": False,
    }


def link_scans(config_scans: Any, catalogs: Any, subjects: list[dict] | None = None,
               observed_identities: list[dict] | None = None) -> dict:
    """저장된 결과를 연결한다.

    config_scans / catalogs: 경로, `(라벨, 경로)`, 또는 그 목록. 라벨은 카탈로그의 `config_link.config_scan_ref`가 가리키는 이름이다.
    subjects: `{"scan_label", "kind", "id"}` 목록. 사용자가 입력한 선언 주체 정보이며 스캐너가 확인한 것이 아니다.
    observed_identities: `{"scan_label", "path"}` 목록. `node_gateway_identity` 결과 파일(정확히 하나의 identity)을 설정 수집 결과(라벨)에
    붙인다. `--subject`와 별도 필드(`declaring_subject.observed_identity`)에 두며 입력이 없으면 출력에 아무 필드도 더하지 않는다.
    """
    red = Redactor()
    cfg_inputs = _norm_inputs(config_scans)
    cat_inputs = _norm_inputs(catalogs)
    subjects = list(subjects or [])
    failure: dict | None = None
    scans: list[dict] = []
    cats: list[dict] = []
    try:
        for _, p in cfg_inputs:
            scans.append(_load(p, CONFIG_FORMAT_NAME, "config_scan"))
        for _, p in cat_inputs:
            cats.append(_load(p, CATALOG_FORMAT_NAME, "catalog"))
    except _InputFailure as exc:
        failure = {"code": exc.code, "message": exc.message}

    result: dict[str, Any] = {"declarations": [], "links": [], "inputs": {"config_scans": [], "catalogs": [], "subject_inputs": []}}
    if failure is not None:
        result["collection"] = {"status": "failed", "outcome": failure["code"], "reasons": [failure], "counts": None}
        return result

    scan_labels = [lb for lb, _ in cfg_inputs]
    cat_labels = [lb for lb, _ in cat_inputs]
    scan_counts = _label_counts(scan_labels)
    cat_counts = _label_counts(cat_labels)
    subject_records, applicable = _process_subject_inputs(subjects, scan_labels, red)
    observed_records, observed_applicable = _process_observed_identities(list(observed_identities or []), scan_labels)
    declarations, summaries = _build_declarations(scans, scan_labels, scan_counts, applicable, red, observed_applicable)
    # 매칭용 값(match_label)과 출력용 값(label)을 분리한다. 매칭용은 검사를 통과한 라벨만 갖고 결과에는 나가지 않는다.
    scan_view = [{**s, "match_label": scan_labels[s["input_index"]] if s["label_status"] in ("ok", "duplicate") else None}
                 for s in summaries]

    links: list[dict] = []
    cat_summaries: list[dict] = []
    for ci, cat in enumerate(cats):
        servers = [s for s in cat["servers"] if isinstance(s, dict)]
        names = _tool_names_by_server(servers)
        label = cat_labels[ci]
        links_here = [_link_server(s, ci, _out_label(label, _label_status(label, cat_counts)),
                                   declarations, scan_view, names, red) for s in servers]
        links.extend(links_here)
        cat_col = cat["collection"]
        cat_summaries.append({
            "input_index": ci,
            "label": _out_label(label, _label_status(label, cat_counts)),
            "label_status": _label_status(label, cat_counts),
            "format": cat.get("format"),
            "source": cat.get("source") if isinstance(cat.get("source"), dict) else None,
            "collection_status": cat_col.get("status"),
            "collection_outcome": cat_col.get("outcome"),
            "server_count": len(servers),
            "input_duplicate_keys": _input_duplicates(cat),
        })

    by_ref = {d["declaration_ref"]: d for d in declarations}
    # 같은 카탈로그 입력 안에서 둘 이상의 서버가 같은 선언을 가리키면 모두 보류한다.
    claims: dict[tuple[int, str], list[dict]] = {}
    for ln in links:
        if ln["link_status"] == "linked":
            claims.setdefault((ln["catalog_input_index"], ln["declaration_ref"]), []).append(ln)
    for (_, ref), group in claims.items():
        if len(group) > 1:
            for ln in group:
                ln.update(link_status="ambiguous", reason="declaration_claimed_by_multiple_catalog_servers",
                          candidates=[ref], declaration_ref=None, basis=None)
    for ln in links:
        if ln["link_status"] == "linked":
            by_ref[ln["declaration_ref"]]["linked_observations"].append(
                {"catalog_input_index": ln["catalog_input_index"], "catalog_server_index": ln["catalog_server_index"]})
        elif ln["link_status"] == "ambiguous":
            for c in ln["candidates"]:
                if c in by_ref:
                    by_ref[c].setdefault("ambiguous_observations", []).append(
                        {"catalog_input_index": ln["catalog_input_index"], "catalog_server_index": ln["catalog_server_index"]})
        _apply_trace(ln, by_ref, scan_view)

    result["inputs"] = {"config_scans": summaries, "catalogs": cat_summaries, "subject_inputs": subject_records}
    if observed_identities:   # 입력을 준 경우에만 키를 더한다 (기존 출력 형태 유지)
        result["inputs"]["observed_identity_inputs"] = observed_records
    result["declarations"] = declarations
    result["links"] = links

    reasons: list[dict] = []
    counts = {"catalog_inputs": len(cats), "catalog_servers": len(links),
              "linked": sum(1 for x in links if x["link_status"] == "linked"),
              "ambiguous": sum(1 for x in links if x["link_status"] == "ambiguous"),
              "unlinked": sum(1 for x in links if x["link_status"] == "unlinked"),
              "declarations": len(declarations)}
    if counts["ambiguous"]:
        reasons.append({"code": "ambiguous_links", "message": "후보를 하나로 정할 수 없는 연결이 있습니다. links[].reason을 확인하세요."})
    if counts["unlinked"]:
        reasons.append({"code": "unlinked_catalog_servers", "message": "연결 근거가 없거나 일치하는 선언이 없는 카탈로그 서버가 있습니다. links[].reason을 확인하세요."})
    for s in summaries:
        if s["label_status"] in ("invalid", "duplicate"):
            reasons.append({"code": "config_scan_label_problem", "input_index": s["input_index"], "label_status": s["label_status"],
                            "message": "설정 수집 결과의 라벨이 올바르지 않거나 중복돼 이 라벨을 가리키는 연결은 보류했습니다."})
        if s["collection_status"] != "complete":
            reasons.append({"code": "config_scan_not_complete", "input_index": s["input_index"],
                            "message": "이 설정 수집 결과가 완전하지 않아 선언이 더 있거나 달랐을 수 있습니다. 일치 선언이 없다는 사실은 선언이 없다는 뜻이 아닙니다."})
        if s["input_duplicate_keys"]:
            reasons.append({"code": "duplicate_key_in_input", "input": "config_scan", "input_index": s["input_index"],
                            "message": "입력 JSON에 같은 키가 중복돼 마지막 값만 읽었습니다."})
        if s["declaring_subject"]["kind_conflicts_with_inference"]:
            reasons.append({"code": "subject_kind_conflict", "input_index": s["input_index"],
                            "message": "사용자가 입력한 선언 주체 종류가 등록 영역·원천 종류에서 추정한 값과 다릅니다. 입력을 보존했고 어느 쪽도 확인하지 않았습니다."})
    for c in cat_summaries:
        if c["label_status"] in ("invalid", "duplicate"):
            reasons.append({"code": "catalog_label_problem", "input_index": c["input_index"], "label_status": c["label_status"],
                            "message": "카탈로그 입력의 라벨이 올바르지 않거나 중복됩니다."})
        if c["collection_status"] != "complete":
            reasons.append({"code": "catalog_not_complete", "input_index": c["input_index"],
                            "message": "Tool 카탈로그 수집이 완전하지 않습니다. tools[]는 읽은 항목일 뿐 서버의 전체 Tool이 아닙니다."})
        if c["input_duplicate_keys"]:
            reasons.append({"code": "duplicate_key_in_input", "input": "catalog", "input_index": c["input_index"],
                            "message": "카탈로그 입력 JSON에 같은 키가 중복돼 마지막 값만 읽었습니다."})
        if c["server_count"] == 0:
            reasons.append({"code": "no_catalog_servers", "input_index": c["input_index"],
                            "message": "이 카탈로그에 서버 항목이 없어 연결할 것이 없습니다."})
    for r in observed_records:
        if r["status"] == "ignored":
            reasons.append({"code": "observed_identity_ignored", "input_index": r["input_index"], "problems": r["problems"],
                            "message": "관측 identity 입력을 적용하지 않았습니다. 해당 선언의 관측 identity는 미수집으로 남습니다."})
    for s in summaries:
        oi = s["declaring_subject"].get("observed_identity")
        if oi and (oi["id_conflicts_with_user_provided"] or oi["kind_conflicts_with_subject_kind"]):
            reasons.append({"code": "observed_identity_conflict", "input_index": s["input_index"],
                            "message": "저장된 명령 출력에서 관측한 identity가 사용자가 입력한 주체 정보(--subject)와 다릅니다. 두 값을 모두 보존했고 어느 쪽도 확인하지 않았습니다."})
    for r in subject_records:
        if r["status"] == "ignored":
            reasons.append({"code": "subject_input_ignored", "input_index": r["input_index"], "problems": r["problems"],
                            "message": "선언 주체 입력을 적용하지 않았습니다. 해당 선언의 주체 식별값은 미수집으로 남습니다."})

    status = "partial" if reasons else "complete"
    outcome = {"complete": "all_catalog_servers_linked", "partial": "links_incomplete"}[status]
    result["collection"] = {"status": status, "outcome": outcome, "reasons": reasons, "counts": counts}
    return result


def build_link_report(collected: dict) -> dict:
    return {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "format_status": ("스캐너 내부 개발용 초안입니다. 팀 공통 스키마가 아니며 필드명과 구조는 협의 후 변경될 수 있습니다. "
                          "공통 asset_id·해시 규칙은 정하지 않았고 declaration_ref·internal_ref·라벨은 이 파일 안에서만 쓰는 이름입니다."),
        "producer": {"name": "agent-scope-asset-scanner", "version": __version__},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "scope": {
            "method": "저장된 설정 수집 결과와 저장된 Tool 카탈로그 결과를 읽어 서버 단위로 연결 (서버 접속·명령 실행 없음)",
            "not_verified": NOT_VERIFIED,
            "link_rule": ("카탈로그 서버의 config_link(config_scan_ref + registry_path + registration_key)가 참조한 설정 수집 결과 안의 "
                          "같은 등록 영역·같은 등록키 선언 하나와 일치할 때만 linked. 참조가 없거나 잘못되면 등록키·영역이 같은 선언이 있어도 연결하지 않고 "
                          "key_region_matches로만 알린다. 후보 다수는 ambiguous. 같은 이름의 서버·Tool은 합치지 않는다."),
            "link_meaning": "linked는 입력 자료 사이의 연결이며 서버 기동·Agent 노출·호출 가능을 뜻하지 않는다.",
            "observation_rule": ("서로 다른 카탈로그 입력이 같은 선언을 가리키면 별개 관측으로 각각 보존한다(declarations[].linked_observations). "
                                 "같은 카탈로그 입력 안에서 둘 이상이 같은 선언을 가리키면 ambiguous로 보류한다."),
            "subject_rule": ("선언 주체의 종류·식별값은 --subject로 사용자가 입력한 값만 user_provided로 보존한다. 스캐너가 확인한 값은 없다"
                             "(verified_by_scanner: false). 입력이 없으면 id는 null·id_origin은 not_collected이며 만들지 않는다."),
            "note": "선언에 Tool 근거(tool_evidence: not_supplied)가 없는 것은 Tool 0개가 아닙니다. 설정 대조·수집률·누락 계산은 하지 않았습니다.",
        },
        "inputs": collected["inputs"],
        "collection": collected["collection"],
        "declarations": collected["declarations"],
        "links": collected["links"],
    }


# ---- CLI --------------------------------------------------------------------------

def _split_label(text: str) -> tuple[str | None, Path]:
    """`라벨=경로` 또는 `경로`. 첫 `=` 앞이 라벨 형식일 때만 라벨로 본다(그 밖의 `=`는 경로의 일부)."""
    head, sep, tail = text.partition("=")
    if sep and _LABEL_RE.match(head) and tail:
        return head, Path(tail)
    return None, Path(text)


def _parse_subject(text: str, parser: argparse.ArgumentParser) -> dict:
    label, sep, rest = text.partition("=")
    if not sep or not _LABEL_RE.match(label) or not rest:
        parser.error("--subject는 '라벨=종류[,id=식별값]' 형식입니다 (예: gw=gateway,id=abc123).")
    kind = sid = None
    for piece in rest.split(","):
        if piece.startswith("id="):
            if sid is not None:
                parser.error("--subject에 id가 둘 이상 있습니다.")
            sid = piece[3:]
        elif piece in SUBJECT_KINDS:
            if kind is not None:
                parser.error("--subject에 종류가 둘 이상 있습니다.")
            kind = piece
        else:
            parser.error(f"--subject 종류는 {', '.join(SUBJECT_KINDS)} 중 하나이거나 id=<값>이어야 합니다.")
    return {"scan_label": label, "kind": kind, "id": sid}


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m asset_scanner.linking",
        description="저장된 설정 수집 결과와 저장된 Tool 카탈로그 결과를 서버 단위로 연결합니다 (내부 개발용 초안, 서버에 접속하지 않음).",
    )
    p.add_argument("--config-scan", required=True, action="append", metavar="[라벨=]경로",
                   help="설정 수집 결과 JSON. 카탈로그의 config_link.config_scan_ref가 가리키려면 라벨이 필요합니다 (여러 번 지정 가능)")
    p.add_argument("--catalog", required=True, action="append", metavar="[라벨=]경로",
                   help="Tool 카탈로그 결과 JSON (관측 하나). 여러 번 지정하면 같은 선언에 대한 관측을 따로 보존합니다")
    p.add_argument("--subject", action="append", default=[], metavar="라벨=종류[,id=값]",
                   help="설정 수집 결과(라벨)의 선언 주체 종류(gateway|node|plugin)와 식별값. 사용자 입력이며 스캐너가 확인하지 않습니다")
    p.add_argument("--observed-identity", action="append", default=[], metavar="라벨=파일",
                   help="설정 수집 결과(라벨)에 붙일 Gateway·Node identity 결과 JSON (node_gateway_identity 출력, identity 하나). "
                        "저장된 명령 출력에서 관측한 값이며 --subject와 별도 필드에 기록합니다")
    p.add_argument("--output", required=True, type=Path, help="연결 결과 JSON을 저장할 경로")
    return p


def main(argv: list[str] | None = None) -> int:
    _make_console_output_safe()
    parser = _parser()
    args = parser.parse_args(argv)
    if len(args.config_scan) > MAX_INPUTS or len(args.catalog) > MAX_INPUTS or len(args.subject) > MAX_INPUTS:
        parser.error(f"각 입력은 {MAX_INPUTS}개까지 지정할 수 있습니다.")
    cfg = [_split_label(t) for t in args.config_scan]
    cat = [_split_label(t) for t in args.catalog]
    subjects = [_parse_subject(t, parser) for t in args.subject]
    observed = []
    for t in args.observed_identity:
        lb, p_ = _split_label(t)
        if lb is None:
            parser.error("--observed-identity는 '라벨=파일' 형식입니다 (예: gw=output/gateway-identity.json).")
        observed.append({"scan_label": lb, "path": p_})
    if len(observed) > MAX_INPUTS:
        parser.error(f"각 입력은 {MAX_INPUTS}개까지 지정할 수 있습니다.")
    for _, src in [*cfg, *cat, *[(None, o["path"]) for o in observed]]:
        if _same_file(src, args.output):
            print("오류: --output이 입력 파일과 같습니다. 입력을 덮어쓰지 않습니다.", file=sys.stderr)
            return EXIT_OUTPUT_ERROR

    report = build_link_report(link_scans(cfg, cat, subjects, observed))
    report, normalized = normalize_for_output(report)
    if normalized:
        report["collection"]["output_text_normalizations"] = normalized
    try:
        write_json_atomic(args.output, report)
    except OutputError as exc:
        print(f"오류: 결과 파일을 저장하지 못했습니다 ({exc.kind}). 기존 결과 파일은 바꾸지 않았습니다.", file=sys.stderr)
        return EXIT_OUTPUT_ERROR

    col = report["collection"]
    print("저장된 수집 결과 연결 (서버 접속·명령 실행 없음)")
    print(f"연결 상태: {col['status']} ({col['outcome']})")
    if col["counts"]:
        c = col["counts"]
        print(f"카탈로그 서버 {c['catalog_servers']}개: linked {c['linked']}, ambiguous {c['ambiguous']}, unlinked {c['unlinked']}")
    for ln in report["links"]:
        print(f"  - catalog[{ln['catalog_input_index']}] server[{ln['catalog_server_index']}] "
              f"{json.dumps(ln['server_ref'], ensure_ascii=False)}  [{ln['link_status']}/{ln['reason']}]")
    for r in col["reasons"]:
        print(f"  사유: {r['code']}")
    print(f"결과 저장: {args.output}")
    return EXIT_BY_STATUS[col["status"]]


if __name__ == "__main__":
    sys.exit(main())
