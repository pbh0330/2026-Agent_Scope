"""스캐너 V7 검토(V7-R1, V7-R2) 회귀 테스트.

- R1: `--max-tools`가 페이지 안의 Tool 수와 최종 페이지를 포함한 **전체 누적**에 적용돼야 한다.
- R2: 시간 제한의 `nan`·`inf`·`-inf`·0·음수는 서버를 실행하기 전에 인자 오류(종료 코드 2)로 거부해야 한다.

R1은 개발용 MCP 서버를 별도 프로세스로 실행하는 실제 stdio 통신으로 검증한다. 팀 테스트베드 검증이 아니다.
`FAKE` 표식은 가짜 인증정보다. 실제 계정·외부 네트워크를 쓰지 않는다.
"""

import hashlib
import json
import os
import subprocess
import sys

import pytest

from conftest import EXAMPLES, SCANNER_ROOT
from test_live_tools import GROUND_TRUTH, run_live


@pytest.fixture
def live(tmp_path_factory):
    def _run(*args, **kw):
        return run_live(tmp_path_factory, *args, **kw)
    return _run


def list_calls(run):
    return [e for e in run.events if e.get("method") == "tools/list"]


# ===========================================================================================
# V7-R1: --max-tools (페이지 안 + 누적 + 최종 페이지)
# ===========================================================================================

def test_r1_1_default_server_one_page_two_tools_with_max_tools_1(live):
    run = live("two-tools", "--max-tools", "1")
    assert run.code == 1, run.stdout
    assert run.server["collection_status"] == "partial" and run.server["outcome"] == "tool_limit_reached"
    assert run.tool_names == ["echo_text"] and run.server["tool_count"] == 1          # 남은 한도까지만 보존
    assert run.report["collection"]["tool_count_complete"] is False
    issue = next(i for i in run.server["issues"] if i["code"] == "tool_limit_reached")
    assert issue["page_index"] == 0 and issue["excluded_tools"] == 1
    assert run.server["live"]["limit_exclusions"] == [{"page_index": 0, "tools_in_response": 2, "tools_kept": 1, "tools_excluded": 1}]
    assert run.server["pages"][0]["tool_count"] == 1 and run.server["pages"][0]["tools_in_response"] == 2
    assert "add_numbers" not in run.out_path.read_text(encoding="utf-8")             # 한도 밖 Tool의 정의는 저장하지 않는다
    assert run.methods == ["server/discover", "tools/list"]


def test_r1_2_last_page_exceeding_the_cumulative_limit_is_truncated(live):
    run = live("uneven-pages", "--max-tools", "2")
    assert run.code == 1
    assert run.server["collection_status"] == "partial" and run.server["tool_count"] == 2
    assert run.tool_names == ["echo_text", "add_numbers"]                            # 1페이지 1개 + 2페이지 앞의 1개
    assert "third_tool" not in run.out_path.read_text(encoding="utf-8")
    assert [(t["page_index"], t["index_in_page"]) for t in run.server["tools"]] == [(0, 0), (1, 0)]
    assert [t["internal_ref"] for t in run.server["tools"]] == ["live-session[0]/tools[0]", "live-session[0]/tools[1]"]
    assert all(t["server_ref"] == "dev-demo-server" and t["server_index"] == 0 for t in run.server["tools"])
    assert run.server["live"]["limit_exclusions"] == [{"page_index": 1, "tools_in_response": 2, "tools_kept": 1, "tools_excluded": 1}]
    assert run.report["collection"]["tool_count_complete"] is False and len(list_calls(run)) == 2


def test_r1_3_page_with_a_next_cursor_exceeding_the_remaining_limit_stops_without_the_next_request(live):
    run = live("big-first-page", "--max-tools", "1")
    assert run.code == 1 and run.server["collection_status"] == "partial"
    assert run.tool_names == ["echo_text"]
    assert {"tool_limit_reached", "next_cursor_remaining"} <= run.codes
    assert len(list_calls(run)) == 1                                                 # 다음 페이지를 요청하지 않았다
    assert run.server["live"]["limit_exclusions"][0]["tools_excluded"] == 1
    assert run.report["collection"]["tool_count_complete"] is False


def test_r1_4_exactly_the_limit_on_the_last_page_stays_complete(live):
    run = live("two-tools", "--max-tools", "2")
    assert run.code == 0, run.stdout
    assert run.server["collection_status"] == "complete" and run.server["outcome"] == "tools_listed"
    assert run.tool_names == ["echo_text", "add_numbers"] and run.server["tool_count"] == 2
    assert run.server["live"]["limit_exclusions"] == [] and run.report["collection"]["tool_count_complete"] is True
    assert "tool_limit_reached" not in run.codes


def test_r1_4b_exactly_the_limit_after_several_pages_stays_complete(live):
    run = live("uneven-pages", "--max-tools", "3")
    assert run.code == 0 and run.server["collection_status"] == "complete" and run.server["tool_count"] == 3
    assert run.server["live"]["limit_exclusions"] == [] and len(list_calls(run)) == 2


def test_r1_5_exactly_the_limit_with_a_cursor_left_is_partial_and_does_not_request_more(live):
    run = live("paginated", "--max-tools", "1")
    assert run.code == 1 and run.server["collection_status"] == "partial"
    assert run.tool_names == ["echo_text"]
    assert {"tool_limit_reached", "next_cursor_remaining"} <= run.codes
    assert len(list_calls(run)) == 1                                                 # 한도에 도달해 다음 요청을 하지 않았다
    assert run.server["live"]["limit_exclusions"] == []                              # 받은 Tool을 잘라 낸 것은 없다
    assert run.report["collection"]["tool_count_complete"] is False


def test_r1_6_limit_handling_sends_no_tools_call_and_cleans_up_the_server(live):
    # run_live는 모든 실행에서 tools/call 없음·허용된 메서드만·서버 pid 종료·결과 외 파일 없음을 확인한다. 한도 시나리오를 한 번씩 모두 실행한다.
    for scenario, limit in (("two-tools", "1"), ("uneven-pages", "2"), ("big-first-page", "1"), ("paginated", "1")):
        run = live(scenario, "--max-tools", limit)
        assert "tools/call" not in run.methods and run.pids


def test_r1_truncation_keeps_redaction_records_and_drops_nothing_secret_from_excluded_tools(live):
    run = live("secrets", "--max-tools", "1")
    assert run.code == 1
    assert run.tool_names == ["deploy_service"]
    deploy = run.server["tools"][0]
    assert (deploy["page_index"], deploy["index_in_page"]) == (0, 0) and deploy["definition_altered"] is True
    reasons = {(r["field_path"], r["reason"]) for r in deploy["redactions"]}
    assert ("_meta.api_key", "secret_named_field_value") in reasons and ("inputSchema.$id", "url_userinfo") in reasons
    assert deploy["definition"]["_meta"]["vendor"] == "acme"
    assert "add_numbers" not in run.out_path.read_text(encoding="utf-8")
    for fake in ("FAKE_LIVE_BEARER", "FAKELIVEGITHUBTOKEN", "FAKE_LIVE_URLPASS", "FAKE_LIVE_META_SECRET", "FAKELIVEPROPERTY"):
        assert fake not in run.everything(), fake


def test_r1_default_limit_and_endless_scenario_behave_as_before(live):
    run = live("endless", "--max-tools", "2", "--max-pages", "50")                    # 기존 V7 테스트와 같은 조건
    assert run.code == 1 and "tool_limit_reached" in run.codes
    assert len(run.server["tools"]) == 2 and len(list_calls(run)) == 2


def test_r1_user_limit_cannot_exceed_the_static_catalog_limit(tmp_path):
    from asset_scanner.tools_catalog import MAX_TOOLS_PER_SERVER
    log = tmp_path / "log"
    proc = cli_live(tmp_path, "--max-tools", str(MAX_TOOLS_PER_SERVER + 1), log=log)
    assert proc.returncode == 2 and b"Traceback" not in proc.stderr and not log.exists()
    assert "--max-tools" in proc.stderr.decode("utf-8", "replace")


def test_r1_static_catalog_cli_is_unchanged_by_the_user_limit_work(tmp_path):
    out = tmp_path / "o.json"
    proc = subprocess.run([sys.executable, "-m", "asset_scanner.tools_catalog", "--capture", str(EXAMPLES / "tools-list-capture.json"),
                           "--output", str(out)], cwd=SCANNER_ROOT, capture_output=True)
    assert proc.returncode == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["collection"]["tool_count"] == 3 and report["collection"]["status"] == "complete"
    assert report["source"]["live_server_query"] is False


# ===========================================================================================
# V7-R2: 시간 제한 NaN·Infinity·0·음수
# ===========================================================================================

BAD_VALUES = ["nan", "inf", "-inf", "0", "-1", "-0.5", "86401", "1e300"]   # 86400초(24시간) 초과는 이벤트 루프 변환 오류를 막으려고 거부


def cli_live(tmp_path, *extra, log=None, output=None):
    log = log or tmp_path / "server-requests.log"
    output = output or tmp_path / "result.json"
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run([sys.executable, "-m", "asset_scanner.live_tools", "--demo", "--output", str(output),
                           "--demo-request-log", str(log), *extra], cwd=SCANNER_ROOT, env=env, capture_output=True)


@pytest.mark.parametrize("option", ["--timeout", "--request-timeout"])
@pytest.mark.parametrize("value", BAD_VALUES)
def test_r2_invalid_time_limits_are_argument_errors_that_start_no_server_and_keep_the_old_result(tmp_path, option, value):
    out, log = tmp_path / "result.json", tmp_path / "server-requests.log"
    out.write_text("OLD RESULT KEEP ME", encoding="utf-8")
    before = (out.read_bytes(), out.stat().st_mtime_ns)
    proc = cli_live(tmp_path, f"{option}={value}", log=log, output=out)
    err = proc.stderr.decode("utf-8", "replace")
    assert proc.returncode == 2, (proc.returncode, err)                              # 저장 실패(4)로 오분류하지 않는다
    assert "Traceback" not in err and option in err
    assert not log.exists()                                                          # 서버 시작 이벤트·요청이 없다 = 서버를 실행하지 않았다
    assert (out.read_bytes(), out.stat().st_mtime_ns) == before                      # 기존 결과의 내용과 수정 시각 보존
    assert [p.name for p in tmp_path.iterdir()] == ["result.json"]                   # 새 결과·로그·임시 파일 없음
    assert "서버 프로세스를 실행합니다" not in proc.stdout.decode("utf-8", "replace")


def test_r2_a_valid_positive_finite_value_still_runs_normally(tmp_path):
    out, log = tmp_path / "result.json", tmp_path / "server-requests.log"
    proc = cli_live(tmp_path, "--timeout", "90", "--request-timeout", "20.5", log=log, output=out)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["servers"][0]["live"]["limits"]["total_timeout_s"] == 90.0
    assert report["servers"][0]["live"]["limits"]["request_timeout_s"] == 20.5
    assert report["collection"]["status"] == "complete"


@pytest.mark.parametrize("field,value", [
    ("total_timeout_s", float("nan")), ("total_timeout_s", float("inf")), ("total_timeout_s", 0.0), ("total_timeout_s", -1.0),
    ("request_timeout_s", float("nan")), ("request_timeout_s", float("-inf")), ("request_timeout_s", 0.0),
    ("max_pages", 0), ("max_tools", 0), ("max_tools", 5001),
])
def test_r2_the_public_function_validates_limits_before_starting_a_server(tmp_path, field, value):
    from asset_scanner.live_tools import LiveLimits, collect_live_demo
    log = tmp_path / "server-requests.log"
    limits = LiveLimits()
    setattr(limits, field, value)
    with pytest.raises(ValueError) as excinfo:
        collect_live_demo("two-tools", limits, log)
    assert field in str(excinfo.value)
    assert not log.exists()                                                          # CLI와 같은 방침: 실행 전에 거부, 서버 미실행


def test_r2_cli_and_function_share_one_validation(tmp_path):
    from asset_scanner.live_tools import LiveLimits, validate_limits
    assert validate_limits(LiveLimits()) == []
    problems = validate_limits(LiveLimits(total_timeout_s=float("nan"), request_timeout_s=-1, max_pages=0, max_tools=0))
    assert [p.split(":")[0] for p in problems] == ["total_timeout_s", "request_timeout_s", "max_pages", "max_tools"]


# ---- 공통 보존 조건 ------------------------------------------------------------------------

def test_ground_truth_is_unchanged_and_default_run_still_matches_it(live):
    before = hashlib.sha256(GROUND_TRUTH.read_bytes()).hexdigest()
    run = live("two-tools")
    expected = {t["name"]: t for t in json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))["tools"]}
    assert {t["definition"]["name"]: t["definition"] for t in run.server["tools"]} == expected
    assert run.code == 0 and run.server["live"]["limit_exclusions"] == []
    assert hashlib.sha256(GROUND_TRUTH.read_bytes()).hexdigest() == before


def test_r2_validate_limits_bounds_and_types():
    from asset_scanner.live_tools import LiveLimits, validate_limits
    assert validate_limits(LiveLimits(total_timeout_s=86400, request_timeout_s=0.001, max_pages=1, max_tools=5000)) == []
    for bad in (86401, 1e300, True, "5", None, float("-inf")):
        assert validate_limits(LiveLimits(request_timeout_s=bad)), bad
        assert validate_limits(LiveLimits(total_timeout_s=bad)), bad
    for bad in (True, 1.5, "3", 0, -1):
        assert validate_limits(LiveLimits(max_pages=bad)), bad
        assert validate_limits(LiveLimits(max_tools=bad)), bad
