"""URL 원문 보존과 `definition_altered` 정확성 회귀 테스트 (가상 자료).

배경: Tool 정의의 `$schema`(`http://json-schema.org/draft-07/schema#`) 끝 `#`이 URL 재조립(urlsplit→urlunsplit)에서
조용히 사라지는데 `definition_altered`는 false였다. 비밀값이 없는 URL은 원문 그대로 보존하고, 실제로 바뀐 정의는
바뀐 사실과 사유를 기록해야 한다.
"""

import json

import pytest

from asset_scanner.redaction import Redactor
from asset_scanner.resources_prompts import build_report, collect_resources_prompts
from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog

V = "2026-07-28"
SAFE_URLS = [
    "http://json-schema.org/draft-07/schema#",
    "https://json-schema.org/draft/2020-12/schema",
    "https://example.com/a/b?",                 # 빈 query 표식
    "https://example.com/a#",                   # 빈 fragment 표식
    "https://example.com:8443/mcp",
    "https://Example.COM/Path/%7Euser",         # 대소문자·퍼센트 인코딩 그대로
    "file:///srv/docs/readme.md",
]


@pytest.mark.parametrize("url", SAFE_URLS)
def test_url_without_secrets_is_preserved_byte_for_byte(url):
    red = Redactor()
    assert red.sanitize_string(url, "x") == url
    assert red.sanitize_text(f"see {url} now", "x") == f"see {url} now"
    assert red.redactions == []


@pytest.mark.parametrize("url,reason", [
    ("https://user:pw123@example.com/a", "url_userinfo"),
    ("https://example.com/a?token=abc", "url_query_values"),
    ("https://example.com/a#frag", "url_fragment"),
])
def test_existing_url_secret_redaction_is_kept(url, reason):
    red = Redactor()
    out = red.sanitize_string(url, "x")
    assert "pw123" not in out and "abc" not in out and "frag" not in out
    assert any(r["reason"] == reason for r in red.redactions)


def test_redacted_url_that_also_loses_an_empty_marker_records_the_reserialization():
    red = Redactor()
    out = red.sanitize_string("https://user:pw123@example.com/a#", "x")
    assert "pw123" not in out
    reasons = {r["reason"] for r in red.redactions}
    assert "url_userinfo" in reasons


def _write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


def _tool_report(tmp_path, schema):
    tool = {"name": "t", "inputSchema": {"$schema": schema, "type": "object"}}
    cap = {"origin": "synthetic_test_data", "servers": [{"server_ref": "s", "protocol_version": V, "pages": [
        {"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "tools": [tool], "ttlMs": 1, "cacheScope": "public"}}]}]}
    rep = build_catalog_report(collect_tools_catalog(_write(tmp_path, "c.json", cap)))
    return tool, rep["servers"][0]["tools"][0]


def test_tool_definition_keeps_schema_url_and_is_not_marked_altered(tmp_path):
    tool, out = _tool_report(tmp_path, "http://json-schema.org/draft-07/schema#")
    assert out["definition"] == tool
    assert out["definition_altered"] is False and out["redactions"] == []


def test_tool_definition_with_real_redaction_records_change_and_reason(tmp_path):
    tool, out = _tool_report(tmp_path, "https://user:pw123@example.com/s#")
    assert out["definition"] != tool and "pw123" not in json.dumps(out["definition"])
    assert out["definition_altered"] is True
    assert out["alteration"]["altered"] is True and "url_userinfo" in out["alteration"]["reasons"]
    assert out["alteration"]["difference_without_recorded_reason"] is False


def test_unaltered_tool_has_an_empty_alteration_record(tmp_path):
    _, out = _tool_report(tmp_path, "https://json-schema.org/draft/2020-12/schema")
    assert out["alteration"] == {"altered": False, "reasons": [], "difference_without_recorded_reason": False}


def test_resource_and_prompt_definitions_keep_urls_and_report_alteration(tmp_path):
    items = {
        "resources": [{"uri": "https://example.com/a#", "name": "r", "icons": [{"src": "https://example.com/i.png?"}]}],
        "resourceTemplates": [{"uriTemplate": "https://example.com/{id}#", "name": "t"}],
        "prompts": [{"name": "p", "description": "see https://example.com/doc#"}],
    }
    lists = {}
    for key, kind in (("resources", "resources"), ("resourceTemplates", "resource_templates"), ("prompts", "prompts")):
        lists[kind] = {"pages": [{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", key: items[key], "ttlMs": 1, "cacheScope": "public"}}]}
    cap = {"format": "mcp-lists-capture", "origin": "synthetic_test_data",
           "servers": [{"server_ref": "s", "protocol_version": V, "lists": lists}]}
    rep = build_report(collect_resources_prompts(_write(tmp_path, "l.json", cap)))
    for kind in ("resources", "resource_templates", "prompts"):
        it = rep["servers"][0]["lists"][kind]["items"][0]
        assert it["definition_altered"] is False and it["redactions"] == []
    res = rep["servers"][0]["lists"]["resources"]["items"][0]["definition"]
    assert res["uri"] == "https://example.com/a#" and res["icons"][0]["src"] == "https://example.com/i.png?"
    assert rep["servers"][0]["lists"]["prompts"]["items"][0]["definition"]["description"] == "see https://example.com/doc#"
