"""실제 MCP 목록 조회(live_discovery) 테스트.

**프로젝트에 포함된 로컬 시험 서버(`asset_scanner.dev_lists_server`)만 실행·접속한다.** 팀 테스트베드·외부 서버 접속은 없다.
HTTP는 127.0.0.1에만 바인딩하고 인증 토큰은 가짜(테스트 중 만든 임의 값)이며, `FAKE` 표식 값은 전부 가짜 비밀값이다.
서버가 받은 요청 기록(메서드 이름만)으로 스캐너가 목록 요청 외의 호출을 하지 않았음을 검증한다.
"""

import json
import os
import socket
import subprocess
import sys
import time

import pytest

from asset_scanner import live_discovery as ld
from asset_scanner.collector import SUPPORTED_REGISTRY_PATHS, collect
from asset_scanner.linking import build_link_report, link_scans
from asset_scanner.live_discovery import (ALLOWED_LIST_METHODS, DiscoveryLimits, FORBIDDEN_EXAMPLES, build_config_target, build_demo_target, build_report,
                                          catalog_report, decide_listing, discover, validate_limits)
from asset_scanner.report import build_report as build_config_report
from conftest import SCANNER_ROOT

_REAL_POPEN = subprocess.Popen
FAST = DiscoveryLimits(total_timeout_s=45, request_timeout_s=10, connect_timeout_s=20)
# 연결 협상(server/discover, 구형은 initialize + initialized 통지)과 목록 요청만 허용한다.
OK_SERVER_METHODS = {"server/discover", "initialize", "notifications/initialized", "ping", "tools/list", "resources/list", "resources/templates/list",
                     "prompts/list"}


def read_log(path):
    if not os.path.exists(path):
        return []
    return [json.loads(x) for x in open(path, encoding="utf-8").read().splitlines() if x.strip()]


def methods_seen(events):
    return [e["method"] for e in events if e["event"] == "request"]


def live(tmp_path, scenario="full", http=False, auth="fake", limits=FAST, name="r", **kw):
    log = tmp_path / f"{name}.log.jsonl"
    target = build_demo_target(http, scenario, auth, log)
    result = discover(target, limits, **kw)
    return build_report(result), read_log(log), target, result


def lst(rep, key):
    return rep["lists"][key]


def assert_only_list_requests(rep, events):
    seen = methods_seen(events)
    assert set(seen) <= OK_SERVER_METHODS, seen
    for bad in FORBIDDEN_EXAMPLES:
        assert bad not in seen
    assert rep["requests"]["forbidden_requests_sent"] == 0
    list_calls = [m for m in seen if m.endswith("/list")]
    sent = sum(rep["requests"]["by_method"].values())
    assert len(list_calls) == sent                          # 스캐너가 센 요청 수와 서버가 받은 목록 요청 수가 같다
    assert all(m in ALLOWED_LIST_METHODS for m in rep["requests"]["by_method"])


def dump(x):
    return json.dumps(x, ensure_ascii=False)


# ---- stdio ----------------------------------------------------------------------------------

def test_stdio_collects_all_four_lists_and_sends_only_list_requests(tmp_path):
    rep, events, target, _ = live(tmp_path)
    assert rep["collection"]["status"] == "complete" and rep["collection"]["outcome"] == "lists_collected"
    assert rep["collection"]["item_counts"] == {"tools": 2, "resources": 2, "resource_templates": 2, "prompts": 2}
    assert rep["source"]["live_server_query"] is True and rep["source"]["dev_target_only"] is True and rep["source"]["target"]["team_testbed"] is False
    p = rep["protocol"]
    assert p["negotiated_protocol_version"] == "2026-07-28" and p["negotiated_supported_by_sdk"] and p["negotiated_readable_by_parser"]
    assert p["stored_response_parser_versions"] == ["2025-11-25", "2026-07-28"]
    assert set(p["sdk"]["communication_versions"]) >= {"2024-11-05", "2025-11-25", "2026-07-28"}      # SDK 통신 범위가 파서보다 넓다
    assert_only_list_requests(rep, events)
    assert rep["requests"]["by_method"] == {"tools/list": 1, "resources/list": 2, "resources/templates/list": 1, "prompts/list": 1}
    assert [e["event"] for e in events if e["event"] in ("start", "stop")] == ["start", "stop"]       # 서버가 정상 종료함
    assert lst(rep, "resources")["items"][0]["identity"]["uri"]["original_value"] == "file:///docs/readme.md"
    assert lst(rep, "prompts")["items"][0]["definition"]["arguments"][0]["required"] is True
    assert rep["capabilities_from_wire"] is not None and rep["server_info_from_wire"]["name"] == "asset-scanner-dev-lists-server"


def test_items_are_tied_to_the_live_session_not_to_a_capture(tmp_path):
    rep, *_ = live(tmp_path)
    refs = [it["internal_ref"] for k in ("resources", "resource_templates", "prompts") for it in lst(rep, k)["items"]]
    assert refs and all(r.startswith("live-session[0]/") for r in refs) and len(set(refs)) == len(refs)
    assert not any("capture-server" in r for r in refs)
    assert all(it["trust"] == "untrusted_server_provided" for k in ("resources", "prompts") for it in lst(rep, k)["items"])


@pytest.mark.parametrize("scenario, statuses", [
    ("empty-all", {"tools": ("complete", "empty_list"), "resources": ("complete", "empty_list"), "resource_templates": ("complete", "empty_list"), "prompts": ("complete", "empty_list")}),
    ("no-prompts", {"prompts": ("not_performed", "capability_not_declared")}),
    ("only-tools", {"tools": ("complete", "tools_listed"), "resources": ("not_performed", "capability_not_declared"),
                    "resource_templates": ("not_performed", "capability_not_declared"), "prompts": ("not_performed", "capability_not_declared")}),
    ("templates-mnf", {"resources": ("complete", "items_listed"), "resource_templates": ("unsupported", "method_not_found")}),
    ("resources-error", {"resources": ("failed", "error_response"), "prompts": ("complete", "items_listed")}),
])
def test_list_states_are_distinguished_by_real_communication(tmp_path, scenario, statuses):
    rep, events, *_ = live(tmp_path, scenario)
    for key, expected in statuses.items():
        got = lst(rep, key)
        assert (got["collection_status"], got["outcome"]) == expected, (key, got["collection_status"], got["outcome"])
    assert_only_list_requests(rep, events)
    seen = methods_seen(events)
    if scenario == "no-prompts":
        assert "prompts/list" not in seen                    # 능력을 선언하지 않은 목록은 요청하지 않음
        assert lst(rep, "prompts")["item_count"] is None and lst(rep, "prompts")["items"] == []
    if scenario == "only-tools":
        assert [m for m in seen if m.endswith("/list")] == ["tools/list"]
    if scenario == "empty-all":
        assert all(lst(rep, k)["item_count"] == 0 for k in ("tools", "resources", "resource_templates", "prompts"))
        assert rep["collection"]["status"] == "complete"
    if scenario == "templates-mnf":
        assert lst(rep, "resource_templates")["evidence"]["error_code"] == -32601 and rep["collection"]["status"] == "complete"
    if scenario == "resources-error":
        assert lst(rep, "resources")["item_count"] is None and rep["collection"]["status"] == "partial"
    if scenario == "no-prompts":
        assert rep["collection"]["status"] == "partial"      # 미수행 목록이 있으면 완전 수집으로 보지 않는다


def test_request_undeclared_turns_a_missing_capability_into_evidence(tmp_path):
    rep, events, *_ = live(tmp_path, "no-prompts", request_undeclared=True)
    p = lst(rep, "prompts")
    assert "prompts/list" in methods_seen(events)
    assert p["collection_status"] == "unsupported" and p["declared_capability"] == "not_declared"     # 선언도 없고 서버도 Method not found
    assert rep["requests"]["request_undeclared"] is True and rep["collection"]["status"] == "complete"


def test_second_page_failure_keeps_the_first_page_as_partial(tmp_path):
    rep, events, *_ = live(tmp_path, "fail-second")
    p = lst(rep, "prompts")
    assert p["collection_status"] == "partial" and p["item_count"] == 1 and [i["definition"]["name"] for i in p["items"]] == ["first"]
    assert "error_response" in [i["code"] for i in p["issues"]]
    assert lst(rep, "resources")["collection_status"] == "complete"


def test_page_and_item_limits_make_a_list_partial_without_keeping_extra_items(tmp_path):
    rep, events, *_ = live(tmp_path, "many", limits=DiscoveryLimits(45, 10, 20, max_pages=2, max_items=4))
    r, p = lst(rep, "resources"), lst(rep, "prompts")
    assert r["collection_status"] == "partial" and r["item_count"] == 4 and r["limit_exclusions"][0]["items_excluded"] == 2
    assert p["collection_status"] == "partial" and "item_limit_reached" in [i["code"] for i in p["issues"]] and p["item_count"] == 4
    assert rep["collection"]["status"] == "partial"
    seen = methods_seen(events)
    assert seen.count("resources/list") == 2 and seen.count("prompts/list") == 2     # 한도 뒤로는 더 요청하지 않음
    assert_only_list_requests(rep, events)


def test_page_limit_alone_also_stops_requesting_and_marks_partial(tmp_path):
    rep, events, *_ = live(tmp_path, "many", name="pages", limits=DiscoveryLimits(45, 10, 20, max_pages=2, max_items=100))
    r, p = lst(rep, "resources"), lst(rep, "prompts")
    for got, n in ((r, 6), (p, 4)):
        assert got["collection_status"] == "partial" and got["item_count"] == n and "max_pages_reached" in [i["code"] for i in got["issues"]]
    assert methods_seen(events).count("resources/list") == 2 and methods_seen(events).count("prompts/list") == 2


def test_exactly_the_limit_is_still_complete(tmp_path):
    rep, *_ = live(tmp_path, "many", limits=DiscoveryLimits(45, 10, 20, max_pages=10, max_items=7))
    assert lst(rep, "resources")["collection_status"] == "complete" and lst(rep, "resources")["item_count"] == 7
    assert lst(rep, "prompts")["collection_status"] == "complete" and lst(rep, "prompts")["item_count"] == 5


def test_request_timeout_fails_only_that_list_and_the_server_is_cleaned_up(tmp_path):
    started = time.monotonic()
    rep, events, *_ = live(tmp_path, "slow-resources", limits=DiscoveryLimits(30, 1.5, 20))
    r = lst(rep, "resources")
    assert r["collection_status"] == "failed" and r["outcome"] == "request_timeout" and r["item_count"] is None
    assert lst(rep, "tools")["collection_status"] == "complete" and lst(rep, "prompts")["collection_status"] in ("complete", "not_performed", "failed")
    assert time.monotonic() - started < 25
    assert "stop" in [e["event"] for e in events]


def test_server_exit_during_a_list_ends_the_session_honestly(tmp_path):
    rep, events, *_ = live(tmp_path, "exit-resources")
    r = lst(rep, "resources")
    assert r["collection_status"] == "failed" and r["outcome"] == "connection_closed"
    assert lst(rep, "tools")["collection_status"] == "complete"                                   # 그 전에 끝난 목록은 보존
    for k in ("resource_templates", "prompts"):
        got = lst(rep, k)
        assert got["collection_status"] == "not_performed" and got["outcome"] == "session_ended"   # 요청하지 않은 목록을 만들어 채우지 않음
    assert rep["collection"]["status"] == "partial" and "Traceback" not in dump(rep)


def test_total_timeout_marks_unfinished_lists_not_performed(tmp_path):
    # 총 제한이 서버 시작+Tool 목록보다 짧으면 resources 요청 전에 끝나 not_performed가 된다(부하가 큰 PC에서 3초는 부족했다). 여유를 둬서
    # "응답 없는 요청이 총 제한에 걸림"이라는 의도를 안정적으로 확인한다.
    rep, *_ = live(tmp_path, "slow-resources", limits=DiscoveryLimits(total_timeout_s=12, request_timeout_s=60, connect_timeout_s=20))
    r = lst(rep, "resources")
    assert r["collection_status"] == "failed" and r["outcome"] == "total_timeout"
    assert lst(rep, "resource_templates")["outcome"] == "total_timeout" and lst(rep, "resource_templates")["collection_status"] == "not_performed"


def test_same_names_across_kinds_are_not_merged(tmp_path):
    rep, *_ = live(tmp_path, "same-names")
    names = {k: [i["definition"]["name"] for i in lst(rep, k)["items"]] for k in ("resources", "resource_templates", "prompts")}
    assert names == {"resources": ["shared"], "resource_templates": ["shared"], "prompts": ["shared"]}
    assert rep["collection"]["item_counts"] == {"tools": 1, "resources": 1, "resource_templates": 1, "prompts": 1}
    refs = [lst(rep, k)["items"][0]["internal_ref"] for k in names]
    assert len(set(refs)) == 3


def test_secrets_in_live_responses_are_masked_everywhere(tmp_path):
    rep, events, target, result = live(tmp_path, "secrets")
    out = dump(rep) + dump(events) + dump(catalog_report(result))
    for marker in ("FAKE_LISTS", "FAKELISTS"):
        assert marker not in out, marker
    assert lst(rep, "resources")["items"][0]["identity"]["uri"]["status"] == "withheld_by_redaction"
    assert lst(rep, "prompts")["items"][0]["identity"]["name"]["original_value"] == "secret-prompt"
    arg0 = lst(rep, "prompts")["items"][0]["definition"]["arguments"][0]
    assert arg0["name"] == "<redacted>"


def test_legacy_client_mode_negotiates_2025_and_reads_without_2026_fields(tmp_path):
    rep, events, *_ = live(tmp_path, client_mode="legacy")
    assert rep["protocol"]["negotiated_protocol_version"] == "2025-11-25" and rep["protocol"]["requested_mode"] == "legacy"
    assert rep["collection"]["status"] == "complete"
    assert "initialize" in methods_seen(events) and "server/discover" not in methods_seen(events)
    assert all("result_type_missing" not in [i["code"] for i in lst(rep, k)["issues"]] for k in ("resources", "prompts"))
    assert_only_list_requests(rep, events)


def test_a_version_the_parser_cannot_read_does_not_get_list_requests(tmp_path, monkeypatch):
    """SDK는 통신할 수 있어도 파서가 읽지 못하는 버전이면 목록을 요청하지 않는다 (협상 버전을 파서가 지원하는 것으로 가정하지 않음)."""
    monkeypatch.setattr(ld, "SUPPORTED_PROTOCOL_VERSIONS", ("2025-11-25",))
    rep, events, *_ = live(tmp_path)          # auto → 2026-07-28 협상
    p = rep["protocol"]
    assert p["negotiated_protocol_version"] == "2026-07-28" and p["negotiated_supported_by_sdk"] is True and p["negotiated_readable_by_parser"] is False
    assert rep["collection"]["status"] == "failed" and rep["collection"]["outcome"] == "protocol_version_not_readable_by_parser"
    assert all(lst(rep, k)["collection_status"] == "not_performed" and lst(rep, k)["outcome"] == "protocol_version_not_readable_by_parser" for k in rep["lists"])
    assert [m for m in methods_seen(events) if m.endswith("/list")] == []


@pytest.mark.parametrize("v, sdk, parser", [("2024-11-05", True, False), ("2025-06-18", True, False), ("2025-11-25", True, True),
                                            ("2026-07-28", True, True), ("2099-01-01", False, False), (None, False, False)])
def test_sdk_communication_support_and_parser_support_are_separate_facts(v, sdk, parser):
    d = decide_listing(v)
    assert (d["negotiated_supported_by_sdk"], d["negotiated_readable_by_parser"]) == (sdk, parser)


# ---- HTTP + 가짜 인증 ------------------------------------------------------------------------------

def test_http_with_fake_bearer_auth_collects_and_never_records_the_token(tmp_path):
    log = tmp_path / "h.log.jsonl"
    target = build_demo_target(True, "full", "fake", log)
    token = target.headers["Authorization"].removeprefix("Bearer ")
    result = discover(target, FAST)
    rep = build_report(result)
    events = read_log(log)
    assert rep["collection"]["status"] == "complete" and rep["source"]["transport"] == "streamable-http"
    assert rep["source"]["target"]["auth"] == "fake_bearer_generated_at_run" and rep["source"]["target"]["host"] == "127.0.0.1"
    http = [e for e in events if e["event"] == "http"]
    assert http and all(e["auth"] == "ok" for e in http)
    assert_only_list_requests(rep, events)
    blob = dump(rep) + dump(events) + dump(catalog_report(result))
    assert token not in blob and "Bearer" not in blob.replace("fake_bearer_generated_at_run", "")
    child = rep["source"]["child_process"]
    assert child["terminated"] is True and child["port_closed_after_cleanup"] is True and child["bind"] == "127.0.0.1"


@pytest.mark.parametrize("headers, verdict", [({}, "missing"), ({"Authorization": "Bearer FAKE-WRONG-TOKEN"}, "bad")])
def test_http_auth_failures_are_connect_rejections_not_empty_lists(tmp_path, headers, verdict):
    log = tmp_path / "h.log.jsonl"
    target = build_demo_target(True, "full", "fake", log)
    target.headers = dict(headers)
    rep = build_report(discover(target, FAST))
    events = read_log(log)
    assert rep["collection"]["status"] == "failed" and rep["collection"]["outcome"] == "connect_rejected"
    assert rep["connect_failure"]["http_status_codes"] == [401] and set(rep["http"]["status_code_counts"]) == {"401"}
    assert {e["auth"] for e in events if e["event"] == "http"} == {verdict}
    assert methods_seen(events) == []                                      # 인증을 통과하지 못해 MCP 요청은 서버에 도달하지 않음
    assert rep["requests"]["by_method"] == {} and all(lst(rep, k)["collection_status"] == "not_performed" for k in rep["lists"])
    assert "FAKE-WRONG-TOKEN" not in dump(rep) + dump(events)
    assert rep["source"]["child_process"]["port_closed_after_cleanup"] is True


def test_http_without_auth_requirement_works_and_is_marked(tmp_path):
    rep, events, *_ = live(tmp_path, "full", http=True, auth="none")
    assert rep["collection"]["status"] == "complete" and rep["source"]["target"]["auth"] == "none"
    assert {e["auth"] for e in events if e["event"] == "http"} == {"not_required"}


def test_http_scenarios_keep_the_same_status_rules(tmp_path):
    rep, events, *_ = live(tmp_path, "templates-mnf", http=True)
    assert lst(rep, "resource_templates")["collection_status"] == "unsupported" and lst(rep, "resources")["collection_status"] == "complete"
    assert_only_list_requests(rep, events)


# ---- 대상 선택과 거부 ---------------------------------------------------------------------------------

def server_cmd(scenario="full"):
    return [sys.executable, "-m", "asset_scanner.dev_lists_server", "--scenario", scenario]


def write_cfg(tmp_path, servers, name="openclaw.json5"):
    p = tmp_path / name
    p.write_text(json.dumps({"mcp": {"servers": servers}}), encoding="utf-8")
    return p


def stdio_decl(extra=None, scenario="full"):
    cmd = server_cmd(scenario)
    return {"command": cmd[0], "args": cmd[1:], "cwd": SCANNER_ROOT.as_posix(), **(extra or {})}


def test_config_server_runs_only_when_selected_by_key_and_allowed(tmp_path):
    cfg = write_cfg(tmp_path, {"mine": stdio_decl(), "other": stdio_decl(scenario="empty-all")})
    refused = build_config_target(cfg, "mine", "mcp.servers", False, False, [], None)
    assert refused.refused["code"] == "launch_not_allowed" and refused.stdio is None
    t = build_config_target(cfg, "mine", "mcp.servers", True, False, [], None)
    assert t.refused is None and t.declaration["registration_key"] == "mine" and t.declaration["name_matching_used"] is False
    assert t.description["command_origin"].startswith("OpenClaw 설정의 선언")


def test_config_stdio_discovery_links_to_the_selected_declaration_and_to_linking(tmp_path):
    cfg = write_cfg(tmp_path, {"mine": stdio_decl(), "other": stdio_decl(scenario="empty-all")})
    target = build_config_target(cfg, "mine", "mcp.servers", True, False, [], None)
    result = discover(target, FAST, config_scan_ref="gw")
    rep = build_report(result)
    assert rep["collection"]["status"] == "complete" and rep["source"]["dev_target_only"] is False
    dl = rep["source"]["declaration_link"]
    assert dl["declaration_path"] == "mcp.servers.mine" and dl["basis"] == "operator_selected_declaration" and dl["name_matching_used"] is False
    # 같은 설정 파일의 설정 수집 결과 + 이 조회의 Tool 카탈로그 → 기존 linking이 등록키·영역·라벨로 연결한다
    scan = tmp_path / "scan.json"
    scan.write_text(json.dumps(build_config_report(collect(cfg, SUPPORTED_REGISTRY_PATHS["mcp.servers"]))), encoding="utf-8")
    cat = tmp_path / "cat.json"
    cat.write_text(json.dumps(catalog_report(result)), encoding="utf-8")
    link = build_link_report(link_scans([("gw", scan)], [("obs", cat)]))
    ln = link["links"][0]
    assert ln["link_status"] == "linked" and ln["basis"] == ["config_scan_ref", "registry_path", "registration_key"]
    assert ln["trace"]["registration_key"] == "mine" and ln["trace"]["logical_location"]["key_path"] == ["mcp", "servers", "mine"]
    assert [t["original_name"] for t in ln["tools"]] == ["echo_text", "add_numbers"]       # 조회한 Tool 이름이 선언에 연결됨
    assert "other" not in dump(ln["trace"])                                                # 다른 서버 선언과 섞이지 않음


def test_without_a_scan_ref_the_catalog_is_not_linked_by_name_alone(tmp_path):
    cfg = write_cfg(tmp_path, {"mine": stdio_decl()})
    result = discover(build_config_target(cfg, "mine", "mcp.servers", True, False, [], None), FAST)
    assert "config_link" not in result["_catalog_server"]
    scan = tmp_path / "scan.json"
    scan.write_text(json.dumps(build_config_report(collect(cfg, SUPPORTED_REGISTRY_PATHS["mcp.servers"]))), encoding="utf-8")
    cat = tmp_path / "cat.json"
    cat.write_text(json.dumps(catalog_report(result)), encoding="utf-8")
    link = build_link_report(link_scans([("gw", scan)], [("obs", cat)]))
    assert link["links"][0]["link_status"] == "unlinked"          # 이름이 같아도 참조가 없으면 자동으로 합치지 않는다


@pytest.mark.parametrize("decl, allow, code", [
    ({"command": "x", "args": ["${SECRET_ARG}"]}, dict(allow_launch=True), "unresolved_reference"),
    ({"command": "x", "env": {"K": {"source": "env", "provider": "p", "id": "I"}}}, dict(allow_launch=True), "unresolved_reference"),
    ({"url": "http://127.0.0.1:1/mcp", "headers": {"Authorization": "Bearer ${TOKEN}"}}, dict(allow_connect=True), "unresolved_reference"),
    ({"command": "x", "url": "http://127.0.0.1:1/mcp"}, dict(allow_launch=True, allow_connect=True), "ambiguous_or_missing_target"),
    ({"args": ["a"]}, dict(allow_launch=True), "ambiguous_or_missing_target"),
    ({"command": "x", "args": "notalist"}, dict(allow_launch=True), "declaration_type_invalid"),
    ({"url": "http://127.0.0.1:1/mcp", "transport": "sse"}, dict(allow_connect=True), "transport_not_supported"),
    ({"url": "http://127.0.0.1:1/mcp", "auth": "oauth"}, dict(allow_connect=True), "oauth_not_supported"),
    ({"url": "http://127.0.0.1:1/mcp", "oauth": {"scope": "x"}}, dict(allow_connect=True), "oauth_not_supported"),
    ({"url": "http://127.0.0.1:1/mcp"}, dict(), "connect_not_allowed"),
    ({"url": "http://u:FAKEPW@127.0.0.1:1/mcp"}, dict(allow_connect=True), "url_userinfo_not_supported"),
    ({"url": "ftp://127.0.0.1/mcp"}, dict(allow_connect=True), "url_scheme_not_supported"),
    ({"url": "https://mcp.example.test/mcp"}, dict(allow_connect=True), "host_not_allowed"),
    ({"url": "http://127.0.0.1:1/mcp"}, dict(allow_connect=True, bearer_env="NO_SUCH_VAR_FOR_TEST"), "bearer_env_not_set"),
])
def test_config_targets_are_refused_with_a_reason_and_nothing_is_started(tmp_path, monkeypatch, decl, allow, code):
    monkeypatch.delenv("NO_SUCH_VAR_FOR_TEST", raising=False)
    cfg = write_cfg(tmp_path, {"s": decl})
    t = build_config_target(cfg, "s", "mcp.servers", allow.get("allow_launch", False), allow.get("allow_connect", False), [], allow.get("bearer_env"))
    assert t.refused is not None and t.refused["code"] == code
    # 거부된 대상은 프로세스를 만들거나 소켓에 접속하지 않는다
    def boom(*a, **k):
        raise AssertionError("실행·접속 시도")
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    rep = build_report(discover(t, FAST))
    assert rep["collection"]["status"] == "failed" and rep["collection"]["outcome"] == "target_refused" and rep["source"]["live_server_query"] is False
    assert rep["requests"]["by_method"] == {} and "FAKEPW" not in dump(rep)


def test_missing_key_and_unreadable_config_are_refused(tmp_path):
    cfg = write_cfg(tmp_path, {"a": stdio_decl()})
    assert build_config_target(cfg, "zzz", "mcp.servers", True, False, [], None).refused["code"] == "declaration_not_found"
    bad = tmp_path / "bad.json5"
    bad.write_text("{ nope", encoding="utf-8")
    assert build_config_target(bad, "a", "mcp.servers", True, False, [], None).refused["code"].startswith("config_")
    assert build_config_target(tmp_path / "missing.json5", "a", "mcp.servers", True, False, [], None).refused is not None


def test_non_loopback_host_needs_an_exact_allow_host_but_is_never_contacted_here(tmp_path):
    cfg = write_cfg(tmp_path, {"r": {"url": "https://mcp.example.test/mcp"}})
    ok = build_config_target(cfg, "r", "mcp.servers", False, True, ["mcp.example.test"], None)     # 접속하지 않고 대상만 만든다
    assert ok.refused is None and ok.description["allowed_by"] == "--allow-host" and ok.description["host"] == "mcp.example.test"
    assert build_config_target(cfg, "r", "mcp.servers", False, True, ["other.example.test"], None).refused["code"] == "host_not_allowed"


@pytest.fixture
def http_server(tmp_path):
    """테스트가 직접 띄우는 로컬 HTTP 시험 서버 (가짜 Bearer 필요). 끝나면 반드시 종료한다."""
    token = "fake-" + os.urandom(12).hex()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    log = tmp_path / "ext.log.jsonl"
    env = {**os.environ, "DEV_MCP_SERVER_TOKEN": token, "DEV_MCP_SERVER_LOG": str(log), "PYTHONUTF8": "1"}
    proc = _REAL_POPEN(server_cmd() + ["--transport", "http", "--port", str(port), "--require-bearer"], env=env, cwd=SCANNER_ROOT,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
            break
        except OSError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("시험 서버가 포트를 열지 못했습니다")
    try:
        yield port, token, log
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) if sys.platform == "win32" else None


def test_config_http_server_uses_a_bearer_token_from_an_environment_variable_and_never_records_it(tmp_path, monkeypatch, http_server):
    port, token, log = http_server
    cfg = write_cfg(tmp_path, {"web": {"url": f"http://127.0.0.1:{port}/mcp", "transport": "streamable-http"}})
    monkeypatch.setenv("SCANNER_TEST_BEARER", token)
    t = build_config_target(cfg, "web", "mcp.servers", False, True, [], "SCANNER_TEST_BEARER")
    assert t.refused is None and t.description["bearer_env_name"] == "SCANNER_TEST_BEARER" and t.description["auth"] == "bearer_from_env_var"
    result = discover(t, FAST, config_scan_ref="gw")
    rep = build_report(result)
    events = read_log(log)
    assert rep["collection"]["status"] == "complete" and rep["source"]["declaration_link"]["declaration_path"] == "mcp.servers.web"
    assert {e["auth"] for e in events if e["event"] == "http"} == {"ok"}
    blob = dump(rep) + dump(events) + dump(catalog_report(result))
    assert token not in blob and "Bearer" not in dump(rep)                       # 토큰도 Bearer 값도 없음 (헤더 이름만 있음)
    assert rep["source"]["target"]["header_names"] == ["Authorization"] and rep["http"]["status_code_counts"].get("401") is None
    assert_only_list_requests(rep, events)
    # 같은 서버에 토큰 없이 접속하면 거부된다 (가짜 인증이 실제로 적용되고 있다는 증거)
    t2 = build_config_target(cfg, "web", "mcp.servers", False, True, [], None)
    rep2 = build_report(discover(t2, FAST))
    assert rep2["collection"]["status"] == "failed" and rep2["collection"]["outcome"] == "connect_rejected"


# ---- 제한값·요청 허용 목록 ---------------------------------------------------------------------------

@pytest.mark.parametrize("kw", [dict(total_timeout_s=0), dict(total_timeout_s=float("nan")), dict(request_timeout_s=-1), dict(request_timeout_s=float("inf")),
                                dict(max_pages=0), dict(max_items=0), dict(max_items=5001), dict(connect_timeout_s=0)])
def test_invalid_limits_are_rejected_before_anything_starts(monkeypatch, kw):
    limits = DiscoveryLimits(**{**{"total_timeout_s": 10, "request_timeout_s": 5}, **kw})
    assert validate_limits(limits)
    def boom(*a, **k):
        raise AssertionError("프로세스 시작")
    monkeypatch.setattr(subprocess, "Popen", boom)
    with pytest.raises(ValueError):
        discover(build_demo_target(False, "full", "fake", None), limits)


def test_only_list_requests_can_be_sent_by_the_client_guard():
    import mcp_types as types
    import anyio

    class Fake:
        class session:
            @staticmethod
            async def send_request(*a, **k):
                raise AssertionError("보내면 안 되는 요청이 전송됨")

    state = ld._State()
    for bad in (types.CallToolRequest(params=types.CallToolRequestParams(name="x")), types.ReadResourceRequest(params=types.ReadResourceRequestParams(uri="file:///x")),
                types.GetPromptRequest(params=types.GetPromptRequestParams(name="p"))):
        with pytest.raises(PermissionError):
            anyio.run(ld._send, Fake(), state, bad, 1.0)
    assert state.requests_by_method == {}


# ---- CLI ---------------------------------------------------------------------------------------------

def run_cli(*args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-m", "asset_scanner.live_discovery", *map(str, args)], cwd=SCANNER_ROOT, env=env,
                          capture_output=True, text=True, encoding="utf-8")


def test_cli_exit_codes_outputs_and_catalog_file(tmp_path):
    out, cat = tmp_path / "o.json", tmp_path / "c.json"
    ok = run_cli("--demo-http", "--output", out, "--catalog-output", cat, "--demo-request-log", tmp_path / "l.jsonl")
    assert ok.returncode == 0 and "목록 요청만 보냅니다" in ok.stdout and "개발용 시험 서버, 팀 테스트베드 아님" in ok.stdout
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["format"] == "agent-scope.scanner.mcp-live-discovery" and "_catalog_server" not in saved
    assert json.loads(cat.read_text(encoding="utf-8"))["format"] == "agent-scope.scanner.mcp-tools-catalog"
    events = read_log(tmp_path / "l.jsonl")
    token_free = ok.stdout + ok.stderr + out.read_text(encoding="utf-8") + (tmp_path / "l.jsonl").read_text(encoding="utf-8")
    assert "Bearer" not in token_free.replace("fake_bearer_generated_at_run", "") and set(methods_seen(events)) <= OK_SERVER_METHODS
    part = run_cli("--demo-stdio", "--scenario", "no-prompts", "--output", tmp_path / "p.json")
    assert part.returncode == 1
    cfg = write_cfg(tmp_path, {"s": stdio_decl()})
    refused = run_cli("--config", cfg, "--server", "s", "--output", tmp_path / "r.json")          # 실행 허용 플래그 없음
    assert refused.returncode == 3 and "대상 거부: launch_not_allowed" in refused.stdout
    assert json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["source"]["live_server_query"] is False
    for bad in (["--config", cfg, "--output", tmp_path / "x.json"],                                # --server 없음: 설정의 서버를 모두 조회하지 않음
                ["--demo-stdio", "--server", "s", "--output", tmp_path / "x.json"],
                ["--demo-stdio", "--allow-launch", "--output", tmp_path / "x.json"],
                ["--demo-stdio", "--timeout", "0", "--output", tmp_path / "x.json"],
                ["--demo-stdio", "--demo-http", "--output", tmp_path / "x.json"],
                ["--demo-stdio"]):
        assert run_cli(*bad).returncode == 2
    blocked = tmp_path / "dir"
    blocked.mkdir()
    assert run_cli("--demo-stdio", "--output", blocked).returncode == 4
