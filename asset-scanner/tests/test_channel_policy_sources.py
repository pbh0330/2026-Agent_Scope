"""가상 채널 정책 선언. 실제 채널·계정 접속이나 실효 권한 판정은 하지 않는다."""
import json

import pytest

from asset_scanner.permission_auth import build_report, collect_permission_auth


def scan(tmp_path, value, **kwargs):
    path = tmp_path / "channels.json5"
    path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
    return build_report(collect_permission_auth(path, **kwargs))


@pytest.mark.parametrize("channel", ["telegram", "discord", "slack", "signal", "whatsapp", "matrix"])
def test_root_and_account_policy_are_separate_declarations(tmp_path, channel):
    report = scan(tmp_path, {"channels": {channel: {
        "dmPolicy": "pairing", "groupPolicy": "allowlist", "allowFrom": ["FAKE_ACTOR", 31],
        "accounts": {"FAKE_ACCOUNT": {"dmPolicy": "disabled", "groupAllowFrom": []}}}}})
    assert len(report["items"]) == 5
    assert report["collection"]["status"] == "complete"
    assert {i["value"] for i in report["items"] if i["value_kind"] == "string"} == {"pairing", "allowlist", "disabled"}
    assert any(i.get("count") == 2 and i["values_withheld"] for i in report["items"])
    assert all(i["applies_to"]["channel"] == channel for i in report["items"])
    assert "FAKE_ACTOR" not in json.dumps(report) and "FAKE_ACCOUNT" not in json.dumps(report)
    masked = [i for i in report["items"] if "<account-key>" in i["config_path"]]
    assert len(masked) == 2 and all(i["original_config_pointer_available"] is False for i in masked)


@pytest.mark.parametrize("path", [
    ("groups", "FAKE_GROUP"), ("groups", "FAKE_GROUP", "topics", "FAKE_TOPIC"),
    ("dms", "FAKE_PEER"), ("guilds", "FAKE_GUILD", "channels", "FAKE_CHANNEL"),
    ("channels", "FAKE_CHANNEL"), ("rooms", "FAKE_ROOM"),
])
def test_nested_policy_preserves_tools_and_withholds_target_keys(tmp_path, path):
    node = {"requireMention": False, "enabled": True, "tools": {"allow": ["read"], "alsoAllow": [], "deny": ["exec"]},
            "toolsBySender": {"id:FAKE_PERSON": {"deny": ["browser"]}}}
    for part in reversed(path):
        node = {part: node}
    report = scan(tmp_path, {"channels": {"telegram": node}})
    assert len(report["items"]) == 6
    assert any(i.get("value") == ["exec"] for i in report["items"])
    assert all(i["config_path_redacted"] and not i["original_config_pointer_available"] for i in report["items"])
    assert "FAKE" not in json.dumps(report)


def test_nested_account_groups_and_private_lists_only_store_counts(tmp_path):
    report = scan(tmp_path, {"channels": {"discord": {"accounts": {"FAKE_ACCOUNT": {
        "guilds": {"FAKE_GUILD": {"users": ["FAKE_USER"], "roles": ["FAKE_ROLE"],
                    "channels": {"FAKE_CHANNEL": {"users": [], "skills": ["greeter"]}}}}}}}}})
    assert len(report["items"]) == 4 and "FAKE" not in json.dumps(report)
    assert any(i.get("value") == ["greeter"] for i in report["items"])


@pytest.mark.parametrize("bad", [True, None, {}, [True], [None], [float("inf")]])
def test_bad_actor_lists_are_partial_and_do_not_drop_other_policy(tmp_path, bad):
    report = scan(tmp_path, {"channels": {"slack": {"allowFrom": bad, "dmPolicy": "disabled"}}})
    assert report["collection"]["status"] == "partial"
    assert any(i["value_kind"] == "invalid_type" for i in report["items"])
    assert any(i.get("value") == "disabled" for i in report["items"])


def test_includes_keep_origin_and_no_default_is_invented(tmp_path):
    (tmp_path / "policy.json").write_text('{"dmPolicy":"allowlist"}', encoding="utf-8")
    report = scan(tmp_path, {"channels": {"telegram": {"$include": "policy.json"}}}, resolve_includes=True)
    assert len(report["items"]) == 1 and report["items"][0]["include_origin"]["file"] == "policy.json"
    assert scan(tmp_path, {"channels": {"telegram": {}}})["items"] == []
    assert "effective_policy" in report["scope"]["not_collected"]


def test_duplicate_private_target_paths_are_not_echoed(tmp_path):
    report = scan(tmp_path, '{channels:{telegram:{groups:{"FAKE_PRIVATE_GROUP":{enabled:true,enabled:false}}}}}')
    assert report["collection"]["status"] == "partial"
    assert any(i["code"] == "duplicate_key" for i in report["issues"])
    assert "FAKE_PRIVATE_GROUP" not in json.dumps(report)


def test_common_defaults_and_unrecognized_extension_fields_are_not_expanded(tmp_path):
    report = scan(tmp_path, {"channels": {"defaults": {"groupPolicy": "disabled"},
        "custom": {"ownerSecrets": {"token": "FAKE_SECRET"}, "groupPolicy": "vendor-policy"}}})
    assert len(report["items"]) == 2
    assert any(i["applies_to"]["scope"] == "channel_defaults" for i in report["items"])
    assert any(i.get("value") == "vendor-policy" and not i["value_documented"] for i in report["items"])
    assert "FAKE_SECRET" not in json.dumps(report)


@pytest.mark.parametrize("node", [[], None, "FAKE_BAD_CONTAINER", True])
def test_wrong_policy_parent_is_not_a_successful_empty_result(tmp_path, node):
    report = scan(tmp_path, {"channels": {"telegram": {"accounts": node}}})
    assert report["collection"]["status"] == "partial"
    assert any(i["code"] == "channel_policy_container_invalid" for i in report["issues"])
    assert "FAKE_BAD_CONTAINER" not in json.dumps(report)
