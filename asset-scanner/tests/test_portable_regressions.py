"""Regression cases for ordinary frontmatter and outgoing-message evidence."""
import json

import anyio
import pytest

from asset_scanner.plugin_skill_assets import collect_assets, parse_frontmatter
from asset_scanner.live_discovery import _State, _TapWriteStream


def parse(body):
    return parse_frontmatter("---\n" + body + "\n---\nbody")


def test_quoted_values_with_comments_preserve_hash_inside_quotes():
    values, unparsed, problem = parse('name: "demo" # display name\ndescription: "hello # world" # note')
    assert problem is None and unparsed == []
    assert values == {"name": "demo", "description": "hello # world"}


def test_flow_sequence_does_not_split_quoted_commas():
    values, unparsed, _ = parse('name: demo\nmetadata:\n  openclaw:\n    requires:\n      bins: [node, "a,b", \'c,d\']')
    assert unparsed == []
    assert values["metadata"]["openclaw"]["requires"]["bins"] == ["node", "a,b", "c,d"]


def test_folded_scalar_preserves_leading_blank_and_indented_paragraphs():
    values, unparsed, _ = parse('name: demo\ndescription: >\n\n  first\n  second\n\n    indented\n\n  last')
    assert unparsed == []
    assert values["description"] == "\nfirst second\n\n  indented\n\nlast\n"


def test_literal_scalar_preserves_leading_blank():
    values, unparsed, _ = parse('name: demo\ndescription: |\n\n  first\n  second')
    assert unparsed == [] and values["description"] == "\nfirst\nsecond\n"


def test_quoted_scalar_preserves_paragraphs():
    values, unparsed, _ = parse('name: demo\ndescription: "first\n\n  paragraph"')
    assert unparsed == [] and values["description"] == "first\nparagraph"


def test_plain_scalar_preserves_paragraphs():
    values, unparsed, _ = parse('name: demo\ndescription: first\n\n  paragraph')
    assert unparsed == [] and values["description"] == "first\nparagraph"


@pytest.mark.parametrize("value", ['"invalid\\qscape"', '"a" "b"', "'a' 'b'"])
def test_unsupported_quoted_syntax_is_not_silently_rewritten(value):
    values, unparsed, _ = parse("name: demo\ndescription: " + value)
    assert values == {"name": "demo"} and unparsed == ["description"]


def test_flow_nested_string_limit_is_reported():
    from asset_scanner.skill_frontmatter import MAX_STR, parse_frontmatter_lines

    result = parse_frontmatter_lines(["name: demo", "metadata: " + json.dumps({"value": "x" * (MAX_STR + 1)})])
    assert result["unparsed"] == ["metadata"]
    assert result["limit_hits"] == [{"key": "metadata", "what": "string"}]


def test_json5_metadata_fallback_retains_duplicate_key_evidence():
    from asset_scanner.skill_frontmatter import parse_frontmatter_lines

    result = parse_frontmatter_lines(["name: demo", "metadata:", '  {"openclaw": {"emoji": "a", "emoji": "b"}}'])
    assert result["unparsed"] == []
    assert result["duplicate_keys"] == ["metadata.openclaw.emoji"]


@pytest.mark.parametrize("block_form", [False, True])
def test_flow_collections_honor_depth_limit_including_json5_fallback(block_form):
    value = {"leaf": "x"}
    for _ in range(40):
        value = {"child": value}
    separator = "\n  " if block_form else " "
    values, unparsed, _ = parse("name: demo\nmetadata:" + separator + json.dumps(value))
    assert values["name"] == "demo"
    assert "metadata" in unparsed and "metadata" not in values


def test_flow_collections_honor_node_limit():
    values, unparsed, _ = parse("name: demo\nmetadata: " + json.dumps({"values": list(range(3000))}))
    assert values["name"] == "demo"
    assert "metadata" in unparsed and "metadata" not in values


def test_flow_duplicate_keys_are_reported_in_the_skill_result(tmp_path):
    directory = tmp_path / "demo"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        '---\nname: demo\ndescription: d\nmetadata: {"openclaw": {"emoji": "a", "emoji": "b"}}\n---\nbody',
        encoding="utf-8")
    result = collect_assets([], [directory], None, None, None)
    skill = result["skills"][0]
    assert skill["collection_status"] == "partial"
    assert any(issue["code"] == "duplicate_key" for issue in skill["issues"])


def test_outgoing_evidence_is_recorded_only_after_successful_forwarding():
    state = _State()
    message = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}}

    class Writer:
        async def send(self, forwarded):
            assert forwarded is message
            assert state.client_sent is None

    anyio.run(_TapWriteStream(Writer(), state).send, message)
    assert state.client_sent["mode"] == "initialize_request"
    assert state.client_sent["client_info"] == {"name": "test", "version": "1"}


def test_failed_forwarding_does_not_claim_capabilities_were_sent():
    state = _State()
    message = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"capabilities": {}}}

    class Writer:
        async def send(self, forwarded):
            raise RuntimeError("synthetic send failure")

    with pytest.raises(RuntimeError, match="synthetic send failure"):
        anyio.run(_TapWriteStream(Writer(), state).send, message)
    assert state.client_sent is None
