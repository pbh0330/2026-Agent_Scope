"""저장된 resources/list · resources/templates/list · prompts/list 응답 읽기 테스트.

모든 입력은 MCP 2025-11-25 / 2026-07-28 응답 형식에 맞춰 손으로 만든 **가상 자료**다. 실제 MCP 서버를 조회하지 않으며
`FAKE` 표식이 붙은 값은 전부 가짜 비밀값이다.
"""

import json
import os
import subprocess
import sys

import pytest

from asset_scanner import resources_prompts as rp
from asset_scanner.resources_prompts import build_report, collect_resources_prompts
from asset_scanner.tools_catalog import MAX_MESSAGE_CHARS, collect_tools_catalog
from conftest import EXAMPLES, SCANNER_ROOT

V6, V5 = "2026-07-28", "2025-11-25"
FIELD = {"resources": "resources", "resource_templates": "resourceTemplates", "prompts": "prompts"}
TOKEN = "ghp_FAKELISTTOKEN1234567890abcdefgh"


def res(uri="file:///a", name="a", **kw):
    return {"uri": uri, "name": name, **kw}


def tpl(t="file:///{p}", name="t", **kw):
    return {"uriTemplate": t, "name": name, **kw}


def prm(name="p", **kw):
    return {"name": name, **kw}


def result(kind, items, version=V6, cursor=None, **extra):
    r = {FIELD[kind]: items}
    if version == V6:
        r.update(resultType="complete", ttlMs=1000, cacheScope="public")
    if cursor is not None:
        r["nextCursor"] = cursor
    r.update(extra)
    return r


def page(kind, items, version=V6, cursor=None, **extra):
    return {"jsonrpc": "2.0", "id": 1, "result": result(kind, items, version, cursor, **extra)}


def error(code=-32601, msg="Method not found", **extra):
    return {"jsonrpc": "2.0", "id": 1, "error": {"code": code, "message": msg, **extra}}


def srv(ref="s", version=V6, caps=None, **lists):
    entry = {"server_ref": ref, "protocol_version": version, "lists": {k: {"pages": v} for k, v in lists.items()}}
    if caps is not None:
        entry["server_capabilities"] = caps
    return entry


def full(ref="s", version=V6):
    return srv(ref, version, resources=[page("resources", [res()], version)],
               resource_templates=[page("resource_templates", [tpl()], version)],
               prompts=[page("prompts", [prm()], version)])


def write(tmp_path, servers, **top):
    cap = {"format": "mcp-lists-capture", "origin": "synthetic_test_data", "servers": servers, **top}
    p = tmp_path / "cap.json"
    p.write_text(json.dumps(cap), encoding="utf-8")
    return p


@pytest.fixture
def run(tmp_path):
    def _run(*servers, **top):
        return build_report(collect_resources_prompts(write(tmp_path, list(servers), **top)))
    return _run


def lst(rep, kind, server=0):
    return rep["servers"][server]["lists"][kind]


def codes(lst_):
    return [i["code"] for i in lst_["issues"]]


# ---- 정상 수집: 세 목록, 두 규격 --------------------------------------------------------

@pytest.mark.parametrize("version", [V6, V5])
def test_three_lists_are_collected_with_kind_and_server(run, version):
    rep = run(full("alpha", version), full("beta", version))
    assert rep["collection"]["status"] == "complete" and rep["collection"]["item_counts"] == {
        "resources": 2, "resource_templates": 2, "prompts": 2}
    for si, ref in enumerate(("alpha", "beta")):
        s = rep["servers"][si]
        assert (s["server_index"], s["server_ref"], s["collection_status"]) == (si, ref, "complete")
        for kind, plural in (("resources", "resource"), ("resource_templates", "resource_template"), ("prompts", "prompt")):
            item = lst(rep, kind, si)["items"][0]
            assert item["kind"] == plural and item["server_index"] == si and item["server_ref"] == ref
            assert item["internal_ref"] == f"capture-server[{si}]/{kind}[0]"
            assert item["trust"] == "untrusted_server_provided"


def test_only_provided_fields_are_collected_and_nothing_is_invented(run):
    r = res("file:///a.md", "a", title="A", description="d", mimeType="text/markdown", size=10,
            annotations={"audience": ["user"], "priority": 0.5, "lastModified": "2026-01-01T00:00:00Z"},
            icons=[{"src": "https://x.test/i.png"}], _meta={"k": "v"})
    p = prm("p", description="pd", arguments=[{"name": "a", "title": "A", "description": "ad", "required": True}])
    rep = run(srv(resources=[page("resources", [r, res("file:///b", "b")])], prompts=[page("prompts", [p, prm("bare")])]))
    items = lst(rep, "resources")["items"]
    assert items[0]["definition"] == r and items[0]["definition_status"] == "passed_limited_checks"
    assert items[1]["definition"] == {"uri": "file:///b", "name": "b"}  # mimeType·size 등을 만들어 넣지 않음
    pr = lst(rep, "prompts")["items"]
    assert pr[0]["definition"] == p and pr[1]["definition"] == {"name": "bare"} and "arguments" not in pr[1]["definition"]


def test_identity_keeps_original_values_for_each_kind(run):
    rep = run(full())
    assert lst(rep, "resources")["items"][0]["identity"] == {
        "uri": {"original_value": "file:///a", "status": "as_reported"}, "name": {"original_value": "a", "status": "as_reported"}}
    assert lst(rep, "resource_templates")["items"][0]["identity"]["uriTemplate"]["original_value"] == "file:///{p}"
    assert lst(rep, "prompts")["items"][0]["identity"] == {"name": {"original_value": "p", "status": "as_reported"}}


# ---- 목록 상태 구분: 빈 목록 / 미지원 / 실패 / 부분 / 미수행 ------------------------------

def test_empty_list_unsupported_failed_partial_and_not_performed_are_distinguished(run):
    rep = run(srv(
        caps={"resources": {}, "prompts": {}},
        resources=[page("resources", [])],                              # 정상 빈 목록
        resource_templates=[error(-32601)],                             # 미지원
        prompts=[page("prompts", [prm("a")], cursor="next")]))          # 다음 페이지 없이 끝남 -> 부분
    assert (lst(rep, "resources")["collection_status"], lst(rep, "resources")["outcome"], lst(rep, "resources")["item_count"]) == ("complete", "empty_list", 0)
    t = lst(rep, "resource_templates")
    assert (t["collection_status"], t["outcome"], t["item_count"], t["items"]) == ("unsupported", "method_not_found", None, [])
    assert t["evidence"]["error_code"] == -32601
    p = lst(rep, "prompts")
    assert (p["collection_status"], p["outcome"], p["item_count"]) == ("partial", "incomplete_list", 1)
    assert "next_cursor_remaining" in codes(p)

    rep2 = run(srv(resources=[page("resources", [res()])]))             # 나머지는 응답 자체가 없음
    assert (lst(rep2, "prompts")["collection_status"], lst(rep2, "prompts")["outcome"], lst(rep2, "prompts")["item_count"]) == (
        "not_performed", "not_requested", None)
    assert rep2["servers"][0]["collection_status"] == "partial"


def test_failed_is_not_an_empty_list(run):
    rep = run(srv(resources=[error(-32603, "internal")], resource_templates=[], prompts=["not an object"]))
    r, t, p = lst(rep, "resources"), lst(rep, "resource_templates"), lst(rep, "prompts")
    assert (r["collection_status"], r["outcome"], r["item_count"], r["items"]) == ("failed", "error_response", None, [])
    assert (t["collection_status"], t["outcome"], t["item_count"]) == ("failed", "no_response", None)   # pages: [] 는 0개가 아님
    assert (p["collection_status"], p["outcome"]) == ("failed", "invalid_response_structure")
    assert rep["servers"][0]["collection_status"] == "failed" and rep["collection"]["status"] == "failed"


def test_method_not_found_only_counts_as_unsupported_on_the_first_page(run):
    rep = run(srv(resources=[page("resources", [res()], cursor="n"), error(-32601)]))
    r = lst(rep, "resources")
    assert r["collection_status"] == "partial" and r["item_count"] == 1 and "error_response" in codes(r)


def test_unsupported_needs_the_exact_error_code(run):
    rep = run(srv(resources=[error(-32602)], resource_templates=[error(-32601, "x" * 5000)], prompts=[error(None)]))
    assert lst(rep, "resources")["collection_status"] == "failed"
    assert lst(rep, "resource_templates")["collection_status"] == "unsupported"
    assert lst(rep, "prompts")["collection_status"] == "failed"
    msg = lst(rep, "resource_templates")["pages"][0]["error_message"]
    assert len(msg) <= MAX_MESSAGE_CHARS + 1                       # 서버가 보낸 긴 메시지는 가린 뒤 길이를 제한


def test_server_aggregation(run):
    all_unsupported = run(srv(resources=[error()], resource_templates=[error()], prompts=[error()]))
    assert all_unsupported["servers"][0]["collection_status"] == "complete" and all_unsupported["collection"]["status"] == "complete"
    nothing = run(srv())
    assert nothing["servers"][0]["collection_status"] == "failed" and nothing["servers"][0]["outcome"] == "no_list_performed"
    assert nothing["collection"]["status"] == "failed"


# ---- 능력 선언은 저장된 값을 옮길 뿐이다 ------------------------------------------------

def test_declared_capabilities_explain_not_performed_but_do_not_create_unsupported(run):
    rep = run(srv(caps={"resources": {"listChanged": True, "x-extra": "FAKE-CAP"}}, resources=[page("resources", [res()])]))
    s = rep["servers"][0]
    assert s["declared_capabilities"] == {"resources": "declared", "prompts": "not_declared", "source": "stored_in_input_not_verified"}
    assert lst(rep, "prompts")["outcome"] == "capability_not_declared" and lst(rep, "prompts")["collection_status"] == "not_performed"
    assert lst(rep, "resource_templates")["declared_capability"] == "declared"   # resources 능력이 템플릿 목록도 포괄
    assert "FAKE-CAP" not in json.dumps(rep)                                       # 능력 내용은 옮기지 않는다


def test_list_present_without_declared_capability_is_still_read_with_a_note(run):
    rep = run(srv(caps={}, prompts=[page("prompts", [prm()])]))
    p = lst(rep, "prompts")
    assert p["collection_status"] == "complete" and "list_without_declared_capability" in codes(p)


def test_capabilities_absent_or_invalid_are_unknown(run):
    assert run(srv(prompts=[page("prompts", [prm()])]))["servers"][0]["declared_capabilities"]["prompts"] == "unknown"
    rep = run(srv(caps="oops", prompts=[page("prompts", [prm()])]))
    assert rep["servers"][0]["declared_capabilities"]["prompts"] == "unknown"
    assert rep["servers"][0]["issues"][0]["code"] == "server_capabilities_invalid"


# ---- 규격 버전별 규칙 -------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["resources", "resource_templates", "prompts"])
def test_2026_requires_result_type_and_cache_fields_for_every_list(run, kind):
    item = {"resources": res(), "resource_templates": tpl(), "prompts": prm()}[kind]
    raw = {"jsonrpc": "2.0", "id": 1, "result": {FIELD[kind]: [item]}}
    rep = run(srv(version=V6, **{kind: [raw]}))
    lt = lst(rep, kind)
    assert (lt["collection_status"], lt["outcome"]) == ("partial", "completion_unverified")   # 완료를 추정하지 않는다
    assert lt["item_count"] == 1 and {"result_type_missing", "cache_hint_missing"} <= set(codes(lt))
    assert lt["spec_conformance"]["status"] == "violations_found"


@pytest.mark.parametrize("kind", ["resources", "resource_templates", "prompts"])
def test_2025_does_not_require_or_invent_2026_fields(run, kind):
    item = {"resources": res(), "resource_templates": tpl(), "prompts": prm()}[kind]
    rep = run(srv(version=V5, **{kind: [page(kind, [item], V5)]}))
    lt = lst(rep, kind)
    assert lt["collection_status"] == "complete" and lt["issues"] == []
    assert "ttl_ms" not in lt["pages"][0] and "result_type" not in lt["pages"][0]
    # 2025에 같은 이름의 확장 필드가 와도 2026의 의미를 적용하지 않는다.
    rep = run(srv(version=V5, **{kind: [page(kind, [item], V5, resultType="input_required", ttlMs="x")]}))
    assert lst(rep, kind)["collection_status"] == "complete"
    assert set(lst(rep, kind)["pages"][0]["other_result_fields"]) == {"resultType", "ttlMs"}


def test_2026_result_type_variants(run):
    rep = run(srv(resources=[page("resources", [res()], resultType="input_required")], resource_templates=[page("resource_templates", [tpl()], resultType="streaming")],
                  prompts=[page("prompts", [prm()], resultType=7)]))
    assert lst(rep, "resources")["outcome"] == "input_required_result"
    assert lst(rep, "resource_templates")["outcome"] == "unsupported_result_type"
    assert lst(rep, "prompts")["outcome"] == "completion_unverified" and "result_type_invalid" in codes(lst(rep, "prompts"))
    bad_cache = run(srv(resources=[page("resources", [res()], ttlMs=-1, cacheScope="shared")]))
    r = lst(bad_cache, "resources")
    assert r["collection_status"] == "complete" and codes(r).count("cache_hint_invalid") == 2   # 캐시 힌트 오류만으로 상태를 바꾸지 않는다


@pytest.mark.parametrize("version", [None, "", "2024-11-05", "2099-01-01", 3])
def test_missing_or_unsupported_version_is_not_guessed(run, version):
    entry = full()
    entry["protocol_version"] = version
    rep = run(entry)
    s = rep["servers"][0]
    assert s["collection_status"] == "failed" and s["lists"] == {}
    assert s["outcome"] in ("protocol_version_not_declared", "protocol_version_unsupported")
    assert s["counts"] == {"resources": None, "resource_templates": None, "prompts": None}


# ---- 목록마다 다른 항목 규칙 -----------------------------------------------------------------

def test_each_list_uses_its_own_array_key_and_required_fields(run):
    # 다른 목록의 배열 이름을 쓰면 읽지 않는다 (Tool 목록의 `tools`도 마찬가지).
    rep = run(srv(resources=[page("prompts", [prm()])], resource_templates=[{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "tools": [], "ttlMs": 1, "cacheScope": "public"}}],
                  prompts=[page("resources", [res()])]))
    for kind in FIELD:
        assert lst(rep, kind)["collection_status"] == "failed" and lst(rep, kind)["outcome"] == "invalid_response_structure"
    # 자리 이름이 맞아도 필드가 다르면 식별 필드 누락으로 제외한다.
    rep = run(srv(resources=[page("resources", [{"name": "n", "uriTemplate": "x"}, tpl()])],
                  resource_templates=[page("resource_templates", [{"name": "n", "uri": "file:///x"}])],
                  prompts=[page("prompts", [{"uri": "file:///x"}, {"name": ""}, "str", None, prm("ok")])]))
    r, t, p = lst(rep, "resources"), lst(rep, "resource_templates"), lst(rep, "prompts")
    assert r["item_count"] == 0 and t["item_count"] == 0 and p["item_count"] == 1
    assert [x["definition"]["name"] for x in p["items"]] == ["ok"]
    for lt in (r, t, p):
        assert lt["collection_status"] == "partial" and "item_invalid" in codes(lt) and "required_field_missing" in codes(lt)


def test_name_is_required_for_resources_and_templates_but_the_item_is_kept(run):
    rep = run(srv(resources=[page("resources", [{"uri": "file:///x"}])], resource_templates=[page("resource_templates", [{"uriTemplate": "x/{y}"}])]))
    for kind in ("resources", "resource_templates"):
        lt = lst(rep, kind)
        assert lt["collection_status"] == "complete" and lt["item_count"] == 1       # 수집 완전성은 유지
        assert lt["items"][0]["definition_status"] == "failed_limited_checks"
        assert lt["items"][0]["identity"]["name"] == {"original_value": None, "status": "missing"}
        assert lt["spec_conformance"]["status"] == "violations_found"


def test_field_type_checks_per_kind(run):
    bad_res = res(title=1, description=[], mimeType={}, size="9", annotations={"audience": ["root"], "priority": 2, "lastModified": 5},
                  icons=[{"src": 1}], _meta=[])
    bad_tpl = tpl(size=3)  # size는 Resource의 필드다. 템플릿에서는 정의 밖 필드로만 취급한다.
    bad_prm = prm(arguments=[{"name": 1, "required": "yes", "title": 2}, "x"], annotations="n/a")
    rep = run(srv(resources=[page("resources", [bad_res])], resource_templates=[page("resource_templates", [bad_tpl])], prompts=[page("prompts", [bad_prm])]))
    paths = {k: {i["field_path"] for i in lst(rep, k)["items"][0]["definition_issues"]} for k in FIELD}
    assert {"title", "description", "mimeType", "size", "annotations.audience", "annotations.priority", "annotations.lastModified", "icons[0]", "_meta"} <= paths["resources"]
    assert paths["resource_templates"] == set() and lst(rep, "resource_templates")["items"][0]["other_definition_fields"] == ["size"]
    assert {"arguments[0].name", "arguments[0].required", "arguments[0].title", "arguments[1]"} <= paths["prompts"]
    assert lst(rep, "prompts")["items"][0]["other_definition_fields"] == ["annotations"]   # 프롬프트에는 annotations가 없다
    for kind in FIELD:
        assert lst(rep, kind)["collection_status"] == "complete"       # 형식 위반은 수집 완전성을 바꾸지 않는다
    assert any(i["field_path"].startswith("pages[0].result.resources[0].") for i in lst(rep, "resources")["issues"] if i["code"] == "field_type_invalid")


def test_non_finite_and_lone_surrogate_values_are_marked_not_copied(run, tmp_path):
    p = tmp_path / "raw.json"
    p.write_text('{"format":"mcp-lists-capture","servers":[{"server_ref":"s","protocol_version":"2026-07-28","lists":{"resources":{"pages":[{"result":'
                 '{"resultType":"complete","ttlMs":1,"cacheScope":"public","resources":[{"uri":"file:///x","name":"n\\ud800","size":NaN}]}}]}}}]}', encoding="utf-8")
    rep = build_report(collect_resources_prompts(p))
    item = lst(rep, "resources")["items"][0]
    assert item["definition"]["size"] == "<non-finite-number>" and "\ud800" not in item["definition"]["name"]
    assert item["identity"]["name"]["status"] == "withheld_by_redaction"
    assert "size" in {i["field_path"] for i in item["definition_issues"]}      # 숫자가 아닌 값으로 기록


# ---- 페이지 처리와 개수 제한 ------------------------------------------------------------

def test_pagination_follows_cursors_and_empty_string_cursor_is_valid(run):
    rep = run(srv(resources=[page("resources", [res("file:///1", "1")], cursor="OPAQUE-CURSOR-77"), page("resources", [res("file:///2", "2")], cursor=""),
                             page("resources", [res("file:///3", "3")])]))
    r = lst(rep, "resources")
    assert r["collection_status"] == "complete" and r["item_count"] == 3
    assert [(x["page_index"], x["index_in_page"]) for x in r["items"]] == [(0, 0), (1, 0), (2, 0)]
    assert "OPAQUE-CURSOR-77" not in json.dumps(rep)          # 커서 값은 저장하지 않는다


def test_pagination_problems_are_partial_per_list(run):
    rep = run(srv(resources=[page("resources", [res()]), page("resources", [res("file:///2")])],           # 마지막 페이지 뒤의 응답
                  resource_templates=[page("resource_templates", [tpl()], cursor="x"), error(-32603)],      # 뒤 페이지 오류
                  prompts=[page("prompts", [prm()], nextCursor=5)]))                                         # 잘못된 커서 자료형
    assert "page_after_final_page" in codes(lst(rep, "resources")) and lst(rep, "resources")["collection_status"] == "partial"
    assert lst(rep, "resource_templates")["collection_status"] == "partial" and lst(rep, "resource_templates")["item_count"] == 1
    assert "next_cursor_invalid" in codes(lst(rep, "prompts")) and lst(rep, "prompts")["collection_status"] == "partial"


def test_item_limit_keeps_counts_honest(run, monkeypatch):
    monkeypatch.setattr(rp, "MAX_ITEMS_PER_LIST", 3)
    items = [res(f"file:///{i}", f"n{i}") for i in range(5)]
    rep = run(srv(resources=[page("resources", items)], prompts=[page("prompts", [prm(f"p{i}") for i in range(3)])]))
    r = lst(rep, "resources")
    assert (r["collection_status"], r["item_count"]) == ("partial", 3) and "item_limit_exceeded" in codes(r)
    assert lst(rep, "prompts")["collection_status"] == "complete"                       # 정확히 한도만큼은 완전
    assert rep["collection"]["item_counts_complete"] is False


# ---- 합치지 않기 --------------------------------------------------------------------------

def test_same_names_across_servers_and_kinds_are_never_merged(run):
    def s(ref):
        return srv(ref, resources=[page("resources", [res("file:///x", "same")])],
                   resource_templates=[page("resource_templates", [tpl("file:///x", "same")])],
                   prompts=[page("prompts", [prm("same")])])
    rep = run(s("a"), s("b"))
    refs = [it["internal_ref"] for sv in rep["servers"] for lt in sv["lists"].values() for it in lt["items"]]
    assert len(refs) == 6 and len(set(refs)) == 6
    assert all("duplicate_identifier_in_list" not in codes(lt) for sv in rep["servers"] for lt in sv["lists"].values())
    assert rep["collection"]["item_counts"] == {"resources": 2, "resource_templates": 2, "prompts": 2}


def test_duplicate_identifier_in_one_list_keeps_both_with_a_warning(run):
    rep = run(srv(prompts=[page("prompts", [prm("dup", description="one"), prm("dup", description="two")])],
                  resources=[page("resources", [res("file:///x", "a"), res("file:///x", "b")])]))
    for kind in ("prompts", "resources"):
        lt = lst(rep, kind)
        assert lt["item_count"] == 2 and "duplicate_identifier_in_list" in codes(lt) and lt["collection_status"] == "complete"
    assert [x["definition"]["description"] for x in lst(rep, "prompts")["items"]] == ["one", "two"]


def test_duplicate_server_ref_is_not_merged(run):
    rep = run(full("same"), full("same"))
    assert rep["servers"][0]["collection_status"] == "complete"
    assert rep["servers"][1]["collection_status"] == "failed" and rep["servers"][1]["outcome"] == "duplicate_server_ref"
    assert rep["collection"]["status"] == "partial" and rep["collection"]["item_counts"]["prompts"] == 1


# ---- 가림 --------------------------------------------------------------------------------

def dump(rep):
    return json.dumps(rep, ensure_ascii=False)


def test_uri_credentials_query_and_fragment_are_masked_and_identity_is_withheld(run):
    uris = ["https://bob:FAKEPASS@host.test/p", "https://host.test/p?token=FAKEQ&x=FAKEY", "https://host.test/p#FAKEFRAG",
            f"https://host.test/{TOKEN}/x", f"note://{TOKEN}"]
    rep = run(srv(resources=[page("resources", [res(u, f"n{i}") for i, u in enumerate(uris)])]))
    out = dump(rep)
    for marker in ("FAKEPASS", "FAKEQ", "FAKEY", "FAKEFRAG", "FAKELISTTOKEN"):
        assert marker not in out
    for it in lst(rep, "resources")["items"]:
        assert it["identity"]["uri"] == {"original_value": None, "status": "withheld_by_redaction"}   # 가린 값은 원본 식별값이 아님
        assert it["identity"]["name"]["status"] == "as_reported" and it["definition_altered"] is True
    assert lst(rep, "resources")["items"][0]["definition"]["uri"] == "https://<redacted>@host.test/p"


def test_masked_identifiers_are_not_treated_as_the_same_item(run):
    a, b = "https://u1:FAKEA@host.test/x", "https://u2:FAKEB@host.test/x"
    rep = run(srv(resources=[page("resources", [res(a, "r1"), res(b, "r2")])],
                  prompts=[page("prompts", [prm(TOKEN), prm("ghp_FAKEOTHERTOKEN0987654321zyxwvuts")])]))
    for kind in ("resources", "prompts"):
        lt = lst(rep, kind)
        assert lt["item_count"] == 2 and "duplicate_identifier_in_list" not in codes(lt)       # 가려진 값끼리는 중복·동일로 보지 않음
    assert [x["identity"]["name"]["original_value"] for x in lst(rep, "prompts")["items"]] == [None, None]
    # 원문이 같아 보이는 가려진 식별값도 "같은 원본 식별값"으로 판정하지 않는다 (가려진 값은 원본 식별값이 아님).
    same = run(srv(resources=[page("resources", [res(a, "r1"), res(a, "r2")])], prompts=[page("prompts", [prm(TOKEN), prm(TOKEN)])]))
    for kind in ("resources", "prompts"):
        assert lst(same, kind)["item_count"] == 2 and "duplicate_identifier_in_list" not in codes(lst(same, kind))
    assert {x["definition"]["name"] for x in lst(rep, "prompts")["items"]} == {"<redacted>"}
    assert "FAKE" not in dump(rep)


def test_uri_template_keeps_expressions_and_masks_secrets(run):
    tpls = ["https://api.test/items/{id}{?fields,page}", "file:///srv/{+path}", "https://u:FAKEP@api.test/{id}",
            f"https://api.test/{TOKEN}/{{id}}", "https://api.test/{" + TOKEN + "}", "https://api.test/q?k={v}"]
    rep = run(srv(resource_templates=[page("resource_templates", [tpl(t, f"n{i}") for i, t in enumerate(tpls)])]))
    d = [x["definition"]["uriTemplate"] for x in lst(rep, "resource_templates")["items"]]
    ident = [x["identity"]["uriTemplate"] for x in lst(rep, "resource_templates")["items"]]
    assert d[0] == tpls[0] and ident[0]["status"] == "as_reported"          # 표현식은 그대로
    assert d[1] == tpls[1] and ident[1]["original_value"] == tpls[1]
    assert d[2] == "https://<redacted>@api.test/{id}"
    assert "<redacted>" in d[3] and "{id}" in d[3]
    assert d[4] == "https://api.test/{<redacted>}"
    assert d[5].startswith("https://api.test/q?k=<redacted>")
    for i in (2, 3, 4, 5):
        assert ident[i] == {"original_value": None, "status": "withheld_by_redaction"}
    assert "FAKE" not in dump(rep)


def test_prompt_arguments_and_nested_metadata_are_masked(run):
    p = prm("p", description=f"Use {TOKEN} for access", arguments=[
        {"name": TOKEN, "description": "see https://u:FAKEPW@h.test/x?k=FAKEV", "required": True},
        {"name": "api_key", "title": "Api key"}],
        _meta={"api_key": "FAKE-META-SECRET", "nested": {"authorization": "Bearer FAKEBEARER", "ok": "fine", "list": [f"{TOKEN}", 3]},
               TOKEN: "x"},
        icons=[{"src": "https://u:FAKEICON@h.test/i.png"}])
    r = res("file:///x", "n", annotations={"audience": ["user"], "lastModified": TOKEN}, _meta={"token": "FAKE-TOKEN-VALUE"})
    t = tpl("file:///{p}", "t", _meta={"password": "FAKE-PW"}, description="https://h.test/?sig=FAKESIG")
    rep = run(srv(resources=[page("resources", [r])], resource_templates=[page("resource_templates", [t])], prompts=[page("prompts", [p])]))
    out = dump(rep)
    for marker in ("FAKELISTTOKEN", "FAKEPW", "FAKEV", "FAKE-META-SECRET", "FAKEBEARER", "FAKEICON", "FAKE-TOKEN-VALUE", "FAKE-PW", "FAKESIG"):
        assert marker not in out, marker
    d = lst(rep, "prompts")["items"][0]["definition"]
    assert d["arguments"][1]["name"] == "api_key"                  # 이름이 비밀처럼 보여도 이름 자체는 유지
    assert d["_meta"]["nested"]["ok"] == "fine" and d["_meta"]["nested"]["list"][1] == 3
    assert lst(rep, "prompts")["items"][0]["definition_altered"] and lst(rep, "prompts")["items"][0]["redactions"]
    assert "<redacted-key-1>" in d["_meta"]


def test_redaction_also_applies_to_server_labels_and_errors(run):
    entry = full(TOKEN)
    entry["registration_key"] = TOKEN
    err_server = srv("e", resources=[error(-32603, f"boom {TOKEN} https://u:FAKEE@h.test/")])
    rep = run(entry, err_server)
    assert "FAKELISTTOKEN" not in dump(rep) and "FAKEE" not in dump(rep)


# ---- 중복 키 -----------------------------------------------------------------------------

def test_duplicate_keys_make_only_the_affected_part_partial(tmp_path):
    p = tmp_path / "d.json"
    item_dup = '{"uri":"file:///x","name":"a","name":"b"}'
    p.write_text('{"format":"mcp-lists-capture","servers":[{"server_ref":"s","protocol_version":"2025-11-25","lists":{'
                 '"resources":{"pages":[{"result":{"resources":[' + item_dup + ']}}]},'
                 '"prompts":{"pages":[{"result":{"prompts":[{"name":"first"}]}}]},'
                 '"prompts":{"pages":[{"result":{"prompts":[{"name":"second"}]}}]}}}]}', encoding="utf-8")
    rep = build_report(collect_resources_prompts(p))
    r = lst(rep, "resources")
    assert r["collection_status"] == "partial" and "duplicate_key" in [i["code"] for i in r["items"][0]["definition_issues"]]
    assert r["items"][0]["definition"]["name"] == "b"
    pr = lst(rep, "prompts")
    assert pr["collection_status"] == "partial" and [x["definition"]["name"] for x in pr["items"]] == ["second"]
    assert pr["issues"][0]["code"] == "duplicate_key"


def test_duplicate_keys_in_server_entry_envelope_and_root(tmp_path):
    p = tmp_path / "d.json"
    p.write_text('{"format":"mcp-lists-capture","format":"mcp-lists-capture","servers":[{"server_ref":"s","protocol_version":"2025-11-25",'
                 '"lists":{"resources":{"pages":[{"jsonrpc":"2.0","result":{"resources":[]},"result":{"resources":[]}}]}},'
                 '"server_ref":"s"}]}', encoding="utf-8")
    rep = build_report(collect_resources_prompts(p))
    assert rep["servers"][0]["collection_status"] == "partial" and rep["servers"][0]["outcome"] != "lists_collected"
    assert "duplicate_key" in codes(lst(rep, "resources"))
    assert any(r["code"] == "duplicate_key_in_capture" for r in rep["collection"]["reasons"])


# ---- 입력 파일 오류 ----------------------------------------------------------------------

@pytest.mark.parametrize("content, code", [
    ("not json", "capture_invalid_json"),
    ('{"servers": 3}', "capture_invalid_structure"),
    ('{"format": "tools-list-capture", "servers": [{}]}', "capture_invalid_structure"),
    ('{"servers": []}', "no_servers_in_capture"),
])
def test_bad_capture_files_fail_without_pretending_to_be_empty(tmp_path, content, code):
    p = tmp_path / "c.json"
    p.write_text(content, encoding="utf-8")
    rep = build_report(collect_resources_prompts(p))
    assert rep["collection"]["status"] == "failed" and rep["collection"]["outcome"] == code
    assert rep["collection"]["server_count"] is None and rep["servers"] == []
    assert build_report(collect_resources_prompts(tmp_path / "missing.json"))["collection"]["outcome"] == "capture_not_found"


def test_invalid_server_entries_and_lists(run):
    rep = run("x", {"protocol_version": V6}, {**full("ok")}, {**full("l"), "lists": []})
    assert [s["collection_status"] for s in rep["servers"]] == ["failed", "failed", "complete", "failed"]
    assert rep["servers"][3]["outcome"] == "invalid_lists" and rep["collection"]["status"] == "partial"


# ---- 보고서 범위와 기존 기능 호환 ----------------------------------------------------------

def test_report_states_scope_basis_and_limits(run):
    rep = run(full())
    assert rep["format"] == "agent-scope.scanner.mcp-resources-prompts" and rep["source"]["live_server_query"] is False
    assert {"resources_read", "prompts_get", "tools_call", "exposure", "callability", "live_server_query"} <= set(rep["scope"]["not_verified"])
    basis = rep["protocol"]["spec_basis"]
    assert basis["2025-11-25"]["commit"] == "c4c367f9f58296a7053f5c78a52fd02bfbb56a49"
    assert basis["2026-07-28"]["commit"] == "271ecc9accafdd9b83a3c869fa67c22953b2af80"
    assert rep["scope"]["definition_validation"]["level"] == "limited_structure"
    text = dump(rep)
    for word in ("exposed", "callable ", "safe", "unsafe"):
        assert word not in text.replace("callability", "")


def test_config_link_shape_matches_the_tools_catalog_so_both_can_be_linked(run, tmp_path):
    extra = {"registration_key": "k", "registry_path": "mcp.servers", "config_scan_ref": "gw"}
    rep = run({**full("s"), **extra})
    tools_cap = {"format": "tools-list-capture", "servers": [{"server_ref": "s", "protocol_version": V6, **extra, "pages": [
        {"result": {"resultType": "complete", "tools": [], "ttlMs": 1, "cacheScope": "public"}}]}]}
    p = tmp_path / "t.json"
    p.write_text(json.dumps(tools_cap), encoding="utf-8")
    tcat = collect_tools_catalog(p)
    assert rep["servers"][0]["config_link"] == tcat["servers"][0]["config_link"]
    assert rep["servers"][0]["server_ref_kind"] == tcat["servers"][0]["server_ref_kind"] == "capture_local_label"


def test_tools_catalog_output_is_unchanged_by_this_module():
    from asset_scanner import tools_catalog as tc
    cat = collect_tools_catalog(EXAMPLES / "tools-list-capture.json")
    report = tc.build_catalog_report(cat)
    assert report["format"] == "agent-scope.scanner.mcp-tools-catalog" and "resources_prompts" in report["scope"]["not_verified"]
    assert set(report["servers"][0]) >= {"tools", "tool_count", "pages", "spec_conformance"}
    assert not any(k in report["servers"][0] for k in ("lists", "counts"))


def test_example_capture_runs_and_shows_every_list_state():
    rep = build_report(collect_resources_prompts(EXAMPLES / "resources-prompts-capture.json"))
    s0, s1 = rep["servers"]
    assert s0["collection_status"] == "complete" and s0["counts"] == {"resources": 2, "resource_templates": 2, "prompts": 2}
    assert [lst(rep, k, 1)["collection_status"] for k in FIELD] == ["complete", "unsupported", "not_performed"]
    assert lst(rep, "prompts", 0)["items"][0]["definition"]["arguments"][0]["required"] is True
    assert "FAKE-QUERY-VALUE" not in dump(rep)


# ---- CLI ---------------------------------------------------------------------------------

def run_cli(*args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-m", "asset_scanner.resources_prompts", *map(str, args)], cwd=SCANNER_ROOT,
                          env=env, capture_output=True, text=True, encoding="utf-8")


def test_cli_exit_codes_and_output_file(tmp_path):
    out = tmp_path / "out.json"
    ok = write(tmp_path, [full("a")])
    proc = run_cli("--capture", ok, "--output", out)
    assert proc.returncode == 0 and "실제 서버 조회가 아님" in proc.stdout
    assert json.loads(out.read_text(encoding="utf-8"))["collection"]["status"] == "complete"

    partial = tmp_path / "p.json"
    partial.write_text(json.dumps({"format": "mcp-lists-capture", "servers": [srv("p", resources=[page("resources", [res()])])]}), encoding="utf-8")
    assert run_cli("--capture", partial, "--output", tmp_path / "p.out.json").returncode == 1

    bad = tmp_path / "b.json"
    bad.write_text("nope", encoding="utf-8")
    assert run_cli("--capture", bad, "--output", tmp_path / "b.out.json").returncode == 3
    assert run_cli("--capture", ok).returncode == 2                                           # 인자 오류
    same = run_cli("--capture", ok, "--output", ok)
    assert same.returncode == 4 and json.loads(ok.read_text(encoding="utf-8"))["format"] == "mcp-lists-capture"   # 입력을 덮어쓰지 않음
    blocked = tmp_path / "dir"
    blocked.mkdir()
    assert run_cli("--capture", ok, "--output", blocked).returncode == 4


def test_cli_never_prints_or_saves_secrets_or_descriptions(tmp_path):
    secret_srv = srv(TOKEN, resources=[page("resources", [res("https://u:FAKECLI@h.test/x?k=FAKECLIQ", TOKEN, description="FAKE-DESC")])],
                     prompts=[page("prompts", [prm("p", arguments=[{"name": "a", "description": f"x {TOKEN}"}])])])
    cap = write(tmp_path, [secret_srv])
    out = tmp_path / "o.json"
    proc = run_cli("--capture", cap, "--output", out)
    saved = out.read_text(encoding="utf-8")
    for marker in ("FAKECLI", "FAKELISTTOKEN"):
        assert marker not in proc.stdout + proc.stderr + saved
    assert "FAKE-DESC" not in proc.stdout + proc.stderr          # 서버가 제공한 설명은 콘솔에 출력하지 않는다
    assert "Traceback" not in proc.stderr


def test_example_cli_run_matches_documented_exit_code(tmp_path):
    proc = run_cli("--capture", EXAMPLES / "resources-prompts-capture.json", "--output", tmp_path / "e.json")
    assert proc.returncode == 1                                  # 두 번째 서버에 not_performed 목록이 있어 부분 수집
    assert "unsupported/method_not_found" in proc.stdout and "not_performed/capability_not_declared" in proc.stdout
