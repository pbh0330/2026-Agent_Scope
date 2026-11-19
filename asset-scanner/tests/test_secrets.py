"""가짜 비밀값이 결과 파일·표준출력·오류출력에 남지 않는지 검증한다."""

import json

from asset_scanner.redaction import REDACTED, Redactor
from conftest import EXAMPLES, run_cli

MARKER = "FAKE"  # 예제의 모든 가짜 비밀값에 들어 있는 표식


def test_fake_secrets_do_not_leak_to_output_stdout_stderr(tmp_path):
    out = tmp_path / "result.json"
    proc = run_cli(EXAMPLES / "fake-secrets.json5", out)
    assert proc.returncode == 1, proc.stderr  # 미해석 참조가 있어 partial
    text = out.read_text(encoding="utf-8")
    assert MARKER not in text
    assert MARKER not in proc.stdout
    assert MARKER not in proc.stderr
    # 가짜 비밀값이 원본에는 실제로 들어 있었는지 (테스트 자체의 유효성)
    assert (EXAMPLES / "fake-secrets.json5").read_text(encoding="utf-8").count(MARKER) >= 15


def test_secret_fields_keep_only_names_and_presence(tmp_path):
    out = tmp_path / "result.json"
    run_cli(EXAMPLES / "fake-secrets.json5", out)
    report = json.loads(out.read_text(encoding="utf-8"))
    servers = {s["registration_key"]: s for s in report["servers"]}

    env = servers["secret-stdio"]["credentials"]["env"]
    assert env["names"] == ["SAMPLE_API_TOKEN", "SAMPLE_FROM_ENV", "SAMPLE_WITH_DEFAULT"]
    assert env["values_withheld"] is True
    assert env["entries"][2] == {
        "name": "SAMPLE_WITH_DEFAULT", "value_kind": "env_ref",
        "ref_names": ["SAMPLE_OTHER"], "default_value_withheld": True,
    }

    remote = servers["secret-remote"]
    assert remote["credentials"]["headers"]["names"] == ["Authorization", "X-Api-Key"]
    assert remote["credentials"]["oauth"] == {"present": True, "value_withheld": True,
                                              "keys": ["scope", "clientSecret"]}
    assert remote["credentials"]["clientKey"] == {"present": True, "value_withheld": True}
    assert remote["declared"]["url"] == (
        f"https://mcp.example.test/hook/{REDACTED}?access_token={REDACTED}#{REDACTED}"
    )
    # 가림 위치와 사유가 남는다
    reasons = {(r["field_path"], r["reason"]) for r in servers["secret-stdio"]["redactions"]}
    assert ("mcp.servers.secret-stdio.args[1]", "value_after_secret_flag") in reasons


def test_parse_error_does_not_echo_config_text(tmp_path):
    cfg = tmp_path / "broken.json5"
    cfg.write_text('{ mcp: { servers: { a: { command: "x" FAKEBROKENVALUE: 1 } } } }', encoding="utf-8")
    out = tmp_path / "result.json"
    proc = run_cli(cfg, out)
    assert proc.returncode == 3
    for text in (out.read_text(encoding="utf-8"), proc.stdout, proc.stderr):
        assert MARKER not in text


def test_redactor_units():
    r = Redactor()
    assert r.sanitize_args(["--password", "${PW}"], "a") == ["--password", "${PW}"]
    assert r.sanitize_args(["--auth-token=${T:-FAKE1}"], "a") == [f"--auth-token={REDACTED}"]
    assert r.sanitize_args(["--port", "8080", "./dir"], "a") == ["--port", "8080", "./dir"]
    assert r.sanitize_args(["ghp_FAKEaaaaaaaaaaaaaaaa"], "a") == [REDACTED]
    assert r.sanitize_string("https://h.example.test/p", "u") == "https://h.example.test/p"
    assert r.sanitize_string("${A:-FAKEDEFAULT}", "u") == f"${{A:-{REDACTED}}}"
    assert r.sanitize_string("C:\\Users\\someone\\mcp\\server.exe", "c") == "C:\\Users\\someone\\mcp\\server.exe"
