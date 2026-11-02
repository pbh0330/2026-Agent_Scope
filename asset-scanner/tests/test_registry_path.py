"""등록 영역 선택(--registry-path)과 `nodeHost.mcp.servers` 수집 테스트.

모든 설정은 가상 예제이며 가짜 비밀값에는 "FAKE" 표식이 있다. 실제 서버 실행·접속은 없다.
"""

import json
import os
import subprocess
import sys

import pytest

from asset_scanner.collector import SUPPORTED_REGISTRY_PATHS, collect
from asset_scanner.report import build_report
from conftest import EXAMPLES, SCANNER_ROOT

NODE = SUPPORTED_REGISTRY_PATHS["nodeHost.mcp.servers"]
GW = SUPPORTED_REGISTRY_PATHS["mcp.servers"]
MARKER = "FAKE"


def run_cli_with(args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-m", "asset_scanner", *args], cwd=SCANNER_ROOT, env=env,
                          capture_output=True, text=True, encoding="utf-8")


def node_cfg(servers_json: str) -> str:
    return '{"nodeHost":{"mcp":{"servers":%s}}}' % servers_json


def by_key(result):
    return {s["registration_key"]: s for s in result["servers"]}


# ---- 두 서버 수집, 비활성 보존, 출처 기록 ----------------------------------------

def test_node_registry_collects_two_servers_and_keeps_disabled():
    result = collect(EXAMPLES / "node-and-gateway.json5", NODE)
    col = result["collection"]
    assert (col["status"], col["outcome"], col["server_count"]) == ("partial", "servers_found", 2)  # ${...} 참조
    servers = by_key(result)
    assert set(servers) == {"sample-node-files", "sample-node-remote"}
    assert servers["sample-node-remote"]["declared"]["enabled"] is False  # 비활성도 남는다
    assert servers["sample-node-files"]["declared"]["command"] == "npx"
    assert servers["sample-node-files"]["other_declared_keys"] == ["toolFilter"]
    assert servers["sample-node-files"]["collection_status"] == "complete"


def test_node_registry_records_selected_path_everywhere():
    result = collect(EXAMPLES / "node-and-gateway.json5", NODE)
    assert result["registry_path"] == "nodeHost.mcp.servers"
    assert build_report(result)["source"]["registry_path"] == "nodeHost.mcp.servers"
    s = by_key(result)["sample-node-files"]
    assert s["declaration_path"] == "nodeHost.mcp.servers.sample-node-files"
    assert s["declaration_pointer"] == "/nodeHost/mcp/servers/sample-node-files"
    for u in by_key(result)["sample-node-remote"]["unresolved"]:
        assert u["field_path"].startswith("nodeHost.mcp.servers.sample-node-remote")


def test_default_registry_is_unchanged():
    result = collect(EXAMPLES / "node-and-gateway.json5")
    assert result["registry_path"] == "mcp.servers"
    assert [s["declaration_path"] for s in result["servers"]] == ["mcp.servers.sample-gateway-only"]


# ---- 선택한 영역만 수집 ---------------------------------------------------------

def test_only_selected_region_is_collected_from_same_file():
    gw = collect(EXAMPLES / "node-and-gateway.json5", GW)
    node = collect(EXAMPLES / "node-and-gateway.json5", NODE)
    assert set(by_key(gw)) == {"sample-gateway-only"}
    assert set(by_key(node)) == {"sample-node-files", "sample-node-remote"}
    assert "sample-gateway-only" not in json.dumps(node)
    assert "sample-node" not in json.dumps(gw)


def test_other_regions_duplicates_includes_and_masked_keys_are_ignored(write_config):
    cfg = write_config(
        '{ mcp: { servers: { "ghp_FAKEOTHERREGION1234": {command:"g"}, a: {command:"g"}, a: {command:"g2"} },'
        ' "$include": "./other.json5" },'
        ' nodeHost: { mcp: { servers: { n: { command: "x" } } } } }')
    node = collect(cfg, NODE)["collection"]
    assert (node["status"], node["server_count"], node["reasons"], node["unresolved"]) == ("complete", 1, [], [])
    assert node["key_redactions"] == []
    gw = collect(cfg, GW)["collection"]  # 반대로 Gateway를 고르면 Gateway 쪽 문제가 보인다
    assert gw["status"] == "partial"


def test_include_on_selected_region_ancestor_makes_partial(write_config):
    cfg = write_config('{ nodeHost: { "$include": "./node.json5", mcp: { servers: { n: { command: "x" } } } } }')
    col = collect(cfg, NODE)["collection"]
    assert col["status"] == "partial"
    assert [u["kind"] for u in col["unresolved"]] == ["include"]
    assert collect(cfg, GW)["collection"]["outcome"] == "registry_absent"
    assert collect(cfg, GW)["collection"]["status"] == "complete"  # Gateway 영역에는 영향 없음


# ---- 영역 없음 / 빈 목록 / 잘못된 구조 ------------------------------------------

@pytest.mark.parametrize("text, missing", [
    ("{}", "nodeHost"),
    ('{"nodeHost":{}}', "nodeHost.mcp"),
    ('{"nodeHost":{"mcp":{}}}', "nodeHost.mcp.servers"),
    ('{"mcp":{"servers":{"gw":{"command":"x"}}}}', "nodeHost"),  # Gateway 서버만 있는 파일
])
def test_registry_absent_is_not_empty_registry(write_config, text, missing):
    col = collect(write_config(text), NODE)["collection"]
    assert (col["status"], col["outcome"], col["server_count"]) == ("complete", "registry_absent", None)
    assert col["reasons"][0]["field_path"] == missing


def test_empty_registry_is_zero_not_absent(write_config):
    result = collect(write_config(node_cfg("{}")), NODE)
    col = result["collection"]
    assert (col["status"], col["outcome"], col["server_count"]) == ("complete", "empty_registry", 0)
    assert result["servers"] == []


@pytest.mark.parametrize("text, code, field", [
    ('{"nodeHost":[]}', "nodeHost_not_object", "nodeHost"),
    ('{"nodeHost":{"mcp":"x"}}', "mcp_not_object", "nodeHost.mcp"),
    ('{"nodeHost":{"mcp":{"servers":[]}}}', "servers_not_object", "nodeHost.mcp.servers"),
    ('{"nodeHost":{"mcp":{"servers":null}}}', "servers_not_object", "nodeHost.mcp.servers"),
])
def test_invalid_structure_fails_instead_of_empty_list(write_config, text, code, field):
    result = collect(write_config(text), NODE)
    col = result["collection"]
    assert (col["status"], col["outcome"], col["server_count"]) == ("failed", "invalid_structure", None)
    assert col["reasons"][0]["code"] == code and col["reasons"][0]["field_path"] == field
    assert result["registry_path"] == "nodeHost.mcp.servers" and result["servers"] == []


def test_default_path_failure_codes_are_unchanged(write_config):
    assert collect(write_config("{ mcp: [] }"))["collection"]["reasons"][0]["code"] == "mcp_not_object"
    assert collect(write_config("{ mcp: { servers: [] } }"))["collection"]["reasons"][0]["code"] == "servers_not_object"


# ---- 서버 단위 문제 격리, 중복, 참조, 비밀값 -------------------------------------

def test_bad_server_does_not_remove_good_server(write_config):
    cfg = write_config(node_cfg('{ ok: {command:"x"}, notobj: "text",'
                                ' bad: { command: "x", headers: { A: { source: [], id: "T" } } } }'))
    result = collect(cfg, NODE)
    servers = by_key(result)
    assert result["collection"]["status"] == "partial" and result["collection"]["server_count"] == 3
    assert servers["ok"]["collection_status"] == "complete"
    assert servers["notobj"]["collection_status"] == "invalid"
    assert servers["notobj"]["issues"][0]["field_path"] == "nodeHost.mcp.servers.notobj"
    issue = [i for i in servers["bad"]["issues"] if i["code"] == "invalid_secret_ref"][0]
    assert issue["field_path"] == "nodeHost.mcp.servers.bad.headers.A"


def test_duplicate_registration_key_in_node_region(write_config):
    result = collect(write_config('{"nodeHost":{"mcp":{"servers":{"a":{"command":"1"},"a":{"command":"2"}}}}}'), NODE)
    col = result["collection"]
    assert col["status"] == "partial" and col["server_count"] == 1
    dup = [r for r in col["reasons"] if r["code"] == "duplicate_registration_key"]
    assert dup and dup[0]["field_path"] == "nodeHost.mcp.servers.a"


def test_duplicate_parent_key_with_absent_registry_is_partial(write_config):
    text = '{"nodeHost":{"mcp":{"servers":{"a":{"command":"x"}}},"mcp":{}}}'
    col = collect(write_config(text), NODE)["collection"]
    assert (col["status"], col["outcome"], col["server_count"]) == ("partial", "registry_absent", None)
    assert [r["code"] for r in col["reasons"]] == ["registry_absent", "duplicate_key"]
    assert col["reasons"][1]["field_path"] == "nodeHost.mcp"


def test_unresolved_env_ref_makes_node_server_partial_without_expanding(write_config, monkeypatch):
    monkeypatch.setenv("NODE_TOKEN_FAKE", "FAKE_REAL_VALUE")
    cfg = write_config(node_cfg('{ r: { url: "https://x.example/mcp",'
                                ' headers: { Authorization: "Bearer ${NODE_TOKEN_FAKE}" } } }'))
    result = collect(cfg, NODE)
    server = by_key(result)["r"]
    assert server["collection_status"] == "partial"
    assert [u["name"] for u in server["unresolved"]] == ["NODE_TOKEN_FAKE"]
    assert "FAKE_REAL_VALUE" not in json.dumps(result)
    assert result["collection"]["status"] == "partial"


def test_secret_looking_keys_masked_not_merged_and_args_redacted(write_config):
    cfg = write_config(node_cfg(
        '{ "ghp_FAKENODEKEY00001": { command: "a", args: ["--token", "FAKE_ARG_SECRET"] },'
        ' "ghp_FAKENODEKEY00002": { command: "b", args: ["--endpoint=https://u:FAKE_PW@h.example/m?token=FAKE_Q"] },'
        ' ok: { command: "c" } }'))
    result = collect(cfg, NODE)
    text = json.dumps(result, ensure_ascii=False)
    assert MARKER not in text
    keys = [s["registration_key"] for s in result["servers"]]
    assert len(set(keys)) == 3 and result["collection"]["server_count"] == 3
    redactions = result["collection"]["key_redactions"]
    assert len(redactions) == 2 and all(r.startswith("nodeHost.mcp.servers[") for r in redactions)
    masked = [s for s in result["servers"] if s.get("registration_key_redacted")]
    assert len(masked) == 2
    for s in masked:
        assert s["declaration_path"].startswith("nodeHost.mcp.servers[")  # 선택한 경로 아래의 위치


# ---- CLI -----------------------------------------------------------------------

def test_cli_node_registry_end_to_end(tmp_path):
    out = tmp_path / "node.json"
    proc = run_cli_with(["--config", str(EXAMPLES / "node-and-gateway.json5"), "--output", str(out),
                         "--registry-path", "nodeHost.mcp.servers"])
    assert proc.returncode == 1, proc.stderr  # ${...} 참조가 있어 partial
    assert proc.stderr == "" and "등록 영역: nodeHost.mcp.servers" in proc.stdout
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["source"]["registry_path"] == "nodeHost.mcp.servers"
    assert report["collection"]["server_count"] == 2
    assert MARKER not in out.read_text(encoding="utf-8").replace("SAMPLE_FAKE_TOKEN", "")  # 참조 이름 외 값 없음
    assert "Bearer" not in out.read_text(encoding="utf-8")


def test_cli_without_flag_behaves_as_before(tmp_path):
    out = tmp_path / "default.json"
    proc = run_cli_with(["--config", str(EXAMPLES / "two-servers.json5"), "--output", str(out)])
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["source"]["registry_path"] == "mcp.servers"
    assert [s["declaration_path"] for s in report["servers"]][0].startswith("mcp.servers.")


def test_cli_rejects_unsupported_registry_path(tmp_path):
    proc = run_cli_with(["--config", str(EXAMPLES / "two-servers.json5"), "--output", str(tmp_path / "x.json"),
                         "--registry-path", "plugins.entries"])
    assert proc.returncode == 2
    assert not (tmp_path / "x.json").exists()


def test_cli_failure_report_records_selected_path(tmp_path):
    out = tmp_path / "f.json"
    proc = run_cli_with(["--config", str(tmp_path / "missing.json"), "--output", str(out),
                         "--registry-path", "nodeHost.mcp.servers"])
    assert proc.returncode == 3, proc.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["source"]["registry_path"] == "nodeHost.mcp.servers"


def test_collect_rejects_unsupported_registry_tuple(write_config):
    with pytest.raises(ValueError):
        collect(write_config("{}"), ("plugins", "entries"))
