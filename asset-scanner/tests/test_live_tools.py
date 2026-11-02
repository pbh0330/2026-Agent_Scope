"""실제 stdio 통신 통합 테스트: 스캐너가 개발용 MCP 서버를 **별도 프로세스**로 실행하고 tools/list를 조회한다.

- 이 테스트는 직접 만든 개발용 서버(`asset_scanner.dev_mcp_server`) 하나에 대한 검증이다. 팀 테스트베드 검증이 아니다.
- 모든 실행은 별도 프로세스 CLI(`python -m asset_scanner.live_tools`)이며, 서버 객체를 같은 프로세스에서 직접 호출하지 않는다.
- 서버 요청 기록(`DEV_MCP_SERVER_LOG`)은 메서드 이름·`tools/list` 커서 상태·pid만 담고 응답 내용·인증정보는 담지 않는다.
- `FAKE` 표식이 붙은 값은 전부 가짜 인증정보다. 실제 계정·외부 네트워크를 쓰지 않는다.
"""

import hashlib
import json
import os
import subprocess
import sys
import time

import pytest

from conftest import EXAMPLES, SCANNER_ROOT

GROUND_TRUTH = EXAMPLES / "dev-server-ground-truth.json"
# notifications/cancelled: 요청이 시간 초과되면 SDK 클라이언트가 서버에 보내는 표준 취소 알림이다 (tools/call이 아니며 응답 내용 없음).
ALLOWED_METHODS = {"server/discover", "initialize", "notifications/initialized", "tools/list", "notifications/cancelled"}
_CACHE: dict = {}


# ---- 도우미 ---------------------------------------------------------------------------

def pid_alive(pid: int) -> bool:
    """프로세스가 아직 살아 있는가. (Windows에서 os.kill(pid, 0)은 프로세스를 종료시키므로 쓰지 않는다.)"""
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def wait_dead(pid: int, seconds: float = 15.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.2)
    return not pid_alive(pid)


class Run:
    def __init__(self, code, stdout, stderr, out_path, log_path, seconds):
        self.code, self.stdout, self.stderr = code, stdout, stderr
        self.out_path, self.log_path, self.seconds = out_path, log_path, seconds
        self.log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        self.events = [json.loads(line) for line in self.log_text.splitlines() if line.strip()]
        self.report = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() and out_path.stat().st_size else None

    @property
    def server(self):
        return self.report["servers"][0]

    @property
    def methods(self):
        return [e["method"] for e in self.events if e["event"] == "request"]

    @property
    def pids(self):
        return [e["pid"] for e in self.events if e["event"] == "start"]

    @property
    def tool_names(self):
        return [t["definition"]["name"] for t in self.server["tools"]]

    @property
    def codes(self):
        return {i["code"] for i in self.server["issues"]}

    def everything(self):
        return (self.out_path.read_text(encoding="utf-8") if self.out_path.exists() else "") + "\n" + self.stdout + "\n" + \
            self.stderr + "\n" + self.log_text


def run_live(tmp_path_factory, scenario="two-tools", *extra, io_encoding="utf-8", cache=True):
    key = (scenario, extra, io_encoding)
    if cache and key in _CACHE:
        return _CACHE[key]
    work = tmp_path_factory.mktemp(f"live-{scenario}")
    out, log = work / "result.json", work / "server-requests.log"
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env["PYTHONIOENCODING"] = io_encoding
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-m", "asset_scanner.live_tools", "--demo", "--scenario", scenario, "--output", str(out),
         "--demo-request-log", str(log), *extra],
        cwd=SCANNER_ROOT, env=env, capture_output=True,
    )
    run = Run(proc.returncode, proc.stdout.decode(io_encoding, "replace"), proc.stderr.decode(io_encoding, "replace"),
              out, log, time.monotonic() - started)
    # 모든 실행에서 공통으로 확인한다: traceback 없음 / tools/call 없음 / 서버가 받은 메서드는 허용 목록 안 / 서버 프로세스 정리
    assert "Traceback" not in run.stderr, run.stderr
    assert "tools/call" not in run.methods
    assert set(run.methods) <= ALLOWED_METHODS, run.methods
    for pid in run.pids:
        assert wait_dead(pid), f"개발용 서버 프로세스({pid})가 종료되지 않고 남았습니다"
    assert sorted(p.name for p in work.iterdir()) == ["result.json", "server-requests.log"]   # 가림 전 응답을 담은 다른 파일 없음
    if cache:
        _CACHE[key] = run
    return run


@pytest.fixture
def live(tmp_path_factory):
    def _run(*args, **kw):
        return run_live(tmp_path_factory, *args, **kw)
    return _run


def ground_truth_tools():
    return {t["name"]: t for t in json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))["tools"]}


# ---- 정상 조회: 정답 목록 대조 · tools/call 없음 · 출처 표시 -------------------------------

def test_two_tools_from_a_real_stdio_server_match_the_ground_truth(live):
    before = hashlib.sha256(GROUND_TRUTH.read_bytes()).hexdigest()
    run = live("two-tools")
    assert run.code == 0, run.stderr
    assert run.stderr == ""
    got = {t["definition"]["name"]: t["definition"] for t in run.server["tools"]}
    assert got == ground_truth_tools()                       # 이름·설명·inputSchema가 정답 목록과 정확히 일치
    assert len(run.server["tools"]) == 2
    assert run.report["collection"]["status"] == "complete" and run.server["outcome"] == "tools_listed"
    assert all(t["definition_status"] == "passed_limited_checks" for t in run.server["tools"])
    assert hashlib.sha256(GROUND_TRUTH.read_bytes()).hexdigest() == before        # 정답 목록은 바뀌지 않는다


def test_the_server_really_received_only_discovery_and_tools_list(live):
    run = live("two-tools")
    assert run.methods == ["server/discover", "tools/list"]  # 서버 쪽 기록: 요청이 실제로 전달됐고 tools/call은 없다
    assert [e["cursor"] for e in run.events if e.get("method") == "tools/list"] == ["absent"]
    assert run.server["live"]["requests"] == {"tools_list_sent": 1, "tools_call_sent": 0}
    # 요청 기록에는 메서드 이름·커서 상태·pid·시나리오만 있다 (응답 내용·인증정보 없음)
    assert {k for e in run.events for k in e} <= {"event", "method", "cursor", "pid", "scenario"}


def test_source_is_marked_as_a_real_stdio_query_not_a_stored_response(live):
    run = live("two-tools")
    src = run.report["source"]
    assert src["source_kind"] == "live_stdio_query" and src["live_server_query"] is True and src["transport"] == "stdio"
    assert src["target"]["kind"] == "dev_demo_server" and src["target"]["team_testbed"] is False
    assert "stored" not in json.dumps(src)
    scope = run.report["scope"]
    assert {"team_testbed", "tools_call", "exposure", "callability", "wire_level_raw_json"} <= set(scope["not_verified"])
    assert "live_server_query" not in scope["not_verified"]
    assert "팀 테스트베드" in scope["note"] and "호출 가능" in scope["note"]
    assert "실제 stdio 조회 결과 (개발용 서버, 팀 테스트베드 아님)" in run.stdout
    assert "서버 프로세스를 실행합니다" in run.stdout


def test_negotiated_version_server_info_and_capabilities_are_what_the_server_sent(live):
    live_info = live("two-tools").server["live"]
    assert live_info["negotiation"]["negotiated_protocol_version"] == "2026-07-28"
    assert live_info["negotiation"]["supported_by_catalog"] is True
    assert live_info["server_info_from_wire"] == {"name": "asset-scanner-dev-server", "version": "0.0.1"}   # 서버가 보낸 필드만
    assert live_info["capabilities_from_wire"] == {"tools": {"listChanged": False}}                       # SDK 기본값을 덧붙이지 않음
    import importlib.metadata
    # 결과의 SDK 버전은 이 실행에 실제로 설치된 버전이어야 한다 (고정 버전 값은 아래 requirements 테스트가 따로 확인)
    assert live_info["sdk"] == {"package": "mcp", "version": importlib.metadata.version("mcp")}
    proc = live_info["sdk_processing"]
    assert proc["tool_models_used"] is False and "cache=None" in proc["client_cache"]
    assert live_info["result_origin"] == "sdk_session_raw_result"


def test_ground_truth_and_example_inputs_are_not_modified_by_any_live_run(live):
    files = sorted(EXAMPLES.iterdir())
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    live("empty")
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(EXAMPLES.iterdir())}
    assert before == after


# ---- 빈 목록 · 서버 오류 · 페이지네이션 ------------------------------------------------

def test_successful_empty_list_and_server_error_are_different_outcomes(live):
    empty, error = live("empty"), live("error")
    assert empty.code == 0
    assert (empty.server["collection_status"], empty.server["outcome"], empty.server["tool_count"]) == ("complete", "empty_list", 0)
    assert error.code == 3
    assert (error.server["collection_status"], error.server["outcome"], error.server["tool_count"]) == ("failed", "error_response", None)
    assert error.server["tools"] == [] and error.report["collection"]["tool_count_complete"] is False
    issue = next(i for i in error.server["issues"] if i["code"] == "error_response")
    assert issue["error_code"] == -32603 and "error_data_omitted" not in issue


def test_two_pages_are_followed_to_the_end(live):
    run = live("paginated")
    assert run.code == 0 and run.server["collection_status"] == "complete"
    assert sorted(run.tool_names) == ["add_numbers", "echo_text"]
    assert [(t["page_index"], t["index_in_page"]) for t in run.server["tools"]] == [(0, 0), (1, 0)]
    assert [e["cursor"] for e in run.events if e.get("method") == "tools/list"] == ["absent", "present"]
    assert run.server["live"]["requests"]["tools_list_sent"] == 2
    assert "page-2" not in run.out_path.read_text(encoding="utf-8")          # 커서 값은 저장하지 않는다


def test_an_empty_string_cursor_is_not_the_end_of_the_list(live):
    run = live("empty-cursor")
    assert run.code == 0 and run.server["collection_status"] == "complete"
    assert sorted(run.tool_names) == ["add_numbers", "echo_text"]
    assert [e["cursor"] for e in run.events if e.get("method") == "tools/list"] == ["absent", "empty"]   # 서버가 빈 문자열 커서를 받음
    assert run.server["pages"][0]["has_next_cursor"] is True


def test_failure_on_a_later_page_keeps_the_earlier_tools_as_partial(live):
    run = live("fail-second")
    assert run.code == 1
    assert run.server["collection_status"] == "partial"
    assert run.tool_names == ["echo_text"]
    issue = next(i for i in run.server["issues"] if i["code"] == "error_response")
    assert issue["page_index"] == 1 and issue["error_code"] == -32603
    assert [e["cursor"] for e in run.events if e.get("method") == "tools/list"] == ["absent", "present"]


# ---- 제한 · 시간 초과 · 서버 조기 종료 · 프로세스 정리 --------------------------------

def test_cursor_loop_is_stopped_and_reported(live):
    run = live("cursor-loop")
    assert run.code == 1 and run.server["collection_status"] == "partial"
    assert "cursor_repeated" in run.codes and len(run.server["tools"]) == 2
    assert run.methods.count("tools/list") == 2 and run.seconds < 60


def test_max_pages_limit_stops_an_endless_listing(live):
    run = live("endless", "--max-pages", "3")
    assert run.code == 1 and run.server["collection_status"] == "partial"
    assert {"max_pages_reached", "next_cursor_remaining"} <= run.codes
    assert len(run.server["pages"]) == 3 and run.methods.count("tools/list") == 3
    assert run.report["collection"]["tool_count_complete"] is False


def test_max_tools_limit_stops_an_endless_listing(live):
    run = live("endless", "--max-tools", "2", "--max-pages", "50")
    assert run.code == 1 and "tool_limit_reached" in run.codes
    assert len(run.server["tools"]) == 2 and run.methods.count("tools/list") == 2


def test_request_timeout_is_reported_without_traceback_and_the_server_is_cleaned_up(live):
    run = live("slow", "--request-timeout", "8", "--timeout", "60")
    assert run.code == 3 and run.stderr == ""
    assert (run.server["collection_status"], run.server["outcome"], run.server["tool_count"]) == ("failed", "request_timeout", None)
    assert run.server["tools"] == [] and run.seconds < 55
    # 요청은 서버에 도달했고 응답이 오지 않았다. 시간 초과 뒤 SDK가 표준 취소 알림을 보낸다 (tools/call 아님).
    assert run.methods == ["server/discover", "tools/list", "notifications/cancelled"]
    assert run.pids and not pid_alive(run.pids[0])                        # 서버 프로세스가 남지 않았다 (run_live에서도 확인)


def test_total_timeout_stops_the_session_and_the_server_is_cleaned_up(live):
    run = live("slow", "--timeout", "10", "--request-timeout", "60")
    assert run.code == 3 and run.stderr == ""
    assert run.server["outcome"] == "total_timeout" and run.server["tool_count"] is None
    assert run.seconds < 45
    assert run.pids and not pid_alive(run.pids[0])


def test_server_exiting_during_the_request_is_reported_and_cleaned_up(live):
    run = live("exit-early")
    assert run.code == 3 and run.stderr == ""
    assert run.server["collection_status"] == "failed" and run.server["outcome"] == "connection_closed"
    assert run.server["tool_count"] is None and run.server["tools"] == []
    assert "tools/list" in run.methods and run.pids and not pid_alive(run.pids[0])


def test_invalid_cli_use_is_an_argument_error_and_starts_no_server(tmp_path):
    log = tmp_path / "log"
    env = dict(os.environ, DEV_MCP_SERVER_LOG=str(log), PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-m", "asset_scanner.live_tools", "--output", str(tmp_path / "o.json")],
                          cwd=SCANNER_ROOT, env=env, capture_output=True)
    assert proc.returncode == 2 and b"Traceback" not in proc.stderr
    assert "--demo" in proc.stderr.decode("utf-8", "replace")
    assert not log.exists() and not (tmp_path / "o.json").exists()        # 서버를 실행하지 않았다


# ---- SDK 검증 거부 · 미지원 버전 · SDK 변환과 원본 응답의 구분 ---------------------------

def test_sdk_validation_rejection_is_a_failure_with_evidence_not_an_empty_list(live):
    run = live("invalid-schema")
    assert run.code == 3 and run.stderr == ""
    assert (run.server["collection_status"], run.server["outcome"], run.server["tool_count"]) == ("failed", "sdk_validation_rejected", None)
    issue = next(i for i in run.server["issues"] if i["code"] == "sdk_validation_rejected")
    assert issue["validation_errors"] and issue["validation_errors"][0]["loc"].endswith("inputSchema.type")
    assert issue["validation_errors"][0]["type"] == "literal_error"
    assert "string" not in json.dumps(issue["validation_errors"])         # 서버가 보낸 입력 값은 근거에 넣지 않는다
    assert run.server["tools"] == [] and run.methods.count("tools/list") == 1


def test_a_version_other_than_2026_07_28_is_unsupported_and_not_parsed(tmp_path):
    from asset_scanner.live_tools import LiveLimits, collect_live_demo
    from asset_scanner.tools_catalog import build_catalog_report
    log = tmp_path / "req.log"
    collected = collect_live_demo("two-tools", LiveLimits(), log, client_mode="legacy")     # SDK의 initialize 흐름: 2025-11-25로 협상됨
    report = build_catalog_report(collected)
    srv = report["servers"][0]
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert (srv["collection_status"], srv["outcome"], srv["tool_count"], srv["tools"]) == ("failed", "protocol_version_unsupported", None, [])
    assert srv["live"]["negotiation"]["negotiated_protocol_version"] == "2025-11-25"
    assert srv["live"]["negotiation"]["supported_by_catalog"] is False
    assert srv["live"]["server_info_from_wire"]["name"] == "asset-scanner-dev-server"       # 협상으로 확인한 값은 기록
    assert srv["live"]["requests"]["tools_list_sent"] == 0
    methods = [e["method"] for e in events if e["event"] == "request"]
    assert "initialize" in methods and "tools/list" not in methods and "tools/call" not in methods
    assert not pid_alive(next(e["pid"] for e in events if e["event"] == "start")) or wait_dead(
        next(e["pid"] for e in events if e["event"] == "start"))


def test_optional_fields_absent_on_the_wire_are_not_invented_by_the_sdk_models(live):
    run = live("sparse")
    bare = next(t for t in run.server["tools"] if t["definition"]["name"] == "bare_tool")
    assert bare["definition"] == {"name": "bare_tool", "inputSchema": {"type": "object"}}   # title·description·annotations 등을 만들지 않음
    assert bare["other_definition_fields"] == []


def test_tools_the_sdk_list_tools_would_silently_drop_are_kept_and_marked(live, tmp_path):
    run = live("bad-header")
    by_name = {t["definition"]["name"]: t for t in run.server["tools"]}
    assert set(by_name) == {"bad_header_tool", "add_numbers"}                              # 원본 응답은 그대로 보존
    assert by_name["bad_header_tool"]["sdk_list_tools_would_drop"] is True
    assert by_name["add_numbers"]["sdk_list_tools_would_drop"] is False
    # 같은 서버를 SDK의 list_tools로 조회하면 실제로 한 개가 사라진다 (실제 stdio 통신)
    import anyio
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters, stdio_client
    params = StdioServerParameters(command=sys.executable, args=["-m", "asset_scanner.dev_mcp_server", "--scenario", "bad-header"],
                                   cwd=str(SCANNER_ROOT), env={"DEV_MCP_SERVER_LOG": str(tmp_path / "sdk.log"), "PYTHONUTF8": "1"})

    async def sdk_names():
        # Client(StdioServerParameters)는 2.1.0부터라서 2.0.0에서도 되도록 Transport(stdio_client)로 넘긴다
        async with Client(stdio_client(params), cache=None, read_timeout_seconds=30) as client:
            return [t.name for t in (await client.list_tools(cache_mode="bypass")).tools]

    assert anyio.run(sdk_names) == ["add_numbers"]
    events = [json.loads(line) for line in (tmp_path / "sdk.log").read_text(encoding="utf-8").splitlines()]
    assert all(e.get("method") != "tools/call" for e in events)
    assert wait_dead(next(e["pid"] for e in events if e["event"] == "start"))


# ---- 가림 · 유니코드 · 콘솔 ------------------------------------------------------------

LIVE_FAKES = ["FAKE_LIVE_BEARER", "FAKELIVEGITHUBTOKEN", "FAKE_LIVE_URLPASS", "FAKE_LIVE_QUERY", "FAKE_LIVE_ID_PASS",
              "FAKE_LIVE_ID_QUERY", "FAKE_LIVE_DEFAULT_SECRET", "FAKELIVEPROPERTY", "FAKE_LIVE_META_SECRET"]


def test_fake_credentials_in_a_live_response_are_not_left_in_file_stdout_stderr_or_server_log(live):
    run = live("secrets")
    assert run.code == 0, run.stderr
    text = run.everything()
    for fake in LIVE_FAKES:
        assert fake not in text, fake
    deploy = next(t for t in run.server["tools"] if t["definition"]["name"] == "deploy_service")
    assert deploy["definition_altered"] is True and deploy["redactions"]
    assert deploy["definition"]["_meta"]["vendor"] == "acme"                                 # 일반 메타데이터는 보존
    reasons = {(r["field_path"], r["reason"]) for r in deploy["redactions"]}
    assert ("_meta.api_key", "secret_named_field_value") in reasons
    assert ("inputSchema.$id", "url_userinfo") in reasons
    assert any(reason == "key_looks_like_secret" for _, reason in reasons)
    assert "FAKE" not in json.dumps(deploy["redactions"])                                    # 기록에도 원문 없음


def test_korean_and_emoji_are_preserved_and_the_cp949_console_does_not_break(live):
    run = live("unicode", io_encoding="cp949")
    assert run.code == 0 and run.stderr == ""
    assert "Traceback" not in run.stdout
    note = next(t for t in run.server["tools"] if t["definition"]["name"] == "read_notes")["definition"]
    assert note["description"] == "노트를 읽습니다 😀 café — 한글·이모지·é 보존 확인"
    assert note["inputSchema"]["properties"]["제목"]["description"] == "노트 제목 😀"
    assert "노트를 읽습니다 😀" in run.out_path.read_text(encoding="utf-8")                  # 파일은 항상 UTF-8 원문
    assert "노트를 읽습니다" not in run.stdout                                                # 설명문은 콘솔에 출력하지 않는다


def test_utf8_console_run_matches_too(live):
    run = live("unicode", io_encoding="utf-8")
    assert run.code == 0 and run.stderr == ""


def test_save_failure_is_exit_4_without_traceback_and_the_server_is_still_cleaned_up(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")
    log = tmp_path / "req.log"
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-m", "asset_scanner.live_tools", "--demo", "--output", str(blocker / "o.json"),
                           "--demo-request-log", str(log)], cwd=SCANNER_ROOT, env=env, capture_output=True)
    assert proc.returncode == 4 and b"Traceback" not in proc.stderr
    assert "저장하지 못했습니다" in proc.stderr.decode("utf-8", "replace")
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert all(e.get("method") != "tools/call" for e in events)
    assert wait_dead(next(e["pid"] for e in events if e["event"] == "start"))


# ---- 정적 수집 CLI와의 분리 ---------------------------------------------------------------

def test_static_modules_do_not_import_the_sdk_and_static_clis_never_start_a_server(tmp_path):
    code = ("import sys, asset_scanner.cli, asset_scanner.collector, asset_scanner.report, asset_scanner.output, "
            "asset_scanner.redaction, asset_scanner.tools_catalog; "
            "print(sorted(m for m in sys.modules if m in ('mcp', 'mcp_types') or m.startswith(('mcp.', 'mcp_types.'))))")
    proc = subprocess.run([sys.executable, "-c", code], cwd=SCANNER_ROOT, capture_output=True, text=True)
    assert proc.returncode == 0 and proc.stdout.strip() == "[]", proc.stderr
    log = tmp_path / "server.log"
    env = dict(os.environ, DEV_MCP_SERVER_LOG=str(log), PYTHONIOENCODING="utf-8")
    for args in (["-m", "asset_scanner", "--config", str(EXAMPLES / "two-servers.json5"), "--output", str(tmp_path / "a.json")],
                 ["-m", "asset_scanner.tools_catalog", "--capture", str(EXAMPLES / "tools-list-capture.json"),
                  "--output", str(tmp_path / "b.json")]):
        proc = subprocess.run([sys.executable, *args], cwd=SCANNER_ROOT, env=env, capture_output=True)
        assert proc.returncode == 0, proc.stderr
    assert not log.exists()                                                                  # 서버가 한 번도 실행되지 않았다


# ---- 검증 도구 자체의 확인 ---------------------------------------------------------------

def test_the_process_check_really_detects_a_running_and_a_stopped_process():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        assert pid_alive(proc.pid) is True            # 살아 있는 프로세스는 '살아 있음'으로 감지된다
    finally:
        proc.terminate()
        proc.wait(timeout=15)
    assert wait_dead(proc.pid, 10.0) is True          # 종료한 프로세스는 '없음'으로 감지된다


def test_requirements_pin_the_exact_sdk_version_that_is_installed():
    import importlib.metadata
    pins = [line.strip() for line in (SCANNER_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("mcp==")]
    assert pins == ["mcp==2.3.0"]                                                    # 정확한 버전 고정
    assert importlib.metadata.version("mcp") == "2.3.0"                              # 개발 환경에 실제 설치된 버전
    lock = (SCANNER_ROOT / "requirements-live-lock.txt").read_text(encoding="utf-8")
    assert "mcp==2.3.0" in lock and "mcp-types==2.3.0" in lock
