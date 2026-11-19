"""공식 manifest 예제에 기반한 정적 수집 검증. 팀 테스트베드 자료를 사용하지 않는다."""

import json
import os
import subprocess
import sys

import pytest

from conftest import SCANNER_ROOT
from asset_scanner.collector import collect_plugin_manifest
from asset_scanner.report import build_report


def write_manifest(tmp_path, servers):
    path = tmp_path / "openclaw.plugin.json"
    path.write_text(json.dumps({"id": "sample-plugin", "configSchema": {}, "mcpServers": servers}), encoding="utf-8")
    return path


def run_manifest(path, output, *extra):
    return subprocess.run(
        [sys.executable, "-m", "asset_scanner", "--plugin-manifest", str(path), "--output", str(output), *extra],
        cwd=SCANNER_ROOT, env={**os.environ, "PYTHONIOENCODING": "utf-8"}, capture_output=True,
    )


def test_static_manifest_records_declaration_without_resolving_relative_paths(tmp_path):
    path = write_manifest(tmp_path, {"catalog": {
        "transport": "stdio", "command": "node", "args": ["./mcp-server.js"], "cwd": "./data"}})
    before = path.read_bytes(), path.stat().st_mtime_ns
    report = build_report(collect_plugin_manifest(path))
    server = report["servers"][0]
    assert report["collection"]["status"] == "complete"
    assert report["source"]["source_kind"] == "openclaw_plugin_manifest"
    assert report["source"]["evidence_type"] == "manifest"
    assert report["source"]["registry_path"] == "mcpServers"
    assert server["declaration_path"] == "mcpServers.catalog"
    assert server["declaration_pointer"] == "/mcpServers/catalog"
    assert server["declared"]["args"] == ["./mcp-server.js"]
    assert server["declared"]["cwd"] == "./data"
    assert report["scope"]["values_resolved"] is False
    assert {"connection", "exposure", "callability"} <= set(report["scope"]["not_verified"])
    assert before == (path.read_bytes(), path.stat().st_mtime_ns)


def test_manifest_preserves_colliding_keys_and_redacts_secret_arguments(tmp_path):
    path = write_manifest(tmp_path, {
        "ghp_FAKEPLUGINREGISTRATION12345": {"command": "demo", "args": ["--token", "FAKE_PLUGIN_SECRET"]},
        "<redacted-key-1>": {"command": "other"},
    })
    result = collect_plugin_manifest(path)
    assert len(result["servers"]) == 2
    assert {s["registration_key"] for s in result["servers"]} == {"<redacted-key-1>", "<redacted-key-2>"}
    assert "FAKE" not in json.dumps(result)


def test_manifest_absent_is_distinct_from_explicit_empty_registry(tmp_path):
    path = tmp_path / "openclaw.plugin.json"
    path.write_text('{"id":"sample-plugin","configSchema":{}}', encoding="utf-8")
    absent = collect_plugin_manifest(path)["collection"]
    empty = collect_plugin_manifest(write_manifest(tmp_path, {}))["collection"]
    assert (absent["outcome"], absent["server_count"]) == ("registry_absent", None)
    assert (empty["outcome"], empty["server_count"]) == ("empty_registry", 0)


@pytest.mark.parametrize("value", [[], "not-an-object", None])
def test_invalid_manifest_registry_is_failure_not_zero_servers(tmp_path, value):
    result = collect_plugin_manifest(write_manifest(tmp_path, value))
    assert result["collection"]["status"] == "failed"
    assert result["collection"]["server_count"] is None
    assert result["registry_path"] == "mcpServers"


def test_one_invalid_server_does_not_remove_valid_or_disabled_declarations(tmp_path):
    result = collect_plugin_manifest(write_manifest(tmp_path, {
        "bad": [], "disabled": {"command": "node", "enabled": False}, "good": {"command": "demo"}}))
    assert result["collection"]["status"] == "partial"
    by_name = {s["registration_key"]: s for s in result["servers"]}
    assert set(by_name) == {"bad", "disabled", "good"}
    assert by_name["disabled"]["declared"]["enabled"] is False
    assert by_name["good"]["declared"]["command"] == "demo"


def test_duplicate_manifest_server_is_reported_as_partial(tmp_path):
    path = tmp_path / "openclaw.plugin.json"
    path.write_text('{"mcpServers":{"catalog":{"command":"first"},"catalog":{"command":"second"}}}', encoding="utf-8")
    result = collect_plugin_manifest(path)
    assert result["collection"]["status"] == "partial"
    assert result["collection"]["server_count"] == 1
    assert result["servers"][0]["declared"]["command"] == "second"


def test_include_is_not_read_and_environment_value_is_not_substituted(tmp_path, monkeypatch):
    monkeypatch.setenv("PLUGIN_TEST_SECRET", "FAKE_ENV_VALUE_MUST_NOT_BE_READ")
    path = tmp_path / "openclaw.plugin.json"
    path.write_text('{"$include":"missing.json","mcpServers":{"catalog":{"command":"${PLUGIN_TEST_SECRET}"}}}', encoding="utf-8")
    result = collect_plugin_manifest(path)
    assert result["collection"]["status"] == "partial"
    assert result["servers"][0]["declared"]["command"] == "${PLUGIN_TEST_SECRET}"
    assert "FAKE_ENV_VALUE_MUST_NOT_BE_READ" not in json.dumps(result)
    assert not (tmp_path / "missing.json").exists()


def test_manifest_cli_writes_source_and_true_exit_code(tmp_path):
    path = write_manifest(tmp_path, {"catalog": {"command": "node"}})
    output = tmp_path / "result.json"
    process = run_manifest(path, output)
    assert process.returncode == 0 and process.stderr == b""
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["source"]["registry_path"] == "mcpServers"
    assert result["source"]["evidence_type"] == "manifest"


def test_manifest_cli_cannot_overwrite_input(tmp_path):
    path = write_manifest(tmp_path, {"catalog": {"command": "node"}})
    before = path.read_bytes(), path.stat().st_mtime_ns
    assert run_manifest(path, path).returncode == 4
    assert before == (path.read_bytes(), path.stat().st_mtime_ns)


@pytest.mark.parametrize("extra", [("--config", "other.json"), ("--registry-path", "nodeHost.mcp.servers")])
def test_manifest_cli_rejects_conflicting_source_options(tmp_path, extra):
    path = write_manifest(tmp_path, {})
    output = tmp_path / "result.json"
    assert run_manifest(path, output, *extra).returncode == 2
    assert not output.exists()
