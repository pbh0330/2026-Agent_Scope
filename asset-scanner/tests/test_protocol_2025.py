"""2025-11-25 응답에는 2026-07-28 전용 완료·캐시 필드를 요구하지 않는다."""

import json

import pytest

from asset_scanner.tools_catalog import collect_tools_catalog


def capture(tmp_path, pages, version="2025-11-25"):
    path = tmp_path / "capture.json"
    path.write_text(json.dumps({"servers": [{"server_ref": "server-a",
                                           "protocol_version": version, "pages": pages}]}), encoding="utf-8")
    return collect_tools_catalog(path)["servers"][0]


def tool(name="read_notes"):
    return {"name": name, "inputSchema": {"type": "object"}}


def test_legacy_plain_result_is_complete_without_newer_fields(tmp_path):
    s = capture(tmp_path, [{"tools": [tool()]}])
    assert s["collection_status"] == "complete"
    assert s["tool_count"] == 1
    assert s["spec_conformance"]["violations"] == []
    assert "result_type" not in s["pages"][0]
    assert "ttl_ms" not in s["pages"][0]
    assert s["tools"][0]["definition"] == tool()


def test_legacy_empty_result_is_a_successful_empty_list(tmp_path):
    s = capture(tmp_path, [{"tools": []}])
    assert (s["collection_status"], s["outcome"], s["tool_count"]) == ("complete", "empty_list", 0)


def test_legacy_pagination_uses_cursor_including_empty_string(tmp_path):
    s = capture(tmp_path, [{"tools": [tool("a")], "nextCursor": ""}, {"tools": [tool("b")]}])
    assert s["collection_status"] == "complete"
    assert [t["definition"]["name"] for t in s["tools"]] == ["a", "b"]


def test_legacy_unfetched_next_page_is_partial(tmp_path):
    s = capture(tmp_path, [{"tools": [tool()], "nextCursor": "next"}])
    assert s["collection_status"] == "partial"
    assert s["tool_count"] == 1
    assert "next_cursor_remaining" in {i["code"] for i in s["issues"]}


def test_legacy_server_error_does_not_erase_prior_page(tmp_path):
    s = capture(tmp_path, [{"tools": [tool()], "nextCursor": "next"},
                           {"error": {"code": -32603, "message": "failed"}}])
    assert s["collection_status"] == "partial"
    assert s["tool_count"] == 1


def test_legacy_extension_fields_do_not_impose_newer_semantics(tmp_path):
    s = capture(tmp_path, [{"tools": [tool()], "resultType": "vendor", "ttlMs": "vendor"}])
    assert s["collection_status"] == "complete"
    assert s["pages"][0]["other_result_fields"] == ["resultType", "ttlMs"]


def test_legacy_execution_is_a_known_preserved_field(tmp_path):
    definition = {**tool(), "execution": {"taskSupport": "required"}}
    s = capture(tmp_path, [{"tools": [definition]}])
    assert s["tools"][0]["definition"] == definition
    assert "execution" not in s["tools"][0]["other_definition_fields"]


def test_modern_missing_completion_fields_still_remains_partial(tmp_path):
    s = capture(tmp_path, [{"tools": [tool()]}], version="2026-07-28")
    assert s["collection_status"] == "partial"
    assert s["outcome"] == "completion_unverified"


@pytest.mark.parametrize("page", [{}, {"tools": {}}, {"tools": None}])
def test_legacy_invalid_tools_is_not_an_empty_success(tmp_path, page):
    assert capture(tmp_path, [page])["collection_status"] == "failed"


def test_legacy_redaction_and_definition_errors_are_preserved(tmp_path):
    s = capture(tmp_path, [{"tools": [{"name": "read_notes", "description": "Bearer FAKE_LEGACY_SECRET"}]}])
    assert s["collection_status"] == "complete"
    assert s["tools"][0]["definition_status"] == "failed_limited_checks"
    assert "FAKE_LEGACY_SECRET" not in json.dumps(s)


def test_unknown_version_is_still_unsupported(tmp_path):
    assert capture(tmp_path, [{"tools": [tool()]}], version="2099-01-01")["outcome"] == "protocol_version_unsupported"


@pytest.mark.parametrize("version", ["2025-11-25", "2026-07-28"])
@pytest.mark.parametrize("cursor", [None, 42, [], False])
def test_explicit_non_string_cursor_does_not_imply_last_page(tmp_path, version, cursor):
    page = {"tools": [tool()], "nextCursor": cursor}
    if version == "2026-07-28":
        page.update(resultType="complete", ttlMs=0, cacheScope="private")
    result = capture(tmp_path, [page], version=version)
    assert result["collection_status"] == "partial"
    assert result["tool_count"] == 1
    assert "next_cursor_invalid" in {i["code"] for i in result["issues"]}


def test_unknown_live_version_is_rejected_before_catalog_parsing():
    from asset_scanner.live_tools import _State, _build_server, LiveLimits
    state = _State(negotiated="2099-01-01")
    server = _build_server(state, "two-tools", LiveLimits(), 0)
    assert server["outcome"] == "protocol_version_unsupported"
    assert server["live"]["negotiation"]["supported_by_catalog"] is False
