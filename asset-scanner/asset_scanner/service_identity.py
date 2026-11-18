"""명시한 systemd unit의 실행 계정 선언만 읽는다. 서비스·셸·환경 파일을 실행/조회하지 않는다.

원천: OpenClaw eb377ac59e6c9fd6c7705028034812becf00271b docs/gateway/index.md
및 systemd.exec(5) User/Group Identity. 선언·관측·실효 계정은 구분한다.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

from .cli import _make_console_output_safe, _same_file
from .output import OutputError, normalize_for_output, write_json_atomic
from .plugin_skill_assets import _safe_path
from .redaction import Redactor

MAX_UNIT_BYTES = 1024 * 1024
MAX_UNITS = 64
MAX_DECLARATIONS = 2000
IDENTITY_KEYS = frozenset({"User", "Group", "DynamicUser", "SupplementaryGroups"})


def collect_service_identities(paths: list[Path]) -> dict:
    result = {"format": "agent-scope.scanner.service-identity-declarations", "format_version": "0.1.0-draft",
              "generated_at": datetime.now(timezone.utc).isoformat(), "units": [], "issues": [],
              "scope": {"method": "operator_selected_systemd_unit_files",
                        "note": "선택한 파일의 선언 순서를 보존합니다. drop-in 병합, 빈 값의 기본 계정, UID/GID 해석, 실행 중 프로세스의 계정은 계산하지 않습니다.",
                        "not_collected": ["environment_values", "environment_file_contents", "exec_commands", "effective_uid_gid", "automatic_service_discovery"],
                        "not_verified": ["service_is_running", "current_process_identity", "team_testbed"]},
              "basis": ["https://github.com/openclaw/openclaw/blob/eb377ac59e6c9fd6c7705028034812becf00271b/docs/gateway/index.md",
                        "https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html#User/Group%20Identity"]}
    if len(paths) > MAX_UNITS:
        result["issues"].append({"code": "unit_limit_exceeded", "severity": "error"})
    for path in paths[:MAX_UNITS]:
        unit = {"source_file": _safe_path(path)[0], "source_kind": "static_systemd_unit", "declarations": [],
                "issues": [], "redactions": [], "executed_by_scanner": False}
        result["units"].append(unit)
        red = Redactor()

        def problem(code, line=None):
            unit["issues"].append({"severity": "error", "code": code, **({"line": line} if line is not None else {})})

        try:
            if not path.is_file():
                raise OSError("not regular file")
            with path.open("rb") as stream:
                raw = stream.read(MAX_UNIT_BYTES + 1)
            if len(raw) > MAX_UNIT_BYTES:
                problem("unit_too_large")
                unit["collection_status"] = "failed"
                continue
            text = raw.decode("utf-8-sig")
        except (OSError, UnicodeDecodeError):
            problem("unit_unreadable_or_not_utf8")
            unit["collection_status"] = "failed"
            continue
        if "\x00" in text:
            problem("unit_contains_null")
            unit["collection_status"] = "failed"
            continue
        section, pending, first_line = "", "", 0
        for line_n, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("#", ";")):
                continue
            if not pending:
                first_line = line_n
            # 건너뛰는 Environment/ExecStart도 줄 연결을 처리해 다음 줄을 User=로 오인하지 않는다.
            slash_count = len(line) - len(line.rstrip("\\"))
            if slash_count % 2:
                pending += line[:-1] + " "
                continue
            logical = (pending + line).strip()
            pending = ""
            if logical.startswith("[") and logical.endswith("]"):
                section = logical[1:-1].strip()
                continue
            if section != "Service" or "=" not in logical:
                continue
            key, value = logical.split("=", 1)
            key, value = key.strip(), value.strip()
            if key not in IDENTITY_KEYS:
                continue
            if len(unit["declarations"]) >= MAX_DECLARATIONS:
                problem("declaration_limit_exceeded", first_line)
                break
            rec = {"field": key, "source_line": first_line, "section": "Service", "origin": "declared_in_selected_unit"}
            if len(value) > 512:
                rec["value_status"] = "too_long_withheld"
                problem("identity_value_too_long", first_line)
            elif key == "DynamicUser":
                if value.lower() in ("yes", "true", "on", "1", "no", "false", "off", "0"):
                    rec.update(value=value.lower() in ("yes", "true", "on", "1"), value_status="as_declared")
                elif value == "":
                    rec.update(value="", value_status="empty_declaration")
                else:
                    rec["value_status"] = "invalid_boolean_withheld"
                    problem("identity_boolean_invalid", first_line)
            else:
                shown = red.sanitize_string(value, f"Service.{key}")
                rec.update(value=shown, value_status="empty_declaration" if not value else ("redacted" if shown != value else "as_declared"))
                if "%" in value or "${" in value or "\\" in value or '"' in value or "'" in value:
                    rec["interpretation"] = "not_expanded_or_unquoted"
                    problem("identity_expression_unresolved", first_line)
            unit["declarations"].append(rec)
        if pending:
            problem("unit_unterminated_continuation", first_line)
        unit["redactions"] = red.redactions
        unit["collection_status"] = "partial" if unit["issues"] else "complete"
    statuses = [u["collection_status"] for u in result["units"]]
    status = "failed" if not statuses or all(s == "failed" for s in statuses) else ("complete" if all(s == "complete" for s in statuses) and not result["issues"] else "partial")
    result["collection"] = {"status": status, "unit_count": len(result["units"]), "declaration_count": sum(len(u["declarations"]) for u in result["units"])}
    return result


def main(argv=None):
    _make_console_output_safe()
    p = argparse.ArgumentParser(description="지정한 systemd unit의 실행 계정 선언을 기록합니다 (읽기 전용).")
    p.add_argument("--systemd-unit", action="append", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args(argv)
    if any(_same_file(args.output, f) for f in args.systemd_unit):
        p.error("입력 파일을 결과로 덮어쓸 수 없습니다.")
    report, _ = normalize_for_output(collect_service_identities(args.systemd_unit))
    try:
        write_json_atomic(args.output, report)
    except OutputError:
        print("결과 파일을 저장하지 못했습니다.", file=sys.stderr)
        return 4
    print(f"서비스 실행 계정 선언 수집: {report['collection']['status']}")
    return {"complete": 0, "partial": 1, "failed": 3}[report["collection"]["status"]]


if __name__ == "__main__":
    sys.exit(main())
