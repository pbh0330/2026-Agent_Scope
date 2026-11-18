"""SKILL.md frontmatter의 YAML 해석 보완 테스트 (가상 SKILL.md).

근거: OpenClaw 2026.9.6 `docs/tools/skills.md` "SKILL.md format" — frontmatter는 YAML을 먼저 해석한다. 기대값은 YAML 1.2의 블록 스칼라
규칙(literal `|`, folded `>`, chomping `-`/`+`/기본, 들여쓰기 지시자)에서 손으로 계산했다. 임의 코드 실행이 없는 자체 해석기이며
별칭·앵커·태그는 확장하지 않는다(해석하지 못한 키로 남김).
"""

import json
import time

import pytest

from asset_scanner.plugin_skill_assets import build_report, collect_assets, parse_frontmatter
from test_plugin_skill_assets import make_skill


def fm(body: str):
    return parse_frontmatter("---\n" + body + "\n---\nbody")


# ---- 블록 스칼라 ------------------------------------------------------------------------------------------

def test_folded_scalar_joins_lines_with_spaces_and_keeps_paragraph_breaks():
    v, unparsed, problem = fm("name: n\ndescription: >\n  first line\n  second line\n\n  next paragraph\nhomepage: https://example.com/x")
    assert problem is None and unparsed == []
    assert v["description"] == "first line second line\nnext paragraph\n"           # clip: 끝 개행 하나
    assert v["homepage"] == "https://example.com/x"                                    # 다음 키는 영향 없음


@pytest.mark.parametrize("header, expected", [
    ("|", "a\n  b\nc\n"),            # literal: 줄바꿈·들여쓰기 보존, clip
    ("|-", "a\n  b\nc"),            # strip
    ("|+", "a\n  b\nc\n\n"),        # keep: 뒤의 빈 줄 하나 보존
    (">-", "a\n  b\nc"),            # folded: 더 들여쓴 줄은 줄바꿈 유지, strip
])
def test_block_scalar_headers_and_chomping(header, expected):
    v, unparsed, _ = fm(f"name: n\ndescription: {header}\n  a\n    b\n  c\n\nother: x")
    assert unparsed == [] and v["description"] == expected and v["other"] == "x"


def test_indentation_indicator_and_empty_block():
    v, unparsed, _ = fm("name: n\ndescription: |2\n    keep two\n  base\nz: 1")
    assert unparsed == [] and v["description"] == "  keep two\nbase\n"
    e, unparsed, _ = fm("name: n\ndescription: |\nz: 1")
    assert unparsed == [] and e["description"] == "" and e["z"] == 1


def test_multiline_plain_and_double_quoted_scalars_fold():
    v, unparsed, _ = fm('name: n\ndescription: first part\n  second part\nnote: "quoted\n  continues"')
    assert unparsed == [] and v["description"] == "first part second part" and v["note"] == "quoted continues"


# ---- 중첩 메타데이터 --------------------------------------------------------------------------------------

def test_nested_metadata_with_lists_of_mappings_and_block_lists():
    body = """name: n
description: d
metadata:
  openclaw:
    skillKey: my-key
    requires:
      bins:
        - git
        - node
      env: [A_ENV, B_ENV]
    install:
      - kind: brew
        formula: foo
      - kind: node
        package: bar
    os: [linux]"""
    v, unparsed, _ = fm(body)
    oc = v["metadata"]["openclaw"]
    assert unparsed == [] and oc["skillKey"] == "my-key"
    assert oc["requires"] == {"bins": ["git", "node"], "env": ["A_ENV", "B_ENV"]}
    assert oc["install"] == [{"kind": "brew", "formula": "foo"}, {"kind": "node", "package": "bar"}] and oc["os"] == ["linux"]


def test_metadata_block_scalar_inside_nested_mapping():
    v, unparsed, _ = fm("name: n\nmetadata:\n  openclaw:\n    note: |\n      line1\n      line2\n    emoji: x")
    assert unparsed == [] and v["metadata"]["openclaw"]["note"] == "line1\nline2\n" and v["metadata"]["openclaw"]["emoji"] == "x"


def test_json5_style_metadata_block_still_works():
    v, unparsed, _ = fm('name: n\nmetadata:\n  {"openclaw": {"emoji": "e",\n   "always": true}}')
    assert unparsed == [] and v["metadata"] == {"openclaw": {"emoji": "e", "always": True}}


# ---- 안전성: 별칭·한도·중복 -------------------------------------------------------------------------------

def test_anchors_aliases_and_tags_are_not_expanded_and_the_keys_are_reported():
    v, unparsed, _ = fm("name: n\nbase: &a [1, 2]\ncopy: *a\ntagged: !!python/object/apply:os.system [x]\nok: fine")
    assert set(unparsed) == {"base", "copy", "tagged"} and v["ok"] == "fine" and "copy" not in v and "tagged" not in v


def test_alias_bomb_is_cheap_because_nothing_is_expanded():
    lines = ["name: n", "a0: &a0 [x]"] + [f"a{i}: &a{i} [*a{i - 1}, *a{i - 1}]" for i in range(1, 30)]
    t0 = time.perf_counter()
    v, unparsed, _ = fm("\n".join(lines))
    assert time.perf_counter() - t0 < 1.0 and len(unparsed) == 30 and v == {"name": "n"}


def test_duplicate_keys_are_reported_at_top_level_and_nested(tmp_path):
    d = make_skill(tmp_path, "s", "---\nname: s\nname: t\ndescription: d\nmetadata:\n  openclaw:\n    emoji: a\n    emoji: b\n---\nb")
    rep = build_report(collect_assets([], [d], None, None, None))
    issues = rep["skills"][0]["issues"]
    dups = [i for i in issues if i["code"] == "duplicate_key"]
    assert dups and {"name", "metadata.openclaw.emoji"} <= {k for i in dups for k in i["keys"]}
    assert rep["skills"][0]["collection_status"] != "complete"


def test_nesting_depth_and_node_limits_are_enforced():
    deep = "name: n\nmetadata:\n" + "".join("  " * (i + 1) + f"k{i}:\n" for i in range(40)) + "  " * 41 + "leaf: 1"
    v, unparsed, _ = fm(deep)
    assert "metadata" in unparsed and v["name"] == "n"
    many = "name: n\nmetadata:\n  list:\n" + "".join(f"    - x{i}\n" for i in range(3000)).rstrip("\n")
    v2, unparsed2, _ = fm(many)
    assert "metadata" in unparsed2


def test_tab_indentation_and_complex_keys_are_not_guessed():
    v, unparsed, _ = fm("name: n\nmetadata:\n\topenclaw:\n\t\temoji: x\n? complex\n: key\nok: 1")
    assert "metadata" in unparsed and v["ok"] == 1


# ---- 비밀값·저장 범위 -------------------------------------------------------------------------------------

def test_secrets_inside_multiline_values_are_masked_and_body_is_not_stored(tmp_path):
    token = "ghp_FAKEFRONTMATTERTOKEN1234567890abcdefgh"
    d = make_skill(tmp_path, "s", f"---\nname: s\ndescription: |\n  use this skill\n  token {token}\n---\nSECRETBODYTEXT")
    rep = build_report(collect_assets([], [d], None, None, None))
    text = json.dumps(rep, ensure_ascii=False)
    assert token not in text and "SECRETBODYTEXT" not in text
    assert rep["skills"][0]["frontmatter"]["description"].startswith("use this skill")
    assert rep["skills"][0]["redactions"]


def test_required_description_is_present_when_written_as_a_block_scalar(tmp_path):
    d = make_skill(tmp_path, "s", "---\nname: s\ndescription: >\n  folded\n  text\n---\nb")
    s = build_report(collect_assets([], [d], None, None, None))["skills"][0]
    assert s["frontmatter"]["description"] == "folded text\n" and "frontmatter_unparsed_keys" not in s
    assert not [i for i in s["issues"] if i["code"] == "required_field_missing"]
