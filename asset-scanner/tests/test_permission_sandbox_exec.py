"""Permission/Auth 원천 확대 테스트: sandbox·exec 정책·네트워크 스위치·호스트 승인 문서 (가상 설정).

근거(모두 OpenClaw 2026.9.6 npm 패키지 문서, 고정 커밋 eb377ac59e6c9fd6c7705028034812becf00271b):
- `docs/gateway/config-agents/sandbox.md`: `agents.defaults.sandbox.{mode,backend,scope,workspaceAccess,workspaceRoot,docker.*,ssh.*,browser.*}`, `tools.sandbox.tools.{allow,deny}`
- `docs/gateway/config-agents/entries-and-multi-agent.md`: `agents.entries.<id>.sandbox.{mode,scope,workspaceAccess}`
- `docs/gateway/config-tools/built-in-tools.md`, `docs/tools/exec-approvals.md`: `tools.exec.{mode,security,ask,host,strictInlineEval,applyPatch.*,grantExpiryDays}`, `tools.web.{search,fetch}.enabled`
- `docs/tools/exec-approvals.md` "Settings and storage": 호스트 승인 문서(`version`·`socket`·`defaults`·`agents.<id>.{security,ask,askFallback,autoAllowSkills,allowlist,mcpTools}`)
선언 값만 수집하고 최종 실효 권한은 계산하지 않는다. 인증정보 원문·길이·해시는 저장하지 않는다. 값은 모두 가짜다.
"""

import json
import os
import subprocess
import sys

from asset_scanner.permission_auth import build_report, collect_permission_auth
from conftest import SCANNER_ROOT

CONFIG = {
    "agents": {
        "defaults": {"sandbox": {
            "mode": "non-main", "backend": "docker", "scope": "agent", "workspaceAccess": "ro", "workspaceRoot": "~/.openclaw/sandboxes",
            "docker": {"network": "none", "readOnlyRoot": True, "user": "1000:1000", "capDrop": ["ALL"], "binds": ["/home/user/source:/source:rw"],
                       "dns": ["1.1.1.1"], "extraHosts": ["internal.service:10.0.0.5"], "seccompProfile": "/p/seccomp.json", "apparmorProfile": "openclaw-sandbox"},
            "ssh": {"target": "user@gateway-host:22", "strictHostKeyChecking": True, "updateHostKeys": True, "identityFile": "~/.ssh/id_ed25519",
                    "identityData": {"source": "env", "provider": "default", "id": "SSH_IDENTITY"}, "knownHostsData": "FAKEKNOWNHOSTSDATA123"},
            "browser": {"enabled": False, "allowHostControl": False, "network": "openclaw-sandbox-browser", "cdpSourceRange": "172.21.0.1/32"},
        }},
        "entries": {"main": {"sandbox": {"mode": "all", "scope": "agent", "workspaceAccess": "none"}, "tools": {"exec": {"mode": "ask", "host": "sandbox"}}}},
    },
    "tools": {
        "sandbox": {"tools": {"allow": ["exec", "read"], "deny": ["browser", "gateway"]}},
        "exec": {"mode": "allowlist", "security": "allowlist", "ask": "on-miss", "host": "gateway", "strictInlineEval": True,
                 "applyPatch": {"enabled": True, "allowModels": ["m-1"]}, "grantExpiryDays": 30},
        "web": {"search": {"enabled": True}, "fetch": {"enabled": False, "maxRedirects": 3}},
    },
}


def run(tmp_path, cfg, **kw):
    p = tmp_path / "openclaw.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return build_report(collect_permission_auth(p, **kw))


def by_path(rep):
    return {i["config_path"]: i for i in rep["items"]}


def test_sandbox_declarations_are_collected_with_their_doc_basis_and_scope(tmp_path):
    items = by_path(run(tmp_path, CONFIG))
    d = items["agents.defaults.sandbox.mode"]
    assert d["category"] == "sandbox_policy" and d["value"] == "non-main" and d["value_documented"] is True
    assert d["applies_to"] == {"scope": "agent_defaults"} and "config-agents/sandbox.md" in d["doc_basis"]
    assert items["agents.defaults.sandbox.workspaceAccess"]["value"] == "ro"
    assert items["agents.defaults.sandbox.docker.network"]["value"] == "none"
    assert items["agents.defaults.sandbox.docker.readOnlyRoot"]["value"] is True
    assert items["agents.defaults.sandbox.docker.capDrop"]["value"] == ["ALL"]
    assert items["agents.defaults.sandbox.docker.binds"]["value"] == ["/home/user/source:/source:rw"]       # 파일 범위(마운트) 선언
    assert items["agents.defaults.sandbox.browser.allowHostControl"]["value"] is False
    assert items["agents.entries.main.sandbox.mode"]["applies_to"] == {"scope": "agent", "agent_key": "main"}
    assert items["tools.sandbox.tools.deny"]["value"] == ["browser", "gateway"]
    assert items["agents.defaults.sandbox.ssh.target"]["value"] == "user@gateway-host:22"


def test_exec_policy_and_network_switches_are_collected_for_global_and_agent_scope(tmp_path):
    items = by_path(run(tmp_path, CONFIG))
    assert items["tools.exec.mode"]["category"] == "exec_policy" and items["tools.exec.mode"]["value"] == "allowlist" and items["tools.exec.mode"]["value_documented"]
    assert items["tools.exec.security"]["value"] == "allowlist" and items["tools.exec.ask"]["value"] == "on-miss" and items["tools.exec.host"]["value"] == "gateway"
    assert items["tools.exec.strictInlineEval"]["value"] is True and items["tools.exec.applyPatch.enabled"]["value"] is True
    assert items["tools.exec.applyPatch.allowModels"]["value"] == ["m-1"] and items["tools.exec.grantExpiryDays"]["value"] == 30
    assert items["agents.entries.main.tools.exec.mode"]["applies_to"] == {"scope": "agent", "agent_key": "main"}
    assert items["tools.web.search.enabled"]["category"] == "network_policy" and items["tools.web.fetch.enabled"]["value"] is False
    assert "tools.web.fetch.maxRedirects" not in items                                                # 스위치만 수집, 조정값은 수집하지 않음


def test_ssh_credentials_are_never_stored_only_kinds_and_references(tmp_path):
    rep = run(tmp_path, CONFIG)
    items = by_path(rep)
    assert items["agents.defaults.sandbox.ssh.identityData"]["credential"]["kind"] == "secret_ref"
    assert items["agents.defaults.sandbox.ssh.knownHostsData"]["credential"] == {"kind": "literal_withheld"}
    assert items["agents.defaults.sandbox.ssh.identityFile"]["value_kind"] == "path_declared"       # 경로 문자열도 저장하지 않음
    text = json.dumps(rep)
    assert "FAKEKNOWNHOSTSDATA123" not in text and "id_ed25519" not in text
    assert {"kind": "secret_ref"}.items() <= items["agents.defaults.sandbox.ssh.identityData"]["credential"].items()


def test_unknown_values_are_kept_but_marked_and_wrong_types_are_reported(tmp_path):
    rep = run(tmp_path, {"agents": {"defaults": {"sandbox": {"mode": "magic", "docker": {"readOnlyRoot": "yes"}}}}, "tools": {"exec": {"grantExpiryDays": "x"}}})
    items = by_path(rep)
    assert items["agents.defaults.sandbox.mode"]["value"] == "magic" and items["agents.defaults.sandbox.mode"]["value_documented"] is False
    assert items["agents.defaults.sandbox.docker.readOnlyRoot"]["value_kind"] == "invalid_type"
    assert sum(1 for i in rep["issues"] if i["code"] == "field_type_invalid") == 2 and rep["collection"]["status"] == "partial"


def test_nothing_is_invented_for_missing_sections_and_no_effective_result_is_computed(tmp_path):
    rep = run(tmp_path, {"agents": {"defaults": {"sandbox": {}}}, "tools": {"exec": {}}})
    assert rep["items"] == [] and rep["collection"]["outcome"] == "no_declared_items"
    assert "effective_policy" in rep["scope"]["not_collected"]
    assert "sandbox_settings" not in rep["scope"]["not_collected"]                                    # 이제 선언 값을 수집한다


# ---- 호스트 승인 문서(사용자가 경로를 명시하는 읽기 전용 입력) ---------------------------------------------------------

APPROVALS = {
    "version": 1,
    "socket": {"path": "~/.openclaw/exec-approvals.sock", "token": "FAKESOCKETTOKEN-abc123"},
    "defaults": {"security": "deny", "ask": "on-miss", "askFallback": "deny", "autoAllowSkills": False},
    "agents": {"main": {
        "security": "allowlist", "ask": "on-miss", "askFallback": "deny", "autoAllowSkills": True,
        "allowlist": [
            {"id": "B0C8C0B3-2C2D-4F8A-9A3C-5A4B3C2D1E0F", "pattern": "~/path/to/**/bin/rg", "argPattern": "sha256:argv:FAKEARGHASH", "source": "allow-always",
             "lastUsedAt": 1737150000000, "lastResolvedPath": "/Users/u/bin/rg", "lastUsedCommand": "rg --token FAKECMDSECRET999"},
            {"pattern": "~/path/to/**/bin/git"},
        ],
        "mcpTools": [{"server": "project-docs", "tool": "publish_page", "source": "allow-always", "addedAt": 1737150000000}],
    }},
    "futureKey": {"x": 1},
}


def run_with_approvals(tmp_path, doc, config=None, raw=None):
    cfg = tmp_path / "openclaw.json"
    cfg.write_text(json.dumps(config or {"tools": {"profile": "full"}}), encoding="utf-8")
    f = tmp_path / "exec-approvals.json"
    f.write_text(raw if raw is not None else json.dumps(doc), encoding="utf-8")
    return build_report(collect_permission_auth(cfg, exec_approvals_path=f))


def test_exec_approvals_document_is_collected_as_declarations_with_source_and_scope(tmp_path):
    rep = run_with_approvals(tmp_path, APPROVALS)
    items = [i for i in rep["items"] if i["category"].startswith("exec_approvals")]
    d = {i["config_path"]: i for i in items}
    assert d["exec-approvals.defaults.security"]["value"] == "deny" and d["exec-approvals.defaults.security"]["applies_to"] == {"scope": "exec_host_defaults"}
    assert d["exec-approvals.defaults.askFallback"]["value"] == "deny" and d["exec-approvals.defaults.autoAllowSkills"]["value"] is False
    assert d["exec-approvals.agents.main.security"]["applies_to"] == {"scope": "agent", "agent_key": "main"} and d["exec-approvals.agents.main.autoAllowSkills"]["value"] is True
    assert all(i["origin"] == "operator_provided_file" and "include_origin" not in i for i in items)
    assert rep["source"]["exec_approvals_file"]["provided_by"] == "operator_selected_file" and rep["source"]["exec_approvals_file"]["version"] == 1
    assert rep["collection"]["status"] == "complete"


def test_allowlist_entries_and_mcp_tools_are_listed_without_arguments_or_history(tmp_path):
    rep = run_with_approvals(tmp_path, APPROVALS)
    allow = [i for i in rep["items"] if i["category"] == "exec_approvals_allowlist_entry"]
    assert [(a["pattern"], a["source"], a["arg_pattern_declared"]) for a in allow] == [("~/path/to/**/bin/rg", "allow-always", True), ("~/path/to/**/bin/git", None, False)]
    assert all(a["applies_to"] == {"scope": "agent", "agent_key": "main"} for a in allow)
    mcp = [i for i in rep["items"] if i["category"] == "exec_approvals_mcp_tool"]
    assert [(m["server"], m["tool"], m["source"]) for m in mcp] == [("project-docs", "publish_page", "allow-always")]


def test_approvals_secrets_arguments_hashes_and_history_are_not_stored(tmp_path):
    rep = run_with_approvals(tmp_path, APPROVALS)
    text = json.dumps(rep, ensure_ascii=False)
    for forbidden in ("FAKESOCKETTOKEN", "FAKEARGHASH", "FAKECMDSECRET999", "sha256:argv", "lastResolvedPath", "/Users/u/bin/rg", "B0C8C0B3"):
        assert forbidden not in text
    sock = [i for i in rep["items"] if i["config_path"] == "exec-approvals.socket.token"][0]
    assert sock["credential"] == {"kind": "literal_withheld"}
    assert "futureKey" in rep["source"]["exec_approvals_file"]["unknown_keys"] and "x" not in rep["source"]["exec_approvals_file"]["unknown_keys"]


def test_approvals_file_problems_are_reported_and_other_items_survive(tmp_path):
    for raw, code in (("{ not json", "json5_syntax_error"), ("[1]", "exec_approvals_not_object")):
        rep = run_with_approvals(tmp_path, None, raw=raw)
        assert any(i["code"].startswith(("exec_approvals", "json5")) for i in rep["issues"]) and rep["collection"]["status"] == "partial"
        assert any(i["config_path"] == "tools.profile" for i in rep["items"])
    bad = dict(APPROVALS, defaults={"security": 5, "ask": "magic"})
    rep = run_with_approvals(tmp_path, bad)
    d = {i["config_path"]: i for i in rep["items"]}
    assert d["exec-approvals.defaults.security"]["value_kind"] == "invalid_type" and d["exec-approvals.defaults.ask"]["value_documented"] is False
    assert rep["collection"]["status"] == "partial"


def test_approvals_file_is_never_discovered_automatically(tmp_path):
    rep = run(tmp_path, {"tools": {"profile": "full"}})
    assert "exec_approvals_file" not in rep["source"] and not [i for i in rep["items"] if i["category"].startswith("exec_approvals")]


def test_cli_requires_an_explicit_path_and_rejects_the_output_collision(tmp_path):
    cfg = tmp_path / "openclaw.json"
    cfg.write_text(json.dumps({"tools": {"profile": "full"}}), encoding="utf-8")
    f = tmp_path / "exec-approvals.json"
    f.write_text(json.dumps(APPROVALS), encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    ok = subprocess.run([sys.executable, "-m", "asset_scanner.permission_auth", "--config", str(cfg), "--exec-approvals-file", str(f), "--output", str(tmp_path / "o.json")],
                        cwd=SCANNER_ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    assert ok.returncode == 0, ok.stderr
    same = subprocess.run([sys.executable, "-m", "asset_scanner.permission_auth", "--config", str(cfg), "--exec-approvals-file", str(f), "--output", str(f)],
                          cwd=SCANNER_ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    assert same.returncode == 4 and json.loads(f.read_text(encoding="utf-8"))["version"] == 1       # 입력 승인 문서를 덮어쓰지 않는다



# ---- 파일·네트워크 범위 선언(2026-11-18 후속: 전체 문서 검색으로 확인된 키) -----------------------------------------------
# 근거: `docs/cli/claws.md`·`docs/cli/policy/rules.md`(tools.fs.workspaceOnly와 에이전트별 tools.fs 재정의), `docs/gateway/config-browser-ui-desktop.md`
# (browser.ssrfPolicy.*), `docs/gateway/config-automation.md`(cron.webhookSsrfPolicy.*, cron.webhookToken). 선언 값만 수집한다.

SCOPE_CONFIG = {
    "tools": {"fs": {"workspaceOnly": True}},
    "agents": {"entries": {"main": {"tools": {"fs": {"workspaceOnly": False}}}}},
    "browser": {"ssrfPolicy": {"dangerouslyAllowPrivateNetwork": False, "allowPrivateNetwork": True,
                               "allowedHostnames": ["*.example.com", "localhost"], "blockedHostnames": ["tracker.example.com"]}},
    "cron": {"webhookToken": "FAKEWEBHOOKTOKEN789", "webhookSsrfPolicy": {"allowedHostnames": ["127.0.0.1"], "dangerouslyAllowPrivateNetwork": False}},
}


def test_file_and_network_scope_declarations_are_collected_with_scope_and_doc_basis(tmp_path):
    items = by_path(run(tmp_path, SCOPE_CONFIG))
    fs = items["tools.fs.workspaceOnly"]
    assert fs["category"] == "file_policy" and fs["value"] is True and fs["applies_to"] == {"scope": "global_tools"} and "claws.md" in fs["doc_basis"]
    assert items["agents.entries.main.tools.fs.workspaceOnly"]["value"] is False and items["agents.entries.main.tools.fs.workspaceOnly"]["applies_to"] == {"scope": "agent", "agent_key": "main"}
    b = items["browser.ssrfPolicy.allowedHostnames"]
    assert b["category"] == "network_policy" and b["value"] == ["*.example.com", "localhost"] and b["applies_to"] == {"scope": "browser"}
    assert items["browser.ssrfPolicy.blockedHostnames"]["value"] == ["tracker.example.com"]
    assert items["browser.ssrfPolicy.dangerouslyAllowPrivateNetwork"]["value"] is False and items["browser.ssrfPolicy.allowPrivateNetwork"]["value"] is True   # 레거시 별칭도 선언 그대로
    w = items["cron.webhookSsrfPolicy.allowedHostnames"]
    assert w["value"] == ["127.0.0.1"] and w["applies_to"] == {"scope": "cron_webhook"} and items["cron.webhookSsrfPolicy.dangerouslyAllowPrivateNetwork"]["value"] is False


def test_webhook_token_is_an_authentication_declaration_without_the_value(tmp_path):
    rep = run(tmp_path, SCOPE_CONFIG)
    t = by_path(rep)["cron.webhookToken"]
    assert t["category"] == "webhook_auth" and t["credential"] == {"kind": "literal_withheld"}
    assert "FAKEWEBHOOKTOKEN789" not in json.dumps(rep)


def test_scope_keys_with_wrong_types_are_reported_and_absent_ones_are_not_invented(tmp_path):
    rep = run(tmp_path, {"tools": {"fs": {"workspaceOnly": "yes"}}, "browser": {"ssrfPolicy": {"allowedHostnames": "example.com"}}})
    items = by_path(rep)
    assert items["tools.fs.workspaceOnly"]["value_kind"] == "invalid_type" and items["browser.ssrfPolicy.allowedHostnames"]["value_kind"] == "invalid_type"
    assert sum(1 for i in rep["issues"] if i["code"] == "field_type_invalid") == 2 and rep["collection"]["status"] == "partial"
    assert run(tmp_path, {"tools": {"fs": {}}, "browser": {"ssrfPolicy": {}}, "cron": {}})["items"] == []


def test_source_backed_network_and_workspace_declarations_are_no_longer_listed_as_missing(tmp_path):
    nc = run(tmp_path, {"tools": {"profile": "full"}})["scope"]["not_collected"]
    assert "channel_and_provider_network_policies" not in nc and "tools_exec_applyPatch_workspaceOnly_type_not_stated" not in nc
    assert "effective_policy" in nc
    assert "file_and_network_allowlists_not_documented" not in nc                 # 잘못된 사유(문서에 키가 있음)라 제거했다
