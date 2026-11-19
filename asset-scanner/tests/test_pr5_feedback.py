"""PR #5 서진님 피드백 3건의 회귀 테스트.

모든 비밀값은 `FAKE` 표식이 붙은 가짜 값이다. 실제 서버에 접속하거나 인증정보를 쓰지 않는다.

1. 인증정보 이름 속성의 default·const·examples·enum 안에 중첩된 객체·배열의 내부 값도 가린다.
2. 긴 오류 메시지는 전체 원문에서 인증정보를 가린 뒤에 길이를 제한한다 (같은 순서 문제가 있는 다른 호출부 포함).
3. env·headers 등 수집 대상 하위 객체의 중복 키를 기록하고 서버와 전체 수집 상태를 partial로 만든다.
"""

import json

import pytest

from asset_scanner.collector import collect
from asset_scanner.tools_catalog import MAX_MESSAGE_CHARS, build_catalog_report, collect_tools_catalog

V = "2026-07-28"


# ---- 공통 도우미 ------------------------------------------------------------------

def page(tools=(), **result_extra):
    result = {"resultType": "complete", "tools": list(tools), "ttlMs": 1000, "cacheScope": "public"}
    result.update(result_extra)
    return {"jsonrpc": "2.0", "id": 1, "result": result}


@pytest.fixture
def catalog(tmp_path):
    """저장된 응답 묶음을 파일로 쓰고 카탈로그 보고서를 만든다."""

    def _build(*servers, origin="synthetic_test_data"):
        path = tmp_path / "capture.json"
        path.write_text(json.dumps({"origin": origin, "servers": list(servers)}, ensure_ascii=False), encoding="utf-8")
        return build_catalog_report(collect_tools_catalog(path))

    return _build


def server(ref="s", pages=None, version=V):
    return {"server_ref": ref, "protocol_version": version, "pages": pages}


def schema_tool(prop_schema, prop_name="api_key"):
    return {"name": "t", "inputSchema": {"type": "object", "properties": {prop_name: prop_schema}}}


def dumped(report) -> str:
    return json.dumps(report, ensure_ascii=False)


# ---- 1. 중첩된 default·const·examples·enum ---------------------------------------------

NESTED_VALUE_CASES = {
    "default_object": {"type": "object", "default": {"user": "FAKEUSER1", "pw": "FAKENESTEDPW1"}},
    "default_array": {"type": "array", "default": ["FAKEARRAYSECRET1", ["FAKEDEEPSECRET2"]]},
    "default_array_of_objects": {"default": [{"a": {"b": "FAKEDEEPOBJ3"}}]},
    "const_object": {"const": {"inner": {"value": "FAKECONSTSECRET4"}}},
    "examples_objects": {"examples": [{"token_like": "FAKEEXAMPLE5"}, {"x": ["FAKEEXAMPLE6"]}]},
    "enum_objects": {"enum": [{"k": "FAKEENUMSECRET7"}, ["FAKEENUMSECRET8"], "FAKEENUMSECRET9"]},
    "default_with_properties_key": {"default": {"properties": {"x": "FAKEPROPSECRET10"}}},
    "anyof_branch_default": {"anyOf": [{"type": "object", "default": {"k": "FAKEANYOF11"}}]},
}


@pytest.mark.parametrize("case", sorted(NESTED_VALUE_CASES))
def test_nested_values_under_secret_named_property_are_redacted(catalog, case):
    report = catalog(server(pages=[page([schema_tool(NESTED_VALUE_CASES[case])])]))
    assert "FAKE" not in dumped(report), case


def test_nested_redaction_keeps_structure_and_non_secret_properties(catalog):
    secret = {"type": "object", "description": "Auth blob", "default": {"user": "FAKEUSER1"}}
    ok = {"type": "object", "default": {"mode": "fast"}, "enum": [{"mode": "fast"}]}
    tool = {"name": "t", "inputSchema": {"type": "object", "properties": {"api_key": secret, "mode": ok}}}
    report = catalog(server(pages=[page([tool])]))
    props = report["servers"][0]["tools"][0]["definition"]["inputSchema"]["properties"]
    assert props["api_key"]["default"] == {"user": "<redacted>"}     # 구조는 유지하고 값만 가린다
    assert props["api_key"]["description"] == "Auth blob"
    assert props["mode"] == ok                                       # 비밀 이름이 아닌 속성은 그대로
    reasons = {r["reason"] for r in report["servers"][0]["tools"][0]["redactions"]}
    assert "secret_named_property_value" in reasons


# ---- 2. 긴 오류 메시지: 가림 후 자르기 -------------------------------------------------------

def long_message(secret: str, prefix_len: int) -> str:
    """비밀값이 길이 제한 경계에 걸치도록 앞에 일반 문장을 채운다."""
    return "x" * prefix_len + " " + secret


@pytest.mark.parametrize("prefix_len", [MAX_MESSAGE_CHARS - 30, MAX_MESSAGE_CHARS - 20, MAX_MESSAGE_CHARS - 12])
@pytest.mark.parametrize("secret", [
    "sk-FAKEOPENAIKEY1234567890ABCDEFGHIJ",
    "Bearer FAKEBEARERVALUE1234567890",
    "eyJFAKEHEADER.FAKEPAYLOAD.FAKESIGNATURE",
    "https://user:FAKEURLPASS@host.example.test/p",
])
def test_error_message_is_redacted_before_truncation(catalog, prefix_len, secret):
    err = {"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": long_message(secret, prefix_len)}}
    report = catalog(server(pages=[err]))
    assert "FAKE" not in dumped(report)


def test_error_message_is_still_truncated_after_redaction(catalog):
    err = {"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "y" * 5000}}
    report = catalog(server(pages=[err]))
    msg = report["servers"][0]["issues"][0]["error_message"]
    assert len(msg) <= MAX_MESSAGE_CHARS + 1


def test_other_truncating_call_sites_redact_before_truncating(catalog):
    pad = "p" * (MAX_MESSAGE_CHARS - 22)
    secret = "eyJFAKEHEADER.FAKEPAYLOAD.FAKESIGNATURE"   # 경계에서 잘리면 세 번째 조각이 사라져 패턴에 걸리지 않는다
    odd = pad + " " + secret
    bad_result_type = page()
    bad_result_type["result"]["resultType"] = odd
    report = catalog(
        server("a", pages=[bad_result_type]),                       # resultType 기록
        server("b", pages=[page()], version=odd),                   # 지원하지 않는 protocol_version
        origin=odd,                                                 # origin
    )
    assert "FAKE" not in dumped(report)


# ---- 3. 하위 객체(env·headers 등)의 중복 키 ------------------------------------------------

def servers_config(body: str) -> str:
    return '{"mcp": {"servers": {' + body + "}}}"


GOOD = '"good": {"command": "node", "args": ["a.js"], "env": {"MODE": "x"}}'


@pytest.mark.parametrize("field,dup_name", [("env", "TOKEN_A"), ("headers", "X-Api-Key")])
def test_duplicate_key_in_credential_map_is_recorded_and_partial(write_config, field, dup_name):
    cfg = servers_config(
        f'"dup": {{"command": "node", "{field}": {{"{dup_name}": "${{FAKE_ONE}}", "{dup_name}": "${{FAKE_TWO}}", "OK": "v"}}}},'
        + GOOD)
    result = collect(write_config(cfg))
    by_key = {s["registration_key"]: s for s in result["servers"]}
    dup = by_key["dup"]
    assert dup["collection_status"] == "partial"
    issues = [i for i in dup["issues"] if i["code"] == "duplicate_key"]
    assert [i["field_path"] for i in issues] == [f"mcp.servers.dup.{field}.{dup_name}"] or \
        [i["field_path"] for i in issues] == [f'mcp.servers.dup.{field}["{dup_name}"]']
    assert result["collection"]["status"] == "partial"
    assert "dup" in next(r for r in result["collection"]["reasons"]
                         if r["code"] == "server_entries_incomplete")["registration_keys"]
    # 정상 서버 정보는 보존된다.
    good = by_key["good"]
    assert good["collection_status"] == "complete"
    assert good["declared"]["command"] == "node"
    assert good["credentials"]["env"]["names"] == ["MODE"]
    # 중복 키가 있어도 나머지 필드는 계속 수집한다.
    assert dup["declared"]["command"] == "node"
    assert "OK" in dup["credentials"][field]["names"]


def test_duplicate_key_in_nested_object_deeper_than_credential_map(write_config):
    cfg = servers_config('"s": {"command": "node", "auth": {"a": 1, "a": 2}, "extra": {"k": {"z": 1, "z": 2}}}')
    result = collect(write_config(cfg))
    s = result["servers"][0]
    assert s["collection_status"] == "partial"
    paths = sorted(i["field_path"] for i in s["issues"] if i["code"] == "duplicate_key")
    assert paths == ["mcp.servers.s.auth.a", "mcp.servers.s.extra.k.z"]
    assert result["collection"]["status"] == "partial"


def test_duplicate_secret_looking_key_does_not_leak_name(write_config):
    secret_key = "ghp_FAKEDUPLICATEKEY12345"
    cfg = servers_config(f'"s": {{"command": "node", "env": {{"{secret_key}": "a", "{secret_key}": "b"}}}}')
    result = collect(write_config(cfg))
    assert "FAKE" not in json.dumps(result, ensure_ascii=False)
    s = result["servers"][0]
    assert s["collection_status"] == "partial"
    assert any(i["code"] == "duplicate_key" for i in s["issues"])


def test_no_duplicate_keys_stays_complete(write_config):
    result = collect(write_config(servers_config(GOOD)))
    assert result["collection"]["status"] == "complete"
    assert result["servers"][0]["collection_status"] == "complete"


# ---- 호환성 통합: manifest · 2025-11-25 --------------------------------------------------

def test_duplicate_key_in_plugin_manifest_env_is_partial(tmp_path):
    from asset_scanner.collector import collect_plugin_manifest
    path = tmp_path / "plugin.json"
    path.write_text('{"mcpServers": {"p": {"command": "node", "env": {"A": "1", "A": "2"}},'
                    ' "ok": {"command": "node"}}}', encoding="utf-8")
    result = collect_plugin_manifest(path)
    by_key = {s["registration_key"]: s for s in result["servers"]}
    assert by_key["p"]["collection_status"] == "partial"
    assert any(i["code"] == "duplicate_key" for i in by_key["p"]["issues"])
    assert by_key["ok"]["collection_status"] == "complete"
    assert result["collection"]["status"] == "partial"


def test_2025_error_message_is_redacted_before_truncation(tmp_path):
    secret = "eyJFAKEHEADER.FAKEPAYLOAD.FAKESIGNATURE"
    err = {"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "x" * (MAX_MESSAGE_CHARS - 22) + " " + secret}}
    path = tmp_path / "capture.json"
    path.write_text(json.dumps({"servers": [{"server_ref": "s", "protocol_version": "2025-11-25", "pages": [err]}]}),
                    encoding="utf-8")
    assert "FAKE" not in dumped(build_catalog_report(collect_tools_catalog(path)))


def test_2025_nested_secret_property_default_is_redacted(tmp_path):
    tool = schema_tool({"type": "object", "default": {"k": ["FAKENESTED2025"]}})
    path = tmp_path / "capture.json"
    path.write_text(json.dumps({"servers": [{"server_ref": "s", "protocol_version": "2025-11-25",
                                             "pages": [{"tools": [tool]}]}]}), encoding="utf-8")
    assert "FAKE" not in dumped(build_catalog_report(collect_tools_catalog(path)))
