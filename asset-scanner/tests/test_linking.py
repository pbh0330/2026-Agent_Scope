"""서버 선언과 Tool 수집 결과 연결(linking) 테스트.

입력은 모두 가상 자료다. 서버 접속·명령 실행 없이 저장된 수집 결과 JSON만 읽는다.
`FAKE` 표식이 붙은 값은 전부 가짜 비밀값이다.
"""

import json
import os
import subprocess
import sys

import pytest

from asset_scanner.collector import SUPPORTED_REGISTRY_PATHS, collect, collect_plugin_manifest
from asset_scanner.linking import build_link_report, link_scans
from asset_scanner.report import build_report
from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
from conftest import EXAMPLES, SCANNER_ROOT

V = "2026-07-28"


def tool(name):
    return {"name": name, "inputSchema": {"type": "object"}}


def cat_server(ref, tools=("read_file",), key=None, reg=None, scan=None, **extra):
    entry = {"server_ref": ref, "protocol_version": V,
             "pages": [{"jsonrpc": "2.0", "id": 1, "result": {
                 "resultType": "complete", "tools": [tool(t) for t in tools], "ttlMs": 1, "cacheScope": "public"}}]}
    if key is not None:
        entry["registration_key"] = key
    if reg is not None:
        entry["registry_path"] = reg
    if scan is not None:
        entry["config_scan_ref"] = scan
    entry.update(extra)
    return entry


@pytest.fixture
def make(tmp_path):
    counter = {"n": 0}

    def config_scan(text, registry="mcp.servers", manifest=False):
        counter["n"] += 1
        cfg = tmp_path / f"cfg{counter['n']}.json5"
        cfg.write_text(text, encoding="utf-8")
        collected = (collect_plugin_manifest(cfg) if manifest
                     else collect(cfg, SUPPORTED_REGISTRY_PATHS[registry]))
        out = tmp_path / f"scan{counter['n']}.json"
        out.write_text(json.dumps(build_report(collected), ensure_ascii=False), encoding="utf-8")
        return out

    def catalog(*servers):
        counter["n"] += 1
        cap = tmp_path / f"cap{counter['n']}.json"
        cap.write_text(json.dumps({"origin": "synthetic_test_data", "servers": list(servers)}), encoding="utf-8")
        out = tmp_path / f"cat{counter['n']}.json"
        out.write_text(json.dumps(build_catalog_report(collect_tools_catalog(cap)), ensure_ascii=False), encoding="utf-8")
        return out

    return config_scan, catalog


def link(scans, cats, subjects=None):
    return build_link_report(link_scans(list(scans), cats, subjects))


def reasons(rep):
    return [r["code"] for r in rep["collection"]["reasons"]]


GATEWAY = '{ mcp: { servers: { files: { command: "demo" }, notes: { command: "demo2", enabled: false } } } }'
HEX64 = "a3f1" * 16


def gw(scan_fn, text=GATEWAY, **kw):
    return ("gw", scan_fn(text, **kw))


# ---- 연결 성공 · 추적 항목 -----------------------------------------------------------

def test_linked_server_traces_subject_location_key_and_original_tool_name(make):
    scan, catalog = make
    rep = link([gw(scan)], catalog(cat_server("files", ("read_file", "list_dir"), key="files", reg="mcp.servers", scan="gw")))
    ln = rep["links"][0]
    assert ln["link_status"] == "linked" and ln["reason"] == "config_scan_ref_registration_key_and_registry_path_match"
    assert ln["basis"] == ["config_scan_ref", "registry_path", "registration_key"]
    t = ln["trace"]
    assert t["registration_key"] == "files"
    assert t["config_scan"] == {"input_index": 0, "label": "gw"}
    assert t["logical_location"]["registry_path"] == "mcp.servers"
    assert t["logical_location"]["key_path"] == ["mcp", "servers", "files"]
    assert t["logical_location"]["source_kind"] == "openclaw_config_file"
    s = t["declaring_subject"]
    assert (s["kind"], s["kind_origin"], s["id"], s["id_origin"], s["verified_by_scanner"]) == \
        ("gateway", "inferred_unverified", None, "not_collected", False)
    assert t["physical_path_is_identity"] is False
    assert [x["original_name"] for x in ln["tools"]] == ["read_file", "list_dir"]
    assert all(x["original_name_status"] == "as_reported" for x in ln["tools"])
    assert rep["collection"]["status"] == "complete"
    assert rep["collection"]["counts"] == {"catalog_inputs": 1, "catalog_servers": 1, "linked": 1,
                                           "ambiguous": 0, "unlinked": 0, "declarations": 2}


def test_declaration_without_tool_evidence_is_not_reported_as_zero_tools(make):
    scan, catalog = make
    rep = link([gw(scan)], catalog(cat_server("files", key="files", reg="mcp.servers", scan="gw")))
    by_key = {d["registration_key"]: d for d in rep["declarations"]}
    assert by_key["notes"]["tool_evidence"] == "not_supplied"
    assert by_key["notes"]["linked_observations"] == []
    assert by_key["notes"]["declared_enabled"] is False
    dumped = json.dumps(rep)
    for forbidden in ("coverage", "missing_count", "collection_rate", "tool_count_expected"):
        assert forbidden not in dumped
    assert "config_vs_tools_comparison" in rep["scope"]["not_verified"]
    assert "서버 기동·Agent 노출·호출 가능을 뜻하지 않는다" in rep["scope"]["link_meaning"]


def test_node_and_plugin_subject_hints_come_from_region_and_source_kind(make):
    scan, catalog = make
    node = ("n1", scan('{ nodeHost: { mcp: { servers: { nfiles: { command: "x" } } } } }', registry="nodeHost.mcp.servers"))
    plug = ("p1", scan('{ id: "p", mcpServers: { cat: { command: "y" } } }', manifest=True))
    rep = link([node, plug], catalog(
        cat_server("a", key="nfiles", reg="nodeHost.mcp.servers", scan="n1"), cat_server("b", key="cat", reg="mcpServers", scan="p1")))
    assert [x["link_status"] for x in rep["links"]] == ["linked", "linked"]
    assert rep["links"][0]["trace"]["declaring_subject"]["kind"] == "node"
    plug_trace = rep["links"][1]["trace"]
    assert plug_trace["declaring_subject"]["kind"] == "plugin"
    assert plug_trace["logical_location"]["source_kind"] == "openclaw_plugin_manifest"
    assert plug_trace["logical_location"]["key_path"] == ["mcpServers", "cat"]


# ---- 설정 수집 결과 참조 ---------------------------------------------------------------------

def test_reference_selects_the_exact_config_scan_when_key_and_region_collide(make):
    scan, catalog = make
    a = ("gw-a", scan('{ mcp: { servers: { shared: { command: "a" } } } }'))
    b = ("gw-b", scan('{ mcp: { servers: { shared: { command: "b" } } } }'))
    rep = link([a, b], catalog(cat_server("x", key="shared", reg="mcp.servers", scan="gw-b")))
    ln = rep["links"][0]
    assert ln["link_status"] == "linked" and ln["declaration_ref"] == "config-scan[1]/servers[0]"
    assert ln["trace"]["config_scan"]["label"] == "gw-b"
    assert rep["declarations"][0]["linked_observations"] == []  # gw-a의 같은 이름 선언에는 붙지 않는다


def test_key_and_region_coincidence_without_reference_is_not_linked(make):
    scan, catalog = make
    a = ("gw-a", scan('{ mcp: { servers: { shared: { command: "a" } } } }'))
    b = ("gw-b", scan('{ mcp: { servers: { shared: { command: "b" } } } }'))
    rep = link([a, b], catalog(cat_server("x", key="shared", reg="mcp.servers")))
    ln = rep["links"][0]
    assert (ln["link_status"], ln["reason"]) == ("unlinked", "config_scan_ref_missing")
    assert ln["declaration_ref"] is None and ln["trace"] is None
    assert ln["key_region_matches"] == ["config-scan[0]/servers[0]", "config-scan[1]/servers[0]"]  # 후보로만 알린다
    assert all(d["linked_observations"] == [] for d in rep["declarations"])
    assert rep["collection"]["status"] == "partial"


@pytest.mark.parametrize("bad_ref, reason", [
    (5, "config_scan_ref_invalid"),
    (["gw"], "config_scan_ref_invalid"),
    (None, "config_scan_ref_invalid"),
    ("", "config_scan_ref_invalid"),
    ("no-such-label", "config_scan_ref_unknown"),
    ("GW", "config_scan_ref_unknown"),  # 대소문자도 다른 라벨이다
])
def test_bad_references_are_unlinked_with_reason(make, bad_ref, reason):
    scan, catalog = make
    entry = cat_server("x", key="files", reg="mcp.servers")
    entry["config_scan_ref"] = bad_ref
    rep = link([gw(scan)], catalog(entry))
    ln = rep["links"][0]
    assert (ln["link_status"], ln["reason"]) == ("unlinked", reason)
    assert ln["key_region_matches"] == ["config-scan[0]/servers[0]"]
    assert ln["trace"] is None


def test_physical_path_is_not_a_reference_or_identity(make):
    scan, catalog = make
    path = scan(GATEWAY)
    rep = link([("gw", path)], catalog(cat_server("x", key="files", reg="mcp.servers", scan=str(path))))
    assert rep["links"][0]["reason"] == "config_scan_ref_unknown"
    ok = link([("gw", path)], catalog(cat_server("x", key="files", reg="mcp.servers", scan="gw")))
    assert ok["links"][0]["link_status"] == "linked"
    assert ok["links"][0]["trace"]["physical_path_is_identity"] is False
    assert ok["links"][0]["trace"]["physical_source_path"].endswith("cfg1.json5")  # 원래 설정 파일 경로(속성일 뿐)


def test_duplicate_scan_labels_make_reference_ambiguous(make):
    scan, catalog = make
    a = ("gw", scan('{ mcp: { servers: { shared: { command: "a" } } } }'))
    b = ("gw", scan('{ mcp: { servers: { shared: { command: "b" } } } }'))
    rep = link([a, b], catalog(cat_server("x", key="shared", reg="mcp.servers", scan="gw")))
    ln = rep["links"][0]
    assert (ln["link_status"], ln["reason"]) == ("ambiguous", "config_scan_ref_duplicate")
    assert ln["candidates"] == ["config-scan[0]", "config-scan[1]"] and ln["trace"] is None
    assert "config_scan_label_problem" in reasons(rep)


def test_invalid_scan_label_cannot_be_referenced(make):
    scan, catalog = make
    rep = link([("bad label!", scan(GATEWAY))], catalog(cat_server("x", key="files", reg="mcp.servers", scan="bad label!")))
    assert rep["links"][0]["reason"] == "config_scan_ref_unknown"
    assert rep["inputs"]["config_scans"][0]["label_status"] == "invalid"


def test_reference_to_scan_with_other_registry_region_is_not_linked(make):
    scan, catalog = make
    node = ("n1", scan('{ nodeHost: { mcp: { servers: { files: { command: "x" } } } } }', registry="nodeHost.mcp.servers"))
    rep = link([node], catalog(cat_server("x", key="files", reg="mcp.servers", scan="n1")))
    assert rep["links"][0]["reason"] == "registry_path_mismatch_with_referenced_scan"


def test_reference_to_scan_without_that_key_is_not_linked_even_if_other_scan_has_it(make):
    scan, catalog = make
    a = ("gw-a", scan('{ mcp: { servers: { other: { command: "a" } } } }'))
    b = ("gw-b", scan('{ mcp: { servers: { files: { command: "b" } } } }'))
    rep = link([a, b], catalog(cat_server("x", key="files", reg="mcp.servers", scan="gw-a")))
    ln = rep["links"][0]
    assert (ln["link_status"], ln["reason"]) == ("unlinked", "no_matching_declaration")


def test_reference_to_failed_scan_is_reported_not_treated_as_empty(make):
    scan, catalog = make
    bad = ("gw", scan("{ mcp: "))
    rep = link([bad], catalog(cat_server("x", key="files", reg="mcp.servers", scan="gw")))
    ln = rep["links"][0]
    assert ln["reason"] == "registry_path_mismatch_with_referenced_scan" or ln["reason"] == "no_matching_declaration"
    assert "config_scan_not_complete" in reasons(rep)


# ---- 같은 이름을 합치지 않는다 · 관측 보존 ------------------------------------------------------

def test_same_key_in_different_regions_is_resolved_by_reference_and_region(make):
    scan, catalog = make
    text = '{ mcp: { servers: { shared: { command: "g" } } }, nodeHost: { mcp: { servers: { shared: { command: "n" } } } } }'
    g = ("gw", scan(text))
    n = ("nd", scan(text, registry="nodeHost.mcp.servers"))
    rep = link([g, n], catalog(
        cat_server("s1", key="shared", reg="nodeHost.mcp.servers", scan="nd"),
        cat_server("s2", key="shared", reg="mcp.servers", scan="gw")))
    a, b = rep["links"]
    assert a["trace"]["declaring_subject"]["kind"] == "node"
    assert a["trace"]["logical_location"]["key_path"] == ["nodeHost", "mcp", "servers", "shared"]
    assert b["trace"]["declaring_subject"]["kind"] == "gateway"
    assert a["declaration_ref"] != b["declaration_ref"]


def test_two_servers_in_one_catalog_claiming_same_declaration_are_both_held(make):
    scan, catalog = make
    rep = link([gw(scan)], catalog(
        cat_server("one", key="files", reg="mcp.servers", scan="gw"), cat_server("two", key="files", reg="mcp.servers", scan="gw")))
    assert [x["link_status"] for x in rep["links"]] == ["ambiguous", "ambiguous"]
    assert {x["reason"] for x in rep["links"]} == {"declaration_claimed_by_multiple_catalog_servers"}
    assert all(d["linked_observations"] == [] for d in rep["declarations"])
    assert rep["declarations"][0]["ambiguous_observations"] == [
        {"catalog_input_index": 0, "catalog_server_index": 0}, {"catalog_input_index": 0, "catalog_server_index": 1}]


def test_observations_of_same_declaration_in_different_catalogs_are_kept_separate(make):
    scan, catalog = make
    c1 = ("obs1", catalog(cat_server("files", ("read_file",), key="files", reg="mcp.servers", scan="gw")))
    c2 = ("obs2", catalog(cat_server("files", ("read_file", "write_file"), key="files", reg="mcp.servers", scan="gw")))
    rep = link([gw(scan)], [c1, c2])
    assert [x["link_status"] for x in rep["links"]] == ["linked", "linked"]
    assert rep["links"][0]["declaration_ref"] == rep["links"][1]["declaration_ref"]
    # Tool 목록을 합집합으로 합치지 않고 관측별로 보존한다.
    assert [t["original_name"] for t in rep["links"][0]["tools"]] == ["read_file"]
    assert [t["original_name"] for t in rep["links"][1]["tools"]] == ["read_file", "write_file"]
    assert [x["catalog_label"] for x in rep["links"]] == ["obs1", "obs2"]
    decl = rep["declarations"][0]
    assert decl["linked_observations"] == [{"catalog_input_index": 0, "catalog_server_index": 0},
                                           {"catalog_input_index": 1, "catalog_server_index": 0}]
    assert rep["collection"]["status"] == "complete"
    assert rep["collection"]["counts"]["catalog_inputs"] == 2


def test_different_declarations_with_same_server_ref_are_not_merged(make):
    scan, catalog = make
    # 같은 카탈로그 안의 같은 server_ref는 카탈로그 단계에서 이미 거부된다. 서로 다른 관측 파일에서 이름이 같은 경우를 본다.
    c1 = catalog(cat_server("same", ("t",), key="files", reg="mcp.servers", scan="gw"))
    c2 = catalog(cat_server("same", ("t",), key="notes", reg="mcp.servers", scan="gw"))
    rep = link([gw(scan)], [("o1", c1), ("o2", c2)])
    assert rep["links"][0]["declaration_ref"] != rep["links"][1]["declaration_ref"]
    assert rep["links"][0]["tools"][0]["internal_ref"] == rep["links"][1]["tools"][0]["internal_ref"]  # 파일 안 위치일 뿐
    assert (rep["links"][0]["catalog_input_index"], rep["links"][1]["catalog_input_index"]) == (0, 1)
    assert [d["linked_observations"] for d in rep["declarations"]] == [
        [{"catalog_input_index": 0, "catalog_server_index": 0}], [{"catalog_input_index": 1, "catalog_server_index": 0}]]


def test_same_tool_name_on_two_servers_stays_separate(make):
    scan, catalog = make
    rep = link([gw(scan)], catalog(
        cat_server("a", ("read_file",), key="files", reg="mcp.servers", scan="gw"),
        cat_server("b", ("read_file",), key="notes", reg="mcp.servers", scan="gw")))
    ta, tb = rep["links"][0]["tools"][0], rep["links"][1]["tools"][0]
    assert ta["original_name"] == tb["original_name"] == "read_file"
    assert ta["internal_ref"] != tb["internal_ref"]
    assert ta["same_name_in_other_catalog_servers"] == [1] and tb["same_name_in_other_catalog_servers"] == [0]
    assert rep["links"][0]["declaration_ref"] != rep["links"][1]["declaration_ref"]


def test_duplicate_tool_names_inside_one_server_are_kept_and_flagged(make):
    scan, catalog = make
    rep = link([gw(scan)], catalog(cat_server("a", ("dup", "dup", "other"), key="files", reg="mcp.servers", scan="gw")))
    tools = rep["links"][0]["tools"]
    assert [t["original_name"] for t in tools] == ["dup", "dup", "other"]
    assert tools[0]["name_repeated_in_server"] and tools[1]["name_repeated_in_server"]
    assert "name_repeated_in_server" not in tools[2]
    assert tools[0]["internal_ref"] != tools[1]["internal_ref"]


def test_projected_names_are_not_split_into_server_and_tool(make):
    scan, catalog = make
    rep = link([gw(scan)], catalog(cat_server("a", ("files__read_file", "notes_read"), key="files", reg="mcp.servers", scan="gw")))
    assert [t["original_name"] for t in rep["links"][0]["tools"]] == ["files__read_file", "notes_read"]
    assert rep["links"][0]["declaration_ref"] == "config-scan[0]/servers[0]"


# ---- 연결 근거 없음 · 모호 · 불완전 ---------------------------------------------------------

def test_server_ref_alone_is_not_a_link_basis(make):
    scan, catalog = make
    rep = link([gw(scan)], catalog(cat_server("files")))
    ln = rep["links"][0]
    assert (ln["link_status"], ln["reason"]) == ("unlinked", "no_link_basis")
    assert ln["trace"] is None and ln["declaration_ref"] is None
    assert [t["original_name"] for t in ln["tools"]] == ["read_file"]  # Tool 자료는 버리지 않는다
    assert rep["collection"]["status"] == "partial"


def test_registry_path_missing_does_not_link_even_with_reference(make):
    scan, catalog = make
    rep = link([gw(scan)], catalog(cat_server("files", key="files", scan="gw")))
    assert (rep["links"][0]["link_status"], rep["links"][0]["reason"]) == ("unlinked", "registry_path_missing")


def test_no_matching_declaration_and_wrong_region(make):
    scan, catalog = make
    rep = link([gw(scan)], catalog(
        cat_server("a", key="ghost", reg="mcp.servers", scan="gw"), cat_server("b", key="files", reg="nodeHost.mcp.servers", scan="gw")))
    assert [(x["link_status"], x["reason"]) for x in rep["links"]] == [
        ("unlinked", "no_matching_declaration"), ("unlinked", "registry_path_mismatch_with_referenced_scan")]


def test_incomplete_config_scan_is_reported_when_nothing_matches(make):
    scan, catalog = make
    partial = ("gw", scan('{ mcp: { servers: { $include: "./more.json5", a: { command: "x" } } } }'))
    rep = link([partial], catalog(cat_server("a", key="ghost", reg="mcp.servers", scan="gw")))
    assert rep["links"][0]["link_status"] == "unlinked"
    assert rep["links"][0]["referenced_scan_status"] == "partial"
    assert "config_scan_not_complete" in reasons(rep)


def test_redacted_keys_are_never_linked(make):
    scan, catalog = make
    token = "ghp_FAKEREGISTRATIONKEY1234567890abcd"
    cfg = '{ mcp: { servers: { "%s": { command: "x" } } } }' % token
    rep = link([gw(scan, cfg)], catalog(cat_server("a", key=token, reg="mcp.servers", scan="gw")))
    ln = rep["links"][0]
    assert ln["link_status"] == "unlinked" and ln["reason"] == "registration_key_redacted"
    assert rep["declarations"][0]["registration_key_redacted"] is True
    assert "FAKEREGISTRATION" not in json.dumps(rep)
    rep2 = link([gw(scan, cfg)], catalog(cat_server("a", key="<redacted-key-1>", reg="mcp.servers", scan="gw")))
    assert rep2["links"][0]["reason"] == "registration_key_redacted"


def test_duplicate_registration_key_in_source_is_ambiguous(make):
    scan, catalog = make
    cfg = '{ mcp: { servers: { files: { command: "first" }, files: { command: "last" } } } }'
    rep = link([gw(scan, cfg)], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")))
    ln = rep["links"][0]
    assert (ln["link_status"], ln["reason"]) == ("ambiguous", "declaration_key_duplicated_in_source")
    assert ln["declaration_ref"] is None


def test_catalog_failure_server_and_empty_tool_list_are_kept_distinct(make):
    scan, catalog = make
    failed = cat_server("a", key="files", reg="mcp.servers", scan="gw", pages=[])
    empty = cat_server("b", (), key="notes", reg="mcp.servers", scan="gw")
    rep = link([gw(scan)], catalog(failed, empty))
    a, b = rep["links"]
    assert a["link_status"] == b["link_status"] == "linked"
    assert (a["catalog_collection_status"], a["tool_count_reported"], a["tools"]) == ("failed", None, [])
    assert (b["catalog_collection_status"], b["tool_count_reported"], b["tools"]) == ("complete", 0, [])


# ---- 선언 주체 입력 --------------------------------------------------------------------------

def test_user_provided_subject_is_preserved_and_distinguished_from_inference(make):
    scan, catalog = make
    subj = [{"scan_label": "gw", "kind": "gateway", "id": HEX64}]
    rep = link([gw(scan)], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")), subj)
    s = rep["links"][0]["trace"]["declaring_subject"]
    assert (s["kind"], s["kind_origin"], s["id"], s["id_origin"]) == ("gateway", "user_provided", HEX64, "user_provided")
    assert s["verified_by_scanner"] is False and s["kind_conflicts_with_inference"] is False
    assert s["inferred_kind_from_source"] == "gateway"  # 추정값도 따로 남는다
    assert rep["inputs"]["subject_inputs"][0]["status"] == "applied"
    assert rep["collection"]["status"] == "complete"
    assert "declaring_subject_identity" in rep["scope"]["not_verified"]


def test_subject_without_id_leaves_identity_not_collected(make):
    scan, catalog = make
    rep = link([gw(scan)], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")),
               [{"scan_label": "gw", "kind": "gateway", "id": None}])
    s = rep["links"][0]["trace"]["declaring_subject"]
    assert (s["kind_origin"], s["id"], s["id_origin"]) == ("user_provided", None, "not_collected")
    assert rep["inputs"]["subject_inputs"][0]["id_provided"] is False


def test_id_only_input_keeps_inferred_kind(make):
    scan, catalog = make
    rep = link([gw(scan)], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")),
               [{"scan_label": "gw", "kind": None, "id": "dev-1"}])
    s = rep["links"][0]["trace"]["declaring_subject"]
    assert (s["kind"], s["kind_origin"], s["id"], s["id_origin"]) == ("gateway", "inferred_unverified", "dev-1", "user_provided")


def test_no_subject_input_never_invents_identity(make):
    scan, catalog = make
    rep = link([gw(scan)], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")))
    for d in rep["declarations"]:
        assert d["declaring_subject"]["id"] is None and d["declaring_subject"]["id_origin"] == "not_collected"
    dumped = json.dumps(rep)
    assert "ast_" not in dumped and "sha256" not in dumped.lower()


def test_subject_kind_conflict_with_source_is_flagged_not_resolved(make):
    scan, catalog = make
    rep = link([gw(scan)], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")),
               [{"scan_label": "gw", "kind": "node", "id": "dev-1"}])
    s = rep["links"][0]["trace"]["declaring_subject"]
    assert (s["kind"], s["inferred_kind_from_source"], s["kind_conflicts_with_inference"]) == ("node", "gateway", True)
    assert "subject_kind_conflict" in reasons(rep) and rep["collection"]["status"] == "partial"


@pytest.mark.parametrize("subjects, problem", [
    ([{"scan_label": "zzz", "kind": "gateway", "id": "x"}], "unknown_scan_label"),
    ([{"scan_label": "gw", "kind": "router", "id": "x"}], "kind_invalid"),
    ([{"scan_label": "gw", "kind": "gateway", "id": "   "}], "id_invalid"),
    ([{"scan_label": "gw", "kind": "gateway", "id": "x" * 201}], "id_invalid"),
    ([{"scan_label": "gw", "kind": None, "id": None}], "empty_subject_input"),
])
def test_invalid_subject_inputs_are_ignored_with_reason(make, subjects, problem):
    scan, catalog = make
    rep = link([gw(scan)], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")), subjects)
    rec = rep["inputs"]["subject_inputs"][0]
    assert rec["status"] == "ignored" and problem in rec["problems"]
    s = rep["links"][0]["trace"]["declaring_subject"]
    assert (s["kind_origin"], s["id"], s["id_origin"]) == ("inferred_unverified", None, "not_collected")
    assert "subject_input_ignored" in reasons(rep)


def test_conflicting_duplicate_subject_inputs_are_both_ignored(make):
    scan, catalog = make
    subj = [{"scan_label": "gw", "kind": "gateway", "id": "one"}, {"scan_label": "gw", "kind": "gateway", "id": "two"}]
    rep = link([gw(scan)], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")), subj)
    assert [r["status"] for r in rep["inputs"]["subject_inputs"]] == ["ignored", "ignored"]
    assert rep["links"][0]["trace"]["declaring_subject"]["id"] is None  # 어느 쪽도 고르지 않는다


def test_subject_for_duplicate_scan_label_is_not_applied(make):
    scan, catalog = make
    a = ("gw", scan('{ mcp: { servers: { a: { command: "a" } } } }'))
    b = ("gw", scan('{ mcp: { servers: { b: { command: "b" } } } }'))
    rep = link([a, b], catalog(cat_server("x", key="a", reg="mcp.servers", scan="gw")),
               [{"scan_label": "gw", "kind": "gateway", "id": "dev-1"}])
    assert "scan_label_duplicate" in rep["inputs"]["subject_inputs"][0]["problems"]
    assert all(d["declaring_subject"]["id"] is None for d in rep["declarations"])


def test_subject_ids_get_secret_pattern_masking_but_not_entropy_masking(make):
    scan, catalog = make
    cat = catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw"))
    ok = link([gw(scan)], cat, [{"scan_label": "gw", "kind": "gateway", "id": HEX64}])
    assert ok["declarations"][0]["declaring_subject"]["id"] == HEX64
    bad = link([gw(scan)], cat, [{"scan_label": "gw", "kind": "gateway", "id": "https://bob:FAKEPASS@host.test/x"}])
    assert "FAKEPASS" not in json.dumps(bad)


def test_subjects_are_per_scan_and_do_not_leak_to_other_scans(make):
    scan, catalog = make
    a = ("gw1", scan('{ mcp: { servers: { files: { command: "a" } } } }'))
    b = ("gw2", scan('{ mcp: { servers: { files: { command: "b" } } } }'))
    rep = link([a, b], catalog(cat_server("x", key="files", reg="mcp.servers", scan="gw1"),
                               cat_server("y", key="files", reg="mcp.servers", scan="gw2")),
               [{"scan_label": "gw1", "kind": "gateway", "id": "dev-1"}])
    assert rep["links"][0]["trace"]["declaring_subject"]["id"] == "dev-1"
    assert rep["links"][1]["trace"]["declaring_subject"]["id"] is None  # 같은 서버 이름이라도 다른 설정이다


# ---- 카탈로그 쪽 참조 전달 ---------------------------------------------------------------------

def test_catalog_carries_config_scan_ref_into_config_link_unverified(make, tmp_path):
    scan, catalog = make
    out = json.loads(catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")).read_text(encoding="utf-8"))
    cl = out["servers"][0]["config_link"]
    assert cl["config_scan_ref"] == "gw" and cl["verified_against_config_scan"] is False


def test_catalog_does_not_copy_non_string_reference_value(make):
    scan, catalog = make
    out = json.loads(catalog(cat_server("a", key="files", reg="mcp.servers", config_scan_ref={"x": 1})).read_text(encoding="utf-8"))
    cl = out["servers"][0]["config_link"]
    assert "config_scan_ref" not in cl and cl["config_scan_ref_invalid_type"] == "object"


def test_secret_looking_reference_is_masked_in_catalog_and_link_output(make):
    scan, catalog = make
    secret = "ghp_FAKEREFTOKEN1234567890abcdefgh"
    rep = link([gw(scan)], catalog(cat_server("a", key="files", reg="mcp.servers", scan=secret)))
    assert rep["links"][0]["reason"] == "config_scan_ref_unknown"
    assert "FAKEREFTOKEN" not in json.dumps(rep)


# ---- 가림 · 오류 처리 ----------------------------------------------------------------------

def test_tool_name_that_was_redacted_is_not_reported_as_original_name(make):
    scan, catalog = make
    secret_name = "ghp_FAKETOOLNAMETOKEN1234567890abcd"
    rep = link([gw(scan)], catalog(
        cat_server("a", (secret_name, "ok"), key="files", reg="mcp.servers", scan="gw"),
        cat_server("b", (secret_name,), key="notes", reg="mcp.servers", scan="gw")))
    t0 = rep["links"][0]["tools"][0]
    assert t0["original_name"] is None and t0["original_name_status"] == "withheld_by_redaction"
    assert "same_name_in_other_catalog_servers" not in t0
    assert rep["links"][0]["tools"][1]["original_name"] == "ok"
    assert "FAKETOOLNAME" not in json.dumps(rep)


def test_hand_edited_input_secrets_are_masked_again(make, tmp_path):
    scan, catalog = make
    c = catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw"))
    data = json.loads(c.read_text(encoding="utf-8"))
    data["servers"][0]["server_ref"] = "https://bob:FAKEPASS@host.test/x"
    c.write_text(json.dumps(data), encoding="utf-8")
    assert "FAKEPASS" not in json.dumps(link([gw(scan)], c))


def test_failed_config_scan_input_gives_failed_result_without_links(make, tmp_path):
    scan, catalog = make
    rep = link([("gw", tmp_path / "nope.json")], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")))
    assert rep["collection"]["status"] == "failed"
    assert rep["collection"]["outcome"] == "config_scan_capture_not_found"
    assert rep["links"] == [] and rep["declarations"] == [] and rep["collection"]["counts"] is None


def test_wrong_format_input_is_rejected(make):
    scan, catalog = make
    s = scan(GATEWAY)
    c = catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw"))
    assert link([("gw", c)], c)["collection"]["outcome"] == "config_scan_format_mismatch"
    assert link([("gw", s)], s)["collection"]["outcome"] == "catalog_format_mismatch"


def test_failed_config_scan_file_is_an_incomplete_input_not_zero_declarations(make):
    scan, catalog = make
    rep = link([("gw", scan("{ mcp: "))], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")))
    assert rep["inputs"]["config_scans"][0]["collection_status"] == "failed"
    assert rep["links"][0]["link_status"] == "unlinked"
    assert "config_scan_not_complete" in reasons(rep)


def test_duplicate_keys_in_input_make_result_partial(make):
    scan, catalog = make
    s = scan(GATEWAY)
    s.write_text(s.read_text(encoding="utf-8").replace('"format"', '"format": "x", "format"', 1), encoding="utf-8")
    rep = link([("gw", s)], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")))
    assert rep["collection"]["status"] == "partial" and "duplicate_key_in_input" in reasons(rep)


def test_unlabeled_scan_is_usable_input_but_cannot_be_referenced(make):
    scan, catalog = make
    rep = link([scan(GATEWAY)], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")))
    assert rep["inputs"]["config_scans"][0]["label_status"] == "not_assigned"
    assert rep["links"][0]["reason"] == "config_scan_ref_unknown"
    assert rep["links"][0]["key_region_matches"] == ["config-scan[0]/servers[0]"]


# ---- 예제 · CLI ----------------------------------------------------------------------------

def run_cli(args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-m", "asset_scanner.linking", *map(str, args)],
                          cwd=SCANNER_ROOT, env=env, capture_output=True, text=True, encoding="utf-8")


def test_cli_labels_subject_and_exit_codes(make, tmp_path):
    scan, catalog = make
    out = tmp_path / "link.json"
    good = catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw"))
    ok = run_cli(["--config-scan", f"gw={scan(GATEWAY)}", "--catalog", f"obs1={good}",
                  "--subject", f"gw=gateway,id={HEX64}", "--output", out])
    assert ok.returncode == 0, ok.stderr
    assert "서버 접속·명령 실행 없음" in ok.stdout and ok.stderr == ""
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["format"] == "agent-scope.scanner.server-tool-links"
    assert rep["links"][0]["trace"]["declaring_subject"]["id"] == HEX64
    assert rep["links"][0]["catalog_label"] == "obs1"

    noref = run_cli(["--config-scan", f"gw={scan(GATEWAY)}", "--catalog", catalog(cat_server("a", key="files", reg="mcp.servers")),
                     "--output", out])
    assert noref.returncode == 1
    failed = run_cli(["--config-scan", f"gw={tmp_path / 'missing.json'}", "--catalog", good, "--output", out])
    assert failed.returncode == 3
    assert json.loads(out.read_text(encoding="utf-8"))["collection"]["status"] == "failed"


def test_cli_path_with_equals_sign_is_not_taken_as_label(make, tmp_path):
    scan, catalog = make
    s = scan(GATEWAY)
    odd = tmp_path / "a b=c.json"  # 첫 '='앞이 라벨 형식이 아니므로 전체가 경로
    odd.write_bytes(s.read_bytes())
    out = tmp_path / "link.json"
    proc = run_cli(["--config-scan", odd, "--catalog", catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")), "--output", out])
    assert proc.returncode == 1, proc.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["inputs"]["config_scans"][0]["label_status"] == "not_assigned"


@pytest.mark.parametrize("bad", ["gw", "gw=", "=gateway", "gw=router", "gw=gateway,gateway", "gw=gateway,id=a,id=b", "bad label=gateway"])
def test_cli_rejects_malformed_subject_syntax(make, tmp_path, bad):
    scan, catalog = make
    proc = run_cli(["--config-scan", f"gw={scan(GATEWAY)}", "--catalog", catalog(cat_server("a")), "--subject", bad,
                    "--output", tmp_path / "o.json"])
    assert proc.returncode == 2 and not (tmp_path / "o.json").exists()


def test_cli_refuses_to_overwrite_input_and_keeps_it(make, tmp_path):
    scan, catalog = make
    s = scan(GATEWAY)
    before = s.read_bytes()
    proc = run_cli(["--config-scan", f"gw={s}", "--catalog", catalog(cat_server("a")), "--output", s])
    assert proc.returncode == 4
    assert s.read_bytes() == before


def test_cli_argument_error_exit_code():
    assert run_cli(["--catalog", "x.json", "--output", "y.json"]).returncode == 2


def test_example_files_link_only_by_explicit_reference(tmp_path):
    two = tmp_path / "two.json"
    two.write_text(json.dumps(build_report(collect(EXAMPLES / "two-servers.json5"))), encoding="utf-8")
    node = tmp_path / "node.json"
    node.write_text(json.dumps(build_report(collect(EXAMPLES / "node-and-gateway.json5",
                                                    SUPPORTED_REGISTRY_PATHS["nodeHost.mcp.servers"]))), encoding="utf-8")
    cat = tmp_path / "cat.json"
    cat.write_text(json.dumps(build_catalog_report(collect_tools_catalog(EXAMPLES / "tools-list-capture.json"))), encoding="utf-8")
    rep = link([("gw", two), ("nd", node)], cat)
    # 예제 capture는 config_scan_ref를 선언하지 않으므로 이름이 같아도 어느 서버도 연결되지 않는다.
    assert [ln["link_status"] for ln in rep["links"]] == ["unlinked"] * 3
    by = {ln["server_ref"]: ln for ln in rep["links"]}
    assert by["sample-files"]["reason"] == "config_scan_ref_missing"
    assert by["sample-files"]["key_region_matches"] == ["config-scan[0]/servers[0]"]
    assert by["sample-notes"]["reason"] == "config_scan_ref_missing" and by["sample-notes"]["key_region_matches"] == []


# ---- 입력 라벨의 비밀값 가림 ---------------------------------------------------------------------
# `_LABEL_RE`를 통과해도 비밀값이 아닌 것은 아니다. 라벨은 연결 입력이지 결과에 복사할 값이 아니다.

TOKEN = "ghp_FAKEREFTOKEN1234567890abcdefgh"
TOKEN2 = "ghp_FAKEOTHERTOKEN0987654321zyxwvuts"
RAW_MARKERS = ("FAKEREFTOKEN", "FAKEOTHERTOKEN", TOKEN, TOKEN2)


def assert_no_raw(*texts):
    for text in texts:
        for marker in RAW_MARKERS:
            assert marker not in text, marker


def good_catalog(catalog, scan_ref="gw"):
    return catalog(cat_server("a", key="files", reg="mcp.servers", scan=scan_ref))


def test_secret_looking_catalog_label_is_not_copied_and_does_not_block_the_link(make):
    scan, catalog = make
    rep = link([gw(scan)], [(TOKEN, good_catalog(catalog))])
    assert_no_raw(json.dumps(rep, ensure_ascii=False))
    ln = rep["links"][0]
    assert ln["link_status"] == "linked"          # 카탈로그 라벨은 연결 근거가 아니다
    assert ln["catalog_label"] is None
    assert rep["inputs"]["catalogs"][0]["label"] is None and rep["inputs"]["catalogs"][0]["label_status"] == "invalid"
    assert "catalog_label_problem" in reasons(rep) and rep["collection"]["status"] == "partial"


def test_secret_looking_config_scan_label_is_not_copied_and_cannot_be_referenced(make):
    scan, catalog = make
    rep = link([(TOKEN, scan(GATEWAY))], good_catalog(catalog, TOKEN))
    assert_no_raw(json.dumps(rep, ensure_ascii=False))
    ln = rep["links"][0]
    assert (ln["link_status"], ln["reason"]) == ("unlinked", "config_scan_ref_unknown")
    assert ln["trace"] is None
    assert rep["inputs"]["config_scans"][0]["label"] is None
    assert rep["inputs"]["config_scans"][0]["label_status"] == "invalid"
    assert rep["declarations"][0]["config_scan_label"] is None
    assert "config_scan_label_problem" in reasons(rep)


def test_masked_labels_never_collide_into_a_wrong_link(make):
    scan, catalog = make
    a = (TOKEN, scan('{ mcp: { servers: { files: { command: "a" } } } }'))
    b = (TOKEN2, scan('{ mcp: { servers: { files: { command: "b" } } } }'))
    cat = catalog(cat_server("x", key="files", reg="mcp.servers", scan=TOKEN),
                  cat_server("y", key="files", reg="mcp.servers", scan=TOKEN2))
    rep = link([a, b], cat)
    assert_no_raw(json.dumps(rep, ensure_ascii=False))
    assert [x["link_status"] for x in rep["links"]] == ["unlinked", "unlinked"]
    assert all(d["linked_observations"] == [] for d in rep["declarations"])
    # 정상 라벨과 섞여 있어도 가려진 이름이 정상 라벨로 잘못 연결되지 않는다.
    ok = ("gw", scan('{ mcp: { servers: { files: { command: "c" } } } }'))
    rep2 = link([a, ok], catalog(cat_server("x", key="files", reg="mcp.servers", scan=TOKEN)))
    assert rep2["links"][0]["link_status"] == "unlinked" and rep2["links"][0]["trace"] is None


def test_two_secret_looking_catalog_labels_stay_two_separate_observations(make):
    scan, catalog = make
    rep = link([gw(scan)], [(TOKEN, good_catalog(catalog)), (TOKEN2, good_catalog(catalog))])
    assert_no_raw(json.dumps(rep, ensure_ascii=False))
    assert [x["link_status"] for x in rep["links"]] == ["linked", "linked"]
    assert [x["catalog_input_index"] for x in rep["links"]] == [0, 1]
    assert len(rep["declarations"][0]["linked_observations"]) == 2


def test_secret_looking_subject_label_is_ignored_without_echo(make):
    scan, catalog = make
    rep = link([(TOKEN, scan(GATEWAY))], good_catalog(catalog, TOKEN),
               [{"scan_label": TOKEN, "kind": "gateway", "id": "dev-1"}])
    assert_no_raw(json.dumps(rep, ensure_ascii=False))
    rec = rep["inputs"]["subject_inputs"][0]
    assert rec["status"] == "ignored" and "scan_label_invalid" in rec["problems"] and rec["scan_label"] is None
    assert all(d["declaring_subject"]["id"] is None for d in rep["declarations"])


def test_secret_looking_reference_in_catalog_is_masked_everywhere(make):
    scan, catalog = make
    rep = link([gw(scan)], good_catalog(catalog, TOKEN))
    assert_no_raw(json.dumps(rep, ensure_ascii=False))
    assert rep["links"][0]["reason"] == "config_scan_ref_unknown"


def test_normal_labels_still_link_and_keep_observations_after_label_screening(make):
    scan, catalog = make
    rep = link([gw(scan)], [("obs1", good_catalog(catalog)), ("obs2", good_catalog(catalog))],
               [{"scan_label": "gw", "kind": "gateway", "id": HEX64}])
    assert [x["link_status"] for x in rep["links"]] == ["linked", "linked"]
    assert [x["catalog_label"] for x in rep["links"]] == ["obs1", "obs2"]
    assert rep["links"][0]["trace"]["config_scan"]["label"] == "gw"
    assert rep["links"][0]["trace"]["declaring_subject"]["id"] == HEX64
    assert len(rep["declarations"][0]["linked_observations"]) == 2
    assert rep["collection"]["status"] == "complete"


@pytest.mark.parametrize("label", ["gw", "gw-1", "node.a", "obs_2", "GW9", "prod-gateway-2026", "a" * 40])
def test_ordinary_labels_are_not_rejected_as_secrets(make, label):
    scan, catalog = make
    rep = link([(label, scan(GATEWAY))], good_catalog(catalog, label))
    assert rep["inputs"]["config_scans"][0]["label_status"] == "ok"
    assert rep["links"][0]["link_status"] == "linked"


def test_cli_never_prints_or_saves_secret_looking_labels(make, tmp_path):
    scan, catalog = make
    out = tmp_path / "link.json"
    proc = run_cli(["--config-scan", f"gw={scan(GATEWAY)}", "--catalog", f"{TOKEN}={good_catalog(catalog)}",
                    "--subject", f"{TOKEN2}=gateway,id=dev-1", "--output", out])
    assert proc.returncode == 1
    assert_no_raw(proc.stdout, proc.stderr, out.read_text(encoding="utf-8"))
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["links"][0]["link_status"] == "linked" and rep["links"][0]["catalog_label"] is None


def test_cli_secret_looking_scan_label_and_error_paths_do_not_echo(make, tmp_path):
    scan, catalog = make
    out = tmp_path / "link.json"
    proc = run_cli(["--config-scan", f"{TOKEN}={scan(GATEWAY)}", "--catalog", good_catalog(catalog, TOKEN), "--output", out])
    assert proc.returncode == 1
    assert_no_raw(proc.stdout, proc.stderr, out.read_text(encoding="utf-8"))
    # 입력 실패(없는 파일), 같은 파일 덮어쓰기 거부, 잘못된 --subject 형식의 메시지에도 라벨을 되풀이하지 않는다.
    missing = run_cli(["--config-scan", f"{TOKEN}={tmp_path / 'missing.json'}", "--catalog", good_catalog(catalog), "--output", out])
    assert missing.returncode == 3
    assert_no_raw(missing.stdout, missing.stderr, out.read_text(encoding="utf-8"))
    s = scan(GATEWAY)
    same = run_cli(["--config-scan", f"{TOKEN}={s}", "--catalog", good_catalog(catalog), "--output", s])
    assert same.returncode == 4
    assert_no_raw(same.stdout, same.stderr)
    bad = run_cli(["--config-scan", f"gw={scan(GATEWAY)}", "--catalog", good_catalog(catalog), "--subject", f"{TOKEN}=router",
                   "--output", out])
    assert bad.returncode == 2
    assert_no_raw(bad.stdout, bad.stderr)
