"""OpenClaw 직접 조회(openclaw_direct)와 기존 수집 모듈 연동 테스트.

**실제 OpenClaw를 실행하지 않는다.** 테스트가 만든 가짜 CLI(`tests/fake_openclaw.py`를 감싼 실행 파일)에 대해 실행 인자, 정상 응답, 오류,
시간 초과, 출력 초과, 프로세스 정리를 검증한다. 실제 OpenClaw에 대한 검증은 이 파일에 없다(미확인).
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from asset_scanner import openclaw_direct as od
from asset_scanner.linking import build_link_report, link_scans
from asset_scanner.node_gateway_identity import build_report as identity_report
from asset_scanner.node_gateway_identity import collect_identities
from asset_scanner.openclaw_direct import QUERIES, DirectConfig, build_argv, probe_version, run_queries, run_query, validate_config
from asset_scanner.plugin_skill_assets import build_report as assets_report
from asset_scanner.plugin_skill_assets import collect_assets, read_plugins_list_direct, read_skills_list_direct
from conftest import SCANNER_ROOT

FAKE = Path(__file__).resolve().parent / "fake_openclaw.py"
PASS = ("FAKE_OPENCLAW_MODE", "FAKE_OPENCLAW_LOG", "FAKE_PLUGIN_ROOT", "FAKE_SKILL_FILE", "FAKE_OPENCLAW_PIDFILE")
GW_URL = "ws://127.0.0.1:18789"
_REAL_RUN = subprocess.run
_REAL_POPEN = subprocess.Popen


@pytest.fixture
def fake(tmp_path, monkeypatch):
    log = tmp_path / "calls.jsonl"
    if sys.platform == "win32":
        shim = tmp_path / "fake-openclaw.cmd"
        shim.write_text(f'@echo off\r\n"{sys.executable}" "{FAKE}" %*\r\n', encoding="utf-8")
    else:
        shim = tmp_path / "fake-openclaw"
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n', encoding="utf-8")
        shim.chmod(0o755)
    monkeypatch.setenv("FAKE_OPENCLAW_LOG", str(log))
    monkeypatch.setenv("FAKE_OPENCLAW_PIDFILE", str(tmp_path / "pids.txt"))

    def cfg(mode="ok", **kw) -> DirectConfig:
        monkeypatch.setenv("FAKE_OPENCLAW_MODE", mode)
        extra = tuple(kw.pop("pass_env", ()))
        kw.setdefault("timeout_s", 20.0)
        return DirectConfig(openclaw_bin=shim, pass_env=PASS + extra, **kw)

    def calls() -> list[dict]:
        return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []

    return SimpleNamespace(cfg=cfg, calls=calls, shim=shim, log=log, tmp=tmp_path, env=monkeypatch)


def pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        out = _REAL_RUN(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def dump(x):
    return json.dumps(x, ensure_ascii=False, default=str)


# ---- 허용 목록: 실행 인자 --------------------------------------------------------------------------

def test_each_allowed_query_runs_exactly_its_argument_array(fake):
    cfg = fake.cfg(expect_gateway_url=GW_URL, accept_skills_gateway_rpc=True)
    results, ver = run_queries(cfg, ["plugins", "node-identity", "gateway-identity", "skills"])
    assert all(r.failure is None for r in results.values()) and ver.failure is None
    argvs = [c["argv"] for c in fake.calls()]
    assert argvs[0] == ["--version"]
    assert argvs[1] == ["plugins", "list", "--json"]
    assert argvs[2] == ["node", "identity", "--json"]
    gw = argvs[3]
    assert gw[:4] == ["gateway", "call", "gateway.identity.get", "--json"] and gw[4] == "--timeout" and gw[6:] == ["--expect-url", GW_URL]
    assert argvs[4] == ["skills", "list", "--json"]
    flat = [a for av in argvs for a in av]
    for forbidden in ("--url", "--token", "--password", "--params", "--container", "install", "update", "pair", "onboard", "setup", "config"):
        assert forbidden not in flat
    assert not any(a.startswith("-") and a not in ("--version", "--json", "--timeout", "--expect-url") for a in flat)


def test_gateway_call_is_pinned_to_one_method_and_the_query_table_is_closed():
    assert set(QUERIES) == {"version", "plugins", "node-identity", "gateway-identity", "skills"}
    gateway_argvs = [q.argv for q in QUERIES.values() if q.argv[:2] == ("gateway", "call")]
    assert gateway_argvs == [("gateway", "call", "gateway.identity.get", "--json")]          # gateway call 전체가 아니라 이 메서드 하나
    cfg = DirectConfig(openclaw_bin=Path(sys.executable))
    for q in ("status", "gateway call health", "config set", "plugins install", "devices approve", "nodes pair", "doctor --fix"):
        assert validate_config(cfg, [q])                                                    # 허용 목록 밖은 모두 거부


def test_profile_and_dev_flags_go_before_the_subcommand_and_are_validated(fake, tmp_path):
    assert build_argv(fake.cfg(profile="staging"), "plugins")[1:] == ["--profile", "staging", "plugins", "list", "--json"]
    assert build_argv(fake.cfg(dev=True), "node-identity")[1:] == ["--dev", "node", "identity", "--json"]
    assert build_argv(fake.cfg(profile="staging"), "version")[1:] == ["--version"]
    for bad in ("a b", "x;rm", "../x", "-x", "", "a" * 40):
        assert validate_config(fake.cfg(profile=bad), ["plugins"])
    assert validate_config(fake.cfg(profile="p", dev=True), ["plugins"])


def test_scope_paths_must_already_exist_and_reach_the_child_as_environment(fake, tmp_path):
    cfgfile, state, home = tmp_path / "openclaw.json5", tmp_path / "state", tmp_path / "home"
    cfgfile.write_text("{}", encoding="utf-8")
    state.mkdir(); home.mkdir()
    assert validate_config(fake.cfg(config_path=tmp_path / "nope.json5"), ["plugins"])         # 새로 만들게 될 경로는 거부
    assert validate_config(fake.cfg(state_dir=tmp_path / "nostate"), ["plugins"])
    assert validate_config(fake.cfg(home=tmp_path / "nohome"), ["plugins"])
    res = run_query(fake.cfg(config_path=cfgfile, state_dir=state, home=home, profile="stg"), "plugins")
    assert res.failure is None
    call = fake.calls()[-1]
    assert call["scope_env"]["OPENCLAW_CONFIG_PATH"] == str(cfgfile) and call["scope_env"]["OPENCLAW_STATE_DIR"] == str(state)
    assert call["scope_env"]["OPENCLAW_HOME"] == str(home) and call["argv"][:2] == ["--profile", "stg"]
    sc = res.observation["scope"]
    assert sc["config_path_set"] and sc["state_dir_set"] and sc["home_set"] and sc["default_state_location"] is False
    assert not (tmp_path / "nostate").exists()                                                  # 스캐너가 폴더를 만들지 않음


def test_default_scope_is_reported_as_the_users_default_location(fake):
    res = run_query(fake.cfg(), "plugins")
    assert res.observation["scope"]["default_state_location"] is True and res.observation["scope"]["profile"] is None


# ---- 거부: 프로세스를 만들지 않는다 -----------------------------------------------------------------------

def test_refusals_never_start_a_process(fake, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("프로세스 시작")
    monkeypatch.setattr(od.subprocess, "Popen", boom)
    with pytest.raises(ValueError, match="gateway-identity"):
        run_query(fake.cfg(), "gateway-identity")                                               # 대상 미고정·미확인
    with pytest.raises(ValueError, match="skills"):
        run_query(fake.cfg(), "skills")                                                         # 기본 거부
    with pytest.raises(ValueError):
        run_queries(fake.cfg(timeout_s=0), ["plugins"])
    with pytest.raises(ValueError):
        run_query(fake.cfg(), "status")                                                         # type: ignore[arg-type]
    assert fake.calls() == []


@pytest.mark.parametrize("url", ["http://127.0.0.1:1", "ws://h/x?token=1", "ws://u:p@h/", "ws://h/ a", "ws://h;x", "ws://h/%20", "ws://h/&x", "file:///x"])
def test_expect_url_must_be_a_plain_websocket_address(fake, url):
    assert validate_config(fake.cfg(expect_gateway_url=url), ["gateway-identity"])


def test_gateway_identity_can_be_accepted_without_pinning_and_is_marked_unverified(fake):
    res = run_query(fake.cfg(accept_configured_gateway=True), "gateway-identity")
    assert res.failure is None
    gt = res.observation["gateway_target"]
    assert gt["basis"] == "configured_by_openclaw_unverified" and gt["gateway_method"] == "gateway.identity.get" and gt["params"] == "none"
    assert "--expect-url" not in fake.calls()[-1]["argv"]
    pinned = run_query(fake.cfg(expect_gateway_url=GW_URL), "gateway-identity").observation["gateway_target"]
    assert pinned["basis"] == "expect_url" and pinned["expect_url"] == GW_URL


def test_skills_list_requires_explicit_acknowledgement_and_records_it(fake):
    ok = run_query(fake.cfg(accept_skills_gateway_rpc=True, agent="main"), "skills")
    assert ok.failure is None and ok.observation["acknowledged_risk"] == "skills_list_gateway_rpc" and ok.observation["uses_gateway"] is True
    assert fake.calls()[-1]["argv"] == ["skills", "list", "--json", "--agent", "main"]
    assert validate_config(fake.cfg(accept_skills_gateway_rpc=True, agent="a b"), ["skills"])


def test_missing_or_non_file_binary_is_rejected_and_never_searched_on_path(fake, tmp_path):
    assert validate_config(DirectConfig(openclaw_bin=tmp_path / "nope"), ["plugins"])
    assert validate_config(DirectConfig(openclaw_bin=tmp_path), ["plugins"])                    # 폴더
    assert validate_config(DirectConfig(openclaw_bin=Path("openclaw")), ["plugins"])            # PATH 검색 없음: 상대 이름은 파일이 아니면 거부
    txt = tmp_path / "not-executable.txt"
    txt.write_text("hello", encoding="utf-8")
    res = run_query(DirectConfig(openclaw_bin=txt, timeout_s=10), "plugins")
    assert res.failure["code"] in ("spawn_failed", "command_failed")


# ---- 환경변수 격리 ---------------------------------------------------------------------------------------

def test_only_base_scope_and_named_environment_reaches_the_child(fake):
    fake.env.setenv("FAKESECRET_PARENT", "FAKE-PARENT-SECRET")
    fake.env.setenv("OPENCLAW_GATEWAY_TOKEN", "FAKE-GATEWAY-TOKEN-VALUE")
    fake.env.setenv("OPENCLAW_CONFIG_PATH", "C:/should/not/leak.json5")
    run_query(fake.cfg(), "plugins")
    names = fake.calls()[-1]["interesting_env_names"]
    assert "FAKESECRET_PARENT" not in names and "OPENCLAW_GATEWAY_TOKEN" not in names           # 이름을 지정하지 않으면 넘기지 않는다
    assert fake.calls()[-1]["scope_env"]["OPENCLAW_CONFIG_PATH"] is None                        # 부모의 범위 변수도 넘기지 않는다
    res = run_query(fake.cfg(pass_env=("OPENCLAW_GATEWAY_TOKEN",)), "plugins")
    assert "OPENCLAW_GATEWAY_TOKEN" in fake.calls()[-1]["interesting_env_names"]
    assert res.observation["scope"]["pass_env_names"].count("OPENCLAW_GATEWAY_TOKEN") == 1
    assert "FAKE-GATEWAY-TOKEN-VALUE" not in dump(res.observation)                              # 이름만 기록, 값은 기록하지 않는다


@pytest.mark.parametrize("name", ["OPENCLAW_CONFIG_PATH", "openclaw_state_dir", "OPENCLAW_HOME", "OPENCLAW_PROFILE", "bad name", "1ABC", ""])
def test_pass_env_cannot_override_scope_options(fake, name):
    assert validate_config(fake.cfg(pass_env=(name,)), ["plugins"])


def test_child_runs_in_a_neutral_directory_with_closed_stdin(fake):
    run_query(fake.cfg(), "plugins")
    call = fake.calls()[-1]
    assert Path(call["cwd"]).resolve() != SCANNER_ROOT.resolve()
    assert call["stdin_first_read"] == ""            # 자식이 입력을 기다리며 멈추지 않는다 (stdin은 DEVNULL)


# ---- 정상 응답·관측 기록 ----------------------------------------------------------------------------------

def test_observation_records_command_version_scope_and_time_without_raw_output(fake):
    cfg = fake.cfg(profile="stg")
    results, ver = run_queries(cfg, ["plugins"])
    obs = results["plugins"].observation
    assert obs["source_kind"] == "direct_query" and obs["executed_by_scanner"] is True and obs["verified_by_scanner"] is False
    assert obs["command"] == "openclaw --profile stg plugins list --json" and obs["shell"] is False and obs["exit_code"] == 0
    assert obs["installed_version"]["version"] == "2026.9.6" and obs["installed_version"]["commit"] == "eb377ac"
    assert obs["installed_version"]["version_matches_researched_basis"] is True
    assert obs["observed_at_origin"] == "scanner_clock_at_query" and obs["observed_at"].endswith("Z") and obs["raw_output_stored"] is False
    assert obs["stdout_bytes"] > 0 and obs["timed_out"] is False and obs["duration_ms"] >= 0
    assert obs["limits"]["timeout_s"] == 20.0 and "read_only_basis" in obs


def test_version_differences_are_flagged_and_can_be_required(fake):
    ver = probe_version(fake.cfg("version_other"))
    iv = ver.observation["installed_version"]
    assert iv["version"] == "2026.10.1" and iv["version_matches_researched_basis"] is False and iv["researched_basis"] == "2026.9.6"
    results, _ = run_queries(fake.cfg("version_other"), ["plugins"])            # 요구하지 않으면 실행하되 불일치를 기록
    assert results["plugins"].failure is None and results["plugins"].observation["installed_version"]["version_matches_researched_basis"] is False
    fake.log.unlink()
    strict, _ = run_queries(fake.cfg("version_other", require_version="2026.9.6"), ["plugins", "node-identity"])
    assert all(r.failure["code"] == "version_requirement_not_met" and r.observation["executed_by_scanner"] is False for r in strict.values())
    assert [c["argv"] for c in fake.calls()] == [["--version"]]                 # 버전 확인 외에는 아무것도 실행하지 않음


# ---- 실패 유형과 정리 --------------------------------------------------------------------------------------

def test_failure_modes_are_classified_without_storing_raw_output(fake):
    r = run_query(fake.cfg("fail"), "plugins")
    assert r.failure["code"] == "command_failed" and r.failure["exit_code"] == 1
    assert r.failure["stdout_error_json_keys"] == ["code", "error", "ok"]                      # 키 이름만
    blob = dump(r.failure) + dump(r.observation)
    for marker in ("FAKESTDERRTOKEN", "FAKESTDERRPASS", "FAKESTDOUTERRORSECRET"):
        assert marker not in blob
    assert r.failure["stderr_excerpt_sanitized"] and "ghp_" not in r.failure["stderr_excerpt_sanitized"]
    for mode, code in (("badjson", "output_not_json"), ("empty", "empty_output"), ("nonutf8", "output_not_utf8")):
        got = run_query(fake.cfg(mode), "node-identity")
        assert got.failure["code"] == code and got.data is None
        assert "FAKEBADJSONSECRET" not in dump(got.failure) + dump(got.observation)


def test_timeout_kills_the_process_tree_and_reports_it(fake):
    started = time.monotonic()
    r = run_query(fake.cfg("slow", timeout_s=1.5), "plugins")
    assert r.failure["code"] == "timeout" and r.observation["timed_out"] is True and r.observation["process_tree_killed"] is True
    assert time.monotonic() - started < 15


def test_grandchild_processes_do_not_survive_a_timeout(fake):
    r = run_query(fake.cfg("grandchild", timeout_s=2.0), "plugins")
    assert r.failure["code"] == "timeout"
    pids = [int(x) for x in (fake.tmp / "pids.txt").read_text(encoding="utf-8").split()]
    assert len(pids) == 2
    time.sleep(1.5)
    assert not any(pid_alive(p) for p in pids)                                                  # 손자 프로세스까지 정리됨


def test_oversized_output_stops_the_process_and_discards_the_excess(fake):
    started = time.monotonic()
    cfg = fake.cfg("huge", max_stdout_bytes=4096, timeout_s=20.0)
    r = run_query(cfg, "plugins")
    assert r.failure["code"] == "output_too_large" and r.observation["output_truncated"] is True and r.observation["process_tree_killed"] is True
    assert r.observation["stdout_bytes"] <= 4096 and r.data is None
    assert time.monotonic() - started < 15


def test_stdout_limit_is_validated(fake):
    assert validate_config(fake.cfg(max_stdout_bytes=10), ["plugins"])
    assert validate_config(fake.cfg(max_stdout_bytes=10 ** 10), ["plugins"])


# ---- 기존 파서 연동: 출처 구분 -------------------------------------------------------------------------------

def make_plugin_dir(tmp_path):
    d = tmp_path / "plug"
    d.mkdir()
    (d / "openclaw.plugin.json").write_text(json.dumps({"id": "voice-call", "name": "Voice Call", "configSchema": {}}), encoding="utf-8")
    return d


def test_direct_plugins_list_flows_into_the_existing_parser_and_links_by_id_and_root(fake, tmp_path):
    d = make_plugin_dir(tmp_path)
    fake.env.setenv("FAKE_PLUGIN_ROOT", str(d))
    results, _ = run_queries(fake.cfg(), ["plugins"])
    rep = assets_report(collect_assets([d], [], None, read_plugins_list_direct(results["plugins"]), None))
    p = rep["plugins"][0]
    ro = p["runtime_observation"]
    assert ro["link_basis"] == "id_and_root_dir_match" and ro["observed"]["status"] == "loaded" and ro["registered_names"]["toolNames"] == ["call"]
    o = ro["observation"]
    assert o["source_kind"] == "direct_query" and o["command"] == "openclaw plugins list --json" and o["installed_version"]["version"] == "2026.9.6"
    assert o["observed_at_origin"] == "scanner_clock_at_query" and "직접 조회한 plugins list --json" in ro["note"]
    assert [r["source"] for r in rep["runtime_only"]["plugins"]] == ["direct_plugins_list_only"]
    assert rep["stored_outputs"]["plugins_list"]["observation"]["source_kind"] == "direct_query"
    assert rep["collection"]["status"] == "complete"


def test_stored_and_direct_results_stay_distinguishable(fake, tmp_path):
    stored = tmp_path / "plugins.json"
    stored.write_text(json.dumps({"plugins": [{"id": "voice-call", "name": "V", "enabled": True, "status": "loaded"}]}), encoding="utf-8")
    from_file = assets_report(collect_assets([], [], None, stored, None))
    direct = assets_report(collect_assets([], [], None, read_plugins_list_direct(run_queries(fake.cfg(), ["plugins"])[0]["plugins"]), None))
    assert from_file["runtime_only"]["plugins"][0]["source"] == "stored_plugins_list_json_only"
    assert from_file["stored_outputs"]["plugins_list"]["observation"]["source_kind"] == "stored_command_output"
    assert direct["stored_outputs"]["plugins_list"]["observation"]["source_kind"] == "direct_query"


def test_direct_failure_becomes_a_failed_input_not_an_empty_inventory(fake):
    r = run_queries(fake.cfg("badjson"), ["plugins"])[0]["plugins"]
    rep = assets_report(collect_assets([], [], None, read_plugins_list_direct(r), None))
    assert rep["collection"]["status"] == "failed" and rep["stored_outputs"]["plugins_list"]["status"] == "failed"
    assert rep["stored_outputs"]["plugins_list"]["issues"][0]["code"] == "direct_output_not_json" and rep["runtime_only"]["plugins"] == []
    assert "FAKEBADJSONSECRET" not in dump(rep)


def test_direct_skills_list_links_by_file_path(fake, tmp_path):
    sd = tmp_path / "greeter"
    sd.mkdir()
    (sd / "SKILL.md").write_text("---\nname: greeter\ndescription: d\n---\nbody", encoding="utf-8")
    fake.env.setenv("FAKE_SKILL_FILE", str(sd / "SKILL.md"))
    results, _ = run_queries(fake.cfg(accept_skills_gateway_rpc=True), ["skills"])
    rep = assets_report(collect_assets([], [sd], None, None, read_skills_list_direct(results["skills"])))
    s = rep["skills"][0]
    assert s["runtime_observation"]["link_basis"] == "skill_file_path_match" and s["runtime_observation"]["observed"]["eligible"] is True
    assert s["runtime_observation"]["observation"]["acknowledged_risk"] == "skills_list_gateway_rpc"


def test_secret_looking_values_in_direct_output_are_masked(fake):
    r = run_queries(fake.cfg("secrets"), ["plugins"])[0]["plugins"]
    rep = assets_report(collect_assets([], [], None, read_plugins_list_direct(r), None))
    assert "FAKEPLUGINNAMETOKEN" not in dump(rep)


def test_direct_identity_goes_through_the_identity_parser_with_its_own_origin(fake):
    results, _ = run_queries(fake.cfg(expect_gateway_url=GW_URL), ["gateway-identity", "node-identity"])
    rep = identity_report(collect_identities([("gw", results["gateway-identity"])], [("nd", results["node-identity"])], {"gw": "2026-11-12T00:00:00Z"}))
    g, n = rep["identities"]
    assert g["origin"] == n["origin"] == "observed_from_direct_query" and g["collection_status"] == n["collection_status"] == "complete"
    assert g["device_id"]["original_value"] == "9f2c" * 16 and g["public_key"]["status"] == "as_reported"
    ob = g["observation"]
    assert ob["source_kind"] == "direct_query" and ob["executed_by_scanner"] is True and ob["required_scope"] == "operator.read"
    assert ob["observed_at_origin"] == "scanner_clock_at_query" and ob["observed_at"] != "2026-11-12T00:00:00Z"        # 사용자 선언 시각은 직접 조회에 적용하지 않음
    assert ob["gateway_target"]["basis"] == "expect_url" and ob["installed_version"]["version"] == "2026.9.6"
    assert "command_executed_by_scanner" not in rep["scope"]["not_verified"] and "observed_from_direct_query" in rep["scope"]["value_origins"]
    assert "직접 조회" in rep["scope"]["method"]


def test_direct_identity_failures_are_reported_per_item(fake):
    r = run_queries(fake.cfg("fail", accept_configured_gateway=True), ["gateway-identity"])[0]["gateway-identity"]
    rep = identity_report(collect_identities([(None, r)], [], {}))
    it = rep["identities"][0]
    assert it["collection_status"] == "failed" and it["outcome"] == "direct_command_failed" and it["device_id"]["status"] == "missing"
    assert rep["collection"]["status"] == "failed" and "FAKESTDERRTOKEN" not in dump(rep)


def link(scans, cats, subjects, observed):
    return build_link_report(link_scans(scans, cats, subjects, observed))


def test_linking_keeps_direct_and_user_provided_identity_apart_and_rejects_unknown_origin(fake, tmp_path):
    from asset_scanner.collector import SUPPORTED_REGISTRY_PATHS, collect
    from asset_scanner.report import build_report as config_report
    from asset_scanner.tools_catalog import build_catalog_report, collect_tools_catalog
    cfg = tmp_path / "c.json5"
    cfg.write_text('{ mcp: { servers: { files: { command: "demo" } } } }', encoding="utf-8")
    scan = tmp_path / "scan.json"
    scan.write_text(json.dumps(config_report(collect(cfg, SUPPORTED_REGISTRY_PATHS["mcp.servers"]))), encoding="utf-8")
    cap = tmp_path / "cap.json"
    cap.write_text(json.dumps({"servers": [{"server_ref": "a", "protocol_version": "2026-07-28", "registration_key": "files", "registry_path": "mcp.servers",
                                            "config_scan_ref": "gw", "pages": [{"result": {"resultType": "complete", "tools": [], "ttlMs": 1, "cacheScope": "public"}}]}]}),
                   encoding="utf-8")
    cat = tmp_path / "cat.json"
    cat.write_text(json.dumps(build_catalog_report(collect_tools_catalog(cap))), encoding="utf-8")
    r = run_queries(fake.cfg(expect_gateway_url=GW_URL), ["gateway-identity"])[0]["gateway-identity"]
    ident = tmp_path / "ident.json"
    ident.write_text(dump(identity_report(collect_identities([(None, r)], [], {}))), encoding="utf-8")
    rep = link([("gw", scan)], [("obs", cat)], [{"scan_label": "gw", "kind": "gateway", "id": "user-typed-id"}], [{"scan_label": "gw", "path": ident}])
    subj = rep["declarations"][0]["declaring_subject"]
    assert subj["id"] == "user-typed-id" and subj["id_origin"] == "user_provided"
    oi = subj["observed_identity"]
    assert oi["origin"] == "observed_from_direct_query" and oi["source_kind"] == "direct_query" and oi["installed_version"] == "2026.9.6"
    assert oi["id_conflicts_with_user_provided"] is True and "observed_identity_conflict" in [x["code"] for x in rep["collection"]["reasons"]]
    forged = json.loads(ident.read_text(encoding="utf-8"))
    forged["identities"][0]["origin"] = "observed_by_magic"
    bad = tmp_path / "forged.json"
    bad.write_text(json.dumps(forged), encoding="utf-8")
    rep2 = link([("gw", scan)], [("obs", cat)], None, [{"scan_label": "gw", "path": bad}])
    assert rep2["inputs"]["observed_identity_inputs"][0]["problems"] == ["identity_origin_invalid"]


# ---- CLI ------------------------------------------------------------------------------------------------

def cli(module, *args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return _REAL_RUN([sys.executable, "-m", f"asset_scanner.{module}", *map(str, args)], cwd=SCANNER_ROOT, env=env,
                     capture_output=True, text=True, encoding="utf-8")


def pass_args():
    out = []
    for n in PASS:
        out += ["--pass-env", n]
    return out


def test_cli_openclaw_direct_summary_has_no_raw_output(fake, tmp_path):
    fake.env.setenv("FAKE_OPENCLAW_MODE", "secrets")
    out = tmp_path / "o.json"
    p = cli("openclaw_direct", "--openclaw-bin", fake.shim, *pass_args(), "--query", "plugins", "--query", "node-identity", "--output", out)
    assert p.returncode == 0 and "출력 원문 저장 없음" in p.stdout
    saved = out.read_text(encoding="utf-8")
    assert "FAKEPLUGINNAMETOKEN" not in saved + p.stdout + p.stderr and json.loads(saved)["queries"][0]["plugins_record_count"] == 2
    assert cli("openclaw_direct", "--output", tmp_path / "x.json").returncode == 2
    assert cli("openclaw_direct", "--openclaw-bin", fake.shim, "--query", "skills", "--output", tmp_path / "x.json").returncode == 2
    fake.env.setenv("FAKE_OPENCLAW_MODE", "fail")
    assert cli("openclaw_direct", "--openclaw-bin", fake.shim, *pass_args(), "--query", "plugins", "--output", tmp_path / "f.json").returncode == 1


def test_cli_plugin_skill_assets_direct_query_end_to_end(fake, tmp_path):
    d = make_plugin_dir(tmp_path)
    fake.env.setenv("FAKE_PLUGIN_ROOT", str(d))
    out = tmp_path / "assets.json"
    ok = cli("plugin_skill_assets", "--plugin-dir", d, "--openclaw-query", "plugins", "--openclaw-bin", fake.shim, *pass_args(), "--output", out)
    assert ok.returncode == 0, ok.stderr
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["plugins"][0]["runtime_observation"]["observation"]["source_kind"] == "direct_query"
    stored = tmp_path / "stored.json"
    stored.write_text('{"plugins": []}', encoding="utf-8")
    both = cli("plugin_skill_assets", "--plugins-list-json", stored, "--openclaw-query", "plugins", "--openclaw-bin", fake.shim, "--output", tmp_path / "b.json")
    assert both.returncode == 2 and "동시에" in both.stderr
    assert cli("plugin_skill_assets", "--openclaw-query", "plugins", "--output", tmp_path / "n.json").returncode == 2
    n_calls = len(fake.calls())
    denied = cli("plugin_skill_assets", "--openclaw-query", "skills", "--openclaw-bin", fake.shim, *pass_args(), "--output", tmp_path / "d.json")
    assert denied.returncode == 2 and "기본 거부" in denied.stderr and len(fake.calls()) == n_calls     # 거부는 프로세스를 만들지 않음
    allowed = cli("plugin_skill_assets", "--openclaw-query", "skills", "--accept-skills-list-gateway-rpc", "--openclaw-bin", fake.shim, *pass_args(),
                  "--output", tmp_path / "s.json")
    assert allowed.returncode == 0 and ["skills", "list", "--json"] in [c["argv"] for c in fake.calls()]


def test_cli_identity_direct_query_end_to_end(fake, tmp_path):
    out = tmp_path / "id.json"
    ok = cli("node_gateway_identity", "--query-gateway-identity", "gw", "--query-node-identity", "--expect-gateway-url", GW_URL,
             "--openclaw-bin", fake.shim, *pass_args(), "--output", out)
    assert ok.returncode == 0, ok.stderr
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert [i["label"] for i in rep["identities"]] == ["gw", None] and {i["origin"] for i in rep["identities"]} == {"observed_from_direct_query"}
    unpinned = cli("node_gateway_identity", "--query-gateway-identity", "--openclaw-bin", fake.shim, *pass_args(), "--output", tmp_path / "u.json")
    assert unpinned.returncode == 2 and "--expect-gateway-url" in unpinned.stderr
    assert cli("node_gateway_identity", "--query-node-identity", "--output", tmp_path / "m.json").returncode == 2
    argvs = [c["argv"] for c in fake.calls()]
    assert not any(a[:1] == ["gateway"] for a in argvs[-1:])                                                 # 거부된 조회는 실행되지 않음


def test_no_raw_cli_output_is_written_anywhere(fake, tmp_path):
    out = tmp_path / "all.json"
    fake.env.setenv("FAKE_OPENCLAW_MODE", "secrets")
    cli("plugin_skill_assets", "--openclaw-query", "plugins", "--openclaw-bin", fake.shim, *pass_args(), "--output", out)
    files = [p for p in tmp_path.rglob("*") if p.is_file() and p.name not in ("calls.jsonl",)]
    for p in files:
        if p.suffix in (".json", ".txt", ".log"):
            assert "FAKEPLUGINNAMETOKEN" not in p.read_text(encoding="utf-8", errors="replace"), p.name
