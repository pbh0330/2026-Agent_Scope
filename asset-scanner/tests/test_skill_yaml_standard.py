"""YAML 1.2 핵심 문법의 직접 계산한 기대값. 입력은 모두 가상이다."""
import json

import pytest

from asset_scanner.skill_frontmatter import parse_frontmatter_lines
from asset_scanner.plugin_skill_assets import read_skill


def parse(text):
    return parse_frontmatter_lines(text.splitlines())


def test_plain_yaml_flow_maps_and_quoted_keys():
    result = parse('name: demo\nmetadata: {openclaw: {requires: {bins: [node, git]}, "emoji": hi}}')
    assert result["unparsed"] == []
    assert result["value"]["metadata"]["openclaw"]["requires"]["bins"] == ["node", "git"]


def test_aliases_and_merge_keep_explicit_override_and_are_independent_values():
    result = parse('base: &base {a: 1, b: 2}\ncopy: *base\nmerged: {<<: *base, b: 3}\nname: demo')
    assert result["unparsed"] == [] and result["duplicate_keys"] == []
    assert result["value"]["merged"] == {"a": 1, "b": 3}
    result["value"]["copy"]["a"] = 9
    assert result["value"]["base"]["a"] == 1


@pytest.mark.parametrize("key,value", [("off", "off"), ("yes", "yes"), ("on", "on"), ("date", "2026-11-18")])
def test_yaml12_does_not_turn_names_or_dates_into_non_json_objects(key, value):
    result = parse(f'{key}: {value}')
    assert result["value"] == {key: value}


def test_known_scalar_tags_are_data_but_python_tags_never_execute(tmp_path):
    marker = tmp_path / "must-not-exist"
    result = parse('name: !!str true\nnumber: !!int "42"\nbad: !!python/object/apply:builtins.open [' + json.dumps(str(marker)) + ']')
    assert result["value"] == {"name": "true", "number": 42}
    assert result["unparsed"] == ["bad"] and not marker.exists()


def test_recursive_alias_is_unparsed_and_other_fields_survive():
    result = parse('name: demo\na: &loop [*loop]\ndescription: ok')
    assert result["value"] == {"name": "demo", "description": "ok"} and result["unparsed"] == ["a"]


def test_alias_expansion_is_bounded_before_materializing_large_outputs():
    result = parse('a: &a [x,x,x,x,x,x,x,x,x,x]\nb: &b [*a,*a,*a,*a,*a,*a,*a,*a,*a,*a]\nc: [*b,*b,*b,*b,*b,*b,*b,*b,*b,*b,*b,*b,*b,*b,*b,*b,*b,*b,*b,*b]\nname: demo')
    assert result["value"]["name"] == "demo"
    assert "c" in result["unparsed"] and any(h["what"] == "nodes" for h in result["limit_hits"])


def test_real_duplicate_keys_still_have_evidence_and_last_explicit_value():
    result = parse('base: &b {x: 1}\nmerged: {<<: *b, x: 2, x: 3}')
    assert result["value"]["merged"] == {"x": 3} and "merged.x" in result["duplicate_keys"]


def test_metadata_anchor_is_collected_but_body_and_secret_values_are_not(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text('---\nname: demo\ndescription: demo\nbase: &b {requires: {bins: [git]}}\nmetadata: {openclaw: {<<: *b}}\n---\nFAKE_BODY_SECRET', encoding="utf-8")
    result = read_skill(p, "synthetic")
    assert result["metadata_openclaw"]["requires"]["bins"] == ["git"]
    assert "FAKE_BODY_SECRET" not in json.dumps(result)


def test_aliased_output_has_a_document_budget_across_many_top_level_keys():
    result = parse('seed: &seed [' + ','.join(['x'] * 100) + ']\n' + '\n'.join(f'copy{i}: *seed' for i in range(150)))
    assert any(h["what"] == "document_nodes" for h in result["limit_hits"])
    assert len(result["value"]) < 150


def test_valid_yaml_escape_and_leading_zero_decimal_are_not_json_restrictions():
    result = parse('description: "text\\eend"\nnumber: 012')
    assert result["value"] == {"description": "text\x1bend", "number": 12}


def test_unparsed_required_metadata_marks_collection_partial(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text('---\nname: demo\ndescription: good\nmetadata: &cycle {openclaw: *cycle}\n---\nbody')
    record = read_skill(p, "synthetic")
    assert record["collection_status"] == "partial" and "metadata" in record["frontmatter_unparsed_keys"]
