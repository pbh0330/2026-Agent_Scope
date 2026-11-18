"""추가 include 경계. 값은 가상이며 파일을 실행하거나 쓰지 않는다."""
import json
import os

import pytest

from asset_scanner.collector import collect, parse_config
from asset_scanner.config_includes import resolve_includes
from asset_scanner.permission_auth import collect_permission_auth
from asset_scanner.plugin_skill_assets import read_activation_settings


@pytest.fixture
def tree(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENCLAW_INCLUDE_ROOTS", raising=False)
    cfg, shared = tmp_path / "config", tmp_path / "shared"
    cfg.mkdir(); shared.mkdir()
    p = cfg / "openclaw.json"
    p.write_text(json.dumps({"$include": "../shared/common.json"}), encoding="utf-8")
    (shared / "common.json").write_text(json.dumps({"mcp": {"servers": {"docs": {"command": "not-run"}}},
                                                  "tools": {"deny": ["browser"]}, "plugins": {"allow": ["voice"]}}), encoding="utf-8")
    return p, shared


def test_unset_roots_preserve_default_boundary_and_explicit_roots_enable_source(tree):
    p, shared = tree
    root = parse_config(p.read_text())
    assert any(i["code"] == "include_path_outside_root" for i in resolve_includes(p, root).issues)
    ctx = resolve_includes(p, root, [shared])
    assert not ctx.issues and ctx.root["tools"]["deny"] == ["browser"]
    assert ctx.origin_of(("tools", "deny"))[0] == "include-root[0]/common.json"


def test_environment_roots_apply_to_all_shared_collector_paths(tree, monkeypatch):
    p, shared = tree
    monkeypatch.setenv("OPENCLAW_INCLUDE_ROOTS", str(shared))
    collected = collect(p, resolve_includes=True)
    assert collected["servers"][0]["registration_key"] == "docs"
    assert not any("OPENCLAW_INCLUDE_ROOTS" in item for item in collected["collection"]["includes"]["not_supported"])
    policy = collect_permission_auth(p, resolve_includes=True)
    assert policy["items"][0]["value"] == ["browser"]
    assert policy["items"][0]["include_origin"]["file"] == "include-root[0]/common.json"
    assert read_activation_settings(p, True)["plugins"]["allow"] == ["voice"]


def test_multiple_roots_and_nested_include_use_distinct_provenance(tree, tmp_path, monkeypatch):
    p, shared = tree
    other = tmp_path / "other"; other.mkdir()
    (other / "common.json").write_text('{"tools":{"allow":["read"]}}', encoding="utf-8")
    (shared / "common.json").write_text('{"$include":"../other/common.json"}', encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_INCLUDE_ROOTS", os.pathsep.join((str(shared), str(other), str(shared))))
    ctx = resolve_includes(p, parse_config(p.read_text()))
    assert not ctx.issues and ctx.origin_of(("tools", "allow"))[0] == "include-root[1]/common.json"
    assert ctx.notes[0]["count"] == 2


@pytest.mark.parametrize("invalid", ["relative-path", "missing", "file"])
def test_invalid_extra_roots_are_reported_without_storing_their_values(tree, tmp_path, invalid):
    p, _ = tree
    bad = tmp_path / "file" if invalid == "file" else (tmp_path / "missing" if invalid == "missing" else "relative-path")
    if invalid == "file":
        bad.write_text("not a directory")
    ctx = resolve_includes(p, {}, [bad])
    assert any(i["code"] == "include_root_invalid" for i in ctx.issues)
    assert str(bad) not in json.dumps(ctx.issues)


def test_symlink_into_allowed_root_is_read_but_outside_to_inside_alias_is_refused(tree, tmp_path):
    p, shared = tree
    try:
        (p.parent / "allowed-link.json").symlink_to(shared / "common.json")
        (tmp_path / "outside-link.json").symlink_to(shared / "common.json")
    except OSError:
        pytest.skip("symlinks unavailable")
    assert not resolve_includes(p, {"$include": "allowed-link.json"}, [shared]).issues
    refused = resolve_includes(p, {"$include": "../outside-link.json"}, [shared])
    assert any(i["code"] == "include_path_outside_root" for i in refused.issues)


def test_symlink_out_of_all_roots_and_hardlinks_remain_refused(tree, tmp_path):
    p, shared = tree
    secret = tmp_path / "outside.json"; secret.write_text('{"tools":{"deny":["FAKE_SHOULD_NOT_READ"]}}')
    try:
        (shared / "link.json").symlink_to(secret)
    except OSError:
        pytest.skip("symlinks unavailable")
    ctx = resolve_includes(p, {"$include": "../shared/link.json"}, [shared])
    assert any(i["code"] == "include_path_outside_root" for i in ctx.issues)
    assert "FAKE_SHOULD_NOT_READ" not in json.dumps(ctx.root)
    hard = shared / "hard.json"
    os.link(secret, hard)
    ctx = resolve_includes(p, {"$include": "../shared/hard.json"}, [shared])
    assert any(i["code"] == "include_hardlink_rejected" for i in ctx.issues)


def test_unresolvable_tilde_root_is_an_issue_not_an_exception(tree, monkeypatch):
    p, _ = tree
    monkeypatch.setenv("OPENCLAW_INCLUDE_ROOTS", "~FAKE_NONEXISTENT_SCANNER_USER_84378/config")
    ctx = resolve_includes(p, {})
    assert any(i["code"] == "include_root_invalid" for i in ctx.issues)
