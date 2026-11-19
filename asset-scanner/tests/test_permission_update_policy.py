"""업데이트 정책 선언(update.*, nodeHost.autoUpdate) 수집 테스트 (가상 설정).

근거: OpenClaw 2026.9.6 `docs/install/updating/automatic-updates.md`. 선언 값만 기록하며 실제 업데이트 동작·환경변수
(OPENCLAW_NO_AUTO_UPDATE) 적용 결과는 계산하지 않는다.
"""

import json

from asset_scanner.permission_auth import build_report, collect_permission_auth


def run(tmp_path, cfg):
    p = tmp_path / "c.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return build_report(collect_permission_auth(p))


def test_update_policy_declarations_are_collected_with_their_source_path(tmp_path):
    rep = run(tmp_path, {"update": {"channel": "stable", "auto": {"enabled": True}, "checkOnStart": False}, "nodeHost": {"autoUpdate": {"enabled": False}}})
    items = {i["config_path"]: i for i in rep["items"] if i["category"] == "update_policy"}
    assert set(items) == {"update.channel", "update.auto.enabled", "update.checkOnStart", "nodeHost.autoUpdate.enabled"}
    assert items["update.channel"]["value"] == "stable" and items["update.auto.enabled"]["value"] is True
    assert items["update.checkOnStart"]["applies_to"] == {"scope": "gateway_update"}
    assert items["nodeHost.autoUpdate.enabled"]["applies_to"] == {"scope": "node_host"} and items["nodeHost.autoUpdate.enabled"]["value"] is False
    assert rep["collection"]["status"] == "complete"


def test_missing_update_keys_are_not_invented_and_wrong_types_are_reported(tmp_path):
    assert run(tmp_path, {"update": {}})["collection"]["outcome"] == "no_declared_items"
    rep = run(tmp_path, {"update": {"auto": {"enabled": "yes"}}})
    assert any(i["code"] == "field_type_invalid" for i in rep["issues"]) and rep["collection"]["status"] == "partial"
