"""빈 `$include` 배열(`[]`) 처리 — 공식 구현에 맞춘 회귀 테스트.

근거: openclaw/openclaw `eb377ac59e6c9fd6c7705028034812becf00271b` `src/config/includes.ts`의 `resolveInclude`:
배열이면 `value.map(loadFile)`을 `reduce(deepMerge, {})`로 접으므로 항목이 0개면 결과는 초기값 `{}`이고 오류가 아니다.
형제 키가 있으면 `deepMerge({}, rest)`이므로 형제 키가 그대로 남는다. (사본: output/openclaw-includes-src/)
"""

import json

import pytest

from asset_scanner.collector import collect, parse_config, read_config
from asset_scanner.config_includes import resolve_includes
from asset_scanner.live_discovery import build_config_target
from asset_scanner.plugin_skill_assets import build_report, collect_assets

REG = ("mcp", "servers")


def w(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
    return path


def res(tmp_path, obj):
    cfg = w(tmp_path / "openclaw.json", obj)
    return resolve_includes(cfg, parse_config(read_config(cfg)))


def plain(x):
    return json.loads(json.dumps(x))


def test_empty_array_resolves_to_an_empty_object_without_issues(tmp_path):
    ctx = res(tmp_path, {"$include": []})
    assert plain(ctx.root) == {} and not ctx.issues and ctx.files_read == 0


def test_siblings_next_to_an_empty_array_are_preserved(tmp_path):
    ctx = res(tmp_path, {"$include": [], "a": 1, "n": {"x": [1]}})
    assert plain(ctx.root) == {"a": 1, "n": {"x": [1]}} and not ctx.issues


def test_empty_array_at_nested_positions(tmp_path):
    ctx = res(tmp_path, {"a": {"$include": []}, "b": {"$include": [], "k": 2}, "list": [{"$include": []}, {"$include": [], "z": 1}]})
    assert plain(ctx.root) == {"a": {}, "b": {"k": 2}, "list": [{}, {"z": 1}]} and not ctx.issues


def test_empty_array_next_to_real_includes_in_the_same_tree(tmp_path):
    w(tmp_path / "f.json", {"x": [1]})
    ctx = res(tmp_path, {"p": {"$include": ["./f.json"]}, "q": {"$include": []}})
    assert plain(ctx.root) == {"p": {"x": [1]}, "q": {}} and not ctx.issues


def test_real_failures_are_still_reported_next_to_an_empty_array(tmp_path):
    ctx = res(tmp_path, {"a": {"$include": []}, "b": {"$include": ["./missing.json"]}, "c": {"$include": 5}, "d": {"$include": ["../out.json"]}})
    codes = {i["code"] for i in ctx.issues}
    assert {"include_file_not_found", "include_type_invalid", "include_path_outside_root"} <= codes
    assert plain(ctx.root)["a"] == {}                                              # 빈 배열 자리는 문제 없음


def test_array_items_must_still_be_strings(tmp_path):
    assert "include_type_invalid" in {i["code"] for i in res(tmp_path, {"$include": [3]}).issues}


# ---- 수집·조회 영향 ---------------------------------------------------------------------------------------

def test_collector_is_not_partial_for_an_empty_include_array(tmp_path):
    main = w(tmp_path / "openclaw.json", {"mcp": {"servers": {"$include": [], "s": {"command": "x"}}}})
    r = collect(main, REG, resolve_includes=True)
    assert r["collection"]["status"] == "complete" and [s["registration_key"] for s in r["servers"]] == ["s"]
    assert not r["collection"]["unresolved"] and r["collection"]["includes"]["issues"] == []
    empty = collect(w(tmp_path / "e" / "openclaw.json", {"mcp": {"servers": {"$include": []}}}), REG, resolve_includes=True)
    assert empty["collection"]["status"] == "complete" and empty["collection"]["outcome"] == "empty_registry" and empty["collection"]["server_count"] == 0


def test_live_discovery_does_not_refuse_because_of_an_empty_include_array(tmp_path):
    main = w(tmp_path / "openclaw.json", {"mcp": {"servers": {"$include": [], "s": {"url": "http://127.0.0.1:1/mcp"}}}})
    t = build_config_target(main, "s", "mcp.servers", False, True, [], None, None, None, True)
    assert t.refused is None and t.declaration["include_origin"]["issues"] == []


def test_live_discovery_still_refuses_a_real_failure_even_with_an_empty_array_sibling(tmp_path):
    main = w(tmp_path / "openclaw.json", {"mcp": {"servers": {"$include": ["./missing.json5"], "s": {"command": "x"}, "t": {"$include": []}}}})
    t = build_config_target(main, "s", "mcp.servers", True, False, [], None, None, None, True)
    assert t.refused is not None and t.refused["code"] == "include_unresolved"


def test_plugin_skill_settings_are_complete_with_an_empty_include_array(tmp_path):
    main = w(tmp_path / "cfg" / "openclaw.json", {"plugins": {"$include": [], "allow": ["p"]}})
    rep = build_report(collect_assets([], [], main, None, None, True))
    st = rep["activation_settings"]
    assert st["status"] == "complete" and st["plugins"]["allow"] == ["p"] and st["includes"]["issues"] == []


def test_permission_auth_is_complete_with_an_empty_include_array(tmp_path):
    from asset_scanner.permission_auth import build_report as pbuild, collect_permission_auth
    main = w(tmp_path / "openclaw.json", {"tools": {"$include": [], "profile": "full"}})
    rep = pbuild(collect_permission_auth(main, resolve_includes=True))
    assert rep["collection"]["status"] == "complete" and [i["config_path"] for i in rep["items"]] == ["tools.profile"]
