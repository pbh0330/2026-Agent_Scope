"""MCP 서버 항목의 문서화된 선언 값(타임아웃·병렬 호출 힌트·codex 투영 제어) 수집 테스트 (가상 설정).

근거: OpenClaw 2026.9.6 `docs/gateway/config-extensions.md`. 값은 선언일 뿐 실제 승인 동작·노출·호출 가능이 아니며,
기존 `declared`·`other_declared_keys` 계약은 바꾸지 않는다(새 값은 `declared_extra`).
"""

import json

from asset_scanner.collector import collect

REG = ("mcp", "servers")


def one(tmp_path, entry):
    p = tmp_path / "c.json5"
    p.write_text(json.dumps({"mcp": {"servers": {"s": entry}}}), encoding="utf-8")
    return collect(p, REG)["servers"][0]


def test_declared_values_are_kept_without_inventing_defaults(tmp_path):
    s = one(tmp_path, {"command": "x", "requestTimeoutMs": 20000, "connectionTimeoutMs": 5000, "supportsParallelToolCalls": True,
                       "codex": {"agents": ["main"], "defaultToolsApprovalMode": "approve"}})
    assert s["declared_extra"] == {"requestTimeoutMs": 20000, "connectionTimeoutMs": 5000, "supportsParallelToolCalls": True,
                                   "codex": {"agents": ["main"], "defaultToolsApprovalMode": "approve", "defaultToolsApprovalMode_documented_value": True,
                                             "other_keys": [], "scope_note": s["declared_extra"]["codex"]["scope_note"]}}
    assert "Codex app-server" in s["declared_extra"]["codex"]["scope_note"]
    assert s["collection_status"] == "complete"
    none = one(tmp_path, {"command": "x"})
    assert "declared_extra" not in none                                       # 선언이 없으면 값을 만들지 않는다


def test_existing_contract_is_unchanged_declared_and_other_keys(tmp_path):
    s = one(tmp_path, {"command": "x", "requestTimeoutMs": 5, "codex": {"agents": ["a"]}})
    assert "requestTimeoutMs" not in s["declared"] and "codex" not in s["declared"]
    assert s["other_declared_keys"] == ["requestTimeoutMs", "codex"]
    assert s["declared_keys"] == ["command", "requestTimeoutMs", "codex"]


def test_unknown_approval_value_is_kept_but_marked_undocumented(tmp_path):
    s = one(tmp_path, {"command": "x", "codex": {"defaultToolsApprovalMode": "magic", "extra": 1}})
    cx = s["declared_extra"]["codex"]
    assert cx["defaultToolsApprovalMode"] == "magic" and cx["defaultToolsApprovalMode_documented_value"] is False
    assert cx["other_keys"] == ["extra"]


def test_wrong_types_become_issues_and_partial_without_storing_values(tmp_path):
    s = one(tmp_path, {"command": "x", "requestTimeoutMs": "fast", "connectionTimeoutMs": True, "supportsParallelToolCalls": "yes",
                       "codex": {"agents": "main", "defaultToolsApprovalMode": 3}})
    assert "declared_extra" not in s or s["declared_extra"].get("codex", {}).get("agents") is None
    fields = {i["field_path"] for i in s["issues"] if i["code"] == "field_type_invalid"}
    assert {"mcp.servers.s.requestTimeoutMs", "mcp.servers.s.connectionTimeoutMs", "mcp.servers.s.supportsParallelToolCalls",
            "mcp.servers.s.codex.agents", "mcp.servers.s.codex.defaultToolsApprovalMode"} <= fields
    assert s["collection_status"] == "partial"
    assert "fast" not in json.dumps(s.get("declared_extra", {}))


def test_codex_agents_with_secret_shape_are_redacted(tmp_path):
    s = one(tmp_path, {"command": "x", "codex": {"agents": ["ghp_FAKEAGENTTOKEN1234567890abcdefgh"]}})
    assert "ghp_FAKEAGENTTOKEN" not in json.dumps(s)
