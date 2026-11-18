"""명시한 devices list --json 출력의 장치·클라이언트 라벨·페어링 증거를 읽는다.

clientId는 OpenClaw의 원천 라벨이다. deviceId, MCP Client ID, 공통 자산 ID로 대체하지 않는다.
원천: OpenClaw eb377ac59e6c9fd6c7705028034812becf00271b
src/cli/devices-cli.ts 및 devices-cli.runtime.ts. 읽기 전용 list만 허용한다.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from .cli import _make_console_output_safe, _same_file
from .node_gateway_identity import _device_id_entry, _public_key_entry, parse_observed_at
from .openclaw_direct import DirectResult, add_direct_arguments, config_from_args, run_queries, validate_config
from .output import OutputError, normalize_for_output, write_json_atomic
from .plugin_skill_assets import _identity
from .redaction import Redactor
from .tools_catalog import _read_capture, _safe_short, _seg

MAX_DEVICES = 2000
MAX_LIST = 500
SOURCE = "openclaw/openclaw eb377ac59e6c9fd6c7705028034812becf00271b src/cli/devices-cli.ts, src/cli/devices-cli.runtime.ts"


def collect_devices(source: Path | DirectResult, *, observed_at: str | None = None) -> dict:
    direct = isinstance(source, DirectResult)
    report = {
        "format": "agent-scope.scanner.openclaw-device-inventory", "format_version": "0.1.0-draft",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "basis": SOURCE,
        "observation": dict(source.observation) if direct else {
            "source_kind": "stored_command_output", "command": "openclaw devices list --json",
            "executed_by_scanner": False, "observed_at": observed_at,
            "observed_at_origin": "operator_declared" if observed_at else None,
        },
        "scope": {"note": "clientId/clientMode는 원천 라벨이며 공통 ID나 MCP Client 인스턴스 ID로 확정하지 않습니다. paired/pending은 해당 출력의 기록이며 현재 연결 상태를 추정하지 않습니다.",
                  "not_collected": ["credential_values", "credential_hashes", "common_asset_id", "pairing_mutations"],
                  "not_verified": ["current_pairing_state", "key_ownership", "team_testbed"]},
        "collection": {}, "devices": [], "issues": [], "redactions": [],
    }
    issues, devices = report["issues"], report["devices"]
    red = Redactor()

    def problem(code, path):
        issues.append({"severity": "error", "code": code, "field_path": _safe_short(red, path, "diagnostic_field_path")})

    def selected(obj, strings=(), lists=(), bools=(), numbers=(), path=""):
        result = {}
        for names, kind in ((strings, "str"), (lists, "list"), (bools, "bool"), (numbers, "number")):
            for key in names:
                if key not in obj:
                    continue
                val = obj[key]
                loc = path + "." + key
                valid = ((kind == "str" and isinstance(val, str)) or
                         (kind == "bool" and isinstance(val, bool)) or
                         (kind == "number" and isinstance(val, int) and not isinstance(val, bool) and val >= 0) or
                         (kind == "list" and isinstance(val, list) and all(isinstance(v, str) for v in val)))
                if not valid:
                    problem("field_type_invalid", loc)
                    continue
                if kind == "list":
                    if len(val) > MAX_LIST:
                        problem("list_limit_exceeded", loc)
                    result[key] = [red.sanitize_string(v, loc) for v in val[:MAX_LIST]]
                else:
                    result[key] = red.sanitize_string(val, loc) if kind == "str" else val
        return result

    if direct:
        data, fail = source.data, source.failure
    else:
        data, fail = _read_capture(source)
    if fail:
        problem(fail["code"], "input")
        report["collection"] = {"status": "failed", "outcome": fail["code"], "device_count": 0, "count_complete": False}
        return report
    if not isinstance(data, dict) or not any(k in data for k in ("paired", "pending")):
        problem("invalid_devices_structure", "input")
        report["collection"] = {"status": "failed", "outcome": "invalid_structure", "device_count": 0, "count_complete": False}
        return report

    def duplicates(node, path):
        if isinstance(node, dict):
            for k in getattr(node, "duplicate_keys", []):
                problem("duplicate_key", path + "." + _seg(k))
            for k, val in node.items():
                duplicates(val, path + "." + _seg(k))
        elif isinstance(node, list):
            for n, val in enumerate(node):
                duplicates(val, f"{path}[{n}]")
    duplicates(data, "input")
    valid_sections = 0
    for section in ("paired", "pending"):
        entries = data.get(section)
        if not isinstance(entries, list):
            problem("section_missing_or_invalid", section)
            continue
        valid_sections += 1
        for n, obj in enumerate(entries):
            path = f"{section}[{n}]"
            if len(devices) >= MAX_DEVICES:
                problem("device_limit_exceeded", path)
                break
            if not isinstance(obj, dict):
                problem("device_not_object", path)
                continue
            dev = {"ref": f"device-record[{len(devices)}]", "source_pointer": f"/{section}/{n}",
                   "reported_pairing_state": section, "identity": {"device_id": _device_id_entry(obj.get("deviceId"), red)},
                   "client": {}, "declared": {}}
            if dev["identity"]["device_id"]["status"] != "as_reported":
                problem("device_id_unavailable", path + ".deviceId")
            if "publicKey" in obj:
                raw_key = obj["publicKey"]
                shown_key = red.sanitize_text(raw_key, path + ".publicKey", check_entropy=False) if isinstance(raw_key, str) else None
                dev["identity"]["public_key"] = (_public_key_entry(raw_key) if shown_key == raw_key else
                                                   {"original_value": None, "status": "withheld_by_redaction"})
                if dev["identity"]["public_key"]["status"] != "as_reported":
                    problem("public_key_invalid", path + ".publicKey")
            for key in ("clientId", "clientMode"):
                raw = obj.get(key)
                shown = red.sanitize_string(raw, path + "." + key) if isinstance(raw, str) else None
                dev["client"][key] = _identity(raw, shown)
                if raw is not None and dev["client"][key]["status"] != "as_reported":
                    problem("client_label_unavailable", path + "." + key)
            dev["declared"] = selected(obj, strings=("displayName", "platform", "deviceFamily", "role", "approvedVia", "lastSeenReason"),
                                       lists=("roles", "scopes"), bools=("connected", "isRepair"),
                                       numbers=("createdAtMs", "approvedAtMs", "lastSeenAtMs"), path=path)
            if "nodeSurface" in obj:
                if isinstance(obj["nodeSurface"], dict):
                    dev["node_surface"] = selected(obj["nodeSurface"], strings=("displayName", "version", "modelIdentifier"),
                                                   lists=("caps", "commands"), bools=("sessionHost",), path=path + ".nodeSurface")
                else:
                    problem("field_type_invalid", path + ".nodeSurface")
            # 토큰 객체 원문·알 수 없는 키·remoteIp·requestId는 복사하지 않는다.
            if "tokens" in obj:
                dev["token_metadata"] = []
                if isinstance(obj["tokens"], list):
                    if len(obj["tokens"]) > MAX_LIST:
                        problem("list_limit_exceeded", path + ".tokens")
                    for t in obj["tokens"][:MAX_LIST]:
                        if isinstance(t, dict):
                            dev["token_metadata"].append(selected(t, strings=("role",), lists=("scopes",),
                                                                  numbers=("createdAtMs", "rotatedAtMs", "revokedAtMs", "lastUsedAtMs"), path=path + ".tokens"))
                        else:
                            problem("field_type_invalid", path + ".tokens")
                else:
                    problem("field_type_invalid", path + ".tokens")
            devices.append(dev)
    status = "failed" if valid_sections == 0 else ("partial" if issues else "complete")
    report["collection"] = {"status": status, "outcome": "device_records_read" if devices else "no_device_records_read",
                            "device_count": len(devices), "count_complete": status == "complete"}
    report["redactions"] = red.redactions
    return report


def main(argv=None):
    _make_console_output_safe()
    p = argparse.ArgumentParser(description="저장된 devices list JSON 또는 읽기 전용 직접 조회에서 장치·클라이언트 원천을 수집합니다.")
    inp = p.add_mutually_exclusive_group(required=True)
    inp.add_argument("--devices-json", type=Path)
    inp.add_argument("--query-devices", action="store_true")
    p.add_argument("--observed-at")
    p.add_argument("--output", type=Path, required=True)
    add_direct_arguments(p)
    args = p.parse_args(argv)
    observed = parse_observed_at(args.observed_at) if args.observed_at else None
    if args.observed_at and observed is None:
        p.error("--observed-at은 시간대를 포함한 ISO8601이어야 합니다.")
    if args.query_devices and args.observed_at:
        p.error("직접 조회의 관측 시각은 스캐너가 기록합니다.")
    inputs = [args.devices_json, args.openclaw_bin, args.config_path]
    if any(x is not None and _same_file(args.output, x) for x in inputs):
        p.error("결과 파일은 입력 파일·실행 파일과 달라야 합니다.")
    if args.query_devices:
        if args.openclaw_bin is None:
            p.error("--openclaw-bin이 필요합니다.")
        cfg = config_from_args(args)
        problems = validate_config(cfg, ["devices"])
        if problems:
            p.error("; ".join(problems))
        results, _ = run_queries(cfg, ["devices"])
        source = results["devices"]
    else:
        source = args.devices_json
    report, _ = normalize_for_output(collect_devices(source, observed_at=observed))
    try:
        write_json_atomic(args.output, report)
    except OutputError:
        print("결과 파일을 저장하지 못했습니다.", file=sys.stderr)
        return 4
    print(f"장치 기록 수집: {report['collection']['status']}, {report['collection']['device_count']}개")
    return {"complete": 0, "partial": 1, "failed": 3}[report["collection"]["status"]]


if __name__ == "__main__":
    sys.exit(main())
