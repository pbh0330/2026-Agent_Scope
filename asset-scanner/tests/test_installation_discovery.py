"""사람이 만든 설치 트리·인덱스·SQLite로만 검증한다. OpenClaw 실행 없음."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from asset_scanner import installation_inventory as inv
from conftest import SCANNER_ROOT


def plugin(root, pid="demo"):
    root.mkdir(parents=True)
    (root / "openclaw.plugin.json").write_text(json.dumps({"id": pid, "name": pid, "configSchema": {"type": "object"}}))
    (root / "package.json").write_text(json.dumps({"name": pid, "version": "1.0.0"}))
    return root


def skill(root):
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text('---\nname: greeter\ndescription: hello\n---\nFAKE_BODY')
    return root


def test_root_discovery_keeps_same_ids_in_separate_installations(tmp_path):
    state, workspace = tmp_path / "state", tmp_path / "workspace"
    plugin(state / "extensions" / "demo")
    plugin(workspace / ".openclaw" / "extensions" / "demo")
    skill(state / "skills" / "greet")
    skill(workspace / "skills" / "greet")
    report = inv.collect_installations([state], [workspace])
    assert report["collection"]["status"] == "complete"
    assert report["collection"]["plugin_count"] == report["collection"]["skill_count"] == 2
    assert len({p["root_dir"]["value"] for p in report["assets"]["plugins"]}) == 2
    assert "FAKE_BODY" not in json.dumps(report)


def test_managed_npm_scopes_and_bundled_sources_are_discovered(tmp_path):
    state, installed = tmp_path / "state", tmp_path / "openclaw"
    plugin(state / "npm" / "projects" / "managed" / "node_modules" / "@scope" / "demo")
    plugin(installed / "extensions" / "voice")
    skill(installed / "skills" / "greeter")
    report = inv.collect_installations([state], installation_roots=[installed])
    assert report["collection"]["plugin_count"] == 2 and report["collection"]["skill_count"] == 1


def index_value(root, pid="demo"):
    return {"version": 1, "plugins": [{"pluginId": pid, "rootDir": str(root), "enabled": True,
        "manifestHash": "FAKE_MANIFEST_DIGEST", "installRecord": {"source": "npm", "installPath": str(root),
        "installedAt": "2026-11-01T00:00:00Z", "integrity": "FAKE_INTEGRITY", "spec": "demo@1.0.0"}}]}


def test_index_link_requires_id_and_root_and_never_relabels_install_time(tmp_path):
    root = plugin(tmp_path / "allowed" / "demo")
    p = tmp_path / "index.json"
    p.write_text(json.dumps(index_value(root)))
    report = inv.collect_installations(allowed_roots=[root.parent], index_json=[p])
    assert report["collection"]["status"] == "complete"
    assert report["assets"]["plugins"][0]["index_record_refs"] == ["install-record[0]"]
    rec = report["installation_records"][0]
    assert rec["install"]["installedAt"] == "2026-11-01T00:00:00Z" and "last_updated" not in rec
    assert not rec["digest_metadata"]["integrity"]["verified"] and "FAKE" not in json.dumps(report)


def test_sqlite_index_reads_wrapper_and_preserves_original_bytes(tmp_path):
    root = plugin(tmp_path / "allowed" / "demo")
    db = tmp_path / "state.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE config_machine_state(state_key TEXT,value_json TEXT)")
        conn.execute("INSERT INTO config_machine_state VALUES(?,?)", ("plugins.installedIndex", json.dumps({"revision": 3, "index": index_value(root)})))
    before = db.read_bytes()
    report = inv.collect_installations(allowed_roots=[root.parent], state_databases=[db])
    assert report["collection"]["plugin_count"] == 1 and report["collection"]["status"] == "complete"
    assert db.read_bytes() == before and not Path(str(db) + "-shm").exists()


def test_index_does_not_authorize_reading_unselected_external_path(tmp_path):
    root = plugin(tmp_path / "outside" / "demo")
    p = tmp_path / "index.json"
    p.write_text(json.dumps(index_value(root)))
    report = inv.collect_installations(index_json=[p])
    assert report["collection"]["status"] == "partial" and report["collection"]["plugin_count"] == 0
    assert report["collection"]["index_record_count"] == 1


def test_config_load_paths_and_includes_respect_explicit_boundaries(tmp_path):
    root = plugin(tmp_path / "assets" / "p")
    s = skill(tmp_path / "assets" / "g")
    included = tmp_path / "load.json"
    included.write_text(json.dumps({"plugins": {"load": {"paths": [str(root)]}}, "skills": {"load": {"extraDirs": [str(s)]}}}))
    config = tmp_path / "openclaw.json"
    config.write_text('{"$include":"load.json"}')
    report = inv.collect_installations(config=config, resolve_includes=True)
    assert report["collection"]["plugin_count"] == report["collection"]["skill_count"] == 1


@pytest.mark.parametrize("value", ["~/private", "relative/path", "${HOME}/private", 4])
def test_unresolved_load_paths_are_not_guessed(tmp_path, value):
    p = tmp_path / "openclaw.json"
    p.write_text(json.dumps({"plugins": {"load": {"paths": [value]}}}))
    report = inv.collect_installations(config=p)
    assert report["collection"]["status"] in ("partial", "failed") and report["collection"]["plugin_count"] == 0


def test_discovery_does_not_follow_symlinks_out_of_scope(tmp_path):
    outside = plugin(tmp_path / "outside" / "secret")
    state = tmp_path / "state"
    (state / "extensions").mkdir(parents=True)
    try:
        (state / "extensions" / "alias").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("이 호스트는 디렉터리 심볼릭 링크 생성 권한이 없음")
    report = inv.collect_installations([state])
    assert report["collection"]["plugin_count"] == 0
    assert any(x["code"] == "discovery_link_not_followed" for x in report["issues"])


def test_asset_and_directory_limits_are_not_silent(tmp_path, monkeypatch):
    state = tmp_path / "state"
    for n in range(3):
        plugin(state / "extensions" / str(n), str(n))
    monkeypatch.setattr(inv, "MAX_ASSETS", 1)
    report = inv.collect_installations([state])
    assert report["collection"]["status"] == "partial" and report["collection"]["plugin_count"] == 1


def test_wrong_id_in_index_does_not_link_by_root_alone(tmp_path):
    root = plugin(tmp_path / "allowed" / "demo")
    p = tmp_path / "index.json"
    p.write_text(json.dumps(index_value(root, "other")))
    report = inv.collect_installations(allowed_roots=[root], index_json=[p])
    assert report["assets"]["plugins"][0]["index_record_refs"] == []


def test_cli_refuses_output_inside_discovery_tree(tmp_path):
    state = tmp_path / "state"
    p = plugin(state / "extensions" / "demo") / "openclaw.plugin.json"
    before = p.read_bytes()
    cmd = [sys.executable, "-m", "asset_scanner.installation_inventory", "--state-dir", str(state), "--output"]
    assert subprocess.run(cmd + [str(p)], cwd=SCANNER_ROOT, capture_output=True).returncode == 2
    assert p.read_bytes() == before
    out = tmp_path / "out.json"
    assert subprocess.run(cmd + [str(out)], cwd=SCANNER_ROOT, capture_output=True).returncode == 0


def test_cli_does_not_overwrite_an_included_config_file(tmp_path):
    included = tmp_path / "included.json"
    included.write_text('{"plugins":{"enabled":true}}')
    config = tmp_path / "root.json"
    config.write_text('{"$include":"included.json"}')
    before = included.read_bytes()
    run = subprocess.run([sys.executable, "-m", "asset_scanner.installation_inventory", "--config", str(config), "--resolve-includes", "--output", str(included)], cwd=SCANNER_ROOT, capture_output=True)
    assert run.returncode == 2 and included.read_bytes() == before


def test_entry_point_file_facts_and_outside_file_refusal(tmp_path):
    state = tmp_path / "state"
    root = plugin(state / "extensions" / "demo")
    (root / "entry.ts").write_text("FAKE_SOURCE_BODY")
    (root / "package.json").write_text(json.dumps({"name": "demo", "openclaw": {"extensions": ["entry.ts", "../../outside.py"]}}))
    report = inv.collect_installations([state])
    assert report["collection"]["status"] == "partial"
    facts = report["assets"]["plugins"][0]["entry_file_observations"]
    assert len(facts) == 1 and facts[0]["file_kind"] == "script_hint" and "FAKE_SOURCE_BODY" not in json.dumps(report)


def test_empty_selected_layout_is_complete_for_its_stated_scope(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    report = inv.collect_installations([state])
    assert report["collection"]["status"] == "complete" and report["collection"]["plugin_count"] == 0


def test_output_parent_alias_cannot_escape_discovery_overwrite_guard(tmp_path):
    state = tmp_path / "state"
    plugin(state / "extensions" / "demo")
    alias = tmp_path / "output-alias"
    try:
        alias.symlink_to(state, target_is_directory=True)
    except OSError:
        pytest.skip("이 호스트는 디렉터리 심볼릭 링크 생성 권한이 없음")
    run = subprocess.run([sys.executable, "-m", "asset_scanner.installation_inventory", "--state-dir", str(state), "--output", str(alias / "new.json")], cwd=SCANNER_ROOT, capture_output=True)
    assert run.returncode == 2 and not (state / "new.json").exists()


def test_install_ledger_is_preserved_even_when_plugin_is_missing_from_index(tmp_path):
    p = tmp_path / "index.json"
    p.write_text(json.dumps({"version": 1, "plugins": [], "installRecords": {"demo": {"source": "npm", "spec": "demo@1.2.3", "installedAt": "2026-11-01T00:00:00Z"}}}))
    report = inv.collect_installations(index_json=[p])
    assert report["collection"]["status"] == "complete" and len(report["installation_records"]) == 1
    rec = report["installation_records"][0]
    assert rec["source_container"] == "installRecords" and rec["install"]["spec"] == "demo@1.2.3"
    assert rec["root_dir"] is None and rec["discovery_status"] == "installation_path_not_reported"


def test_index_and_ledger_are_distinct_sources_but_one_physical_asset(tmp_path):
    root = plugin(tmp_path / "allowed" / "demo")
    value = index_value(root)
    value["installRecords"] = {"demo": value["plugins"][0]["installRecord"]}
    p = tmp_path / "index.json"
    p.write_text(json.dumps(value))
    report = inv.collect_installations(allowed_roots=[root.parent], index_json=[p])
    assert report["collection"]["plugin_count"] == 1 and report["collection"]["index_record_count"] == 2
    assert len(report["assets"]["plugins"][0]["index_record_refs"]) == 2
