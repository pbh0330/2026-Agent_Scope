"""client capabilities 기록 테스트.

- 직접 조회(`live_discovery`): 스캐너의 SDK 클라이언트가 **실제로 서버에 보낸** initialize(또는 요청별 `_meta`)의 값을 기록한다.
  이 값을 OpenClaw 클라이언트의 능력으로 표시하지 않는다(`is_openclaw_client: false`, `sender` 명시).
- 저장 캡처(`tools_catalog`·`resources_prompts`): 입력에 **제공된** `client_capabilities`·`client_info`와 출처(`client_sender`)만 기록하고, 없으면 만들지 않는다.
시험 서버는 프로젝트의 개발용 서버(로컬 stdio)이며 팀 테스트베드·OpenClaw가 아니다.
"""

import json
import pathlib
import tempfile

from asset_scanner.live_discovery import DiscoveryLimits, build_config_target, build_demo_target, build_report, discover
from asset_scanner.resources_prompts import build_report as rp_report, collect_resources_prompts
from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog

FAST = DiscoveryLimits(total_timeout_s=45, request_timeout_s=10, connect_timeout_s=20)
V = "2025-11-25"
CLIENT_CAPS = {"roots": {"listChanged": True}, "sampling": {}}


def write(tmp_path, obj):
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / "c.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


def tools_srv(tmp_path, **extra):
    page = {"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "t", "inputSchema": {"type": "object"}}]}}
    cap = {"origin": "synthetic_test_data", "servers": [{"server_ref": "s", "protocol_version": V, "pages": [page], **extra}]}
    return build_catalog_report(collect_tools_catalog(write(tmp_path, cap)))["servers"][0]


def lists_srv(tmp_path, **extra):
    page = {"jsonrpc": "2.0", "id": 1, "result": {"resources": []}}
    cap = {"format": "mcp-lists-capture", "origin": "synthetic_test_data",
           "servers": [{"server_ref": "s", "protocol_version": V, "server_capabilities": {"resources": {}}, "lists": {"resources": {"pages": [page]}}, **extra}]}
    return rp_report(collect_resources_prompts(write(tmp_path, cap)))["servers"][0]


# ---- 저장 캡처 ------------------------------------------------------------------------------------------

def test_stored_capture_records_provided_client_values_with_their_stated_sender(tmp_path):
    info = {"name": "some-client", "version": "1"}
    for srv in (tools_srv(tmp_path / "t", client_capabilities=CLIENT_CAPS, client_info=info, client_sender="openclaw-gateway"),
                lists_srv(tmp_path / "l", client_capabilities=CLIENT_CAPS, client_info=info, client_sender="openclaw-gateway")):
        c = srv["client_capabilities_as_provided"]
        assert c["value"] == CLIENT_CAPS and c["origin"] == "stored_capture_field" and c["sender"] == "openclaw-gateway" and c["verified_by_scanner"] is False
        assert srv["client_info_as_provided"]["value"]["name"] == "some-client"


def test_stored_capture_does_not_assume_who_sent_the_values_or_invent_missing_ones(tmp_path):
    srv = tools_srv(tmp_path / "a", client_capabilities=CLIENT_CAPS)
    assert srv["client_capabilities_as_provided"]["sender"] == "not_stated_in_capture"
    for s in (tools_srv(tmp_path / "b"), lists_srv(tmp_path / "c")):
        assert "client_capabilities_as_provided" not in s and "client_info_as_provided" not in s


def test_stored_client_values_are_masked_and_wrong_types_are_reported(tmp_path):
    token = "ghp_FAKECLIENTTOKEN1234567890abcdefgh"
    s = tools_srv(tmp_path / "m", client_capabilities={"experimental": {"u": "https://x:FAKEPWCLIENT@example.com/?k=" + token}}, client_info="x")
    text = json.dumps(s)
    assert token not in text and "FAKEPWCLIENT" not in text
    assert s["client_info_as_provided"]["status"] == "invalid_type" and "value" not in s["client_info_as_provided"]


# ---- resources_prompts: 서버 능력·정보 보존(기존 요약 유지) -------------------------------------------------------

def test_resources_prompts_keeps_the_summary_and_preserves_provided_server_values_separately(tmp_path):
    caps = {"resources": {"listChanged": True, "x-extra": "kept"}, "extensions": {"vendor/x": {"a": 1}}}
    s = lists_srv(tmp_path / "s", server_capabilities=caps, server_info={"name": "demo", "version": "1"})
    assert s["declared_capabilities"] == {"resources": "declared", "prompts": "not_declared", "source": "stored_in_input_not_verified"}   # 기존 요약 유지
    assert s["capabilities_as_provided"]["value"] == caps and s["server_info_as_provided"]["value"] == {"name": "demo", "version": "1"}
    assert s["capabilities_as_provided"]["verified_by_scanner"] is False and "x-extra" not in json.dumps(s["declared_capabilities"])
    assert s["lists"]["resources"]["collection_status"] == "complete"                                    # 목록 판정에 영향 없음


def test_resources_prompts_masks_secrets_in_preserved_values_and_creates_nothing_when_absent(tmp_path):
    token = "ghp_FAKESERVERCAPTOKEN1234567890abcdef"
    s = lists_srv(tmp_path / "x", server_capabilities={"resources": {}, "experimental": {"u": "https://u:FAKEPWSRV@example.com/?k=" + token}})
    assert token not in json.dumps(s) and "FAKEPWSRV" not in json.dumps(s) and s["redactions"]
    assert "server_info_as_provided" not in lists_srv(tmp_path / "y")                                    # 입력에 없으므로 만들지 않는다


# ---- 직접 조회: 실제로 보낸 값 ------------------------------------------------------------------------------

def test_live_discovery_records_what_the_scanner_client_actually_sent_and_does_not_call_it_openclaws():
    rep = build_report(discover(build_demo_target(False, "full", "none", None), FAST))
    c = rep["client_capabilities_sent"]
    assert c["status"] == "observed" and c["is_openclaw_client"] is False and "MCP Python SDK client" in c["sender"]
    assert c["origin"] == "observed_outgoing_message" and c["mode"] in ("initialize_request", "per_request_meta")
    assert isinstance(c["capabilities"], dict) and isinstance(c["client_info"], dict) and c["client_info"].get("name")
    assert "OpenClaw" in c["note"] and rep["requests"]["forbidden_requests_sent"] == 0


def test_live_discovery_reports_not_observed_when_nothing_was_sent():
    with tempfile.TemporaryDirectory() as d:
        cfg = pathlib.Path(d) / "c.json"
        cfg.write_text(json.dumps({"mcp": {"servers": {"s": {"command": "x"}}}}), encoding="utf-8")
        target = build_config_target(cfg, "s", "mcp.servers", False, False, [], None)      # 실행 허용 없음 → 거부, 아무것도 보내지 않음
        rep = build_report(discover(target, FAST))
    assert rep["client_capabilities_sent"]["status"] == "not_observed" and "capabilities" not in rep["client_capabilities_sent"]
