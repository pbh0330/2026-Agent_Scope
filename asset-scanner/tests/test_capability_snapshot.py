"""저장 캡처 경로의 서버 능력·서버 정보 스냅샷 보존 테스트 (가상 캡처).

공격표면 정의서 11.1의 server capabilities·extensions는 실제 조회(`live_discovery`)에서는 서버가 보낸 값 그대로 보존된다.
저장 캡처 경로 중 `tools_catalog`도 입력에 제공된 `server_capabilities`·`server_info`를 **제공된 그대로**(가림 후) 옮기고,
제공되지 않으면 만들지 않는다. 입력에 적힌 값이며 스캐너가 서버에서 확인한 것이 아니다. 기존 `declared_capabilities`는 바뀌지 않는다.
"""

import json

from asset_scanner.resources_prompts import build_report as rp_report, collect_resources_prompts
from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog

V = "2025-11-25"
CAPS = {"tools": {"listChanged": True}, "resources": {"subscribe": True, "listChanged": False}, "prompts": {}, "extensions": {"vendor/x": {"level": 2}},
        "logging": {}}
INFO = {"name": "demo-server", "version": "0.1.0", "title": "Demo"}


def tools_cap(**extra):
    page = {"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "t", "inputSchema": {"type": "object"}}]}}
    return {"origin": "synthetic_test_data", "servers": [{"server_ref": "s", "protocol_version": V, "pages": [page], **extra}]}


def lists_cap(**extra):
    page = {"jsonrpc": "2.0", "id": 1, "result": {"resources": []}}
    return {"format": "mcp-lists-capture", "origin": "synthetic_test_data",
            "servers": [{"server_ref": "s", "protocol_version": V, "server_capabilities": {"resources": {}, "prompts": {}}, "lists": {"resources": {"pages": [page]}}, **extra}]}


def write(tmp_path, obj):
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / "c.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


def tools_srv(tmp_path, **extra):
    return build_catalog_report(collect_tools_catalog(write(tmp_path, tools_cap(**extra))))["servers"][0]


def lists_srv(tmp_path, **extra):
    return rp_report(collect_resources_prompts(write(tmp_path, lists_cap(**extra))))["servers"][0]


def test_tools_catalog_keeps_capabilities_and_server_info_as_provided(tmp_path):
    s = tools_srv(tmp_path, server_capabilities=CAPS, server_info=INFO, requested_protocol_version="2026-07-28")
    assert s["capabilities_as_provided"]["value"] == CAPS and s["server_info_as_provided"]["value"] == INFO
    for k in ("capabilities_as_provided", "server_info_as_provided"):
        assert s[k]["origin"] == "stored_capture_field" and s[k]["verified_by_scanner"] is False
    assert s["requested_protocol_version_as_provided"] == "2026-07-28" and s["declared_protocol_version"] == V


def test_resources_prompts_keeps_the_presence_summary_and_adds_the_provided_content_separately(tmp_path):
    s = lists_srv(tmp_path, server_capabilities=CAPS, server_info=INFO)
    assert s["declared_capabilities"]["resources"] == "declared" and s["declared_capabilities"]["prompts"] == "declared"     # 기존 요약 유지
    assert s["capabilities_as_provided"]["value"] == CAPS and s["server_info_as_provided"]["value"] == INFO


def test_nothing_is_created_when_the_input_does_not_provide_them(tmp_path):
    s = tools_srv(tmp_path)
    assert "capabilities_as_provided" not in s and "server_info_as_provided" not in s and "requested_protocol_version_as_provided" not in s


def test_secrets_inside_provided_values_are_masked(tmp_path):
    token = "ghp_FAKECAPSTOKEN1234567890abcdefghij"
    s = tools_srv(tmp_path, server_capabilities={"experimental": {"endpoint": f"https://u:FAKEPWCAP@example.com/x?key={token}"}}, server_info={"name": f"srv {token}"})
    text = json.dumps(s)
    assert token not in text and "FAKEPWCAP" not in text and s["redactions"]


def test_wrong_types_and_oversized_values_are_reported_not_stored(tmp_path):
    s = tools_srv(tmp_path, server_capabilities=["x"], server_info="x")
    assert s["capabilities_as_provided"] == {"status": "invalid_type", "type": "array", "origin": "stored_capture_field"} and s["server_info_as_provided"]["status"] == "invalid_type"
    big = tools_srv(tmp_path / "b", server_capabilities={"experimental": {"blob": "a" * 20000}})
    assert big["capabilities_as_provided"]["status"] == "too_large" and "aaaa" not in json.dumps(big["capabilities_as_provided"])
