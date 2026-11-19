"""사용자가 지정한 가상 systemd 파일. 계정 조회·서비스 실행 없이 선언만 읽는다."""
import json
import subprocess
import sys

import pytest

from asset_scanner.service_identity import collect_service_identities
from conftest import SCANNER_ROOT


def write(tmp_path, text):
    p = tmp_path / "openclaw.service"
    p.write_text(text, encoding="utf-8")
    return p


def test_service_identity_declarations_keep_source_line_and_dont_copy_environment(tmp_path):
    p = write(tmp_path, '[Unit]\nUser=not-service\n[Service]\nUser=scanner\nGroup=agents\nDynamicUser=no\nEnvironment=TOKEN=FAKE_ENV_SECRET\nExecStart=/bin/false FAKE_EXEC_SECRET\nEnvironmentFile=/not/read\n')
    before = p.read_bytes()
    rep = collect_service_identities([p])
    unit = rep["units"][0]
    assert rep["collection"]["status"] == "complete"
    assert [(r["field"], r["value"], r["source_line"]) for r in unit["declarations"]] == [("User", "scanner", 4), ("Group", "agents", 5), ("DynamicUser", False, 6)]
    assert "FAKE_" not in json.dumps(rep) and "not-service" not in json.dumps(rep)
    assert before == p.read_bytes() and unit["executed_by_scanner"] is False


def test_absent_user_does_not_infer_root_and_empty_resets_do_not_infer_effective_user(tmp_path):
    rep = collect_service_identities([write(tmp_path, '[Service]\nUser=first\nUser=\nGroup=\n')])
    declarations = rep["units"][0]["declarations"]
    assert [r["value"] for r in declarations] == ["first", "", ""]
    assert declarations[1]["value_status"] == "empty_declaration"
    assert "effective_uid_gid" in rep["scope"]["not_collected"]
    assert collect_service_identities([write(tmp_path, '[Service]\nExecStart=/bin/false\n')])["units"][0]["declarations"] == []


@pytest.mark.parametrize("value,expected", [("yes", True), ("true", True), ("1", True), ("on", True), ("off", False), ("0", False), ("false", False)])
def test_dynamic_user_boolean_does_not_mean_a_static_uid(tmp_path, value, expected):
    rep = collect_service_identities([write(tmp_path, f'[Service]\nDynamicUser={value}\n')])
    assert rep["units"][0]["declarations"][0]["value"] is expected
    assert "uid" not in rep["units"][0]["declarations"][0]


def test_unresolved_specifiers_and_invalid_boolean_are_partial_not_runtime_accounts(tmp_path):
    rep = collect_service_identities([write(tmp_path, '[Service]\nUser=%i\nDynamicUser=FAKE_NOT_BOOLEAN\n')])
    assert rep["collection"]["status"] == "partial"
    assert rep["units"][0]["declarations"][0]["interpretation"] == "not_expanded_or_unquoted"
    assert "FAKE_NOT_BOOLEAN" not in json.dumps(rep)


def test_continuations_of_ignored_fields_cannot_inject_a_user_declaration(tmp_path):
    p = write(tmp_path, '[Service]\nEnvironment=FAKE_SECRET\\\nUser=FAKE_CONTINUATION_SECRET\n# ignored\nUser=real-user\n')
    rep = collect_service_identities([p])
    assert [r["value"] for r in rep["units"][0]["declarations"]] == ["real-user"]
    assert "FAKE_" not in json.dumps(rep)


def test_unterminated_continuations_and_unreadable_files_are_not_success(tmp_path):
    p = write(tmp_path, '[Service]\nUser=unresolved\\')
    assert collect_service_identities([p])["collection"]["status"] == "partial"
    assert collect_service_identities([tmp_path / "missing"])["collection"]["status"] == "failed"
    p.write_bytes(b'\xff')
    assert collect_service_identities([p])["collection"]["status"] == "failed"


def test_cli_and_overwrite_protection(tmp_path):
    p = write(tmp_path, '[Service]\nUser=scanner\n'); out = tmp_path / "result.json"
    cmd = [sys.executable, "-m", "asset_scanner.service_identity", "--systemd-unit", str(p), "--output"]
    run = subprocess.run(cmd + [str(out)], cwd=SCANNER_ROOT, capture_output=True, text=True)
    assert run.returncode == 0 and json.loads(out.read_text())["collection"]["declaration_count"] == 1
    before = p.read_bytes()
    assert subprocess.run(cmd + [str(p)], cwd=SCANNER_ROOT, capture_output=True).returncode == 2
    assert p.read_bytes() == before
