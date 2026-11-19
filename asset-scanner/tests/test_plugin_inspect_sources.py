"""가상 plugin inspect 설치 원천. 설치 시각을 업데이트 시각으로 바꾸지 않는다."""
import json
import subprocess
import sys

import pytest

from asset_scanner.plugin_skill_assets import build_report, collect_assets, read_plugin_inspect_json
from conftest import SCANNER_ROOT


def capture(tmp_path, plugin_id="voice", root="/sample/plugin", install=None):
    p = tmp_path / "inspect.json"
    data = {"plugin": {"id": plugin_id, "rootDir": str(root), "version": "1.2.3", "hookNames": ["boot"]},
            "install": install if install is not None else {"source": "npm", "spec": "@sample/voice@1.2.3", "installPath": str(root),
                "version": "1.2.3", "installedAt": "2026-11-01T00:00:00Z", "acceptedSurfaceAt": "2026-11-02T00:00:00Z",
                "acceptedSurfaceHash": "FAKE_DIGEST_SHOULD_NOT_STORE", "integrity": "sha512-FAKE_INTEGRITY",
                "acceptedSurface": {"mcpServers": ["docs"], "tools": ["speak"]},
                "sourcePath": "https://user:FAKE_PASSWORD@example.org/plugin.tgz", "password": "FAKE_INSTALL_PASSWORD"}}
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_explicit_install_fields_provenance_and_digest_presence_only(tmp_path):
    rec = read_plugin_inspect_json(capture(tmp_path))
    inst = rec["install"]
    assert rec["status"] == "complete"
    assert inst["declared"]["version"] == "1.2.3"
    assert inst["declared"]["installedAt"] == "2026-11-01T00:00:00Z"
    assert "last_updated" not in inst["declared"] and "modified" not in inst["declared"]
    assert inst["digest_metadata"]["integrity"]["verification"] == "not_performed"
    assert inst["accepted_surface"]["mcpServers"] == ["docs"]
    assert rec["observation"]["source_kind"] == "stored_command_output"
    assert "FAKE_" not in json.dumps(rec)


def make_plugin(root):
    root.mkdir()
    (root / "openclaw.plugin.json").write_text('{"id":"voice","configSchema":{"type":"object"}}')
    (root / "package.json").write_text('{"name":"@sample/voice","version":"1.2.3"}')


def test_multiple_installs_are_linked_only_by_id_and_root_and_unlinked_exports_preserved(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    make_plugin(a); make_plugin(b)
    p = capture(tmp_path, root=b)
    rep = build_report(collect_assets([a, b], [], None, None, None, plugin_inspects=[p]))
    assert rep["collection"]["status"] == "complete"
    assert rep["plugins"][0]["installation_observations"] == []
    assert len(rep["plugins"][1]["installation_observations"]) == 1
    assert rep["plugins"][1]["installation_observations"][0]["link_basis"] == "id_and_root_dir_match"
    assert len(rep["plugin_inspect_outputs"]) == 1
    assert "raw_root_dir" not in json.dumps(rep)


@pytest.mark.parametrize("bad", ["secret", [], 5])
def test_bad_install_type_is_partial_and_the_value_is_not_saved(tmp_path, bad):
    p = capture(tmp_path, install=bad)
    rep = build_report(collect_assets([], [], None, None, None, plugin_inspects=[p]))
    assert rep["collection"]["status"] == "partial"
    assert rep["plugin_inspect_outputs"][0]["install"]["status"] == "invalid_type"


def test_absent_install_is_recorded_as_not_reported_not_invented(tmp_path):
    p = tmp_path / "inspect.json"; p.write_text('{"plugin":{"id":"voice"}}')
    assert read_plugin_inspect_json(p)["install"] == {"status": "not_reported", "verified_by_scanner": False}


def test_malformed_digest_and_source_fields_keep_errors_without_values(tmp_path):
    r = read_plugin_inspect_json(capture(tmp_path, install={"source": ["FAKE_SECRET"], "integrity": 123, "acceptedSurface": {"tools": {"secret": "FAKE_SECRET"}}}))
    assert r["status"] == "partial" and "FAKE_SECRET" not in json.dumps(r)


def test_duplicate_install_fields_are_partial(tmp_path):
    p = tmp_path / "inspect.json"
    p.write_text('{"plugin":{"id":"voice"},"install":{"source":"npm","source":"git"}}')
    r = read_plugin_inspect_json(p)
    assert r["status"] == "partial" and any(i["code"] == "duplicate_key" for i in r["issues"])


def test_secret_named_duplicate_keys_are_sanitized_in_evidence(tmp_path):
    p = tmp_path / "inspect.json"
    token = "ghp_FAKEINSTALLKEY12345678901234567890"
    p.write_text('{"plugin":{"id":"voice"},"install":{"' + token + '":1,"' + token + '":2}}')
    rec = read_plugin_inspect_json(p)
    assert rec["status"] == "partial" and token not in json.dumps(rec)


def test_url_password_in_unknown_duplicate_key_is_masked_in_diagnostic_path(tmp_path):
    p = tmp_path / "inspect.json"
    key = "https://user:FAKE_INSTALL_DIAGNOSTIC_PASSWORD@example.test/source"
    p.write_text('{"plugin":{"id":"voice"},"install":{"' + key + '":1,"' + key + '":2}}')
    rec = read_plugin_inspect_json(p)
    assert rec["status"] == "partial"
    assert "FAKE_INSTALL_DIAGNOSTIC_PASSWORD" not in json.dumps(rec)


def test_cli_can_collect_explicit_export_alone_and_refuses_overwrite(tmp_path):
    p = capture(tmp_path); out = tmp_path / "result.json"
    argv = [sys.executable, "-m", "asset_scanner.plugin_skill_assets", "--plugin-inspect-json", str(p), "--output"]
    run = subprocess.run(argv + [str(out)], cwd=SCANNER_ROOT, capture_output=True, text=True)
    assert run.returncode == 0 and json.loads(out.read_text())["plugin_inspect_outputs"][0]["install"]["status"] == "recorded"
    before = p.read_bytes()
    run = subprocess.run(argv + [str(p)], cwd=SCANNER_ROOT, capture_output=True, text=True)
    assert run.returncode == 4 and before == p.read_bytes()
