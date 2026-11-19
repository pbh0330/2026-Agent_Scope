"""`$include` 해석이 실패하거나 규칙이 미확정이어서 선택한 서버의 command·args·URL에 영향을 줄 수 있으면
live_discovery는 실행·접속을 거부해야 한다. 수집 결과의 partial 표시와 실제 실행 허용 여부는 별개다.

- 영향 판정: include 문제의 위치가 선택한 서버 선언과 같거나 그 조상·하위일 때만 거부한다.
- 무관한 다른 서버의 include 문제는 수집 결과를 partial로 만들지만 선택한 서버의 조회는 막지 않는다.
모든 설정은 가상이며 프로세스·소켓은 만들지 않는다(대상 생성만 확인).
"""

import json
import socket
import subprocess

import pytest

from asset_scanner.collector import collect
from asset_scanner.live_discovery import build_config_target

REG = ("mcp", "servers")


def w(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def no_process_or_socket(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("실행·접속 시도")
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(socket, "create_connection", boom)


def target(main, key="s", **kw):
    return build_config_target(main, key, "mcp.servers", True, True, [], None, None, None, True)


def servers_cfg(tmp_path, servers, name="openclaw.json"):
    return w(tmp_path / name, {"mcp": {"servers": servers}})


def refused_code(t):
    return t.refused["code"] if t.refused else None


# ---- 영향이 있으면 거부 ---------------------------------------------------------------------------------

def test_failed_include_inside_the_selected_entry_is_refused(tmp_path):
    main = servers_cfg(tmp_path, {"s": {"$include": "./missing.json5", "command": "x"}})
    assert refused_code(target(main)) == "include_unresolved"


@pytest.mark.parametrize("name, make", [
    ("missing", lambda d: {"$include": "./missing.json5", "s": {"command": "x"}}),
    ("outside", lambda d: {"$include": "../outside.json5", "s": {"command": "x"}}),
    ("parse_error", lambda d: {"$include": "./bad.json5", "s": {"command": "x"}}),
    ("not_a_file", lambda d: {"$include": "./dir", "s": {"command": "x"}}),
    ("type_invalid", lambda d: {"$include": 5, "s": {"command": "x"}}),
])
def test_failed_include_at_the_registry_level_can_change_the_selected_server_so_it_is_refused(tmp_path, name, make):
    (tmp_path / "dir").mkdir()
    w(tmp_path / "bad.json5", "{ a: ")
    main = servers_cfg(tmp_path, make(tmp_path))
    t = target(main)
    assert refused_code(t) == "include_unresolved", t.refused
    assert t.refused["include_issue_codes"]                                         # 사유 코드만 알려 준다
    assert collect(main, REG, resolve_includes=True)["collection"]["status"] == "partial"      # 수집 결과도 partial


def test_arrays_that_merge_normally_are_not_refused_and_not_partial(tmp_path):
    # 공식 구현은 같은 위치의 배열을 연결한다(arrays: "concat"). 정상 해석 가능한 병합은 미확정이 아니다.
    main = servers_cfg(tmp_path, {"$include": ["./a.json5", "./b.json5"]})
    w(tmp_path / "a.json5", {"s": {"command": "x", "args": ["--one"]}})
    w(tmp_path / "b.json5", {"s": {"args": ["--two"]}})
    t = target(main)
    assert t.refused is None and t.stdio.args == ["--one", "--two"]
    assert collect(main, REG, resolve_includes=True)["collection"]["status"] == "complete"


def test_array_concat_in_toolfilter_and_headers_areas_is_allowed_and_ordered(tmp_path):
    main = servers_cfg(tmp_path, {"$include": ["./a.json5", "./b.json5"]})
    w(tmp_path / "a.json5", {"s": {"url": "http://127.0.0.1:1/mcp", "toolFilter": {"include": ["a"]}}})
    w(tmp_path / "b.json5", {"s": {"toolFilter": {"include": ["b"]}}})
    assert refused_code(target(main)) is None
    scan = collect(main, REG, resolve_includes=True)["servers"][0]
    assert scan["declared"]["toolFilter"]["include"] == ["a", "b"]


def test_a_real_failure_next_to_a_healthy_array_merge_is_still_refused(tmp_path):
    main = servers_cfg(tmp_path, {"$include": ["./a.json5", "./b.json5", "./missing.json5"]})
    w(tmp_path / "a.json5", {"s": {"command": "x", "args": ["1"]}})
    w(tmp_path / "b.json5", {"s": {"args": ["2"]}})
    t = target(main)
    assert refused_code(t) == "include_unresolved" and t.refused["include_issue_codes"] == ["include_file_not_found"]


def test_circular_and_depth_problems_are_refused(tmp_path):
    main = servers_cfg(tmp_path, {"$include": "./a.json5"})
    w(tmp_path / "a.json5", {"s": {"$include": "./b.json5"}})
    w(tmp_path / "b.json5", {"$include": "./a.json5"})
    assert refused_code(target(main)) == "include_unresolved"
    deep = servers_cfg(tmp_path / "deep", {"$include": "./l1.json5"})
    for i in range(1, 12):
        w(tmp_path / "deep" / f"l{i}.json5", {"$include": f"./l{i + 1}.json5"} if i < 11 else {"s": {"command": "x"}})
    assert refused_code(target(deep)) == "include_unresolved"


def test_a_root_level_problem_affects_every_server(tmp_path):
    main = w(tmp_path / "openclaw.json", {"$include": "./missing.json5", "mcp": {"servers": {"s": {"command": "x"}}}})
    assert refused_code(target(main)) == "include_unresolved"


def test_without_the_option_includes_stay_unresolved_and_are_refused_as_before(tmp_path):
    main = servers_cfg(tmp_path, {"s": {"command": "x", "args": [{"$include": "./a.json5"}]}})
    t = build_config_target(main, "s", "mcp.servers", True, True, [], None)
    assert refused_code(t) in ("unresolved_reference", "declaration_type_invalid")


# ---- 영향이 없으면 허용(수집 결과는 partial) ---------------------------------------------------------------

def test_a_problem_in_another_server_does_not_block_the_selected_one_but_the_scan_is_partial(tmp_path):
    main = servers_cfg(tmp_path, {"s": {"command": "x"}, "other": {"$include": "./missing.json5"}})
    t = target(main)
    assert t.refused is None                                                         # 실행 허용 여부
    assert t.declaration["include_origin"]["issues"] == ["include_file_not_found"]   # 사유는 기록
    scan = collect(main, REG, resolve_includes=True)
    assert scan["collection"]["status"] == "partial"                                # 수집 결과 상태는 별개로 partial
    assert refused_code(target(main, "other")) == "include_unresolved"              # 문제가 있는 서버는 거부


def test_healthy_include_is_allowed_and_origin_is_recorded(tmp_path):
    main = servers_cfg(tmp_path, {"$include": "./servers.json5"})
    w(tmp_path / "servers.json5", {"s": {"url": "http://127.0.0.1:1/mcp"}})
    t = target(main)
    assert t.refused is None and t.declaration["include_origin"] == {"file": "servers.json5", "include_chain": ["servers.json5"], "issues": []}


def test_sibling_override_without_conflict_is_allowed(tmp_path):
    main = servers_cfg(tmp_path, {"$include": "./f.json5", "s": {"command": "from-main"}})
    w(tmp_path / "f.json5", {"s": {"command": "from-include", "cwd": "/w"}})
    t = target(main)
    assert t.refused is None and t.stdio.command == "from-main"                      # 문서의 병합 규칙(형제 키 우선)을 따른다
