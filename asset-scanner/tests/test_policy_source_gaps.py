"""공식 2026.9.6 스키마에 있는 선언 원천의 누락 회귀. 모두 가상 설정이다."""
import json

import pytest

from asset_scanner.permission_auth import build_report, collect_permission_auth


def scan(tmp_path, data, **kwargs):
    p = tmp_path / "openclaw.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return build_report(collect_permission_auth(p, **kwargs))


def index(report):
    return {i["config_path"]: i for i in report["items"]}


def test_explicit_per_agent_overrides_are_preserved_separately_from_defaults(tmp_path):
    cfg = {"agents": {"defaults": {"sandbox": {"docker": {"network": "none"}}},
                      "entries": {"writer": {"sandbox": {"docker": {"network": "bridge", "user": "1001:1001", "binds": ["/source:/workspace:ro"]},
                                                                     "browser": {"enabled": False}, "ssh": {"strictHostKeyChecking": True}},
                                                "tools": {"exec": {"host": "sandbox", "applyPatch": {"workspaceOnly": False, "enabled": True}}}}}}}
    rep = scan(tmp_path, cfg)
    got = index(rep)
    for suffix, value in [("docker.network", "bridge"), ("docker.user", "1001:1001"), ("browser.enabled", False), ("ssh.strictHostKeyChecking", True)]:
        item = got["agents.entries.writer.sandbox." + suffix]
        assert item["value"] == value and item["applies_to"] == {"scope": "agent", "agent_key": "writer"}
    assert got["agents.defaults.sandbox.docker.network"]["value"] == "none"
    assert got["agents.entries.writer.tools.exec.applyPatch.workspaceOnly"]["value"] is False
    assert got["agents.entries.writer.tools.exec.host"]["value"] == "sandbox"
    assert rep["collection"]["status"] == "complete"
    assert "effective_policy" in rep["scope"]["not_collected"]


def test_private_network_declarations_keep_channel_and_provider_scope(tmp_path):
    rep = scan(tmp_path, {"channels": {"tlon": {"network": {"dangerouslyAllowPrivateNetwork": False}}},
                          "models": {"providers": {"local": {"request": {"allowPrivateNetwork": True}},
                                                   "cloud": {"request": {"allowPrivateNetwork": False}}}},
                          "tools": {"exec": {"applyPatch": {"workspaceOnly": True}}}})
    got = index(rep)
    assert got["channels.tlon.network.dangerouslyAllowPrivateNetwork"]["value"] is False
    assert got["channels.tlon.network.dangerouslyAllowPrivateNetwork"]["applies_to"] == {"scope": "channel", "channel": "tlon"}
    assert got["models.providers.local.request.allowPrivateNetwork"]["applies_to"] == {"scope": "model_provider", "provider": "local"}
    assert got["models.providers.cloud.request.allowPrivateNetwork"]["value"] is False
    assert got["tools.exec.applyPatch.workspaceOnly"]["value"] is True
    assert len(got) == 4


@pytest.mark.parametrize("bad", ["yes", {}, [True], 1, None])
def test_new_boolean_fields_reject_wrong_types_without_copying_values(tmp_path, bad):
    rep = scan(tmp_path, {"channels": {"tlon": {"network": {"dangerouslyAllowPrivateNetwork": bad}}},
                          "models": {"providers": {"p": {"request": {"allowPrivateNetwork": bad}}}},
                          "tools": {"exec": {"applyPatch": {"workspaceOnly": bad}}}})
    assert len(rep["items"]) == 3
    assert all(i["value_kind"] == "invalid_type" and "value" not in i for i in rep["items"])
    assert rep["collection"]["status"] == "partial"


def test_missing_new_sections_do_not_invent_defaults_or_provider_access(tmp_path):
    rep = scan(tmp_path, {"channels": {"tlon": {"network": {}}, "unknown": {"network": {"dangerouslyAllowPrivateNetwork": True}}},
                          "models": {"providers": {"p": {"request": {}}}}})
    assert rep["items"] == []
    assert rep["collection"]["outcome"] == "no_declared_items"


def test_per_agent_credential_literals_are_withheld(tmp_path):
    rep = scan(tmp_path, {"agents": {"entries": {"main": {"sandbox": {"ssh": {"identityData": "FAKE_PRIVATE_KEY_LITERAL"}}}}}})
    assert rep["items"][0]["credential"] == {"kind": "literal_withheld"}
    assert "FAKE_PRIVATE_KEY_LITERAL" not in json.dumps(rep)


def test_new_declarations_keep_include_origin(tmp_path):
    (tmp_path / "policy.json").write_text(json.dumps({"models": {"providers": {"p": {"request": {"allowPrivateNetwork": True}}}}}), encoding="utf-8")
    rep = scan(tmp_path, {"$include": "policy.json"}, resolve_includes=True)
    assert rep["items"][0]["include_origin"]["file"] == "policy.json"
    assert rep["items"][0]["config_pointer"] == "/models/providers/p/request/allowPrivateNetwork"
