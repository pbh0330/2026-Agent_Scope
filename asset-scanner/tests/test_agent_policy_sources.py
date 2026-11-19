"""AgentToolsSchema가 공유하는 권한 원천. 모든 설정·ID·인증값은 가상이다."""
import json

import pytest

from asset_scanner.permission_auth import build_report, collect_permission_auth


def scan(tmp_path, value, **kwargs):
    p = tmp_path / "openclaw.json5"
    p.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
    return build_report(collect_permission_auth(p, **kwargs))


def index(report):
    return {item["config_path"]: item for item in report["items"]}


def test_agent_provider_profile_and_all_lists_keep_agent_and_provider_scope(tmp_path):
    rep = scan(tmp_path, {"agents": {"entries": {"writer": {"tools": {"byProvider": {
        "local/model": {"profile": "coding", "allow": ["read"], "alsoAllow": ["browser"], "deny": ["exec"]},
        "cloud": {"deny": []}}}}, "reviewer": {"tools": {"byProvider": {"local/model": {"deny": ["write"]}}}}}}})
    got = index(rep)
    own = [i for i in rep["items"] if i["applies_to"].get("agent_key") == "writer" and i["applies_to"].get("provider") == "local/model"]
    assert len(own) == 4
    assert all(i["applies_to"]["scope"] == "agent_provider" for i in own)
    assert {i["config_pointer"].rsplit("/", 1)[1]: i["value"] for i in own} == {
        "profile": "coding", "allow": ["read"], "alsoAllow": ["browser"], "deny": ["exec"]}
    assert own[0]["config_pointer"].startswith("/agents/entries/writer/tools/byProvider/local~1model/")
    assert any(i["value"] == [] and i["applies_to"]["provider"] == "cloud" for i in rep["items"])
    assert any(i["value"] == ["write"] and i["applies_to"]["agent_key"] == "reviewer" for i in rep["items"])
    assert rep["collection"]["status"] == "complete"
    assert "effective_policy" in rep["scope"]["not_collected"]


def test_agent_sender_policy_withholds_actor_and_flags_unavailable_original_path(tmp_path):
    actor = "id:FAKE_ACTOR_021"
    rep = scan(tmp_path, {"agents": {"entries": {"writer": {"tools": {"toolsBySender": {
        actor: {"allow": ["read"], "alsoAllow": ["browser"], "deny": ["exec"]}}}}}}})
    assert len(rep["items"]) == 3
    assert all(i["applies_to"] == {"scope": "agent_sender_group", "agent_key": "writer", "sender_key_kind": "id", "sender_key": "<withheld>"} for i in rep["items"])
    assert all(i["config_path_redacted"] is True and i["original_config_pointer_available"] is False for i in rep["items"])
    assert actor not in json.dumps(rep)
    assert all("<sender-key:id>" in i["config_pointer"] for i in rep["items"])


def test_global_sender_path_is_also_explicitly_marked_as_not_an_original_identifier(tmp_path):
    rep = scan(tmp_path, {"tools": {"toolsBySender": {"id:FAKE_ACTOR": {"deny": ["exec"]}}}})
    assert rep["items"][0]["config_path_redacted"] is True
    assert rep["items"][0]["original_config_pointer_available"] is False
    assert "FAKE_ACTOR" not in json.dumps(rep)


def test_agent_elevated_allow_from_uses_provider_scope_and_withholds_values(tmp_path):
    rep = scan(tmp_path, {"agents": {"entries": {"writer": {"tools": {"elevated": {
        "allowFrom": {"chat": ["FAKE_ACTOR", 42, 2.5]}}}}}}})
    assert len(rep["items"]) == 1
    item = rep["items"][0]
    assert item["value_kind"] == "count_only" and item["count"] == 3 and item["values_withheld"] is True
    assert item["applies_to"] == {"scope": "agent_elevated_sender_allowlist", "agent_key": "writer", "provider": "chat"}
    assert "FAKE_ACTOR" not in json.dumps(rep)


@pytest.mark.parametrize("bad", [True, False, {}, None])
def test_actor_allow_from_wrong_member_types_are_partial_without_value_copy(tmp_path, bad):
    rep = scan(tmp_path, {"agents": {"entries": {"writer": {"tools": {"elevated": {"allowFrom": {"chat": [bad]}}}}}}})
    assert rep["collection"]["status"] == "partial" and rep["items"][0]["value_kind"] == "invalid_type"
    assert any(i["code"] == "field_type_invalid" for i in rep["issues"])


@pytest.mark.parametrize("bad", [True, False, {}, None])
def test_global_actor_allowlist_type_matches_the_same_schema(tmp_path, bad):
    rep = scan(tmp_path, {"tools": {"elevated": {"allowFrom": {"chat": [bad]}}}})
    assert rep["collection"]["status"] == "partial"
    assert rep["items"][0]["value_kind"] == "invalid_type"


def test_agent_and_global_sandbox_tool_lists_preserve_every_declared_list(tmp_path):
    cfg = {"agents": {"entries": {"writer": {"tools": {"sandbox": {"tools": {
        "allow": ["read"], "alsoAllow": ["edit"], "deny": ["exec"], "profile": "not-in-this-schema"}}}}}},
           "tools": {"sandbox": {"tools": {"alsoAllow": ["browser"]}}}}
    rep = scan(tmp_path, cfg)
    assert len(rep["items"]) == 4
    got = index(rep)
    assert got["agents.entries.writer.tools.sandbox.tools.allow"]["value"] == ["read"]
    assert got["agents.entries.writer.tools.sandbox.tools.alsoAllow"]["value"] == ["edit"]
    assert got["agents.entries.writer.tools.sandbox.tools.deny"]["value"] == ["exec"]
    assert got["tools.sandbox.tools.alsoAllow"]["value"] == ["browser"]
    assert all(not k.endswith(".profile") for k in got)


@pytest.mark.parametrize("bad", ["read", {"token": "FAKE_BAD_VALUE"}, [1], [None]])
def test_agent_provider_bad_lists_report_type_without_losing_normal_policy(tmp_path, bad):
    rep = scan(tmp_path, {"agents": {"entries": {"writer": {"tools": {"byProvider": {"p": {"allow": bad, "deny": ["exec"]}}}}}}})
    assert rep["collection"]["status"] == "partial"
    assert any(i.get("value_kind") == "invalid_type" for i in rep["items"])
    assert any(i.get("value") == ["exec"] for i in rep["items"])
    assert "FAKE_BAD_VALUE" not in json.dumps(rep)


def test_agent_provider_include_preserves_origin_and_empty_config_invents_nothing(tmp_path):
    (tmp_path / "policy.json").write_text('{"tools":{"byProvider":{"p":{"deny":["exec"]}}}}')
    rep = scan(tmp_path, {"agents": {"entries": {"writer": {"$include": "policy.json"}}}}, resolve_includes=True)
    assert rep["items"][0]["include_origin"]["file"] == "policy.json"
    assert scan(tmp_path, {"agents": {"entries": {"writer": {"tools": {}}}}})["items"] == []


def test_agent_duplicate_and_sender_records_are_not_merged(tmp_path):
    rep = scan(tmp_path, '{agents:{entries:{a:{tools:{byProvider:{p:{deny:["read"],deny:["exec"]}},toolsBySender:{"id:FAKE_ONE":{allow:["read"]},"id:FAKE_TWO":{deny:["write"]}}}}}}}')
    assert rep["collection"]["status"] == "partial"
    assert any(i["code"] == "duplicate_key" for i in rep["issues"])
    assert len(rep["items"]) == 3
    assert len({i["ref"] for i in rep["items"]}) == 3
    assert "FAKE_ONE" not in json.dumps(rep) and "FAKE_TWO" not in json.dumps(rep)


def test_credential_in_provider_key_cannot_leak_through_paths_or_scope(tmp_path):
    key = "https://user:FAKE_PROVIDER_PASSWORD@example.test/x"
    rep = scan(tmp_path, {"agents": {"entries": {"writer": {"tools": {"byProvider": {key: {"deny": ["exec"]}}}}}}})
    assert len(rep["items"]) == 1
    assert "FAKE_PROVIDER_PASSWORD" not in json.dumps(rep)
    assert rep["items"][0]["config_path_redacted"] is True


def test_masked_agent_key_is_explicitly_not_available_as_an_original_pointer(tmp_path):
    key = "ghp_FAKEAGENTKEY12345678901234567890"
    rep = scan(tmp_path, {"agents": {"entries": {key: {"tools": {"deny": ["exec"]}}}}})
    assert len(rep["items"]) == 1 and key not in json.dumps(rep)
    assert rep["items"][0]["config_path_redacted"] is True
    assert rep["items"][0]["original_config_pointer_available"] is False


def test_provider_uri_duplicate_diagnostic_does_not_echo_credentials(tmp_path):
    key = "https://user:FAKE_DIAGNOSTIC_PASSWORD@example.test/x"
    data = '{agents:{entries:{a:{tools:{byProvider:{' + json.dumps(key) + ':{deny:["read"],deny:["exec"]}}}}}}}'
    rep = scan(tmp_path, data)
    assert rep["collection"]["status"] == "partial"
    assert any(i["code"] == "duplicate_key" for i in rep["issues"])
    assert "FAKE_DIAGNOSTIC_PASSWORD" not in json.dumps(rep)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_actor_numbers_are_invalid_not_counted_as_valid_declarations(tmp_path, value):
    rep = scan(tmp_path, {"agents": {"entries": {"writer": {"tools": {"elevated": {"allowFrom": {"chat": [value]}}}}}}})
    assert rep["collection"]["status"] == "partial" and rep["items"][0]["value_kind"] == "invalid_type"


def test_redacted_mcp_registration_key_is_flagged_in_the_target_reference(tmp_path):
    key = "https://user:FAKE_MCP_KEY_PASSWORD@example.test/x"
    rep = scan(tmp_path, {"mcp": {"servers": {key: {"auth": "none"}}}})
    item = rep["items"][0]
    assert "FAKE_MCP_KEY_PASSWORD" not in json.dumps(rep)
    assert item["applies_to"]["registration_key_redacted"] is True
    assert item["original_config_pointer_available"] is False


def test_global_subagent_tool_lists_are_an_explicit_distinct_source(tmp_path):
    rep = scan(tmp_path, {"tools": {"subagents": {"tools": {
        "allow": ["read"], "alsoAllow": ["edit"], "deny": ["exec"], "profile": "outside-schema"}}}})
    assert len(rep["items"]) == 3
    assert all(i["applies_to"]["scope"] == "global_subagent_tools" for i in rep["items"])
    assert {i["config_path"].rsplit(".", 1)[1] for i in rep["items"]} == {"allow", "alsoAllow", "deny"}


def test_agent_to_agent_and_session_visibility_are_literal_declarations(tmp_path):
    rep = scan(tmp_path, {"tools": {"agentToAgent": {"enabled": False, "allow": ["worker-*", "reviewer"]}, "sessions": {"visibility": "tree"}}})
    got = index(rep)
    assert got["tools.agentToAgent.enabled"]["value"] is False
    assert got["tools.agentToAgent.allow"]["value"] == ["worker-*", "reviewer"]
    assert got["tools.agentToAgent.allow"]["applies_to"]["scope"] == "agent_to_agent"
    visibility = got["tools.sessions.visibility"]
    assert visibility["value"] == "tree" and visibility["value_documented"] is True
    assert visibility["applies_to"]["scope"] == "session_visibility"
    assert "effective_policy" in rep["scope"]["not_collected"]


@pytest.mark.parametrize("visibility", ["self", "tree", "agent", "all"])
def test_each_documented_visibility_value_is_preserved(tmp_path, visibility):
    rep = scan(tmp_path, {"tools": {"sessions": {"visibility": visibility}}})
    assert rep["items"][0]["value"] == visibility and rep["items"][0]["value_documented"] is True


def test_message_cross_context_flags_preserve_global_and_agent_declarations(tmp_path):
    cfg = {"tools": {"message": {"crossContext": {"allowWithinProvider": True, "allowAcrossProviders": False}}},
           "agents": {"entries": {"writer": {"tools": {"message": {"crossContext": {
               "allowWithinProvider": False, "allowAcrossProviders": True}}}}}}}
    rep = scan(tmp_path, cfg)
    got = index(rep)
    assert len(rep["items"]) == 4
    assert got["tools.message.crossContext.allowAcrossProviders"]["value"] is False
    item = got["agents.entries.writer.tools.message.crossContext.allowAcrossProviders"]
    assert item["value"] is True and item["applies_to"] == {"scope": "agent_message_cross_context", "agent_key": "writer"}


def test_new_global_policy_types_are_checked_without_inventing_missing_values(tmp_path):
    rep = scan(tmp_path, {"tools": {"agentToAgent": {"enabled": "yes", "allow": 1},
                                  "sessions": {"visibility": False}, "message": {"crossContext": {"allowAcrossProviders": "no"}}}})
    assert len(rep["items"]) == 4 and all(i["value_kind"] == "invalid_type" for i in rep["items"])
    assert rep["collection"]["status"] == "partial"
    assert scan(tmp_path, {"tools": {"agentToAgent": {}, "sessions": {}, "subagents": {"tools": {}}}})["items"] == []
