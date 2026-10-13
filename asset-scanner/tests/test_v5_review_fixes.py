"""스캐너 V5 검토(V5-R1~R3) 회귀 테스트.

모든 입력은 손으로 만든 **가상 자료**이며, `FAKE` 표식이 붙은 값은 전부 가짜 비밀값이다.
실제 MCP 서버에 접속하지 않고 실제 설정·인증정보를 쓰지 않는다.

- R1: Tool 정의의 키·properties 이름·구조 키($id/$ref)·_meta 인증 필드 가림
- R2: 입력 최상위·서버 항목·응답 외피의 중복 키를 완전 수집으로 보고하지 않음
- R3: 고립된 surrogate·비유한 숫자 처리, 저장 실패 시 결과 파일 보존, 종료 코드 구분
"""

import hashlib
import json
import os
import re
import subprocess
import sys

import pytest

from conftest import EXAMPLES, SCANNER_ROOT

V = "2026-07-28"
REDACTED = "<redacted>"


# ---- 도우미 ---------------------------------------------------------------------------

def tool(name="t", **extra):
    base = {"name": name, "inputSchema": {"type": "object"}}
    base.update(extra)
    return base


def page(tools, **result_extra):
    result = {"resultType": "complete", "tools": tools, "ttlMs": 1000, "cacheScope": "public"}
    result.update(result_extra)
    return {"jsonrpc": "2.0", "id": 1, "result": result}


def server(ref="s", pages=None, **extra):
    entry = {"server_ref": ref, "protocol_version": V, "pages": pages if pages is not None else [page([tool()])]}
    entry.update(extra)
    return entry


def write_json(tmp_path, *servers, name="capture.json", **top):
    path = tmp_path / name
    path.write_text(json.dumps({"origin": "synthetic_test_data", "servers": list(servers), **top}), encoding="utf-8")
    return path


def write_text(tmp_path, text, name="capture.json"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_catalog(capture, output, io_encoding="utf-8"):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env["PYTHONIOENCODING"] = io_encoding
    proc = subprocess.run(
        [sys.executable, "-m", "asset_scanner.tools_catalog", "--capture", str(capture), "--output", str(output)],
        cwd=SCANNER_ROOT, env=env, capture_output=True,
    )
    return proc.returncode, proc.stdout.decode(io_encoding, "replace"), proc.stderr.decode(io_encoding, "replace")


def run_config(config, output, io_encoding="utf-8"):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env["PYTHONIOENCODING"] = io_encoding
    proc = subprocess.run(
        [sys.executable, "-m", "asset_scanner", "--config", str(config), "--output", str(output)],
        cwd=SCANNER_ROOT, env=env, capture_output=True,
    )
    return proc.returncode, proc.stdout.decode(io_encoding, "replace"), proc.stderr.decode(io_encoding, "replace")


def load(out):
    return json.loads(out.read_text(encoding="utf-8"))


def strict_load(out):
    """엄격한 JSON으로만 읽는다: NaN·Infinity 토큰이나 잘못된 UTF-8이 있으면 실패한다."""
    def refuse(token):
        raise AssertionError(f"non-standard JSON constant in output: {token}")
    return json.loads(out.read_bytes().decode("utf-8"), parse_constant=refuse)


def all_text(out, stdout, stderr):
    return out.read_text(encoding="utf-8") + "\n" + stdout + "\n" + stderr


# ===========================================================================================
# V5-R1: 가림 누락
# ===========================================================================================

R1_FAKES = [
    "FAKEKEY12345678901234567890", "FAKEPROPERTY1234567890123456", "FAKE_ID_PASSWORD", "FAKE_ID_QUERY",
    "FAKE_REF_PASSWORD", "FAKE_REF_QUERY", "FAKE_NAMED_META_SECRET",
]


def r1_tool():
    return tool(
        "t",
        inputSchema={
            "$id": "https://u:FAKE_ID_PASSWORD@example.test/schema?token=FAKE_ID_QUERY",
            "type": "object",
            "properties": {
                "ghp_FAKEPROPERTY1234567890123456": {"type": "string", "description": "kept description"},
                "plain": {"type": "integer"},
            },
            "required": ["ghp_FAKEPROPERTY1234567890123456", "plain"],
        },
        _meta={
            "ghp_FAKEKEY12345678901234567890": "kept value",
            "$ref": "https://u:FAKE_REF_PASSWORD@example.test/mcp?token=FAKE_REF_QUERY",
            "api_key": "FAKE_NAMED_META_SECRET",
            "vendor": "acme",
        },
    )


def test_r1_reproduction_inputs_leave_no_fake_value_in_file_stdout_or_stderr(tmp_path):
    cap = write_json(tmp_path, server(pages=[page([r1_tool()])]))
    before = sha(cap)
    out = tmp_path / "o.json"
    code, stdout, stderr = run_catalog(cap, out)
    assert code == 0, stderr
    text = all_text(out, stdout, stderr)
    for fake in R1_FAKES:
        assert fake not in text, fake
    assert "ghp_FAKE" not in text
    assert sha(cap) == before                                   # 입력 파일은 바뀌지 않는다


def test_r1_token_shaped_keys_and_property_names_become_non_colliding_placeholders(tmp_path):
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    cap = write_json(tmp_path, server(pages=[page([r1_tool()])]))
    t = build_catalog_report(collect_tools_catalog(cap))["servers"][0]["tools"][0]
    schema = t["definition"]["inputSchema"]
    assert set(schema["properties"]) == {"<redacted-key-1>", "plain"}
    assert schema["properties"]["<redacted-key-1>"] == {"type": "string", "description": "kept description"}
    assert schema["required"] == ["<redacted-key-1>", "plain"]          # required의 참조도 같은 이름으로 맞춘다
    meta = t["definition"]["_meta"]
    assert meta["<redacted-key-1>"] == "kept value" and meta["vendor"] == "acme"
    reasons = {(r["field_path"], r["reason"]) for r in t["redactions"]}
    assert ("inputSchema.properties.<redacted-key-1>", "key_looks_like_secret") in reasons
    assert ("_meta.<redacted-key-1>", "key_looks_like_secret") in reasons


def test_r1_placeholder_never_overwrites_an_ordinary_key(tmp_path):
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    meta = {"<redacted-key-1>": "ordinary", "ghp_FAKEKEY12345678901234567890": "masked one",
            "ghp_FAKEOTHERKEY1234567890123456": "masked two"}
    cap = write_json(tmp_path, server(pages=[page([tool("t", _meta=meta)])]))
    out_meta = build_catalog_report(collect_tools_catalog(cap))["servers"][0]["tools"][0]["definition"]["_meta"]
    assert out_meta["<redacted-key-1>"] == "ordinary"
    assert sorted(out_meta.values()) == ["masked one", "masked two", "ordinary"]   # 값 3개가 모두 남는다
    assert len(out_meta) == 3


def test_r1_credential_urls_in_structural_keys_are_masked_but_ordinary_ones_kept(tmp_path):
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://u:FAKE_ID_PASSWORD@example.test/schema?token=FAKE_ID_QUERY",
        "type": "object",
        "properties": {
            "good_ref": {"$ref": "#/$defs/item"},
            "remote_ref": {"$ref": "https://example.com/schemas/remote.json"},
            "bad_ref": {"$ref": "https://u:FAKE_REF_PASSWORD@example.test/x.json?token=FAKE_REF_QUERY"},
            "name": {"type": "string", "pattern": "^[a-z0-9_-]{3,32}$", "format": "hostname"},
            "token_in_pattern": {"type": "string", "pattern": "^ghp_FAKEPATTERNTOKEN12345$"},
        },
        "$defs": {"item": {"type": "object"}},
    }
    cap = write_json(tmp_path, server(pages=[page([tool("t", inputSchema=schema)])]))
    t = build_catalog_report(collect_tools_catalog(cap))["servers"][0]["tools"][0]
    s = t["definition"]["inputSchema"]
    assert s["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert s["type"] == "object" and s["$defs"] == {"item": {"type": "object"}}
    assert s["properties"]["good_ref"] == {"$ref": "#/$defs/item"}
    assert s["properties"]["remote_ref"] == {"$ref": "https://example.com/schemas/remote.json"}
    assert s["properties"]["name"] == {"type": "string", "pattern": "^[a-z0-9_-]{3,32}$", "format": "hostname"}
    dumped = json.dumps(t)
    for fake in ("FAKE_ID_PASSWORD", "FAKE_ID_QUERY", "FAKE_REF_PASSWORD", "FAKE_REF_QUERY", "FAKEPATTERNTOKEN"):
        assert fake not in dumped, fake
    assert s["$id"].startswith("https://<redacted>@example.test/schema?token=<redacted>")
    reasons = {(r["field_path"], r["reason"]) for r in t["redactions"]}
    assert ("inputSchema.$id", "url_userinfo") in reasons
    assert ("inputSchema.properties.bad_ref.$ref", "url_query_values") in reasons


def test_r1_long_identifiers_under_structural_keys_are_not_erased_for_looking_random(tmp_path):
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    anchor = "ItemSchema2026Anchor0123456789ABCDEF"          # 문자·숫자만의 긴 식별자 (비밀값 모양 규칙에는 걸리는 형태)
    schema = {"type": "object", "$anchor": anchor, "properties": {"p": {"type": "string", "description": anchor}}}
    cap = write_json(tmp_path, server(pages=[page([tool("t", inputSchema=schema)])]))
    t = build_catalog_report(collect_tools_catalog(cap))["servers"][0]["tools"][0]
    s = t["definition"]["inputSchema"]
    assert s["$anchor"] == anchor                            # 구조 키: 토큰·URL 자격증명만 가리고 식별자는 보존
    assert s["properties"]["p"]["description"] == REDACTED   # 같은 모양의 일반 문장 값은 기존 규칙대로 가린다
    assert [r["field_path"] for r in t["redactions"]] == ["inputSchema.properties.p.description"]


def test_r1_named_meta_credential_fields_are_masked_by_name_and_position(tmp_path):
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    meta = {
        "api_key": "FAKE_NAMED_META_SECRET",
        "accessToken": "FAKE_CAMEL_TOKEN",
        "credentials": {"user": "FAKE_CRED_USER", "note": "FAKE_CRED_NOTE"},
        "auth": {"password": "FAKE_NESTED_PASSWORD"},
        "env_ref": {"api_key": "${API_KEY}"},                 # 값 없이 이름만 참조하는 경우는 보존
        "author": "Alice Kim", "vendor": "acme", "version": "1.2.3", "token_budget": 4000, "tags": ["a", "b"],
    }
    cap = write_json(tmp_path, server(pages=[page([tool("t", _meta=meta)])]))
    t = build_catalog_report(collect_tools_catalog(cap))["servers"][0]["tools"][0]
    m = t["definition"]["_meta"]
    assert m["api_key"] == REDACTED and m["accessToken"] == REDACTED
    assert m["credentials"] == {"user": REDACTED, "note": REDACTED}
    assert m["auth"] == {"password": REDACTED}
    assert m["env_ref"] == {"api_key": "${API_KEY}"}
    assert (m["author"], m["vendor"], m["version"], m["token_budget"], m["tags"]) == ("Alice Kim", "acme", "1.2.3", 4000, ["a", "b"])
    dumped = json.dumps(t)
    for fake in ("FAKE_NAMED_META_SECRET", "FAKE_CAMEL_TOKEN", "FAKE_CRED_USER", "FAKE_CRED_NOTE", "FAKE_NESTED_PASSWORD"):
        assert fake not in dumped, fake
    reasons = {(r["field_path"], r["reason"]) for r in t["redactions"]}
    assert ("_meta.api_key", "secret_named_field_value") in reasons
    assert ("_meta.credentials.user", "secret_named_field_value") in reasons


def test_r1_redaction_records_never_contain_original_values_or_keys(tmp_path):
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    cap = write_json(tmp_path, server(pages=[page([r1_tool()])]))
    t = build_catalog_report(collect_tools_catalog(cap))["servers"][0]["tools"][0]
    assert t["redactions"]
    recorded = json.dumps(t["redactions"])
    for fake in R1_FAKES + ["ghp_FAKE"]:
        assert fake not in recorded


def test_r1_ordinary_schema_and_metadata_are_preserved_unchanged(tmp_path):
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    good = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.com/schemas/tool.json",
        "type": "object",
        "$defs": {"item": {"type": "object", "properties": {"id": {"type": "string", "pattern": "^[a-z0-9_-]{3,32}$"}}, "required": ["id"]}},
        "properties": {
            "items": {"type": "array", "items": {"$ref": "#/$defs/item"}},
            "remote": {"$ref": "https://example.com/schemas/remote.json"},
            "mode": {"enum": ["fast", "slow"], "default": "fast"},
        },
        "required": ["items"], "additionalProperties": False,
    }
    meta = {"vendor": "acme", "docs": "https://example.com/docs", "author": "Alice"}
    cap = write_json(tmp_path, server(pages=[page([tool("t", inputSchema=good, _meta=meta)])]))
    t = build_catalog_report(collect_tools_catalog(cap))["servers"][0]["tools"][0]
    assert t["definition"]["inputSchema"] == good and t["definition"]["_meta"] == meta
    assert t["redactions"] == [] and t["definition_altered"] is False


def test_r1_altered_definitions_are_marked_and_refs_are_documented_as_not_resolved(tmp_path):
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    cap = write_json(tmp_path, server(pages=[page([r1_tool()])]))
    report = build_catalog_report(collect_tools_catalog(cap))
    assert report["servers"][0]["tools"][0]["definition_altered"] is True
    note = report["scope"]["definition_validation"]["redaction_note"]
    assert "원본과 달라질 수 있" in note and "$ref" in note and "실행·조회하지 않" in note


# ===========================================================================================
# V5-R2: 상위 중복 키
# ===========================================================================================

def dup_response_text():
    a = json.dumps({"resultType": "complete", "tools": [tool("a")], "ttlMs": 1, "cacheScope": "public"})
    b = json.dumps({"resultType": "complete", "tools": [tool("b")], "ttlMs": 1, "cacheScope": "public"})
    return '{"jsonrpc":"2.0","id":1,"result":' + a + ',"result":' + b + "}"


def one_server_text(ref="dup", pages_text=None):
    pages_text = pages_text or "[" + json.dumps(page([tool("x")])) + "]"
    return '{"server_ref":"' + ref + '","protocol_version":"2026-07-28","pages":' + pages_text + "}"


def names(srv):
    return [t["definition"]["name"] for t in srv["tools"]]


def test_r2_duplicate_result_in_a_response_envelope_is_not_complete(tmp_path):
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    text = '{"servers":[' + one_server_text("dup", "[" + dup_response_text() + "]") + "," + json.dumps(server("ok")) + "]}"
    cap = write_text(tmp_path, text)
    report = build_catalog_report(collect_tools_catalog(cap))
    dup, ok = report["servers"]
    assert dup["collection_status"] == "partial" and names(dup) == ["b"]      # 마지막 값만 남음 + 불완전 보고
    issue = next(i for i in dup["issues"] if i["code"] == "duplicate_key")
    assert issue["field_path"] == "pages[0]" and issue["duplicate_keys"] == ["result"] and issue["page_index"] == 0
    assert (ok["collection_status"], names(ok)) == ("complete", ["t"])         # 다른 정상 서버는 보존
    assert report["collection"]["status"] == "partial"
    out = tmp_path / "o.json"
    assert run_catalog(cap, out)[0] == 1


def test_r2_duplicate_servers_array_at_top_level_marks_the_whole_file_incomplete(tmp_path):
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    text = '{"servers":[' + json.dumps(server("a")) + '],"servers":[' + json.dumps(server("b")) + "]}"
    cap = write_text(tmp_path, text)
    before = sha(cap)
    report = build_catalog_report(collect_tools_catalog(cap))
    assert [s["server_ref"] for s in report["servers"]] == ["b"]               # 마지막 값은 읽는다
    assert report["servers"][0]["collection_status"] == "complete"
    col = report["collection"]
    assert col["status"] == "partial" and col["outcome"] == "duplicate_keys_in_capture"
    assert col["tool_count_complete"] is False
    reason = next(r for r in col["reasons"] if r["code"] == "duplicate_key_in_capture")
    assert reason["field_path"] == "(root)" and reason["duplicate_keys"] == ["servers"]
    out = tmp_path / "o.json"
    assert run_catalog(cap, out)[0] == 1
    assert sha(cap) == before


def test_r2_duplicate_pages_in_a_server_entry_marks_only_that_server(tmp_path):
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    first = "[" + json.dumps(page([tool("first")])) + "]"
    second = "[" + json.dumps(page([tool("second")])) + "]"
    entry = '{"server_ref":"dup","protocol_version":"2026-07-28","pages":' + first + ',"pages":' + second + "}"
    cap = write_text(tmp_path, '{"servers":[' + entry + "," + json.dumps(server("ok")) + "]}")
    dup, ok = build_catalog_report(collect_tools_catalog(cap))["servers"]
    assert dup["collection_status"] == "partial" and dup["outcome"] == "duplicate_keys"
    assert names(dup) == ["second"]
    issue = next(i for i in dup["issues"] if i["code"] == "duplicate_key")
    assert issue["field_path"] == "servers[0]" and issue["duplicate_keys"] == ["pages"]
    assert ok["collection_status"] == "complete" and names(ok) == ["t"]


def test_r2_a_failed_server_stays_failed_and_still_reports_the_duplicate(tmp_path):
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    entry = '{"server_ref":"dup","protocol_version":"2026-07-28","protocol_version":"2025-06-18","pages":[]}'
    cap = write_text(tmp_path, '{"servers":[' + entry + "," + json.dumps(server("ok")) + "]}")
    dup, ok = build_catalog_report(collect_tools_catalog(cap))["servers"]
    assert dup["collection_status"] == "failed" and dup["tool_count"] is None
    assert any(i["code"] == "duplicate_key" and i["duplicate_keys"] == ["protocol_version"] for i in dup["issues"])
    assert ok["collection_status"] == "complete"


def test_r2_other_top_level_and_envelope_duplicates_are_detected(tmp_path):
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    p = json.dumps(page([tool("a")]))
    envelope = p[:-1] + ',"id":2}'                                              # 응답 외피의 id 중복
    cap = write_text(tmp_path, '{"origin":"x","origin":"y","servers":[' + one_server_text("e", "[" + envelope + "]") + "]}")
    report = build_catalog_report(collect_tools_catalog(cap))
    assert report["collection"]["status"] == "partial"
    assert next(r for r in report["collection"]["reasons"] if r["code"] == "duplicate_key_in_capture")["duplicate_keys"] == ["origin"]
    srv = report["servers"][0]
    assert srv["collection_status"] == "partial"
    assert any(i["code"] == "duplicate_key" and i["field_path"] == "pages[0]" and i["duplicate_keys"] == ["id"] for i in srv["issues"])


def test_r2_token_shaped_duplicate_key_names_are_not_recorded_verbatim(tmp_path):
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    k = "ghp_FAKEDUPKEY1234567890123456"
    cap = write_text(tmp_path, '{"' + k + '":1,"' + k + '":2,"servers":[' + json.dumps(server("a")) + "]}")
    out = tmp_path / "o.json"
    code, stdout, stderr = run_catalog(cap, out)
    assert code == 1 and "FAKEDUPKEY" not in all_text(out, stdout, stderr)


def test_r2_existing_inner_duplicate_checks_and_same_name_tools_are_kept(tmp_path):
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    tool_dup = ('{"name":"a","description":"x","description":"y","inputSchema":{"type":"object"}}')
    result = '{"resultType":"complete","ttlMs":1,"cacheScope":"public","tools":[' + tool_dup + "]}"
    resp = '{"jsonrpc":"2.0","id":1,"result":' + result + "}"
    cap = write_text(tmp_path, '{"servers":[' + one_server_text("inner", "[" + resp + "]") + "]}")
    srv = build_catalog_report(collect_tools_catalog(cap))["servers"][0]
    assert srv["collection_status"] == "partial"
    assert any(i["code"] == "duplicate_key" and i["field_path"] == "pages[0].result.tools[0]" for i in srv["issues"])
    same = write_json(tmp_path, server("one", pages=[page([tool("read_file")])]), server("two", pages=[page([tool("read_file")])]),
                      name="same.json")
    report = build_catalog_report(collect_tools_catalog(same))
    assert report["collection"]["status"] == "complete" and report["collection"]["tool_count"] == 2
    assert report["servers"][0]["tools"][0]["internal_ref"] != report["servers"][1]["tools"][0]["internal_ref"]


def test_r2_clean_input_is_still_complete(tmp_path):
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    report = build_catalog_report(collect_tools_catalog(EXAMPLES / "tools-list-capture.json"))
    assert report["collection"]["status"] == "complete"
    assert not any(r["code"] == "duplicate_key_in_capture" for r in report["collection"]["reasons"])


# ===========================================================================================
# V5-R3: surrogate · 비유한 숫자 · 저장 안전성
# ===========================================================================================

def test_r3_lone_surrogate_in_description_is_replaced_and_the_result_is_saved(tmp_path):
    cap = write_json(tmp_path, server(pages=[page([tool("bad", description="A\ud800B"), tool("good", description="한글 😀 é")])]))
    before = sha(cap)
    out = tmp_path / "o.json"
    code, stdout, stderr = run_catalog(cap, out)
    assert code == 0, stderr
    assert "Traceback" not in stderr and stderr == ""
    assert out.stat().st_size > 0
    report = strict_load(out)                                                # 엄격한 UTF-8 JSON이어야 한다
    tools = report["servers"][0]["tools"]
    assert tools[0]["definition"]["description"] == "A�B"             # 문제 글자만 U+FFFD로 대체
    assert {"field_path": "description", "reason": "lone_surrogate_replaced"} in tools[0]["redactions"]
    assert tools[0]["definition_altered"] is True
    assert tools[1]["definition"]["description"] == "한글 😀 é"              # 유효한 문자열은 원문 보존
    raw = out.read_bytes().decode("utf-8")
    assert "한글 😀 é" in raw                                                # 이스케이프하지 않고 원문 그대로 저장
    assert report["collection"]["status"] == "complete" and report["collection"]["tool_count"] == 2
    assert sha(cap) == before


def test_r3_valid_surrogate_pair_escape_is_an_ordinary_emoji(tmp_path):
    path = write_text(tmp_path, '{"servers":[' + json.dumps(server("s", pages=[page([tool("t", description="x")])])).replace(
        '"description": "x"', '"description": "\\ud83d\\ude00"') + "]}")
    out = tmp_path / "o.json"
    assert run_catalog(path, out)[0] == 0
    t = strict_load(out)["servers"][0]["tools"][0]
    assert t["definition"]["description"] == "\U0001f600" and t["redactions"] == []


@pytest.mark.parametrize("place", ["property_name", "meta_key", "server_ref", "registration_key", "origin", "error_message", "tool_name"])
def test_r3_lone_surrogates_anywhere_never_crash_the_save(tmp_path, place):
    tools = [tool("t", inputSchema={"type": "object", "properties": {"p\ud800": {"type": "string"}}})] if place == "property_name" else \
            [tool("t", _meta={"k\ud800": "v"})] if place == "meta_key" else \
            [tool("n\ud800ame")] if place == "tool_name" else [tool("t")]
    pages = [page(tools)]
    if place == "error_message":
        pages = [{"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "bad \ud800 message"}}]
    entry = server("ref\ud800" if place == "server_ref" else "s", pages=pages,
                   **({"registration_key": "rk\ud800"} if place == "registration_key" else {}))
    other = server("other", pages=[page([tool("kept")])])
    top = {"origin": "o\ud800"} if place == "origin" else {}
    cap = write_json(tmp_path, entry, other, **top)
    out = tmp_path / "o.json"
    code, stdout, stderr = run_catalog(cap, out)
    assert code in (0, 1), stderr                                            # 저장 실패(4)나 예외(1+traceback)가 아니다
    assert "Traceback" not in stderr
    report = strict_load(out)
    assert report["servers"][1]["tools"][0]["definition"]["name"] == "kept"  # 다른 서버는 보존
    assert "\ud800" not in out.read_bytes().decode("utf-8")


def test_r3_lone_surrogate_in_a_key_is_replaced_by_a_non_colliding_placeholder(tmp_path):
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    meta = {"k\ud800": "one", "<redacted-key-1>": "ordinary"}
    cap = write_json(tmp_path, server(pages=[page([tool("t", _meta=meta)])]))
    t = build_catalog_report(collect_tools_catalog(cap))["servers"][0]["tools"][0]
    assert t["definition"]["_meta"] == {"<redacted-key-2>": "one", "<redacted-key-1>": "ordinary"}
    assert {"field_path": "_meta.<redacted-key-2>", "reason": "lone_surrogate_in_key"} in t["redactions"]


NONFINITE_TOKENS = ["Infinity", "-Infinity", "NaN", "1e400", "-1e400", "1" + "0" * 400]


@pytest.mark.parametrize("token", NONFINITE_TOKENS)
def test_r3_non_finite_ttl_is_not_accepted_and_not_written(tmp_path, token):
    text = json.dumps({"servers": [server("s", pages=[page([tool("kept")], ttlMs="__X__")])]}).replace('"__X__"', token)
    cap = write_text(tmp_path, text)
    before = sha(cap)
    out = tmp_path / "o.json"
    code, stdout, stderr = run_catalog(cap, out)
    assert code == 0, stderr                                                 # 읽은 Tool은 보존, 수집 완전성은 그대로
    raw = out.read_text(encoding="utf-8")
    assert not re.search(r"(?<![A-Za-z])(NaN|-?Infinity)(?![A-Za-z])", raw)  # 결과에 비유한 토큰이 없다
    report = strict_load(out)
    srv = report["servers"][0]
    assert "ttl_ms" not in srv["pages"][0]                                   # 정상 캐시 힌트로 기록하지 않는다
    assert srv["spec_conformance"]["violations"] == ["cache_hint_invalid"]
    assert [t["definition"]["name"] for t in srv["tools"]] == ["kept"]
    assert sha(cap) == before


def test_r3_non_finite_numbers_inside_definitions_are_replaced_with_a_record(tmp_path):
    schema = '{"type":"object","properties":{"n":{"type":"number","maximum":Infinity,"minimum":-1e400,"default":NaN,"multipleOf":0.5}}}'
    t_json = '{"name":"t","inputSchema":' + schema + "}"
    resp = '{"jsonrpc":"2.0","id":1,"result":{"resultType":"complete","ttlMs":1,"cacheScope":"public","tools":[' + t_json + "]}}"
    cap = write_text(tmp_path, '{"servers":[{"server_ref":"s","protocol_version":"2026-07-28","pages":[' + resp + "]}]}")
    out = tmp_path / "o.json"
    code, stdout, stderr = run_catalog(cap, out)
    assert code == 0, stderr
    report = strict_load(out)
    t = report["servers"][0]["tools"][0]
    n = t["definition"]["inputSchema"]["properties"]["n"]
    assert n["maximum"] == n["minimum"] == n["default"] == "<non-finite-number>"
    assert n["multipleOf"] == 0.5 and n["type"] == "number"                   # 유한한 값은 그대로
    reasons = {(r["field_path"], r["reason"]) for r in t["redactions"]}
    assert ("inputSchema.properties.n.maximum", "non_finite_number_replaced") in reasons
    assert t["definition_altered"] is True


def test_r3_output_is_always_strict_json_even_for_unexpected_values():
    from asset_scanner.output import OutputError, dumps_strict
    with pytest.raises(OutputError):
        dumps_strict({"x": float("nan")})
    with pytest.raises(OutputError):
        dumps_strict({"x": float("inf")})
    with pytest.raises(OutputError):
        dumps_strict({"x": "a\ud800b"})


def test_r3_atomic_write_keeps_the_existing_file_when_serialization_fails(tmp_path):
    from asset_scanner.output import OutputError, write_json_atomic
    target = tmp_path / "result.json"
    target.write_text("OLD RESULT", encoding="utf-8")
    for bad in ({"x": object()}, {"x": float("nan")}, {"x": "a\ud800b"}):
        with pytest.raises(OutputError):
            write_json_atomic(target, bad)
        assert target.read_text(encoding="utf-8") == "OLD RESULT"
    assert [p.name for p in tmp_path.iterdir()] == ["result.json"]           # 임시 파일이 남지 않는다
    fresh = tmp_path / "fresh.json"
    with pytest.raises(OutputError):
        write_json_atomic(fresh, {"x": "a\ud800b"})
    assert not fresh.exists()                                                # 빈 파일도 만들지 않는다


def test_r3_atomic_write_keeps_the_existing_file_when_the_final_replace_fails(tmp_path, monkeypatch):
    import asset_scanner.output as output
    target = tmp_path / "result.json"
    target.write_text("OLD RESULT", encoding="utf-8")

    def boom(*a, **k):
        raise OSError("simulated replace failure")
    monkeypatch.setattr(output.os, "replace", boom)
    with pytest.raises(output.OutputError):
        output.write_json_atomic(target, {"ok": 1})
    assert target.read_text(encoding="utf-8") == "OLD RESULT"
    assert [p.name for p in tmp_path.iterdir()] == ["result.json"]


def test_r3_catalog_cli_save_failure_is_exit_4_without_traceback_and_keeps_old_result(tmp_path, monkeypatch, capsys):
    import asset_scanner.output as output
    from asset_scanner import tools_catalog
    cap = write_json(tmp_path, server())
    out = tmp_path / "result.json"
    out.write_text("OLD RESULT", encoding="utf-8")
    monkeypatch.setattr(output.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("simulated")))
    code = tools_catalog.main(["--capture", str(cap), "--output", str(out)])
    err = capsys.readouterr().err
    assert code == 4 and "저장하지 못했습니다" in err and "Traceback" not in err
    assert out.read_text(encoding="utf-8") == "OLD RESULT"


def test_r3_save_failure_input_problem_and_collection_status_use_different_exit_codes(tmp_path):
    bad_json = write_text(tmp_path, "{not json", name="bad.json")
    out = tmp_path / "o1.json"
    assert run_catalog(bad_json, out)[0] == 3 and out.stat().st_size > 0      # 입력 문제 = 수집 실패(3), 결과는 저장됨
    partial = write_json(tmp_path, server(pages=[page([tool("a")], nextCursor="c")]), name="partial.json")
    assert run_catalog(partial, tmp_path / "o2.json")[0] == 1                 # 수집 상태 = 부분(1)
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")
    code, _, err = run_catalog(write_json(tmp_path, server(), name="ok.json"), blocker / "o3.json")
    assert code == 4 and "Traceback" not in err                                # 저장 실패 = 4


def test_r3_catalog_cp949_console_and_utf8_file_regression(tmp_path):
    cap = write_json(tmp_path, server("서버😀", pages=[page([tool("파일읽기", description="설명 😀 é")])]))
    out = tmp_path / "o.json"
    code, stdout, stderr = run_catalog(cap, out, io_encoding="cp949")
    assert code == 0 and stderr == "" and "Traceback" not in stderr
    t = strict_load(out)["servers"][0]
    assert t["server_ref"] == "서버😀"                                          # 파일은 항상 UTF-8 원문
    assert t["tools"][0]["definition"] == {"name": "파일읽기", "description": "설명 😀 é", "inputSchema": {"type": "object"}}


# ---- 설정 수집 CLI의 같은 저장 결함 ------------------------------------------------------

def test_r3_config_cli_lone_surrogate_no_longer_crashes_or_leaves_an_empty_file(tmp_path):
    cfg = tmp_path / "openclaw.json5"
    cfg.write_text('{ mcp: { servers: { "sur": { command: "a\\ud800b" }, "한글": { command: "example" } } } }', encoding="utf-8")
    before = sha(cfg)
    out = tmp_path / "o.json"
    code, stdout, stderr = run_config(cfg, out)
    assert code == 0, stderr
    assert "Traceback" not in stderr and stderr == ""
    report = strict_load(out)
    by_key = {s["registration_key"]: s for s in report["servers"]}
    assert by_key["sur"]["declared"]["command"] == "a�b"
    assert "한글" in by_key and out.stat().st_size > 0
    assert report["collection"]["output_text_normalizations"] >= 1
    assert sha(cfg) == before                                                  # 원본 설정은 바뀌지 않는다


def test_r3_config_cli_failure_keeps_the_previous_result(tmp_path, monkeypatch, capsys):
    import asset_scanner.output as output
    from asset_scanner import cli
    cfg = tmp_path / "openclaw.json5"
    cfg.write_text('{ mcp: { servers: { "ok": { command: "example" } } } }', encoding="utf-8")
    out = tmp_path / "result.json"
    out.write_text("OLD RESULT", encoding="utf-8")
    monkeypatch.setattr(output.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("simulated")))
    code = cli.main(["--config", str(cfg), "--output", str(out)])
    err = capsys.readouterr().err
    assert code == 4 and "Traceback" not in err
    assert out.read_text(encoding="utf-8") == "OLD RESULT"
    assert [p.name for p in tmp_path.iterdir() if p.name != "openclaw.json5"] == ["result.json"]


def test_r3_config_cli_normal_runs_are_unchanged(tmp_path):
    out = tmp_path / "o.json"
    code, stdout, stderr = run_config(EXAMPLES / "two-servers.json5", out)
    assert code == 0 and stderr == ""
    report = strict_load(out)
    assert report["collection"]["status"] == "complete" and "output_text_normalizations" not in report["collection"]
