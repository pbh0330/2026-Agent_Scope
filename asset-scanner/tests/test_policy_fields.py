"""서버 설정의 `sslVerify`와 `toolFilter.include/exclude` 값 수집 테스트.

수집은 설정에 적힌 값의 기록이며, 연결 안전성이나 Tool 노출·호출 가능 여부의 판단이 아니다.
모든 설정은 가상 예제이며 가짜 비밀값에는 "FAKE" 표식이 있다. 서버 실행·접속은 없다.
"""

import json

import pytest

from asset_scanner.collector import SUPPORTED_REGISTRY_PATHS, collect, collect_plugin_manifest
from asset_scanner.report import build_report

GW = SUPPORTED_REGISTRY_PATHS["mcp.servers"]
NODE = SUPPORTED_REGISTRY_PATHS["nodeHost.mcp.servers"]
TOKEN = "ghp_FAKEPOLICYTOKEN1234567890abcdefgh"


def gw_cfg(servers: str) -> str:
    return '{ mcp: { servers: %s } }' % servers


def collect_gw(write_config, servers: str, registry=GW):
    text = gw_cfg(servers) if registry == GW else '{ nodeHost: { mcp: { servers: %s } } }' % servers
    return collect(write_config(text), registry)


def one(result, key="a"):
    return {s["registration_key"]: s for s in result["servers"]}[key]


def codes(server):
    return [i["code"] for i in server["issues"]]


# ---- 값 있음 --------------------------------------------------------------------

@pytest.mark.parametrize("flag", [True, False])
def test_explicit_ssl_verify_is_recorded_as_written(write_config, flag):
    s = one(collect_gw(write_config, '{ a: { url: "https://x.test/mcp", sslVerify: %s } }' % str(flag).lower()))
    assert s["declared"]["sslVerify"] is flag
    assert s["collection_status"] == "complete"
    assert "sslVerify" not in s["other_declared_keys"] and "sslVerify" in s["declared_keys"]


def test_tool_filter_lists_are_kept_verbatim_in_order_with_duplicates_and_patterns(write_config):
    s = one(collect_gw(write_config, '''{ a: { command: "x", toolFilter: {
        include: ["search_*", "read", "search_*", "*", "a*b*c", " spaced "], exclude: ["admin_*", ""] } } }'''))
    assert s["declared"]["toolFilter"] == {
        "include": ["search_*", "read", "search_*", "*", "a*b*c", " spaced "],  # 정규화·중복 제거·공백 제거 없음
        "exclude": ["admin_*", ""],
    }
    assert s["collection_status"] == "complete" and s["issues"] == []


def test_only_one_list_declared_keeps_only_that_list(write_config):
    s = one(collect_gw(write_config, '{ a: { command: "x", toolFilter: { exclude: ["admin_*"] } } }'))
    assert s["declared"]["toolFilter"] == {"exclude": ["admin_*"]}  # include를 채우지 않는다


def test_empty_lists_and_empty_object_are_recorded_not_dropped(write_config):
    s = one(collect_gw(write_config, '{ a: { command: "x", toolFilter: { include: [], exclude: [] } },'
                                      ' b: { command: "x", toolFilter: {} } }'))
    assert s["declared"]["toolFilter"] == {"include": [], "exclude": []}
    assert one(collect_gw(write_config, '{ b: { command: "x", toolFilter: {} } }'), "b")["declared"]["toolFilter"] == {}


# ---- 생략 -----------------------------------------------------------------------

def test_omitted_fields_are_not_invented(write_config):
    s = one(collect_gw(write_config, '{ a: { url: "https://x.test/mcp" } }'))
    assert "sslVerify" not in s["declared"] and "toolFilter" not in s["declared"]
    assert s["collection_status"] == "complete" and s["issues"] == []
    assert "false" not in json.dumps(s["declared"]).lower() and "true" not in json.dumps(s["declared"]).lower()


# ---- 잘못된 자료형 ---------------------------------------------------------------

@pytest.mark.parametrize("literal, actual", [
    ('"false"', "string"), ("0", "number"), ("null", "null"), ("[true]", "array"), ('{ source: "env", provider: "p", id: "I" }', "object"),
])
def test_ssl_verify_wrong_type_is_an_issue_and_never_coerced(write_config, literal, actual):
    res = collect_gw(write_config, '{ a: { url: "https://x.test/mcp", sslVerify: %s }, b: { command: "ok", sslVerify: false } }' % literal)
    a = one(res)
    assert "sslVerify" not in a["declared"]
    issue = next(i for i in a["issues"] if i["field_path"] == "mcp.servers.a.sslVerify")
    assert (issue["code"], issue["expected"], issue["actual"]) == ("field_type_invalid", "boolean", actual)
    assert a["collection_status"] == "partial" and a["declared"]["url"] == "https://x.test/mcp"  # 나머지 필드는 수집
    b = one(res, "b")
    assert b["declared"]["sslVerify"] is False and b["collection_status"] == "complete"  # 다른 서버는 정상


@pytest.mark.parametrize("literal, actual", [('"search_*"', "string"), ('["x"]', "array"), ("true", "boolean"), ("null", "null")])
def test_tool_filter_not_an_object_is_an_issue(write_config, literal, actual):
    res = collect_gw(write_config, '{ a: { command: "x", toolFilter: %s }, b: { command: "y", toolFilter: { include: ["k"] } } }' % literal)
    a = one(res)
    assert "toolFilter" not in a["declared"]
    issue = next(i for i in a["issues"] if i["field_path"] == "mcp.servers.a.toolFilter")
    assert (issue["expected"], issue["actual"]) == ("object", actual)
    assert a["collection_status"] == "partial" and a["declared"]["command"] == "x"
    assert one(res, "b")["declared"]["toolFilter"] == {"include": ["k"]}


def test_bad_list_is_withheld_without_raw_value_and_the_other_list_survives(write_config):
    res = collect_gw(write_config, '''{ a: { command: "x", toolFilter: {
        include: "%s", exclude: ["admin_*"] } },
      c: { command: "x", toolFilter: { include: ["ok", 5, "%s"], exclude: ["z"] } } }''' % (TOKEN, TOKEN))
    a = one(res)
    assert a["declared"]["toolFilter"] == {"exclude": ["admin_*"]}
    i = next(i for i in a["issues"] if i["field_path"] == "mcp.servers.a.toolFilter.include")
    assert (i["expected"], i["actual"]) == ("array of string", "string")
    c = one(res, "c")
    assert c["declared"]["toolFilter"] == {"exclude": ["z"]}  # 섞인 목록은 통째로 보류(일부만 남기지 않음)
    ci = next(i for i in c["issues"] if i["field_path"] == "mcp.servers.c.toolFilter.include")
    assert ci["element_types"] == ["number", "string"]
    assert "FAKEPOLICYTOKEN" not in json.dumps(res) and TOKEN not in json.dumps(build_report(res))


def test_unexpected_toolfilter_key_is_noted_without_reading_its_value(write_config):
    s = one(collect_gw(write_config, '{ a: { command: "x", toolFilter: { include: ["k"], allow: ["%s"] } } }' % TOKEN))
    assert s["declared"]["toolFilter"] == {"include": ["k"]}
    assert "field_key_unexpected" in codes(s) and s["collection_status"] == "complete"  # 값 손실이 없어 완전성은 유지
    assert "FAKEPOLICYTOKEN" not in json.dumps(s)


# ---- 중복 키 ---------------------------------------------------------------------

def test_duplicate_ssl_verify_keeps_last_value_and_marks_partial(write_config):
    s = one(collect_gw(write_config, '{ a: { url: "https://x.test/mcp", sslVerify: true, sslVerify: false } }'))
    assert s["declared"]["sslVerify"] is False  # 마지막 값만 읽음
    dup = [i for i in s["issues"] if i["code"] == "duplicate_key"]
    assert [d["field_path"] for d in dup] == ["mcp.servers.a.sslVerify"] and s["collection_status"] == "partial"


def test_duplicate_tool_filter_keys_are_reported_at_their_own_paths(write_config):
    s = one(collect_gw(write_config, '''{ a: { command: "x", toolFilter: { include: ["first"], include: ["last"] },
                                         toolFilter: { exclude: ["only-last-object"] } } }'''))
    paths = sorted(i["field_path"] for i in s["issues"] if i["code"] == "duplicate_key")
    assert paths == ["mcp.servers.a.toolFilter"]  # 앞의 toolFilter 객체 전체를 읽지 못함
    assert s["declared"]["toolFilter"] == {"exclude": ["only-last-object"]} and s["collection_status"] == "partial"
    s2 = one(collect_gw(write_config, '{ a: { command: "x", toolFilter: { include: ["first"], include: ["last"] } } }'))
    assert [i["field_path"] for i in s2["issues"] if i["code"] == "duplicate_key"] == ["mcp.servers.a.toolFilter.include"]
    assert s2["declared"]["toolFilter"] == {"include": ["last"]}


# ---- 가림 처리 -------------------------------------------------------------------

def test_secret_looking_filter_entries_are_masked_and_recorded(write_config):
    res = collect_gw(write_config, '{ a: { command: "x", toolFilter: { include: ["ok_*", "%s"], exclude: ["https://u:FAKEPASS@h.test/p?token=FAKEQ"] } } }' % TOKEN)
    s = one(res)
    inc, exc = s["declared"]["toolFilter"]["include"], s["declared"]["toolFilter"]["exclude"]
    assert inc[0] == "ok_*" and inc[1] == "<redacted>" and "FAKE" not in json.dumps(exc)
    assert {"field_path": "mcp.servers.a.toolFilter.include[1]", "reason": "token_pattern:github_token"} in s["redactions"]
    assert {"field_path": "mcp.servers.a.toolFilter.exclude[0]", "reason": "url_userinfo"} in s["redactions"]
    assert exc == ["https://<redacted>@h.test/p?token=<redacted>"]  # 형태는 유지하고 비밀 부분만 가림
    assert "FAKE" not in json.dumps(res) and "FAKE" not in json.dumps(build_report(res))


def test_env_reference_in_a_filter_entry_is_recorded_unresolved_and_default_is_masked(write_config):
    s = one(collect_gw(write_config, '{ a: { command: "x", toolFilter: { include: ["${TOOLS}", "${P:-FAKEfallback}"] } } }'))
    assert s["declared"]["toolFilter"]["include"] == ["${TOOLS}", "${P:-<redacted>}"]
    assert {u["name"] for u in s["unresolved"] if u["kind"] == "env_var"} == {"TOOLS", "P"}
    assert s["collection_status"] == "partial" and "FAKEfallback" not in json.dumps(s)


def test_secret_looking_key_inside_tool_filter_never_appears(write_config):
    res = collect_gw(write_config, '{ a: { command: "x", toolFilter: { "%s": ["k"], include: ["ok"] } } }' % TOKEN)
    s = one(res)
    assert s["declared"]["toolFilter"] == {"include": ["ok"]}
    assert any("<redacted-key-1>" in i["field_path"] for i in s["issues"])
    assert "FAKEPOLICYTOKEN" not in json.dumps(res) and "FAKEPOLICYTOKEN" not in json.dumps(build_report(res))


# ---- 기존 동작과 지원 원천 ---------------------------------------------------------

def test_existing_fields_paths_and_other_keys_are_unchanged(write_config):
    s = one(collect_gw(write_config, '''{ a: { url: "https://x.test/mcp", transport: "sse", enabled: false, requestTimeoutMs: 5,
                                         sslVerify: true, toolFilter: { include: ["k"] } } }'''))
    assert s["declared"] == {"url": "https://x.test/mcp", "transport": "sse", "enabled": False,
                             "sslVerify": True, "toolFilter": {"include": ["k"]}}
    assert s["other_declared_keys"] == ["requestTimeoutMs"]
    assert s["declaration_path"] == "mcp.servers.a" and s["declaration_pointer"] == "/mcp/servers/a"
    assert s["declared_keys"] == ["url", "transport", "enabled", "requestTimeoutMs", "sslVerify", "toolFilter"]


def test_node_registry_collects_the_same_fields_with_node_paths(write_config):
    res = collect_gw(write_config, '{ a: { url: "https://x.test/mcp", sslVerify: "no", toolFilter: { include: ["k"], exclude: 3 } } }', NODE)
    s = one(res)
    assert s["declared"]["toolFilter"] == {"include": ["k"]}
    assert sorted(i["field_path"] for i in s["issues"]) == ["nodeHost.mcp.servers.a.sslVerify", "nodeHost.mcp.servers.a.toolFilter.exclude"]
    assert s["declaration_path"] == "nodeHost.mcp.servers.a"


def test_plugin_manifest_uses_the_same_collection(write_config):
    path = write_config('{ mcpServers: { a: { command: "x", toolFilter: { include: ["k"] }, sslVerify: false } } }', "manifest.json5")
    s = one(collect_plugin_manifest(path))
    assert s["declared"]["sslVerify"] is False and s["declared"]["toolFilter"] == {"include": ["k"]}


def test_value_collection_does_not_decide_policy_or_safety(write_config):
    """수집 결과에는 안전성·노출 판정이 없다. sslVerify:false와 빈 필터도 경고·판정 필드를 만들지 않는다."""
    res = collect_gw(write_config, '{ a: { url: "https://x.test/mcp", sslVerify: false, toolFilter: { exclude: ["*"] } } }')
    text = json.dumps(res, ensure_ascii=False).lower()
    for word in ("insecure", "unsafe", "warning", "exposed", "allowed", "blocked", "effective"):
        assert word not in text
    assert one(res)["collection_status"] == "complete"
