"""`$include` 해석을 OpenClaw 공식 구현·테스트에 맞춰 검증한다.

기대값의 근거(스캐너 구현이 아니라 공식 소스에서 정함): openclaw/openclaw `eb377ac59e6c9fd6c7705028034812becf00271b`의
`src/config/includes.ts`(`deepMerge = mergeDeep(..., {arrays: "concat", undefinedValues: "replace"})`),
`src/infra/deep-merge.ts`, `src/config/includes.test.ts`(`resolveConfigIncludes` 케이스). 해당 케이스의 입력·기대값을 옮기고,
deep-merge.ts의 분기(자료형 충돌·null·금지 키)는 소스를 읽고 손으로 계산한 값이다. 가상 설정만 사용한다.
"""

import json
import os
import sys

import pytest

from asset_scanner.collector import parse_config, read_config
from asset_scanner.config_includes import resolve_includes


def setup(tmp_path, obj, files=None, config="openclaw.json"):
    cfg = tmp_path / config
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
    for rel, content in (files or {}).items():
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return cfg


def resolve(tmp_path, obj, files=None, config="openclaw.json"):
    cfg = setup(tmp_path, obj, files, config)
    return resolve_includes(cfg, parse_config(read_config(cfg)))


def plain(x):
    return json.loads(json.dumps(x))


def codes(ctx):
    return [i["code"] for i in ctx.issues]


# ---- includes.test.ts: "resolves include merges" --------------------------------------------------------

def test_single_file_include(tmp_path):
    ctx = resolve(tmp_path, {"agents": {"$include": "./agents.json"}}, {"agents.json": {"list": [{"id": "main"}]}})
    assert plain(ctx.root) == {"agents": {"list": [{"id": "main"}]}} and not ctx.issues


def test_array_include_deep_merge(tmp_path):
    files = {"a.json": {"group-a": ["agent1"]}, "b.json": {"group-b": ["agent2"]}}
    ctx = resolve(tmp_path, {"broadcast": {"$include": ["./a.json", "./b.json"]}}, files)
    assert plain(ctx.root) == {"broadcast": {"group-a": ["agent1"], "group-b": ["agent2"]}}


def test_array_include_overlapping_keys_at_root(tmp_path):
    files = {"a.json": {"agents": {"defaults": {"workspace": "~/a"}}}, "b.json": {"agents": {"list": [{"id": "main"}]}}}
    ctx = resolve(tmp_path, {"$include": ["./a.json", "./b.json"]}, files)
    assert plain(ctx.root) == {"agents": {"defaults": {"workspace": "~/a"}, "list": [{"id": "main"}]}}


@pytest.mark.parametrize("obj, expected", [
    ({"$include": "./base.json", "c": 3}, {"a": 1, "b": 2, "c": 3}),            # adds sibling keys after include
    ({"$include": "./base.json", "b": 99}, {"a": 1, "b": 99}),                    # lets siblings override included keys
])
def test_sibling_keys_merge_after_the_include(tmp_path, obj, expected):
    assert plain(resolve(tmp_path, obj, {"base.json": {"a": 1, "b": 2}}).root) == expected


@pytest.mark.parametrize("inc, content", [("list.json", ["a", "b"]), ("value.json", '"hello"')])
def test_sibling_keys_with_a_non_object_include_are_an_error(tmp_path, inc, content):
    ctx = resolve(tmp_path, {"$include": f"./{inc}", "extra": True}, {inc: content})
    assert "include_non_object_with_siblings" in codes(ctx)                        # 공식: ConfigIncludeError


def test_nested_includes_and_nested_override_ordering(tmp_path):
    files = {"base.json": {"nested": {"$include": "./nested.json"}}, "nested.json": {"a": 1, "b": 2}}
    ctx = resolve(tmp_path, {"$include": "./base.json", "nested": {"b": 9}}, files)
    assert plain(ctx.root) == {"nested": {"a": 1, "b": 9}}                        # "preserves nested override ordering"
    assert not ctx.issues


def test_real_world_per_client_layout_concatenates_arrays_in_order(tmp_path):
    files = {
        "clients/mueller.json": {"agents": [{"id": "mueller-screenshot", "workspace": "~/clients/mueller/screenshot"},
                                            {"id": "mueller-transcribe", "workspace": "~/clients/mueller/transcribe"}],
                                 "broadcast": {"group-mueller": ["mueller-screenshot", "mueller-transcribe"]}},
        "clients/schmidt.json": {"agents": [{"id": "schmidt-screenshot", "workspace": "~/clients/schmidt/screenshot"}],
                                 "broadcast": {"group-schmidt": ["schmidt-screenshot"]}},
    }
    ctx = resolve(tmp_path, {"gateway": {"port": 18789}, "$include": ["./clients/mueller.json", "./clients/schmidt.json"]}, files)
    assert plain(ctx.root) == {
        "gateway": {"port": 18789},
        "agents": [{"id": "mueller-screenshot", "workspace": "~/clients/mueller/screenshot"},
                   {"id": "mueller-transcribe", "workspace": "~/clients/mueller/transcribe"},
                   {"id": "schmidt-screenshot", "workspace": "~/clients/schmidt/screenshot"}],
        "broadcast": {"group-mueller": ["mueller-screenshot", "mueller-transcribe"], "group-schmidt": ["schmidt-screenshot"]},
    }


def test_modular_config_structure(tmp_path):
    files = {"gateway.json": {"gateway": {"port": 18789, "bind": "loopback"}},
             "channels/whatsapp.json": {"channels": {"whatsapp": {"dmPolicy": "pairing", "allowFrom": ["+49123"]}}},
             "agents/defaults.json": {"agents": {"defaults": {"sandbox": {"mode": "all"}}}}}
    ctx = resolve(tmp_path, {"$include": ["./gateway.json", "./channels/whatsapp.json", "./agents/defaults.json"]}, files)
    assert plain(ctx.root) == {"gateway": {"port": 18789, "bind": "loopback"},
                               "channels": {"whatsapp": {"dmPolicy": "pairing", "allowFrom": ["+49123"]}},
                               "agents": {"defaults": {"sandbox": {"mode": "all"}}}}


def test_prototype_pollution_keys_are_dropped_in_included_and_sibling_config(tmp_path):
    inc = '{"__proto__":{"polluted":true},"constructor":{"hidden":true},"normal":3}'
    main = '{"$include":"./pollution.json","__proto__":{"alsoPolluted":true},"safe":1}'
    ctx = resolve(tmp_path, main, {"pollution.json": inc})
    assert plain(ctx.root) == {"normal": 3, "safe": 1}


# ---- deep-merge.ts 분기(소스를 읽고 손으로 계산) ------------------------------------------------------------

def test_arrays_concatenate_in_include_order_keeping_duplicates_across_three_files(tmp_path):
    files = {"a.json": {"l": [1, "x"]}, "b.json": {"l": ["x", 2]}, "c.json": {"l": [1]}}
    ctx = resolve(tmp_path, {"$include": ["./a.json", "./b.json", "./c.json"]}, files)
    assert plain(ctx.root) == {"l": [1, "x", "x", 2, 1]}                          # 중복 제거 없음, 순서 그대로


def test_sibling_arrays_are_appended_after_the_included_arrays(tmp_path):
    ctx = resolve(tmp_path, {"$include": "./base.json", "list": [3]}, {"base.json": {"list": [1, 2]}})
    assert plain(ctx.root) == {"list": [1, 2, 3]}                                   # deepMerge(included, rest): concat


def test_top_level_arrays_from_two_includes_concatenate_but_array_then_object_is_replaced(tmp_path):
    ctx = resolve(tmp_path, {"x": {"$include": ["./a.json", "./b.json"]}, "y": {"$include": ["./a.json", "./obj.json"]}},
                  {"a.json": [1], "b.json": [2], "obj.json": {"k": 1}})
    assert plain(ctx.root) == {"x": [1, 2], "y": {"k": 1}}                          # 객체가 뒤라면 객체가 대체


@pytest.mark.parametrize("first, second, expected", [
    ({"v": {"k": 1}}, {"v": 5}, {"v": 5}),                    # 객체 → 스칼라: 뒤가 이김
    ({"v": 5}, {"v": {"k": 1}}, {"v": {"k": 1}}),             # 스칼라 → 객체: 객체가 대체
    ({"v": [1]}, {"v": {"k": 1}}, {"v": {"k": 1}}),           # 배열 → 객체
    ({"v": {"k": 1}}, {"v": [1]}, {"v": [1]}),                # 객체 → 배열
    ({"v": {"k": 1}}, {"v": None}, {"v": None}),              # null이 대체
    ({"v": None}, {"v": {"k": 1}}, {"v": {"k": 1}}),
    ({"v": {"a": 1, "n": {"x": [1]}}}, {"v": {"b": 2, "n": {"x": [2], "y": 3}}}, {"v": {"a": 1, "b": 2, "n": {"x": [1, 2], "y": 3}}}),   # 재귀 병합
])
def test_type_conflicts_follow_deep_merge_semantics(tmp_path, first, second, expected):
    ctx = resolve(tmp_path, {"$include": ["./a.json", "./b.json"]}, {"a.json": first, "b.json": second})
    assert plain(ctx.root) == expected and not ctx.issues                            # 정상 병합이므로 이슈(partial)가 없다


def test_type_conflicts_are_noted_not_reported_as_issues(tmp_path):
    ctx = resolve(tmp_path, {"$include": ["./a.json", "./b.json"]}, {"a.json": {"v": [1]}, "b.json": {"v": {"k": 1}}})
    assert any(n["code"] == "type_conflict_later_value_wins" and n["field_path"] == "v" for n in ctx.notes) and not ctx.issues


# ---- 실제 실패(공식은 오류) ---------------------------------------------------------------------------------

def test_depth_ten_files_are_allowed_but_eleven_fail(tmp_path):
    ok = {f"ok{i}.json": ({"$include": f"./ok{i + 1}.json"} if i < 9 else {"done": True}) for i in range(10)}
    assert plain(resolve(tmp_path / "ok", {"$include": "./ok0.json"}, ok).root) == {"done": True}
    fail = {f"fail{i}.json": ({"$include": f"./fail{i + 1}.json"} if i < 10 else {"done": True}) for i in range(11)}
    ctx = resolve(tmp_path / "fail", {"$include": "./fail0.json"}, fail)
    assert "include_depth_exceeded" in codes(ctx)


def test_traversal_boundary_and_safe_nested_parent_paths(tmp_path):
    root = tmp_path / "cfg"
    ctx = resolve(root, {"$include": "../shared/common.json"}, {}, config="sub/openclaw.json")
    w = tmp_path / "x"
    assert "include_path_outside_root" in codes(ctx)
    ok = resolve(w, {"$include": "./sub/child.json"}, {"sub/child.json": {"$include": "../shared/common.json"}, "shared/common.json": {"shared": True}})
    assert plain(ok.root) == {"shared": True} and not ok.issues


def test_circular_null_byte_length_and_missing_path(tmp_path):
    assert "include_circular" in codes(resolve(tmp_path / "c", {"$include": "./a.json"}, {"a.json": {"$include": "./b.json"}, "b.json": {"$include": "./a.json"}}))
    assert "include_path_invalid" in codes(resolve(tmp_path / "n", {"$include": "./file\x00.json"}))
    assert "include_path_too_long" in codes(resolve(tmp_path / "l1", {"$include": "a" * 4096}))
    assert "include_path_too_long" in codes(resolve(tmp_path / "l2", {"$include": "b" * 4097}))
    assert "include_file_not_found" in codes(resolve(tmp_path / "m", {"$include": "./nope.json"}))


def test_invalid_include_value_and_array_item_types(tmp_path):
    assert "include_type_invalid" in codes(resolve(tmp_path / "t1", {"$include": 5}))
    assert "include_type_invalid" in codes(resolve(tmp_path / "t2", {"$include": ["./a.json", 3]}, {"a.json": {}}))


def test_file_over_two_megabytes_is_rejected(tmp_path):
    big = '{"blob":"' + "a" * (2 * 1024 * 1024 + 1) + '"}'
    assert "include_file_too_large" in codes(resolve(tmp_path, {"$include": "./big.json5"}, {"big.json5": big}))


@pytest.mark.skipif(sys.platform == "win32", reason="공식 테스트도 win32에서 건너뜀(하드링크)")
def test_hardlinked_include_file_is_rejected(tmp_path):
    outside = tmp_path / "outside.json5"
    outside.write_text('{"logging":{"redactSensitive":"tools"}}', encoding="utf-8")
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    try:
        os.link(outside, cfg_dir / "extra.json5")
    except OSError:
        pytest.skip("하드링크를 만들 수 없는 파일시스템")
    ctx = resolve(cfg_dir, {"$include": "./extra.json5"})
    assert "include_hardlink_rejected" in codes(ctx)


# ---- 배열 원소별 출처 ----------------------------------------------------------------------------------------

def test_each_array_element_keeps_its_own_origin_after_concatenation(tmp_path):
    files = {"a.json": {"l": [{"id": "x1"}, {"id": "x2"}]}, "sub/b.json": {"l": [{"id": "y1"}]}}
    ctx = resolve(tmp_path, {"$include": ["./a.json", "./sub/b.json"], "l": [{"id": "z1"}]}, files)
    assert [e["id"] for e in ctx.root["l"]] == ["x1", "x2", "y1", "z1"]
    got = [ctx.origin_of(("l", i)) for i in range(4)]
    assert got == [("a.json", ("a.json",)), ("a.json", ("a.json",)), ("sub/b.json", ("sub/b.json",)), ("(top-level config)", ())]
    assert ctx.origin_of(("l", 2, "id")) == ("sub/b.json", ("sub/b.json",))        # 원소 안쪽 값도 같은 출처


def test_object_keys_from_several_includes_and_siblings_keep_per_key_origin(tmp_path):
    files = {"a.json": {"p": {"keep": 1, "over": "a"}, "only_a": True}, "b.json": {"p": {"over": "b"}, "only_b": True}}
    ctx = resolve(tmp_path, {"$include": ["./a.json", "./b.json"], "p": {"over": "main", "extra": 1}}, files)
    assert plain(ctx.root)["p"] == {"keep": 1, "over": "main", "extra": 1}
    assert ctx.origin_of(("p", "keep"))[0] == "a.json" and ctx.origin_of(("p", "over"))[0] == "(top-level config)"
    assert ctx.origin_of(("only_a",))[0] == "a.json" and ctx.origin_of(("only_b",))[0] == "b.json" and ctx.origin_of(("p", "extra"))[0] == "(top-level config)"


def test_nested_include_chain_is_kept_for_elements(tmp_path):
    files = {"a.json": {"l": [1], "n": {"$include": "./sub/c.json"}}, "sub/c.json": {"m": [{"$include": "../d.json"}]}, "d.json": {"deep": True}}
    ctx = resolve(tmp_path, {"$include": "./a.json"}, files)
    assert plain(ctx.root) == {"l": [1], "n": {"m": [{"deep": True}]}}
    assert ctx.origin_of(("n", "m", 0, "deep")) == ("d.json", ("a.json", "sub/c.json", "d.json"))
    assert ctx.origin_of(("l", 0)) == ("a.json", ("a.json",))
