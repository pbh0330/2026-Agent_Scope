"""scanner-review-v2 검토: 가림용 이름(<redacted-key-N>)과 실제 등록키의 충돌 회귀 테스트.

가짜 토큰 모양 등록키에는 모두 "FAKE" 표식이 있다.
"""

import json

from asset_scanner.collector import collect
from conftest import run_cli

MARKER = "FAKE"
SECRET_KEY = "ghp_FAKEREGISTRATION12345"


def servers_config(*entries: tuple[str, str]) -> str:
    """(등록키, command) 순서를 그대로 유지한 mcp.servers 설정 문자열."""
    body = ", ".join(f"{json.dumps(k)}: {{\"command\": {json.dumps(c)}}}" for k, c in entries)
    return '{"mcp": {"servers": {' + body + "}}}"


def commands(result: dict) -> dict:
    return {s["declared"]["command"]: s for s in result["servers"]}


def assert_no_secret(result: dict) -> None:
    assert MARKER not in json.dumps(result, ensure_ascii=False)


def assert_distinct_identifiers(result: dict) -> None:
    servers = result["servers"]
    for field in ("registration_key", "declaration_path", "declaration_pointer"):
        values = [s[field] for s in servers]
        assert len(set(values)) == len(values), field


def test_masked_key_does_not_overwrite_plain_placeholder_like_key(write_config):
    result = collect(write_config(servers_config((SECRET_KEY, "sample-a"), ("<redacted-key-1>", "sample-b"))))
    col = result["collection"]
    assert (col["status"], col["server_count"]) == ("complete", 2)
    assert col["reasons"] == []  # 실제 중복이 아니므로 중복 경고 없음
    by_cmd = commands(result)
    assert set(by_cmd) == {"sample-a", "sample-b"}
    # 일반 키는 그대로, 가린 키는 다른 자리표시자
    assert by_cmd["sample-b"]["registration_key"] == "<redacted-key-1>"
    assert "registration_key_redacted" not in by_cmd["sample-b"]
    assert by_cmd["sample-a"]["registration_key_redacted"] is True
    assert by_cmd["sample-a"]["registration_key"] != "<redacted-key-1>"
    for s in result["servers"]:
        assert s["source_path"] == str(result["source_path"])
    assert_distinct_identifiers(result)
    assert_no_secret(result)


def test_reversed_input_order(write_config):
    result = collect(write_config(servers_config(("<redacted-key-1>", "sample-b"), (SECRET_KEY, "sample-a"))))
    col = result["collection"]
    assert (col["status"], col["server_count"]) == ("complete", 2)
    by_cmd = commands(result)
    assert set(by_cmd) == {"sample-a", "sample-b"}
    assert by_cmd["sample-b"]["registration_key"] == "<redacted-key-1>"
    assert by_cmd["sample-a"]["registration_key_redacted"] is True
    assert_distinct_identifiers(result)
    assert_no_secret(result)


def test_many_masked_and_placeholder_like_keys(write_config):
    entries = [
        ("ghp_FAKEAAAAAAAAAAAAAAAA1", "masked-1"),
        ("<redacted-key-1>", "plain-1"),
        ("sk-FAKEBBBBBBBBBBBBBBBB2", "masked-2"),
        ("<redacted-key-2>", "plain-2"),
        ("xoxb-FAKECCCCCCCCCCCCCC3", "masked-3"),
        ("<redacted-key-4>", "plain-4"),
        ("ok", "plain-ok"),
    ]
    result = collect(write_config(servers_config(*entries)))
    col = result["collection"]
    assert (col["status"], col["server_count"]) == ("complete", 7)
    by_cmd = commands(result)
    assert set(by_cmd) == {c for _, c in entries}
    for key, cmd in entries:
        server = by_cmd[cmd]
        if cmd.startswith("plain"):
            assert server["registration_key"] == key
            assert "registration_key_redacted" not in server
        else:
            assert server["registration_key_redacted"] is True
    assert len(col["key_redactions"]) == 3
    assert_distinct_identifiers(result)
    assert_no_secret(result)


def test_real_duplicate_of_masked_key_is_still_a_duplicate(write_config):
    result = collect(write_config(servers_config(
        (SECRET_KEY, "first"), ("<redacted-key-1>", "plain"), (SECRET_KEY, "second"))))
    col = result["collection"]
    assert col["status"] == "partial"
    assert col["server_count"] == 2
    dup = [r for r in col["reasons"] if r["code"] == "duplicate_registration_key"]
    assert len(dup) == 1
    masked = [s for s in result["servers"] if s.get("registration_key_redacted")]
    assert len(masked) == 1
    assert masked[0]["declared"]["command"] == "second"  # 중복 시 마지막 값 (기존 규칙)
    assert dup[0]["field_path"] == masked[0]["declaration_path"]
    assert commands(result)["plain"]["registration_key"] == "<redacted-key-1>"
    assert_no_secret(result)


def test_real_duplicate_of_plain_key_is_unchanged(write_config):
    result = collect(write_config(servers_config(("a", "1"), ("a", "2"))))
    col = result["collection"]
    assert (col["status"], col["server_count"]) == ("partial", 1)
    assert col["reasons"][0]["code"] == "duplicate_registration_key"


def test_collision_inside_nested_objects(write_config):
    cfg = write_config(json.dumps({"mcp": {"servers": {"s": {
        "command": "x",
        "env": {SECRET_KEY: "v1", "<redacted-key-1>": "v2"},
    }}}}))
    server = collect(cfg)["servers"][0]
    names = server["credentials"]["env"]["names"]
    assert len(names) == 2 and len(set(names)) == 2
    assert "<redacted-key-1>" in names
    assert server["issues"] == []
    assert MARKER not in json.dumps(server)


def test_cli_output_has_both_servers_and_no_secret(tmp_path):
    cfg = tmp_path / "collision.json5"
    cfg.write_text(servers_config((SECRET_KEY, "sample-a"), ("<redacted-key-1>", "sample-b")), encoding="utf-8")
    out = tmp_path / "out.json"
    proc = run_cli(cfg, out)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert {s["declared"]["command"] for s in report["servers"]} == {"sample-a", "sample-b"}
    assert proc.stdout.count("mcp.servers[") == 2
    for text in (out.read_text(encoding="utf-8"), proc.stdout, proc.stderr):
        assert MARKER not in text
