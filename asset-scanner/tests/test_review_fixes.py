"""1차 검토(scanner-step1-review-and-fixes.md) R1~R4 회귀 테스트.

각 테스트는 검토 문서의 재현 입력을 그대로 사용한다. 가짜 비밀값에는 모두 "FAKE" 표식이 있다.
"""

import json

import pytest

from asset_scanner import redaction
from asset_scanner.collector import collect
from asset_scanner.redaction import REDACTED, Redactor
from conftest import EXAMPLES, run_cli


def classify_secret_ref(value):
    return redaction.classify_secret_ref(value)

MARKER = "FAKE"
ARGS_PATH = "mcp.servers.demo.args"


def by_key(result):
    return {s["registration_key"]: s for s in result["servers"]}


# ---- R1. 비밀값 가림 누락 ------------------------------------------------------

@pytest.mark.parametrize("args", [
    ["--endpoint=https://user:FAKE_EQ_PASSWORD@api.example.test/mcp?token=FAKE_EQ_QUERY#FAKE_EQ_FRAGMENT"],
    ["-H", "X-Api-Key: FAKE_HEADER_VALUE"],
    ["-c", "sample-server --token FAKE_SHELL_TOKEN"],
])
def test_r1_review_inputs_are_redacted(args):
    r = Redactor()
    out = r.sanitize_args(args, ARGS_PATH)
    assert MARKER not in json.dumps(out)
    assert r.redactions  # 가림 위치·사유가 남는다


def test_r1_option_equals_url_keeps_useful_parts():
    out = Redactor().sanitize_args(
        ["--endpoint=https://user:FAKE_P@api.example.test/mcp?token=FAKE_Q#FAKE_F"], ARGS_PATH)
    assert out == [f"--endpoint=https://{REDACTED}@api.example.test/mcp?token={REDACTED}#{REDACTED}"]


def test_r1_header_forms():
    r = Redactor()
    out = r.sanitize_args([
        "-H", "X-Api-Key: FAKE_1",
        "--header", "Authorization: Token FAKE_2",
        "--header=Cookie: FAKE_3",
        "-H", "Content-Type: application/json",
    ], ARGS_PATH)
    assert out == [
        "-H", f"X-Api-Key: {REDACTED}",
        "--header", f"Authorization: {REDACTED}",
        f"--header=Cookie: {REDACTED}",
        "-H", "Content-Type: application/json",   # 인증과 무관한 헤더는 유지
    ]


def test_r1_shell_command_string_is_withheld_not_parsed():
    r = Redactor()
    out = r.sanitize_args(["-c", "sample-server --token FAKE_SHELL_TOKEN"], ARGS_PATH)
    assert out == ["-c", REDACTED]
    assert {"field_path": f"{ARGS_PATH}[1]", "reason": "shell_command_string_withheld"} in r.redactions


def test_r1_compound_arg_with_embedded_secret_is_withheld():
    out = Redactor().sanitize_args(["run --api-key FAKE_X now", "hello world"], ARGS_PATH)
    assert out == [REDACTED, "hello world"]


def test_r1_useful_values_are_preserved():
    args = ["--port", "8080", "-y", "@modelcontextprotocol/server-filesystem", "C:\\work\\data",
            "--endpoint=https://api.example.test/mcp", "./workspace"]
    r = Redactor()
    assert r.sanitize_args(args, ARGS_PATH) == args
    assert r.redactions == []


def test_r1_include_target_default_is_redacted(write_config):
    cfg = write_config('{ "$include": "${CONFIG_FILE:-FAKE_INCLUDE_SECRET}",'
                       ' "mcp": {"servers": {"ok": {"command": "example"}}} }')
    result = collect(cfg)
    assert MARKER not in json.dumps(result, ensure_ascii=False)
    inc = result["collection"]["unresolved"][0]
    assert inc["kind"] == "include" and inc["targets"] == [f"${{CONFIG_FILE:-{REDACTED}}}"]


def test_r1_secret_looking_registration_keys_are_masked_but_not_merged(write_config):
    cfg = write_config('{ mcp: { servers: {'
                       ' "ghp_FAKEREGISTRATION12345": { command: "a" },'
                       ' "ghp_FAKEREGISTRATION67890": { command: "b" },'
                       ' ok: { command: "c" } } } }')
    result = collect(cfg)
    text = json.dumps(result, ensure_ascii=False)
    assert MARKER not in text
    servers = result["servers"]
    assert result["collection"]["server_count"] == 3
    keys = [s["registration_key"] for s in servers]
    assert len(set(keys)) == 3  # 가린 키끼리 합쳐지지 않음
    assert keys[2] == "ok"
    masked = [s for s in servers if s.get("registration_key_redacted")]
    assert [s["declared"]["command"] for s in masked] == ["a", "b"]
    for s in masked:
        assert {"field_path": s["declaration_path"], "reason": "key_looks_like_secret"} in s["redactions"]


def test_r1_full_cli_run_leaks_nothing(tmp_path):
    out = tmp_path / "r1.json"
    proc = run_cli(EXAMPLES / "review-r1-secrets.json5", out)
    assert proc.returncode == 1, proc.stderr  # 미해석 include가 있어 partial
    for text in (out.read_text(encoding="utf-8"), proc.stdout, proc.stderr):
        assert MARKER not in text
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["collection"]["server_count"] == 4
    demo = by_key(report)["demo"]["declared"]["args"]
    assert demo[-4:] == ["-H", "Content-Type: application/json", "--port", "8080"]


# ---- R2. 잘못된 SecretRef ------------------------------------------------------

@pytest.mark.parametrize("value", [
    {"source": [], "id": "TOKEN"},
    {"source": {}, "id": "TOKEN"},
    {"source": "env", "id": 123},
    {"source": "env", "provider": ["x"], "id": "TOKEN"},
    {"source": "unknown-kind", "id": "TOKEN"},
])
def test_r2_invalid_secret_ref_is_classified_without_exception(value):
    kind, detail = classify_secret_ref(value)
    assert kind == "invalid"
    assert detail  # 어떤 필드가 문제인지 (값은 담지 않음)


def test_r2_valid_and_plain_objects():
    assert classify_secret_ref({"source": "env", "provider": "default", "id": "TOKEN"})[0] == "valid"
    assert classify_secret_ref({"source": "git", "url": "https://x"})[0] == "not_ref"
    assert classify_secret_ref("text")[0] == "not_ref"


def test_r2_bad_ref_keeps_good_server(write_config):
    cfg = write_config(json.dumps({"mcp": {"servers": {
        "ok": {"command": "example"},
        "bad": {"command": "example", "env": {"TOKEN": {"source": [], "id": "TOKEN"}}},
    }}}))
    result = collect(cfg)
    col = result["collection"]
    assert col["status"] == "partial"
    assert col["server_count"] == 2
    servers = by_key(result)
    assert servers["ok"]["collection_status"] == "complete"
    bad = servers["bad"]
    assert bad["collection_status"] == "partial"
    issue = [i for i in bad["issues"] if i["code"] == "invalid_secret_ref"]
    assert issue and issue[0]["field_path"] == "mcp.servers.bad.env.TOKEN"
    assert bad["credentials"]["env"]["entries"][0]["value_kind"] == "invalid_secret_ref"


def test_r2_source_key_in_unrelated_settings_is_not_an_issue(write_config):
    cfg = write_config(json.dumps({"mcp": {"servers": {
        "ok": {"command": "example", "codex": {"source": ["marketplace"], "id": 3}},
    }}}))
    server = collect(cfg)["servers"][0]
    assert server["collection_status"] == "complete"
    assert server["issues"] == []


# ---- R3. 중복 상위 키 ----------------------------------------------------------

def test_r3_duplicate_top_level_key_is_partial(write_config):
    col = collect(write_config('{"mcp":{"servers":{"ok":{"command":"example"}}},"mcp":{}}'))["collection"]
    assert col["outcome"] == "registry_absent"
    assert col["status"] == "partial"
    assert col["server_count"] is None
    assert [r["code"] for r in col["reasons"]] == ["registry_absent", "duplicate_key"]


@pytest.mark.parametrize("text, outcome, count", [
    ("{}", "registry_absent", None),
    ('{"mcp":{}}', "registry_absent", None),
    ('{"mcp":{"servers":{}}}', "empty_registry", 0),
])
def test_r3_normal_meanings_are_kept(write_config, text, outcome, count):
    col = collect(write_config(text))["collection"]
    assert (col["status"], col["outcome"], col["server_count"]) == ("complete", outcome, count)


# ---- R4. 환경변수 참조 문법 ----------------------------------------------------

@pytest.mark.parametrize("value, refs, sanitized", [
    ("${VAR}", ["VAR"], "${VAR}"),
    ("${VAR:-fallback}", ["VAR"], f"${{VAR:-{REDACTED}}}"),
    ("${VAR:-}", ["VAR"], "${VAR:-}"),
    ("$${VAR}", [], "$${VAR}"),
    ("$${VAR:-x}", [], "$${VAR:-x}"),
    ("${A:-${B}}", ["B"], "${A:-${B}}"),
])
def test_r4_env_expressions(value, refs, sanitized):
    r = Redactor()
    assert r.sanitize_string(value, "p") == sanitized
    assert [ref["name"] for ref in r.env_refs] == refs


def test_r4_fallback_redaction_is_recorded():
    r = Redactor()
    r.sanitize_string("${VAR:-FAKE_FALLBACK}", "p")
    assert r.redactions == [{"field_path": "p", "reason": "env_default_value_removed"}]
    r2 = Redactor()
    r2.sanitize_string("${VAR:-}", "p")
    assert r2.redactions == []  # 빈 기본값은 가릴 것이 없음


def test_r4_values_are_never_expanded(write_config, monkeypatch):
    monkeypatch.setenv("B", "FAKE_REAL_B")
    monkeypatch.setenv("A", "FAKE_REAL_A")
    cfg = write_config('{ mcp: { servers: { a: { command: "${A:-${B}}" } } } }')
    server = collect(cfg)["servers"][0]
    assert MARKER not in json.dumps(server)
    assert [u["name"] for u in server["unresolved"]] == ["B"]
