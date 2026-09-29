"""수집 결과의 구조·상태 구분 테스트."""

from pathlib import Path

from asset_scanner.collector import collect
from conftest import EXAMPLES


def by_key(result: dict) -> dict:
    return {s["registration_key"]: s for s in result["servers"]}


# ---- 정상 수집 ------------------------------------------------------------------

def test_two_different_servers_are_each_collected():
    result = collect(EXAMPLES / "two-servers.json5")
    col = result["collection"]
    assert col["status"] == "complete"
    assert col["outcome"] == "servers_found"
    assert col["server_count"] == 2

    servers = by_key(result)
    assert set(servers) == {"sample-files", "sample-remote"}

    local = servers["sample-files"]
    assert local["declaration_path"] == "mcp.servers.sample-files"
    assert local["declaration_pointer"] == "/mcp/servers/sample-files"
    assert local["source_path"] == str((EXAMPLES / "two-servers.json5").resolve())
    assert local["declared"] == {
        "command": "npx",
        "args": ["-y", "@example/sample-files-mcp", "./workspace"],
        "cwd": "./sandbox",
    }

    remote = servers["sample-remote"]
    assert remote["declared"] == {
        "url": "https://mcp.example.test/mcp",
        "transport": "streamable-http",
        "enabled": False,
    }
    assert remote["other_declared_keys"] == ["requestTimeoutMs"]


def test_disabled_server_is_kept_as_registered_asset():
    servers = by_key(collect(EXAMPLES / "two-servers.json5"))
    assert servers["sample-remote"]["declared"]["enabled"] is False
    assert servers["sample-remote"]["collection_status"] == "complete"


def test_missing_values_are_not_guessed():
    """설정에 없는 enabled·transport를 기본값으로 채우지 않는다."""
    local = by_key(collect(EXAMPLES / "two-servers.json5"))["sample-files"]
    assert "enabled" not in local["declared"]
    assert "transport" not in local["declared"]


def test_server_names_and_count_are_not_hardcoded(write_config):
    cfg = write_config("""{
      mcp: { servers: {
        fs: { command: "a" },
        "zeta.server": { command: "b" },
        "한글-서버": { url: "https://x.example.test/mcp" },
      } }
    }""")
    result = collect(cfg)
    assert result["collection"]["server_count"] == 3
    paths = [s["declaration_path"] for s in result["servers"]]
    assert paths == ['mcp.servers.fs', 'mcp.servers["zeta.server"]', 'mcp.servers["한글-서버"]']


def test_json5_comments_and_trailing_commas(write_config):
    cfg = write_config("""
    // 줄 주석
    { /* 블록 주석 */ mcp: { servers: { a: { command: "x", args: ["1", "2",], }, }, }, }
    """)
    result = collect(cfg)
    assert result["collection"]["status"] == "complete"
    assert result["servers"][0]["declared"]["args"] == ["1", "2"]


def test_plain_json_is_supported(write_config):
    cfg = write_config('{"mcp": {"servers": {"a": {"command": "x"}}}}', name="openclaw.json")
    assert collect(cfg)["collection"]["server_count"] == 1


# ---- 빈 목록 / 등록 영역 없음 / 잘못된 구조 / 파싱 실패 / 파일 없음 구분 ---------

def test_empty_registry_is_complete_with_zero_servers(write_config):
    col = collect(write_config("{ mcp: { servers: {} } }"))["collection"]
    assert (col["status"], col["outcome"], col["server_count"]) == ("complete", "empty_registry", 0)


def test_registry_absent_when_mcp_missing(write_config):
    col = collect(write_config("{ gateway: { port: 1 } }"))["collection"]
    assert col["outcome"] == "registry_absent"
    assert col["server_count"] is None  # 0개와 구분
    assert col["reasons"][0]["field_path"] == "mcp"


def test_registry_absent_when_servers_missing(write_config):
    col = collect(write_config("{ mcp: { other: true } }"))["collection"]
    assert col["outcome"] == "registry_absent"
    assert col["reasons"][0]["field_path"] == "mcp.servers"


def test_invalid_structures_fail_instead_of_empty_list(write_config):
    cases = {
        "[1, 2]": "root_not_object",
        "{ mcp: [] }": "mcp_not_object",
        "{ mcp: { servers: [] } }": "servers_not_object",
        "{ mcp: { servers: null } }": "servers_not_object",
        '{ mcp: { servers: "fs" } }': "servers_not_object",
    }
    for text, code in cases.items():
        result = collect(write_config(text))
        col = result["collection"]
        assert col["status"] == "failed", text
        assert col["outcome"] == "invalid_structure", text
        assert col["reasons"][0]["code"] == code, text
        assert col["server_count"] is None
        assert result["servers"] == []


def test_broken_json5_is_parse_error_with_position_only(write_config):
    cfg = write_config('{\n  mcp: { servers: { a: { command: "FAKE-BROKEN-SECRET" args: [] } } }\n}')
    col = collect(cfg)["collection"]
    assert col["status"] == "failed"
    assert col["outcome"] == "parse_error"
    reason = col["reasons"][0]
    assert reason["code"] == "json5_syntax_error"
    assert reason["line"] == 2
    assert "column" in reason


def test_missing_file(tmp_path):
    col = collect(tmp_path / "nope.json5")["collection"]
    assert (col["status"], col["outcome"]) == ("failed", "file_not_found")


def test_directory_instead_of_file(tmp_path):
    col = collect(tmp_path)["collection"]
    assert (col["status"], col["outcome"]) == ("failed", "read_error")


def test_non_utf8_file(tmp_path):
    path = tmp_path / "bad.json5"
    path.write_bytes(b'{ mcp: { servers: { a: { command: "\xff\xfe" } } } }')
    col = collect(path)["collection"]
    assert (col["status"], col["outcome"]) == ("failed", "read_error")
    assert col["reasons"][0]["code"] == "decode_failed"


# ---- 서버별 문제 (파일 전체 실패와 구분) ----------------------------------------

def test_per_server_problems_do_not_fail_whole_file(write_config):
    cfg = write_config("""{ mcp: { servers: {
      good: { command: "x" },
      broken: "not-an-object",
      typed: { command: 42, enabled: "yes", args: ["ok", 3] },
      empty: {},
    } } }""")
    result = collect(cfg)
    col = result["collection"]
    assert col["status"] == "partial"
    assert col["outcome"] == "servers_found"
    assert col["server_count"] == 4

    s = by_key(result)
    assert s["good"]["collection_status"] == "complete"
    assert s["broken"]["collection_status"] == "invalid"
    assert s["broken"]["issues"][0]["code"] == "entry_not_object"

    typed = s["typed"]
    assert typed["collection_status"] == "partial"
    assert typed["declared"] == {}  # 잘못된 타입의 값은 저장하지 않음
    assert {i["field_path"] for i in typed["issues"] if i["code"] == "field_type_invalid"} == {
        "mcp.servers.typed.command", "mcp.servers.typed.enabled", "mcp.servers.typed.args",
    }

    assert [i["code"] for i in s["empty"]["issues"]] == ["no_connection_target_declared"]
    assert set(col["reasons"][0]["registration_keys"]) == {"broken", "typed"}


def test_duplicate_registration_key_is_reported(write_config):
    cfg = write_config('{ mcp: { servers: { a: { command: "1" }, a: { command: "2" } } } }')
    col = collect(cfg)["collection"]
    assert col["status"] == "partial"
    assert col["reasons"][0]["code"] == "duplicate_registration_key"


# ---- 미해석 include·참조 --------------------------------------------------------

def test_include_and_env_refs_make_collection_partial():
    result = collect(EXAMPLES / "include-and-refs.json5")
    col = result["collection"]
    assert col["status"] == "partial"
    codes = [r["code"] for r in col["reasons"]]
    assert "unresolved_include" in codes and "server_entries_incomplete" in codes

    # mcp.servers 위치의 include만 등록 영역에 영향 → 기록. agents 위치 include는 제외.
    assert [(u["kind"], u["field_path"], u["targets"]) for u in col["unresolved"]] == [
        ("include", "mcp.servers", ["./more-servers.json5"]),
    ]
    # "$include"는 서버 등록키로 오인하지 않는다.
    assert [s["registration_key"] for s in result["servers"]] == ["ref-server"]

    server = result["servers"][0]
    assert server["collection_status"] == "partial"
    assert {u["name"] for u in server["unresolved"] if u["kind"] == "env_var"} == {
        "SAMPLE_MCP_BIN", "SAMPLE_ROOT_DIR",
    }
    assert server["declared"]["command"] == "${SAMPLE_MCP_BIN}"  # 펼치지 않고 참조 그대로


def test_root_include_without_mcp_is_not_reported_complete(write_config):
    col = collect(write_config('{ $include: "./base.json5" }'))["collection"]
    assert col["outcome"] == "registry_absent"
    assert col["status"] == "partial"


def test_include_inside_server_entry(write_config):
    cfg = write_config('{ mcp: { servers: { a: { command: "x", env: { $include: "./env.json5" } } } } }')
    server = collect(cfg)["servers"][0]
    assert server["collection_status"] == "partial"
    assert server["unresolved"][0] == {
        "kind": "include", "field_path": "mcp.servers.a.env", "targets": ["./env.json5"],
        "reason": "이번 단계는 $include 파일을 읽지 않습니다.",
    }


def test_escaped_env_syntax_is_literal(write_config):
    cfg = write_config('{ mcp: { servers: { a: { command: "echo", args: ["$${NOT_A_REF}"] } } } }')
    server = collect(cfg)["servers"][0]
    assert server["collection_status"] == "complete"
    assert server["unresolved"] == []


def test_env_values_are_not_expanded(write_config, monkeypatch):
    monkeypatch.setenv("SAMPLE_EXPANDED", "FAKE-REAL-ENV-VALUE")
    cfg = write_config('{ mcp: { servers: { a: { command: "${SAMPLE_EXPANDED}" } } } }')
    server = collect(cfg)["servers"][0]
    assert server["declared"]["command"] == "${SAMPLE_EXPANDED}"
    assert "FAKE-REAL-ENV-VALUE" not in repr(server)
