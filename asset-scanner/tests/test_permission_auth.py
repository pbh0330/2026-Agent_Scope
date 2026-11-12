"""Permission/Auth 선언 수집(permission_auth) 테스트.

설정은 모두 테스트가 만든 **가상 자료**다. 실제 OpenClaw를 실행하거나 서버에 접속하지 않으며 `FAKE` 표식이 붙은 값은 전부
가짜 비밀값이다.
"""

import hashlib
import json
import os
import subprocess
import sys

import pytest

from asset_scanner.collector import SUPPORTED_REGISTRY_PATHS, collect
from asset_scanner.permission_auth import build_report, collect_permission_auth
from conftest import SCANNER_ROOT

TOKEN = "FAKEGATEWAYTOKENVALUE"
PHONE = "+15555550123"

CONFIG = """{
  tools: {
    profile: "coding", allow: ["group:fs", "web_*"], deny: ["browser", "canvas"],
    byProvider: { anthropic: { profile: "minimal" }, "openai/gpt-5.4": { allow: ["group:fs"] } },
    toolsBySender: { "e164:%(phone)s": { deny: ["exec"] }, "*": { deny: ["write"] }, "id:guest-user-id": { alsoAllow: ["group:fs"] } },
    elevated: { enabled: true, allowFrom: { whatsapp: ["%(phone)s"], discord: ["1234567890123", "987654321098765432"] } },
  },
  agents: { defaults: { skills: ["image-lab"] },
            entries: { main: { tools: { deny: ["exec"], elevated: { enabled: false } }, skills: ["peekaboo"] }, helper: { tools: { allow: ["read"] } } } },
  gateway: {
    auth: { mode: "token", token: "%(token)s", allowTailscale: true, trustedProxy: { userHeader: "x-forwarded-user" } },
    trustedProxies: ["10.0.0.5"],
    remote: { token: { source: "env", provider: "default", id: "REMOTE_GW_TOKEN" }, password: "${REMOTE_GW_PASSWORD}" },
    nodes: { commands: { allow: ["canvas.navigate"], deny: ["system.run"] }, pluginTools: { enabled: false }, allowSkills: false,
             pairing: { autoApproveLocal: true } },
  },
  nodeHost: { skills: { enabled: false } },
  plugins: { enabled: true, allow: ["voice-call"], deny: ["bad"] },
  skills: { allowBundled: ["image-lab"] },
  security: { installPolicy: { enabled: true, targets: ["skill", "plugin"],
              exec: { command: "/usr/local/bin/policy", args: ["--json", "--token", "FAKEINSTALLTOKEN"], timeoutMs: 10000,
                      env: { POLICY_MODE: "FAKEPOLICYENVVALUE" }, passEnv: ["PATH"], trustedDirs: ["/usr/local/bin"] } } },
  mcp: { servers: { remote: { url: "https://mcp.test/mcp", auth: "oauth", oauth: { identity: "per-requester", scope: "docs.read" },
                              clientCert: "/path/FAKE.crt", clientKey: "/path/FAKE.key" },
                    files: { command: "x" } } },
}""" % {"phone": PHONE, "token": TOKEN}


def write_cfg(tmp_path, text=CONFIG, name="openclaw.json5"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def run(tmp_path, text=CONFIG):
    return build_report(collect_permission_auth(write_cfg(tmp_path, text)))


def item(rep, path):
    found = [i for i in rep["items"] if i["config_path"] == path]
    assert len(found) == 1, (path, [i["config_path"] for i in rep["items"]][:60])
    return found[0]


def dump(x):
    return json.dumps(x, ensure_ascii=False)


# ---- 항목 보존과 적용 대상 -------------------------------------------------------------------------

def test_policy_items_keep_location_target_and_documentation_basis(tmp_path):
    rep = run(tmp_path)
    assert rep["collection"]["outcome"] == "items_read" and rep["scope"]["aggregation"] == "none"
    g = item(rep, "tools.deny")
    assert g["value"] == ["browser", "canvas"] and g["applies_to"] == {"scope": "global_tools"} and g["category"] == "tool_policy"
    assert g["config_pointer"] == "/tools/deny" and g["origin"] == "config_declared" and "tool-policy.md" in g["doc_basis"]
    assert item(rep, "tools.allow")["value"] == ["group:fs", "web_*"]                                  # 순서·패턴 그대로
    assert item(rep, 'tools.byProvider.anthropic.profile')["applies_to"] == {"scope": "provider", "provider": "anthropic"}
    assert item(rep, 'tools.byProvider["openai/gpt-5.4"].allow')["applies_to"]["provider"] == "openai/gpt-5.4"
    agent = item(rep, "agents.entries.main.tools.deny")
    assert agent["applies_to"] == {"scope": "agent", "agent_key": "main"} and agent["value"] == ["exec"]
    assert item(rep, "agents.entries.helper.tools.allow")["applies_to"]["agent_key"] == "helper"
    assert item(rep, "agents.defaults.skills")["applies_to"] == {"scope": "agent_defaults"} and item(rep, "agents.entries.main.skills")["value"] == ["peekaboo"]


def test_sources_are_never_merged_or_resolved_into_an_effective_policy(tmp_path):
    rep = run(tmp_path)
    denies = [i for i in rep["items"] if i["config_path"].endswith(".deny") and i["category"] == "tool_policy"]
    assert len(denies) >= 3                                                       # 전역·Agent·발신자 그룹의 deny가 각각 따로 존재
    text = dump(rep["items"]).lower()       # 수집 항목에는 계산된 정책이 없다 (계산하지 않은 영역은 scope.not_collected에 명시)
    for word in ("effective", "resolved_policy", "final_decision", "allowed_tools", "denied_tools"):
        assert word not in text
    assert "effective_policy" in rep["scope"]["not_collected"]
    # 같은 deny 항목이 서로 다른 적용 대상으로 따로 남아 있다
    assert {i["applies_to"]["scope"] for i in denies} == {"global_tools", "agent", "sender_group"}
    node_deny = [i for i in rep["items"] if i["config_path"] == "gateway.nodes.commands.deny"]
    assert len(node_deny) == 1 and node_deny[0]["category"] == "node_policy" and node_deny[0]["applies_to"]["scope"] == "gateway_nodes"


def test_sender_keys_and_allow_from_values_are_personal_data_and_never_stored(tmp_path):
    rep = run(tmp_path)
    out = dump(rep)
    assert PHONE not in out and "987654321098765432" not in out and "guest-user-id" not in out
    sender = [i for i in rep["items"] if i["applies_to"].get("scope") == "sender_group"]
    assert {i["applies_to"]["sender_key_kind"] for i in sender} == {"e164", "any", "id"}
    assert all(i["config_path"].startswith("tools.toolsBySender[") and "<sender-key:" in i["config_path"] for i in sender)
    star = [i for i in sender if i["applies_to"]["sender_key_kind"] == "any"][0]
    assert star["applies_to"]["sender_key"] == "*" and star["value"] == ["write"]
    af = item(rep, "tools.elevated.allowFrom.discord")
    assert af == {**af, "value_kind": "count_only", "count": 2, "values_withheld": True} and "value" not in af
    assert item(rep, "tools.elevated.enabled")["value"] is True


# ---- 인증정보 --------------------------------------------------------------------------------------

def test_credentials_keep_kind_and_reference_names_but_no_value_length_or_hash(tmp_path):
    rep = run(tmp_path)
    tok = item(rep, "gateway.auth.token")
    assert tok["value_kind"] == "credential" and tok["credential"] == {"kind": "literal_withheld"} and "value" not in tok
    out = dump(rep)
    assert TOKEN not in out
    for h in (hashlib.sha256, hashlib.sha1, hashlib.md5, hashlib.sha512):
        assert h(TOKEN.encode()).hexdigest() not in out
    assert "len" not in dump(tok).lower().replace("literal_withheld", "")        # 길이도 남기지 않는다
    ref = item(rep, "gateway.remote.token")
    assert ref["credential"]["kind"] == "secret_ref" and ref["credential"]["ref"] == {"source": "env", "provider": "default", "id": "REMOTE_GW_TOKEN"}
    env = item(rep, "gateway.remote.password")
    assert env["credential"] == {"kind": "env_ref", "ref_names": ["REMOTE_GW_PASSWORD"]} and env["category"] == "gateway_remote_client_auth"
    kinds = {(u["kind"], u.get("name") or u.get("id")) for u in rep["unresolved"]}
    assert ("secret_ref", "REMOTE_GW_TOKEN") in kinds and ("env_var", "REMOTE_GW_PASSWORD") in kinds
    assert rep["collection"]["status"] == "partial"                              # 해석하지 않은 참조가 있음


def test_gateway_auth_mode_and_flags(tmp_path):
    rep = run(tmp_path)
    mode = item(rep, "gateway.auth.mode")
    assert mode["value"] == "token" and mode["value_documented"] is True and mode["documented_values"] == ["none", "token", "password", "trusted-proxy"]
    assert item(rep, "gateway.auth.allowTailscale")["value"] is True
    assert item(rep, "gateway.auth.trustedProxy.userHeader")["value"] == "x-forwarded-user"
    assert item(rep, "gateway.trustedProxies")["value"] == ["10.0.0.5"]
    odd = run(tmp_path, '{ gateway: { auth: { mode: "magic" } } }')
    m = item(odd, "gateway.auth.mode")
    assert m["value"] == "magic" and m["value_documented"] is False             # 문서에 없는 값도 그대로 보존하고 판정하지 않는다


def test_invalid_secret_ref_in_a_credential_position_is_reported_without_values(tmp_path):
    rep = run(tmp_path, '{ gateway: { auth: { token: { source: "git", provider: 5, id: "FAKEBADREF" } } } }')
    tok = item(rep, "gateway.auth.token")
    assert tok["credential"]["kind"] == "invalid_secret_ref" and "FAKEBADREF" not in dump(rep)
    assert any(i["code"] == "field_type_invalid" for i in rep["issues"]) and rep["collection"]["status"] == "partial"


# ---- Node·플러그인·설치 정책 ---------------------------------------------------------------------------

def test_node_plugin_skill_and_install_policy_items(tmp_path):
    rep = run(tmp_path)
    assert item(rep, "gateway.nodes.commands.deny")["value"] == ["system.run"] and item(rep, "gateway.nodes.commands.allow")["applies_to"] == {"scope": "gateway_nodes"}
    assert item(rep, "gateway.nodes.pluginTools.enabled")["value"] is False and item(rep, "gateway.nodes.allowSkills")["value"] is False
    assert item(rep, "gateway.nodes.pairing.autoApproveLocal")["value"] is True
    assert item(rep, "nodeHost.skills.enabled")["applies_to"] == {"scope": "node_host"}
    assert item(rep, "plugins.allow")["value"] == ["voice-call"] and item(rep, "plugins.deny")["category"] == "plugin_policy"
    assert item(rep, "skills.allowBundled")["value"] == ["image-lab"]
    ip = item(rep, "security.installPolicy.exec.command")
    assert ip["value"] == "/usr/local/bin/policy" and ip["category"] == "install_policy"
    args = item(rep, "security.installPolicy.exec.args")["value"]
    assert args[:2] == ["--json", "--token"] and args[2] == "<redacted>"
    env = item(rep, "security.installPolicy.exec.env")
    assert env["names"] == ["POLICY_MODE"] and env["values_withheld"] is True
    out = dump(rep)
    assert "FAKEINSTALLTOKEN" not in out and "FAKEPOLICYENVVALUE" not in out


def test_mcp_server_auth_items_use_the_same_declaration_paths_as_the_config_scan(tmp_path):
    cfg = write_cfg(tmp_path)
    rep = build_report(collect_permission_auth(cfg))
    scan = collect(cfg, SUPPORTED_REGISTRY_PATHS["mcp.servers"])
    declared = {s["registration_key"]: s["declaration_path"] for s in scan["servers"]}
    auth = item(rep, "mcp.servers.remote.auth")
    assert auth["value"] == "oauth" and auth["category"] == "mcp_server_auth"
    a = auth["applies_to"]
    assert a["scope"] == "mcp_server" and a["registry_path"] == "mcp.servers" and a["registration_key"] == "remote"
    assert a["declaration_path"] == declared["remote"] and a["link_basis"] == "same_declaration_path_as_config_scan"
    assert item(rep, "mcp.servers.remote.oauth.identity")["value"] == "per-requester"
    assert item(rep, "mcp.servers.remote.oauth.scope")["value"] == "docs.read"
    cert = item(rep, "mcp.servers.remote.clientCert")
    assert cert["value_kind"] == "path_declared" and "value" not in cert and "FAKE.crt" not in dump(rep)
    assert not [i for i in rep["items"] if i["config_path"].startswith("mcp.servers.files.")]       # 선언 없는 서버는 항목 없음(만들지 않음)


def test_node_host_registry_is_read_too_and_secret_registration_keys_stay_masked(tmp_path):
    tok = "ghp_FAKEREGKEYTOKEN1234567890abcdefgh"
    text = '{ nodeHost: { mcp: { servers: { nodesrv: { url: "https://n.test", auth: "oauth" }, "%s": { auth: "oauth" } } } } }' % tok
    rep = run(tmp_path, text)
    a = item(rep, "nodeHost.mcp.servers.nodesrv.auth")["applies_to"]
    assert a["registry_path"] == "nodeHost.mcp.servers" and a["declaration_path"] == "nodeHost.mcp.servers.nodesrv"
    masked = [i for i in rep["items"] if i["applies_to"].get("registration_key_redacted")]
    assert masked and masked[0]["applies_to"]["registration_key"] == "<redacted-key-1>"
    assert "FAKEREGKEYTOKEN" not in dump(rep)


# ---- 오류와 경계 -------------------------------------------------------------------------------------

def test_wrong_types_are_reported_and_the_rest_is_collected(tmp_path):
    rep = run(tmp_path, '{ tools: { deny: "browser", allow: ["a", 3], profile: 5, elevated: { enabled: "yes" } }, gateway: { auth: { mode: 5, allowTailscale: true } } }')
    bad = {i["field_path"] for i in rep["issues"] if i["code"] == "field_type_invalid"}
    assert bad == {"tools.deny", "tools.allow", "tools.profile", "tools.elevated.enabled", "gateway.auth.mode"}
    for p in bad:
        it = item(rep, p)
        assert it["value_kind"] == "invalid_type" and "value" not in it
    assert item(rep, "gateway.auth.allowTailscale")["value"] is True and rep["collection"]["status"] == "partial"
    assert "browser" not in dump([i for i in rep["items"] if i["config_path"] == "tools.deny"])        # 잘못된 자료형의 원문은 저장하지 않음


def test_no_declared_items_is_not_reported_as_having_no_policy(tmp_path):
    rep = run(tmp_path, '{ channels: { discord: {} } }')
    assert rep["collection"]["status"] == "complete" and rep["collection"]["outcome"] == "no_declared_items" and rep["collection"]["item_count"] == 0
    assert "선언이 없다는 것은" in rep["scope"]["note"]


def test_duplicate_keys_and_includes_only_matter_in_the_areas_this_module_reads(tmp_path):
    rep = run(tmp_path, '{ tools: { deny: ["a"], deny: ["b"] }, channels: { x: 1, x: 2, "$include": "other.json5" } }')
    assert [i["field_path"] for i in rep["issues"] if i["code"] == "duplicate_key"] == ["tools.deny"]
    assert item(rep, "tools.deny")["value"] == ["b"] and rep["unresolved"] == [] and rep["collection"]["status"] == "partial"
    rep = run(tmp_path, '{ tools: { "$include": "tools-policy.json5" } }')
    assert rep["unresolved"] and rep["unresolved"][0]["kind"] == "include" and rep["collection"]["status"] == "partial"


def test_env_reference_inside_a_list_is_recorded_as_unresolved_with_default_masked(tmp_path):
    rep = run(tmp_path, '{ tools: { deny: ["${DENY_TOOL}", "${X:-FAKEDEFAULT}"] } }')
    assert item(rep, "tools.deny")["value"] == ["${DENY_TOOL}", "${X:-<redacted>}"] and "FAKEDEFAULT" not in dump(rep)
    assert {u["name"] for u in rep["unresolved"] if u["kind"] == "env_var"} == {"DENY_TOOL", "X"}


@pytest.mark.parametrize("content", ["{ nope", "[1]", ""])
def test_unreadable_config_fails_without_traceback(tmp_path, content):
    rep = run(tmp_path, content)
    assert rep["collection"]["status"] == "failed" and rep["items"] == [] and "Traceback" not in dump(rep)
    assert build_report(collect_permission_auth(tmp_path / "missing.json5"))["collection"]["status"] == "failed"


def test_not_collected_areas_are_stated(tmp_path):
    rep = run(tmp_path)
    assert {"effective_policy", "secret_values", "runtime_approvals_and_pairing_state"} <= set(rep["scope"]["not_collected"])
    assert rep["source"]["evidence_type"] == "static_file"


# ---- CLI ---------------------------------------------------------------------------------------------

def run_cli(*args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-m", "asset_scanner.permission_auth", *map(str, args)], cwd=SCANNER_ROOT, env=env,
                          capture_output=True, text=True, encoding="utf-8")


def test_cli_exit_codes_and_no_leaks(tmp_path):
    cfg = write_cfg(tmp_path)
    out = tmp_path / "o.json"
    proc = run_cli("--config", cfg, "--output", out)
    assert proc.returncode == 1 and "읽기 전용" in proc.stdout                      # 미해석 참조가 있어 부분 수집
    saved = out.read_text(encoding="utf-8")
    for marker in (TOKEN, PHONE, "FAKEINSTALLTOKEN", "FAKEPOLICYENVVALUE", "FAKE.crt"):
        assert marker not in proc.stdout + proc.stderr + saved
    clean = write_cfg(tmp_path, '{ tools: { deny: ["browser"] }, gateway: { auth: { mode: "none" } } }', "clean.json5")
    assert run_cli("--config", clean, "--output", tmp_path / "c.json").returncode == 0
    assert run_cli("--config", tmp_path / "missing.json5", "--output", tmp_path / "m.json").returncode == 3
    assert run_cli("--output", tmp_path / "x.json").returncode == 2
    assert run_cli("--config", clean, "--output", clean).returncode == 4 and "browser" in clean.read_text(encoding="utf-8")
