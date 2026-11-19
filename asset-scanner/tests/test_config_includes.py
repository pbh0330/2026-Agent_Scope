"""`$include` 읽기 전용 해석(--resolve-includes) 테스트 — 가상 설정만 사용한다.

근거 규칙: OpenClaw 2026.9.6 문서 "Config includes". 문서에 없는 규칙(배열 병합 방식 등)은 구현으로 확인하지 못해
결과에 사유를 남기고 partial로 두는지만 확인한다.
"""

import json
import os
import subprocess
import sys

import pytest

from asset_scanner.collector import collect
from conftest import SCANNER_ROOT

REG = ("mcp", "servers")


def w(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
    return path


def run(main, **kw):
    return collect(main, REG, resolve_includes=True, **kw)


def issues(res):
    return [i["code"] for i in res["collection"]["includes"]["issues"]]


def by_key(res):
    return {s["registration_key"]: s for s in res["servers"]}


# ---- 기본 동작: 옵션이 없으면 파일을 읽지 않는다(기존 동작 유지) -------------------------------------------

def test_without_the_option_includes_are_not_read_and_stay_unresolved(tmp_path):
    main = w(tmp_path / "openclaw.json", {"mcp": {"servers": {"$include": "./servers.json5"}}})
    w(tmp_path / "servers.json5", {"a": {"command": "x"}})
    res = collect(main, REG)
    assert res["collection"]["status"] == "partial" and res["servers"] == [] and res["collection"]["unresolved"]
    assert "includes" not in res["collection"]


# ---- 병합 규칙 -----------------------------------------------------------------------------------------

def test_single_file_replaces_the_containing_object_and_records_the_origin(tmp_path):
    main = w(tmp_path / "openclaw.json", {"mcp": {"servers": {"$include": "./servers.json5"}}})
    w(tmp_path / "servers.json5", {"a": {"command": "x"}})
    res = run(main)
    assert res["collection"]["status"] == "complete" and list(by_key(res)) == ["a"]
    a = by_key(res)["a"]
    assert a["include_origin"]["file"] == "servers.json5" and a["include_origin"]["include_chain"] == ["servers.json5"]
    assert a["declaration_path"] == "mcp.servers.a"                            # 논리 경로는 그대로
    assert res["collection"]["includes"]["edges"] == [{"declared_in": "(top-level config)", "field_path": "mcp.servers", "target": "servers.json5", "depth": 1}]
    assert str(tmp_path) not in json.dumps(res["collection"]["includes"])      # 물리 경로는 결과에 없다


def test_array_is_merged_in_order_and_siblings_override_included_values(tmp_path):
    main = w(tmp_path / "openclaw.json", {"mcp": {"servers": {"$include": ["./f1.json5", "./f2.json5"], "a": {"command": "from-main"}}}})
    w(tmp_path / "f1.json5", {"a": {"command": "from-f1", "cwd": "/w"}, "b": {"command": "b1"}})
    w(tmp_path / "f2.json5", {"b": {"command": "b2"}})
    res = run(main)
    s = by_key(res)
    assert s["a"]["declared"]["command"] == "from-main" and s["a"]["declared"]["cwd"] == "/w"       # 형제가 덮고 나머지는 f1
    assert s["b"]["declared"]["command"] == "b2"                                                    # 뒤 파일이 앞 파일을 덮음
    # 항목을 처음 선언한 파일(f1)과, 필드 단위로 덮어쓴 파일(f2)을 구분해 기록한다
    assert s["b"]["include_origin"]["file"] == "f1.json5"
    assert {"field_path": "mcp.servers.b.command", "file": "f2.json5"} in s["b"]["include_origin"]["field_origin_overrides"]
    assert s["a"]["include_origin"]["file"] == "f1.json5"
    assert s["a"]["include_origin"]["field_origin_overrides"] == [{"field_path": "mcp.servers.a.command", "file": "(top-level config)"}]
    assert res["collection"]["status"] == "complete"


def test_nested_includes_keep_the_chain(tmp_path):
    main = w(tmp_path / "openclaw.json", {"mcp": {"servers": {"$include": "./a.json5"}}})
    w(tmp_path / "a.json5", {"s": {"$include": "./sub/b.json5"}})
    w(tmp_path / "sub" / "b.json5", {"command": "deep"})
    res = run(main)
    s = by_key(res)["s"]
    assert s["declared"]["command"] == "deep" and s["include_origin"]["include_chain"] == ["a.json5", "sub/b.json5"]


def test_depth_limit_is_ten_levels(tmp_path):
    main = w(tmp_path / "openclaw.json", {"mcp": {"servers": {"$include": "./l1.json5"}}})
    for i in range(1, 12):
        w(tmp_path / f"l{i}.json5", {"$include": f"./l{i + 1}.json5"} if i < 11 else {"s": {"command": "x"}})
    res = run(main)
    assert "include_depth_exceeded" in issues(res) and res["collection"]["status"] == "partial"
    ok = w(tmp_path / "ok" / "openclaw.json", {"mcp": {"servers": {"$include": "./l1.json5"}}})
    for i in range(1, 10):
        w(tmp_path / "ok" / f"l{i}.json5", {"$include": f"./l{i + 1}.json5"} if i < 9 else {"s": {"command": "x"}})
    assert run(ok)["collection"]["status"] == "complete"            # 9단계 중첩은 허용


# ---- 오류와 한계 ---------------------------------------------------------------------------------------

def test_circular_include_is_reported_and_terminates(tmp_path):
    main = w(tmp_path / "openclaw.json", {"mcp": {"servers": {"$include": "./a.json5"}}})
    w(tmp_path / "a.json5", {"x": {"$include": "./b.json5"}})
    w(tmp_path / "b.json5", {"$include": "./a.json5"})
    assert "include_circular" in issues(run(main))
    main2 = w(tmp_path / "self" / "openclaw.json", {"mcp": {"servers": {"$include": "./openclaw.json"}}})
    assert "include_circular" in issues(run(main2))                 # 최상위 파일 자신을 포함


@pytest.mark.parametrize("target", ["../outside.json5", "sub/../../outside.json5"])
def test_path_escape_is_refused_and_the_outside_file_is_not_read(tmp_path, target):
    root = tmp_path / "cfg"
    main = w(root / "openclaw.json", {"mcp": {"servers": {"$include": target}}})
    w(tmp_path / "outside.json5", {"leak": {"command": "SECRET_OUTSIDE"}})
    res = run(main)
    assert "include_path_outside_root" in issues(res) and res["servers"] == []
    assert "SECRET_OUTSIDE" not in json.dumps(res) and res["collection"]["status"] == "partial"


def test_absolute_path_outside_is_refused_but_absolute_inside_is_allowed(tmp_path):
    root = tmp_path / "cfg"
    inside = w(root / "in.json5", {"a": {"command": "x"}})
    outside = w(tmp_path / "out.json5", {"leak": {"command": "x"}})
    assert "include_path_outside_root" in issues(run(w(root / "o1.json", {"mcp": {"servers": {"$include": str(outside)}}})))
    ok = run(w(root / "o2.json", {"mcp": {"servers": {"$include": str(inside)}}}))
    assert list(by_key(ok)) == ["a"]
    assert str(tmp_path) not in json.dumps(ok["collection"]["includes"])


def test_symlink_pointing_outside_is_refused(tmp_path):
    root = tmp_path / "cfg"
    root.mkdir()
    target = w(tmp_path / "secret.json5", {"leak": {"command": "x"}})
    try:
        os.symlink(target, root / "link.json5")
    except (OSError, NotImplementedError):
        pytest.skip("이 환경에서 심볼릭 링크를 만들 수 없음")
    res = run(w(root / "openclaw.json", {"mcp": {"servers": {"$include": "./link.json5"}}}))
    assert "include_path_outside_root" in issues(res) and res["servers"] == []


def test_size_limit_missing_file_not_a_file_and_parse_error(tmp_path):
    main = w(tmp_path / "openclaw.json", {"mcp": {"servers": {"$include": ["./big.json5", "./missing.json5", "./dir", "./bad.json5"]}}})
    w(tmp_path / "big.json5", "{" + " " * (2 * 1024 * 1024 + 10) + "}")
    (tmp_path / "dir").mkdir()
    w(tmp_path / "bad.json5", "{ a: ")
    res = run(main)
    codes = issues(res)
    for c in ("include_file_too_large", "include_file_not_found", "include_not_a_file", "include_parse_error"):
        assert c in codes
    assert res["collection"]["status"] == "partial" and res["collection"]["unresolved"]       # 선언을 남겨 불완전을 숨기지 않는다


def test_invalid_path_forms_null_byte_long_path_and_wrong_type(tmp_path):
    main = w(tmp_path / "openclaw.json", {"mcp": {"servers": {"$include": ["a\u0000b.json5", "x" * 5000]}}})
    codes = issues(run(main))
    assert "include_path_invalid" in codes and "include_path_too_long" in codes
    bad = w(tmp_path / "t" / "openclaw.json", {"mcp": {"servers": {"$include": 5}}})
    assert "include_type_invalid" in issues(run(bad))


def test_file_count_limit(tmp_path):
    targets = [f"./f{i}.json5" for i in range(70)]
    main = w(tmp_path / "openclaw.json", {"mcp": {"servers": {"$include": targets}}})
    for i in range(70):
        w(tmp_path / f"f{i}.json5", {f"s{i}": {"command": "x"}})
    res = run(main)
    assert "include_file_limit" in issues(res) and res["collection"]["includes"]["files_read"] == 64
    assert res["collection"]["status"] == "partial"


def test_arrays_at_the_same_position_are_concatenated_like_the_official_implementation(tmp_path):
    # 공식 deep-merge.ts(arrays: "concat"): 순서·중복 원소를 그대로 이어 붙인다. 미확정이 아니므로 partial이 아니다.
    main = w(tmp_path / "openclaw.json", {"mcp": {"servers": {"$include": ["./a.json5", "./b.json5"]}}})
    w(tmp_path / "a.json5", {"s": {"command": "x", "args": ["1", "dup"]}})
    w(tmp_path / "b.json5", {"s": {"args": ["dup", "2"]}})
    res = run(main)
    assert by_key(res)["s"]["declared"]["args"] == ["1", "dup", "dup", "2"]
    assert res["collection"]["status"] == "complete" and "array_merge_unverified" not in issues(res)


def test_secrets_in_included_files_are_still_redacted(tmp_path):
    main = w(tmp_path / "openclaw.json", {"mcp": {"servers": {"$include": "./s.json5"}}})
    w(tmp_path / "s.json5", {"a": {"command": "x", "env": {"API_TOKEN": "FAKEPLAINSECRET123"}, "args": ["--token", "FAKEARGSECRET456"]}})
    out = json.dumps(run(main))
    assert "FAKEPLAINSECRET123" not in out and "FAKEARGSECRET456" not in out


def test_secret_looking_keys_from_different_files_are_flagged_not_silently_merged(tmp_path):
    main = w(tmp_path / "openclaw.json", {"mcp": {"servers": {"$include": ["./a.json5", "./b.json5"]}}})
    w(tmp_path / "a.json5", {"ghp_FAKEAAAAAAAAAAAAAAAA1": {"command": "x"}})
    w(tmp_path / "b.json5", {"sk-FAKEBBBBBBBBBBBBBBBB2": {"command": "y"}})
    res = run(main)
    assert "masked_key_collision" in issues(res) and res["collection"]["status"] == "partial"
    assert "ghp_FAKEAAAAAAAAAAAAAAAA1" not in json.dumps(res)


def test_node_registry_path_and_array_entry_includes(tmp_path):
    main = w(tmp_path / "node.json", {"nodeHost": {"mcp": {"servers": {"$include": "./n.json5"}}}})
    w(tmp_path / "n.json5", {"k": {"command": "x"}})
    res = collect(main, ("nodeHost", "mcp", "servers"), resolve_includes=True)
    assert by_key(res)["k"]["include_origin"]["file"] == "n.json5" and by_key(res)["k"]["declaration_path"] == "nodeHost.mcp.servers.k"


def test_registry_absent_still_reports_include_context(tmp_path):
    main = w(tmp_path / "openclaw.json", {"other": {"$include": "./o.json5"}})
    w(tmp_path / "o.json5", {"x": 1})
    res = run(main)
    assert res["collection"]["outcome"] == "registry_absent" and res["collection"]["includes"]["files_read"] == 1


# ---- CLI -----------------------------------------------------------------------------------------------

def cli(*args):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, "-m", "asset_scanner", *args], cwd=SCANNER_ROOT, env=env, capture_output=True, text=True, encoding="utf-8")


def test_cli_option_resolves_includes_and_rejects_manifest_use(tmp_path):
    main = w(tmp_path / "openclaw.json", {"mcp": {"servers": {"$include": "./s.json5"}}})
    w(tmp_path / "s.json5", {"a": {"command": "x"}})
    out = tmp_path / "out.json"
    r = cli("--config", str(main), "--resolve-includes", "--output", str(out))
    assert r.returncode == 0, r.stderr
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["servers"][0]["include_origin"]["file"] == "s.json5"
    r2 = cli("--plugin-manifest", str(main), "--resolve-includes", "--output", str(tmp_path / "o2.json"))
    assert r2.returncode == 2
    r3 = cli("--config", str(main), "--output", str(tmp_path / "o3.json"))        # 옵션 없으면 기존 동작: partial(1)
    assert r3.returncode == 1


# ---- Permission/Auth ------------------------------------------------------------------------------------

def test_permission_auth_reads_policy_from_an_included_file_and_keeps_the_origin(tmp_path):
    from asset_scanner.permission_auth import build_report, collect_permission_auth
    main = w(tmp_path / "openclaw.json", {"tools": {"$include": "./tools.json5"}, "gateway": {"auth": {"mode": "token", "token": "FAKEGWSECRET789"}}})
    w(tmp_path / "tools.json5", {"profile": "full", "deny": ["exec"]})
    plain = build_report(collect_permission_auth(main))
    assert plain["collection"]["status"] == "partial" and not [i for i in plain["items"] if i["config_path"].startswith("tools")]
    rep = build_report(collect_permission_auth(main, resolve_includes=True))
    assert rep["collection"]["status"] == "complete"
    tools = {i["config_path"]: i for i in rep["items"] if i["config_path"].startswith("tools")}
    assert set(tools) == {"tools.profile", "tools.deny"}
    assert all(i["include_origin"]["file"] == "tools.json5" for i in tools.values())
    gw = [i for i in rep["items"] if i["config_path"] == "gateway.auth.mode"][0]
    assert gw["include_origin"]["file"] == "(top-level config)"
    assert rep["includes"]["files_read"] == 1
    assert "FAKEGWSECRET789" not in json.dumps(rep) and str(tmp_path) not in json.dumps(rep["includes"])


def test_permission_auth_include_failure_is_partial_with_the_reason(tmp_path):
    from asset_scanner.permission_auth import build_report, collect_permission_auth
    main = w(tmp_path / "openclaw.json", {"tools": {"$include": "../outside.json5"}})
    rep = build_report(collect_permission_auth(main, resolve_includes=True))
    assert rep["collection"]["status"] == "partial"
    assert any(i["code"] == "include_path_outside_root" for i in rep["issues"])
