"""
attribution.py의 패턴 판별 로직(순차/병렬/배치) 단위 테스트.

실제 캡처 로그(otel-debug-log.txt)에는 순차 사례 1건밖에 없어서, 병렬/배치 분기는
검증되지 않은 채로 남아있었음. 여기서는 합성(synthetic) Span으로 세 패턴을 모두 만들어
classify_segments()가 각각을 올바르게 분류하는지 확인한다.
"""

from datetime import datetime, timedelta, timezone

from otel_log_parser import Span
from attribution import apply_pricing, classify_segments, group_runs

T0 = datetime(2026, 9, 22, 10, 0, 0)


def mk_model_call(span_id, start_s, end_s, parent, trace, in_tok, out_tok):
    return Span(
        trace_id=trace, parent_id=parent, span_id=span_id,
        name="openclaw.model.call",
        start=T0 + timedelta(seconds=start_s), end=T0 + timedelta(seconds=end_s),
        attrs={
            "openclaw.model_call.usage.input_tokens": in_tok,
            "openclaw.model_call.usage.output_tokens": out_tok,
        },
    )


def mk_tool(span_id, start_s, end_s, parent, trace, tool_name):
    return Span(
        trace_id=trace, parent_id=parent, span_id=span_id,
        name="openclaw.tool.execution",
        start=T0 + timedelta(seconds=start_s), end=T0 + timedelta(seconds=end_s),
        attrs={"openclaw.toolName": tool_name},
    )


def test_sequential():
    trace, parent = "trace-seq", "run-seq"
    spans = [
        mk_model_call("m1", 0, 2, parent, trace, in_tok=1000, out_tok=50),
        mk_tool("t1", 2, 3, parent, trace, "toolA"),
        mk_model_call("m2", 3, 5, parent, trace, in_tok=1300, out_tok=40),
    ]
    runs = group_runs(spans)
    results = classify_segments(runs)
    assert len(results) == 1, results
    r = results[0]
    assert r.pattern == "sequential"
    assert r.approx_tokens == 1300 - 1000 - 50 == 250
    print("test_sequential OK ->", r)


def test_parallel():
    # 두 tool.execution이 시간상 겹침 (동시 실행)
    trace, parent = "trace-par", "run-par"
    spans = [
        mk_model_call("m1", 0, 2, parent, trace, in_tok=1000, out_tok=50),
        mk_tool("t1", 2, 5, parent, trace, "toolA"),
        mk_tool("t2", 3, 6, parent, trace, "toolB"),  # t1과 [3,5] 구간 겹침
        mk_model_call("m2", 6, 8, parent, trace, in_tok=1800, out_tok=30),
    ]
    runs = group_runs(spans)
    results = classify_segments(runs)
    assert len(results) == 2, results
    assert {r.pattern for r in results} == {"parallel"}
    assert {r.tool_name for r in results} == {"toolA", "toolB"}
    assert all(r.approx_tokens is None for r in results)
    print("test_parallel OK ->", results)


def test_batch():
    # 두 tool.execution이 순차적이지만(안 겹침) 같은 model.call 사이에 몰려 있음
    trace, parent = "trace-batch", "run-batch"
    spans = [
        mk_model_call("m1", 0, 2, parent, trace, in_tok=1000, out_tok=50),
        mk_tool("t1", 2, 3, parent, trace, "toolA"),
        mk_tool("t2", 3, 4, parent, trace, "toolB"),  # 안 겹치지만 model.call 사이에 2개
        mk_model_call("m2", 4, 6, parent, trace, in_tok=1600, out_tok=20),
    ]
    runs = group_runs(spans)
    results = classify_segments(runs)
    assert len(results) == 2, results
    assert {r.pattern for r in results} == {"batch"}
    assert all(r.approx_tokens is None for r in results)
    print("test_batch OK ->", results)


def test_negative_delta_flagged():
    # 다음 model.call의 입력 토큰이 오히려 줄어든 경우 (컨텍스트 압축 등) — 0으로 clamp, note 남김
    trace, parent = "trace-neg", "run-neg"
    spans = [
        mk_model_call("m1", 0, 2, parent, trace, in_tok=5000, out_tok=50),
        mk_tool("t1", 2, 3, parent, trace, "toolA"),
        mk_model_call("m2", 3, 5, parent, trace, in_tok=1200, out_tok=40),  # 요약/압축 가정
    ]
    runs = group_runs(spans)
    results = classify_segments(runs)
    assert len(results) == 1
    r = results[0]
    assert r.pattern == "sequential"
    assert r.approx_tokens == 0
    assert "delta<0" in r.note
    print("test_negative_delta_flagged OK ->", r)


def test_boundary_touch_is_not_parallel():
    # t1이 끝나는 시각(=3)에 t2가 시작 — 겹치는 게 아니라 맞닿기만 함.
    # _overlaps()는 엄격부등호(<)를 쓰므로 이건 병렬이 아니라 batch여야 함.
    trace, parent = "trace-boundary", "run-boundary"
    spans = [
        mk_model_call("m1", 0, 2, parent, trace, in_tok=1000, out_tok=50),
        mk_tool("t1", 2, 3, parent, trace, "toolA"),
        mk_tool("t2", 3, 4, parent, trace, "toolB"),
        mk_model_call("m2", 4, 6, parent, trace, in_tok=1600, out_tok=20),
    ]
    runs = group_runs(spans)
    results = classify_segments(runs)
    assert {r.pattern for r in results} == {"batch"}, results
    print("test_boundary_touch_is_not_parallel OK ->", results)


def test_no_model_call_marked_unattributed():
    # 3주차 정확도 검증 중 발견한 버그의 회귀 테스트: model.call이 아예 없는 run은
    # 예전엔 결과에서 조용히 사라졌음(k-루프가 안 돌아서). 이제는 "unattributed"로
    # 명시적으로 남아야 함 — 그래야 비용 리포트 총합에서 이 도구 호출이 "왜 빠졌는지"
    # 나중에 감사(audit)할 수 있음.
    trace, parent = "trace-nomc", "run-nomc"
    spans = [
        mk_tool("t1", 0, 1, parent, trace, "toolA"),
    ]
    runs = group_runs(spans)
    results = classify_segments(runs)
    assert len(results) == 1, results
    assert results[0].pattern == "unattributed"
    assert results[0].approx_tokens is None
    print("test_no_model_call_marked_unattributed OK ->", results)


def test_missing_timestamp_flags_batch_confidence():
    # 3주차 정확도 검증 중 발견한 리스크의 회귀 테스트: tool.execution 스팬 중 하나라도
    # start/end가 없으면 _overlaps()가 항상 False를 반환해서, 실제로는 병렬인데
    # batch로 오분류될 수 있음. 최소한 note에 경고가 남아야 함(자신있게 batch로 단정 X).
    trace, parent = "trace-missing-ts", "run-missing-ts"
    spans = [
        mk_model_call("m1", 0, 2, parent, trace, in_tok=1000, out_tok=50),
        mk_tool("t1", 2, 3, parent, trace, "toolA"),
        Span(  # 타임스탬프 파싱 실패를 흉내: end가 없음
            trace_id=trace, parent_id=parent, span_id="t2",
            name="openclaw.tool.execution", start=T0 + timedelta(seconds=2), end=None,
            attrs={"openclaw.toolName": "toolB"},
        ),
        mk_model_call("m2", 4, 6, parent, trace, in_tok=1600, out_tok=20),
    ]
    runs = group_runs(spans)
    results = classify_segments(runs)
    assert {r.pattern for r in results} == {"batch"}, results
    assert all("타임스탬프 누락" in r.note or "⚠" in r.note for r in results), results
    print("test_missing_timestamp_flags_batch_confidence OK ->", results)


def test_tool_after_last_model_call_is_unattributed():
    # 4주차 Go 이식 중 발견한 버그의 회귀 테스트: 마지막 model.call 뒤의 도구는
    # 비교할 다음 model.call이 없으므로 sequential/batch가 아니라 unattributed여야 함.
    trace, parent = "trace-tail", "run-tail"
    spans = [
        mk_model_call("m1", 0, 2, parent, trace, in_tok=1000, out_tok=50),
        mk_tool("t1", 2, 3, parent, trace, "toolA"),
    ]
    results = classify_segments(group_runs(spans))
    assert len(results) == 1, results
    assert results[0].pattern == "unattributed", results
    assert results[0].approx_tokens is None
    print("test_tool_after_last_model_call_is_unattributed OK ->", results)


def test_tool_started_during_model_call_is_unattributed():
    # 모델 응답 도중(첫 model.call 종료 전)에 시작한 도구는 어느 구간에도 안 들어감 —
    # 예전엔 결과에서 조용히 빠졌음. 이제 unattributed로 남아야 함.
    trace, parent = "trace-early", "run-early"
    spans = [
        mk_model_call("m1", 0, 2, parent, trace, in_tok=1000, out_tok=50),
        mk_tool("t1", 1, 3, parent, trace, "toolA"),
        mk_model_call("m2", 3, 5, parent, trace, in_tok=1300, out_tok=40),
    ]
    results = classify_segments(group_runs(spans))
    assert len(results) == 1, results
    assert results[0].pattern == "unattributed", results
    print("test_tool_started_during_model_call_is_unattributed OK ->", results)


def test_missing_start_with_timezone_aware_times_does_not_crash():
    # PR 리뷰 회귀 테스트: 실제 파서 결과처럼 UTC 시간대가 붙은 시각 사이에 시작 시각이
    # 없는 스팬이 하나 섞여도 정렬에서 TypeError가 나면 안 됨 (예전엔 datetime.min과 비교하다 중단).
    utc = timezone.utc
    base = datetime(2026, 9, 22, 10, 0, 0, tzinfo=utc)
    spans = [
        Span(trace_id="t", parent_id="r", span_id="m1", name="openclaw.model.call",
             start=base, end=base + timedelta(seconds=2),
             attrs={"openclaw.model_call.usage.input_tokens": 1000,
                    "openclaw.model_call.usage.output_tokens": 50}),
        Span(trace_id="t", parent_id="r", span_id="t1", name="openclaw.tool.execution",
             start=None, end=base + timedelta(seconds=3), attrs={"openclaw.toolName": "toolA"}),
        Span(trace_id="t", parent_id="r", span_id="m2", name="openclaw.model.call",
             start=base + timedelta(seconds=3), end=base + timedelta(seconds=5),
             attrs={"openclaw.model_call.usage.input_tokens": 1300,
                    "openclaw.model_call.usage.output_tokens": 40}),
    ]
    results = classify_segments(group_runs(spans))
    assert len(results) == 1 and results[0].pattern == "unattributed", results
    print("test_missing_start_with_timezone_aware_times_does_not_crash OK ->", results)


def test_model_recorded_for_pricing():
    # PR 리뷰 회귀 테스트: 비용 환산용 모델은 고정값이 아니라 구간을 닫는 다음 model.call의
    # 모델이어야 함. 다른 모델 단가표로 계산했을 때 그 모델 단가가 적용되는지 확인.
    trace, parent = "trace-model", "run-model"
    m1 = mk_model_call("m1", 0, 2, parent, trace, in_tok=1000, out_tok=50)
    m2 = mk_model_call("m2", 3, 5, parent, trace, in_tok=1300, out_tok=40)
    m2.attrs["openclaw.model"] = "claude-sonnet-x"
    m2.attrs["openclaw.provider"] = "anthropic"
    results = classify_segments(group_runs([m1, mk_tool("t1", 2, 3, parent, trace, "toolA"), m2]))
    r = results[0]
    assert (r.model, r.provider) == ("claude-sonnet-x", "anthropic"), r
    table = {"claude-sonnet-x": {"input": 3.0, "output": 15.0}}
    assert abs(apply_pricing(r.model, r.approx_tokens, pricing_table=table) - 250 * 3.0 / 1e6) < 1e-12
    print("test_model_recorded_for_pricing OK ->", r)


if __name__ == "__main__":
    test_missing_start_with_timezone_aware_times_does_not_crash()
    test_model_recorded_for_pricing()
    test_tool_after_last_model_call_is_unattributed()
    test_tool_started_during_model_call_is_unattributed()
    test_sequential()
    test_parallel()
    test_batch()
    test_negative_delta_flagged()
    test_boundary_touch_is_not_parallel()
    test_no_model_call_marked_unattributed()
    test_missing_timestamp_flags_batch_confidence()
    print("\n모든 테스트 통과")
