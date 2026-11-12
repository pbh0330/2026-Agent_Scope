"""Gateway·Node 자체 identity를 저장된 읽기 전용 명령 출력에서 수집한다 (자산 수집 확대 ②, 내부 개발용 초안).

    python -m asset_scanner.node_gateway_identity [--gateway-identity [라벨=]파일]... [--node-identity [라벨=]파일]... \
        [--observed-at 라벨=ISO8601]... --output OUT

이 모듈은 **명령을 실행하지 않는다.** 사용자가 미리 저장해 둔 출력 파일만 읽는다. 대상 명령은 OpenClaw 2026.9.6 패키지 문서·코드에서
다음과 같이 확인한 읽기 전용 원천이다 (docs/asset-collection.md 2장).

- Node: `openclaw node identity --json` — 로컬 상태 DB의 `device_identities`/`primary` 행에서 `{deviceId, publicKey}`를 출력한다.
  신원이 없으면 만들지 않고 오류로 끝난다(`loadDeviceIdentityIfPresentAsync`).
- Gateway: `openclaw gateway call gateway.identity.get --json` — 읽기 전용 호출(`callGatewayReadOnlyCli`), 메서드 범위 `operator.read`,
  결과 `{deviceId, publicKey}`.

값의 출처를 구분한다. 이 모듈의 값은 `observed_from_stored_command_output`이며, `linking`의 `--subject`로 사용자가 입력한
`user_provided` 값과 다른 필드에 둔다. 저장된 출력에는 실행 시각이 없으므로 `observed_at`은 사용자가 `--observed-at`으로 선언한
경우에만 `operator_declared`로 기록하고, 파일 수정 시각(`file_modified_at`)은 관측 시각이 아니라고 명시한다.
`deviceId`·`publicKey` 외의 필드는 값을 읽지 않고 이름만 남긴다. 개인 키처럼 보이는 값은 저장하지 않는다.
종료 코드: 0 완전, 1 부분, 2 인자 오류, 3 실패, 4 저장 실패.
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
from .redaction import REDACTED, Redactor, looks_like_secret_value
from .tools_catalog import _read_capture, _seg, _short

FORMAT_NAME = "agent-scope.scanner.gateway-node-identity"
FORMAT_VERSION = "0.1.0-draft"
MAX_ID_CHARS = 200
MAX_INPUTS = 20
_PUBLIC_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{20,200}$")      # base64url (publicKeyRawBase64UrlFromPem의 출력 형태)
_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
EXIT_BY_STATUS = {"complete": 0, "partial": 1, "failed": 3}
EXIT_OUTPUT_ERROR = 4

SOURCES = {
    "gateway": {
        "command": "openclaw gateway call gateway.identity.get --json",
        "read_only": True,
        "required_scope": "operator.read",
        "basis": "OpenClaw 2026.9.6 번들 코드: systemHandlers[\"gateway.identity.get\"] → {deviceId, publicKey}; gateway call은 callGatewayReadOnlyCli 사용",
    },
    "node": {
        "command": "openclaw node identity --json",
        "read_only": True,
        "required_scope": None,
        "basis": "OpenClaw 2026.9.6 문서(cli/node.md) 및 번들 코드 runNodeIdentityShow → {deviceId, publicKey}, 신원이 없으면 만들지 않음",
    },
}
NOT_VERIFIED = [
    "device_id_matches_running_process",   # 저장된 출력이 지금 실행 중인 Gateway·Node의 값인지 확인하지 않았다
    "pairing_state",                       # 페어링·승인 상태는 이 출력에 없다
    "key_ownership",                       # 공개키가 deviceId에서 유도된 값인지 검증하지 않았다
    "command_executed_by_scanner",         # 스캐너는 명령을 실행하지 않았다
    "common_asset_id",                     # 팀 공통 ID 미확정. deviceId를 공통 ID로 확정하지 않았다
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _issue(severity: str, code: str, message: str, **where: Any) -> dict:
    item = {"severity": severity, "code": code, "message": message}
    item.update({k: v for k, v in where.items() if v is not None})
    return item


def _mtime(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except OSError:
        return None


def parse_observed_at(text: str) -> str | None:
    """ISO 8601 시각만 받는다. 시간대가 없으면 UTC로 간주하지 않고 거부한다(관측 시각을 만들어 내지 않기 위해)."""
    try:
        dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _device_id_entry(value: Any, red: Redactor) -> dict:
    if value is None:
        return {"original_value": None, "status": "missing"}
    if not isinstance(value, str) or value.strip() == "" or len(value) > MAX_ID_CHARS or any(c.isspace() for c in value):
        return {"original_value": None, "status": "invalid"}
    shown = red.sanitize_text(value, "deviceId", check_entropy=False)   # deviceId는 긴 hex일 수 있어 엔트로피로 가리지 않는다
    if shown != value:
        return {"original_value": None, "status": "withheld_by_redaction"}
    return {"original_value": value, "status": "as_reported"}


def _public_key_entry(value: Any) -> dict:
    if value is None:
        return {"original_value": None, "status": "missing"}
    if not isinstance(value, str) or not _PUBLIC_KEY_RE.match(value):
        # PEM·개인 키 표지·공백이 든 값은 형식을 어긋난 것으로 보고 저장하지 않는다.
        return {"original_value": None, "status": "invalid_format"}
    return {"original_value": value, "status": "as_reported"}


def read_identity(kind: str, label: str | None, path: Path, observed_at: str | None, index: int) -> dict:
    src = SOURCES[kind]
    item: dict[str, Any] = {
        "kind": kind, "internal_ref": f"identity-input[{index}]", "label": label,
        "origin": "observed_from_stored_command_output",
        "observation": {
            "source_kind": "stored_command_output", "command": src["command"], "read_only_command": src["read_only"],
            "required_scope": src["required_scope"], "basis": src["basis"],
            "observed_at": observed_at, "observed_at_origin": "operator_declared" if observed_at else None,
            "file_modified_at": _mtime(path),
            "observed_at_note": "저장된 출력 파일에는 실행 시각이 없습니다. file_modified_at은 파일 수정 시각이며 관측 시각이 아닙니다.",
            "collected_at": _now(), "executed_by_scanner": False, "verified_by_scanner": False,
        },
        "issues": [],
    }
    data, failure = _read_capture(path)
    if failure is not None:
        item.update(collection_status="failed", outcome=failure["code"], device_id={"original_value": None, "status": "missing"},
                    public_key={"original_value": None, "status": "missing"}, unknown_fields=[])
        item["issues"].append(_issue("error", failure["code"], failure["message"]))
        return item
    if not isinstance(data, dict):
        item.update(collection_status="failed", outcome="invalid_structure", device_id={"original_value": None, "status": "missing"},
                    public_key={"original_value": None, "status": "missing"}, unknown_fields=[])
        item["issues"].append(_issue("error", "invalid_structure", "출력 최상위가 객체가 아닙니다 ({deviceId, publicKey} 형태가 필요)."))
        return item
    red = Redactor()
    dup = getattr(data, "duplicate_keys", [])
    item["device_id"] = _device_id_entry(data.get("deviceId"), red)
    item["public_key"] = _public_key_entry(data.get("publicKey"))
    known = {"deviceId", "publicKey"}
    item["unknown_fields"] = sorted(_seg(k) for k in data if k not in known)[:40]    # 값은 읽지 않는다
    for field_name, entry in (("deviceId", item["device_id"]), ("publicKey", item["public_key"])):
        st = entry["status"]
        if st == "missing":
            item["issues"].append(_issue("error", "required_field_missing", f"{field_name}가 없습니다.", field_path=field_name))
        elif st in ("invalid", "invalid_format"):
            item["issues"].append(_issue("error", "field_invalid", f"{field_name}의 형식이 올바르지 않아 값을 저장하지 않았습니다.", field_path=field_name))
        elif st == "withheld_by_redaction":
            item["issues"].append(_issue("warning", "identifier_withheld", f"{field_name}가 비밀값처럼 보여 저장하지 않았습니다.", field_path=field_name))
    if item["unknown_fields"]:
        item["issues"].append(_issue("warning", "unknown_fields_ignored", "알려진 필드(deviceId, publicKey) 외의 필드는 값을 읽지 않았습니다.",
                                     names=item["unknown_fields"]))
    if dup:
        item["issues"].append(_issue("error", "duplicate_key", "같은 키가 중복돼 마지막 값만 읽었습니다.", duplicate_keys=[_seg(k) for k in dup]))
    item["redactions"] = red.redactions
    # 식별값(deviceId)을 읽지 못하면 이 관측은 identity로서 쓸모가 없다. 공개키만 읽어도 deviceId를 대신하지 않는다.
    if item["device_id"]["status"] != "as_reported":
        item["collection_status"] = "failed"
        item["outcome"] = "device_id_" + item["device_id"]["status"]
    elif any(i["severity"] == "error" for i in item["issues"]):
        item["collection_status"] = "partial"
        item["outcome"] = "identity_incomplete"
    else:
        item["collection_status"] = "complete"
        item["outcome"] = "identity_read"
    return item


def collect_identities(gateways: list[tuple[str | None, Path]], nodes: list[tuple[str | None, Path]], observed: dict[str, str]) -> dict:
    items: list[dict] = []
    extra_issues: list[dict] = []
    labels: dict[str, int] = {}
    for kind, entries in (("gateway", gateways), ("node", nodes)):
        for label, path in entries:
            if label:
                labels[label] = labels.get(label, 0) + 1
    used_times: set[str] = set()
    for kind, entries in (("gateway", gateways), ("node", nodes)):
        for label, path in entries:
            at = None
            if label and labels.get(label) == 1 and label in observed:
                at = observed[label]
                used_times.add(label)
            item = read_identity(kind, label if label and labels.get(label) == 1 else None, path, at, len(items))
            if label and labels.get(label, 0) > 1:
                item["issues"].append(_issue("warning", "label_duplicate", "같은 라벨이 둘 이상이라 라벨과 관측 시각을 적용하지 않았습니다."))
            items.append(item)
    for lb in observed:
        if lb not in used_times:
            extra_issues.append(_issue("warning", "observed_at_label_unused", "--observed-at의 라벨이 단일 입력과 맞지 않아 적용하지 않았습니다."))
    # 같은 deviceId가 여러 입력에 있어도 합치지 않는다. 서로 다른 종류(gateway/node)에서 같으면 사실만 표시한다.
    seen: dict[str, list[int]] = {}
    for it in items:
        v = it["device_id"]["original_value"]
        if v is not None:
            seen.setdefault(v, []).append(it["internal_ref"])
    for v, refs in seen.items():
        if len(refs) > 1:
            for it in items:
                if it["internal_ref"] in refs:
                    it["issues"].append(_issue("warning", "same_device_id_in_multiple_inputs",
                                               "같은 deviceId가 여러 입력에 있습니다. 항목을 합치지 않았습니다.", other_inputs=[r for r in refs if r != it["internal_ref"]]))
    return {"identities": items, "issues": extra_issues}


def build_report(collected: dict, given: bool = True) -> dict:
    items = collected["identities"]
    statuses = [i["collection_status"] for i in items]
    if not given or not items:
        status, outcome = "failed", "no_input"
    elif all(s == "complete" for s in statuses) and not any(i["severity"] == "error" for i in collected["issues"]):
        status, outcome = "complete", "identities_read"
    elif all(s == "failed" for s in statuses):
        status, outcome = "failed", "no_identity_read"
    else:
        status, outcome = "partial", "some_identities_incomplete"
    return {
        "format": FORMAT_NAME, "format_version": FORMAT_VERSION,
        "format_status": "스캐너 내부 개발용 초안입니다. 팀 공통 스키마·공통 ID가 아닙니다. deviceId를 공통 자산 ID로 확정하지 않았습니다.",
        "producer": {"name": "agent-scope-asset-scanner", "version": __version__}, "generated_at": _now(),
        "basis": {"openclaw_version": "2026.9.6", "evidence": "패키지 문서·코드(정적 읽기). docs/asset-collection.md"},
        "scope": {
            "method": "저장된 읽기 전용 명령 출력 파일 읽기 (명령 실행 없음)",
            "not_verified": NOT_VERIFIED,
            "value_origins": {"observed_from_stored_command_output": "저장된 openclaw 명령 출력의 값. 스캐너가 확인한 것이 아님",
                              "user_provided": "linking의 --subject로 사용자가 입력한 값. 이 모듈의 값과 별개 필드"},
        },
        "collection": {"status": status, "outcome": outcome, "identity_count": len(items)},
        "identities": items, "issues": collected["issues"],
    }


def _split(text: str) -> tuple[str | None, Path]:
    """`라벨=경로` 또는 경로. 경로 자체에 `=`가 있어도 라벨 형식이 아니면 경로로 본다."""
    head, sep, tail = text.partition("=")
    if sep and _LABEL_RE.match(head) and tail:
        return head, Path(tail)
    return None, Path(text)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m asset_scanner.node_gateway_identity",
                                description="저장해 둔 `openclaw gateway call gateway.identity.get --json`·`openclaw node identity --json` 출력에서 "
                                            "Gateway·Node identity를 수집합니다 (명령 실행 없음, 내부 개발용 초안).")
    p.add_argument("--gateway-identity", action="append", default=[], metavar="[라벨=]파일", help="Gateway identity 출력 파일")
    p.add_argument("--node-identity", action="append", default=[], metavar="[라벨=]파일", help="Node identity 출력 파일")
    p.add_argument("--observed-at", action="append", default=[], metavar="라벨=ISO8601",
                   help="그 라벨 입력을 사용자가 관측한 시각(시간대 포함, 예: 2026-11-12T09:00:00+09:00). 선언한 값으로만 기록합니다")
    p.add_argument("--output", required=True, type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    _make_console_output_safe()
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.gateway_identity and not args.node_identity:
        parser.error("--gateway-identity 또는 --node-identity가 필요합니다.")
    if len(args.gateway_identity) + len(args.node_identity) > MAX_INPUTS:
        parser.error(f"입력은 {MAX_INPUTS}개까지입니다.")
    gws = [_split(t) for t in args.gateway_identity]
    nds = [_split(t) for t in args.node_identity]
    observed: dict[str, str] = {}
    for t in args.observed_at:
        label, sep, when = t.partition("=")
        parsed = parse_observed_at(when) if sep and _LABEL_RE.match(label) else None
        if parsed is None:
            parser.error("--observed-at는 '라벨=시간대가 포함된 ISO 8601 시각' 형식입니다 (예: gw=2026-11-12T09:00:00+09:00).")
        if label in observed:
            parser.error("--observed-at에 같은 라벨이 둘 이상 있습니다.")
        observed[label] = parsed
    for _, path in [*gws, *nds]:
        if _same_file(path, args.output):
            print("오류: --output이 입력과 같은 파일입니다. 입력을 덮어쓰지 않습니다.", file=sys.stderr)
            return EXIT_OUTPUT_ERROR
    report = build_report(collect_identities(gws, nds, observed))
    report, normalized = normalize_for_output(report)
    if normalized:
        report["collection"]["output_text_normalizations"] = normalized
    try:
        write_json_atomic(args.output, report)
    except OutputError as exc:
        print(f"오류: 결과 파일을 저장하지 못했습니다 ({exc.kind}). 기존 결과 파일은 바꾸지 않았습니다.", file=sys.stderr)
        return EXIT_OUTPUT_ERROR
    col = report["collection"]
    print("Gateway·Node identity 수집 결과 (저장된 명령 출력 읽기, 명령 실행 없음)")
    print(f"수집 상태: {col['status']} ({col['outcome']})")
    for it in report["identities"]:
        print(f"  - {it['kind']}  {json.dumps(_short(it['label'] or '(라벨 없음)'))}  [{it['collection_status']}/{it['outcome']}]")
    print(f"결과 저장: {args.output}")
    return EXIT_BY_STATUS[col["status"]]


if __name__ == "__main__":
    sys.exit(main())
