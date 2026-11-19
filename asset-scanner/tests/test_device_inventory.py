"""가상 devices list 출력. 실제 OpenClaw 또는 팀 VM을 실행하지 않는다."""
import json
import subprocess
import sys

import pytest

from asset_scanner.device_inventory import collect_devices
from asset_scanner.openclaw_direct import DirectConfig, DirectResult, build_argv, run_query, validate_config
from conftest import SCANNER_ROOT


def read(tmp_path, data):
    p = tmp_path / "devices.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return collect_devices(p)


def node(**overrides):
    return {"deviceId": "ab12" * 16, "clientId": "node-host", "clientMode": "node", "roles": ["node"],
            "connected": False, "nodeSurface": {"caps": ["mcp"], "commands": ["system.run"]}, **overrides}


def test_client_label_and_device_identity_are_separate_and_pairing_is_reported(tmp_path):
    rep = read(tmp_path, {"pending": [node()], "paired": [node()]})
    assert rep["collection"]["status"] == "complete" and rep["collection"]["device_count"] == 2
    a, b = rep["devices"]
    assert a["reported_pairing_state"] == "paired" and b["reported_pairing_state"] == "pending"
    assert a["client"]["clientId"] == {"original_value": "node-host", "status": "as_reported"}
    assert a["identity"]["device_id"]["original_value"] == "ab12" * 16
    assert a["declared"]["connected"] is False
    assert a["node_surface"]["caps"] == ["mcp"]
    assert a["source_pointer"] == "/paired/0"
    assert "server_id" not in json.dumps(rep)


def test_credentials_and_unknown_values_are_not_copied(tmp_path):
    rep = read(tmp_path, {"pending": [], "paired": [node(
        privateKey="FAKE_PRIVATE_KEY", unknown={"secret": "FAKE_UNKNOWN_SECRET"}, remoteIp="FAKE_PRIVATE_IP",
        tokens=[{"role": "node", "scopes": ["operator.read"], "createdAtMs": 123, "token": "FAKE_TOKEN_SECRET"}])]})
    text = json.dumps(rep)
    assert "FAKE_" not in text
    assert rep["devices"][0]["token_metadata"] == [{"role": "node", "scopes": ["operator.read"], "createdAtMs": 123}]


def test_secret_shaped_value_in_public_key_is_not_copied(tmp_path):
    token = "ghp_FAKEPUBLICKEYFIELD12345678901234567890"
    rep = read(tmp_path, {"paired": [node(publicKey=token)], "pending": []})
    assert rep["collection"]["status"] == "partial"
    assert rep["devices"][0]["identity"]["public_key"]["status"] == "withheld_by_redaction"
    assert token not in json.dumps(rep)


@pytest.mark.parametrize("value", [None, [], {}, {"paired": "bad", "pending": []}, {"paired": ["bad"], "pending": []}])
def test_malformed_sections_do_not_become_a_complete_empty_inventory(tmp_path, value):
    assert read(tmp_path, value)["collection"]["status"] in ("partial", "failed")


def test_missing_optional_labels_and_empty_valid_lists_are_not_invented(tmp_path):
    rep = read(tmp_path, {"paired": [{"deviceId": "node-1"}], "pending": []})
    assert rep["devices"][0]["client"]["clientId"]["status"] == "missing"
    assert read(tmp_path, {"paired": [], "pending": []})["collection"] == {
        "status": "complete", "outcome": "no_device_records_read", "device_count": 0, "count_complete": True}


def test_duplicate_keys_are_evidence_and_identical_client_labels_are_not_merged(tmp_path):
    p = tmp_path / "devices.json"
    p.write_text('{"paired":[{"deviceId":"node-1","clientId":"old","clientId":"node-host"},{"deviceId":"node-2","clientId":"node-host"}],"pending":[]}', encoding="utf-8")
    rep = collect_devices(p)
    assert rep["collection"]["status"] == "partial" and len(rep["devices"]) == 2
    assert any(i["code"] == "duplicate_key" for i in rep["issues"])


def test_unknown_duplicate_url_keys_cannot_leak_password_in_issue_paths(tmp_path):
    p = tmp_path / "devices.json"
    key = "https://user:FAKE_DEVICE_DIAGNOSTIC_PASSWORD@example.test/a"
    p.write_text('{"paired":[{"deviceId":"node-1","' + key + '":1,"' + key + '":2}],"pending":[]}')
    rep = collect_devices(p)
    assert rep["collection"]["status"] == "partial"
    assert "FAKE_DEVICE_DIAGNOSTIC_PASSWORD" not in json.dumps(rep)


def test_direct_data_uses_same_parser_and_preserves_observation():
    rep = collect_devices(DirectResult("devices", data={"paired": [node()], "pending": []}, observation={"executed_by_scanner": True, "observed_at": "2026-11-18T00:00:00Z"}))
    assert rep["collection"]["status"] == "complete" and rep["observation"]["executed_by_scanner"] is True


def test_devices_direct_query_requires_explicit_target_or_ack_and_only_lists(tmp_path):
    cfg = DirectConfig(openclaw_bin=tmp_path / "does-not-exist")
    assert any("devices:" in msg for msg in validate_config(cfg, ["devices"]))
    cfg.expect_gateway_url = "ws://127.0.0.1:18789"
    argv = build_argv(cfg, "devices")
    assert argv[1:4] == ["devices", "list", "--json"]
    assert argv[-2:] == ["--url", cfg.expect_gateway_url]
    assert "--expect-url" not in argv and "--token" not in argv
    for mutation in ("approve", "reject", "remove", "rotate", "revoke"):
        assert any("허용하지 않는 조회" in msg for msg in validate_config(cfg, [mutation]))


def test_cli_reads_stored_data_and_refuses_input_overwrite(tmp_path):
    p, out = tmp_path / "devices.json", tmp_path / "result.json"
    p.write_text(json.dumps({"paired": [node()], "pending": []}), encoding="utf-8")
    cmd = [sys.executable, "-m", "asset_scanner.device_inventory", "--devices-json", str(p), "--output"]
    ok = subprocess.run(cmd + [str(out)], cwd=SCANNER_ROOT, capture_output=True, text=True)
    assert ok.returncode == 0 and json.loads(out.read_text())["devices"][0]["client"]["clientId"]["original_value"] == "node-host"
    before = p.read_bytes()
    refused = subprocess.run(cmd + [str(p)], cwd=SCANNER_ROOT, capture_output=True, text=True)
    assert refused.returncode == 2 and p.read_bytes() == before


def test_direct_failures_are_not_reported_as_empty_success():
    rep = collect_devices(DirectResult("devices", failure={"code": "command_failed", "message": "FAKE_SECRET"}))
    assert rep["collection"]["status"] == "failed" and "FAKE_SECRET" not in json.dumps(rep)
