"""
attribution.py의 패턴 판별 로직(순차/병렬/배치) 단위 테스트.

실제 캡처 로그(otel-debug-log.txt)에는 순차 사례 1건밖에 없어서, 병렬/배치 분기는
검증되지 않은 채로 남아있었음. 여기서는 합성(synthetic) Span으로 세 패턴을 모두 만들어
classify_segments()가 각각을 올바르게 분류하는지 확인한다.
"""

from datetime import datetime, timedelta

from otel_log_parser import Span
from attribution import classify_segments, group_runs

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


if __name__ == "__main__":
    test_sequential()
    test_parallel()
    test_batch()
    test_negative_delta_flagged()
    print("\n모든 테스트 통과")
