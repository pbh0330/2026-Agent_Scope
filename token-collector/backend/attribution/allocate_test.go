package attribution

import (
	"testing"
	"time"
)

// parallelRun은 model.call → 도구 len(calls)개 동시 실행 → model.call 구조의 run을 만든다.
func parallelRun(prevIn, prevOut, nextIn int64, calls ...string) []Span {
	t0 := time.Date(2026, 10, 6, 0, 0, 0, 0, time.UTC)
	ms := func(n int) time.Time { return t0.Add(time.Duration(n) * time.Millisecond) }
	spans := []Span{
		{TraceID: "t", ParentID: "run", SpanID: "m1", Name: SpanModelCall, Start: ms(0), End: ms(100),
			Attrs: map[string]any{AttrInputTokens: prevIn, AttrOutputTokens: prevOut, AttrModel: "claude-haiku-4-5"}},
		{TraceID: "t", ParentID: "run", SpanID: "m2", Name: SpanModelCall, Start: ms(1000), End: ms(1100),
			Attrs: map[string]any{AttrInputTokens: nextIn, AttrOutputTokens: int64(10), AttrModel: "claude-haiku-4-5"}},
	}
	for i, id := range calls {
		spans = append(spans, Span{TraceID: "t", ParentID: "run", SpanID: "s" + id, Name: SpanToolExec,
			Start: ms(200 + i), End: ms(500),
			Attrs: map[string]any{AttrToolName: "fs__read_text_file", AttrToolCallID: id}})
	}
	return spans
}

func byCall(rs []Result) map[string]Result {
	m := map[string]Result{}
	for _, r := range rs {
		m[r.ToolCallID] = r
	}
	return m
}

func TestClassifyRecordsSegmentDelta(t *testing.T) {
	rs := Classify(parallelRun(10000, 50, 13930, "a", "b"), Options{})
	for _, r := range rs {
		if r.Pattern != Parallel || !r.HasSegmentDelta || r.SegmentDelta != 3880 || r.HasTokens {
			t.Fatalf("병렬 구간 증가분 기록 오류: %+v", r)
		}
	}
}

func TestAllocateByCountsPreservesSum(t *testing.T) {
	rs := Classify(parallelRun(10000, 50, 13930, "a", "b"), Options{})
	got := byCall(AllocateByCounts(rs, map[string]int64{"a": 600, "b": 3265}))
	a, b := got["a"], got["b"]
	if !a.HasTokens || !b.HasTokens || a.AllocationMethod != AllocationTokenCount {
		t.Fatalf("배분 안 됨: %+v %+v", a, b)
	}
	if a.ApproxTokens+b.ApproxTokens != 3880 {
		t.Fatalf("합계 보존 실패: %d + %d", a.ApproxTokens, b.ApproxTokens)
	}
	// 3880×600/3865 = 602.3…, 3880×3265/3865 = 3277.6… → 최대 잔여 방식으로 602 / 3278
	if a.ApproxTokens != 602 || b.ApproxTokens != 3278 {
		t.Fatalf("배분값 오류: %d / %d", a.ApproxTokens, b.ApproxTokens)
	}
	if !a.HasCount || a.CountedTokens != 600 {
		t.Fatalf("근거 토큰 수 기록 오류: %+v", a)
	}
	// 원본 슬라이스는 그대로여야 한다.
	for _, r := range rs {
		if r.HasTokens {
			t.Fatal("입력 슬라이스가 수정됨")
		}
	}
}

func TestAllocateByCountsSkipsIncompleteSegment(t *testing.T) {
	rs := Classify(parallelRun(10000, 50, 13930, "a", "b", "c"), Options{})
	for _, r := range AllocateByCounts(rs, map[string]int64{"a": 600, "b": 3265}) {
		if r.HasTokens {
			t.Fatalf("토큰 수가 빠진 구간을 배분함: %+v", r)
		}
		if r.Note == "" {
			t.Fatal("사유 메모 없음")
		}
	}
}

func TestAllocateByCountsZeroSumAndNegative(t *testing.T) {
	rs := Classify(parallelRun(10000, 50, 13930, "a", "b"), Options{})
	for _, r := range AllocateByCounts(rs, map[string]int64{"a": 0, "b": 0}) {
		if r.HasTokens {
			t.Fatal("Σc=0인데 배분함")
		}
	}
	neg := Classify(parallelRun(10000, 50, 9000, "a", "b"), Options{})
	got := byCall(AllocateByCounts(neg, map[string]int64{"a": 10, "b": 30}))
	if !got["a"].HasTokens || got["a"].ApproxTokens+got["b"].ApproxTokens != 0 || !got["a"].NegativeDelta {
		t.Fatalf("음수 구간 처리 오류: %+v", got["a"])
	}
}

func TestAllocateByCountsLeavesSequential(t *testing.T) {
	rs := Classify(parallelRun(10000, 50, 10660, "a"), Options{})
	got := AllocateByCounts(rs, map[string]int64{"a": 999})
	if got[0].Pattern != Sequential || got[0].ApproxTokens != 610 || got[0].AllocationMethod != "" {
		t.Fatalf("순차 결과가 바뀜: %+v", got[0])
	}
}

func TestLargestRemainderManyTools(t *testing.T) {
	rs := Classify(parallelRun(0, 0, 1001, "a", "b", "c"), Options{})
	got := AllocateByCounts(rs, map[string]int64{"a": 1, "b": 1, "c": 1})
	var sum int64
	for _, r := range got {
		sum += r.ApproxTokens
	}
	if sum != 1001 {
		t.Fatalf("합계 %d", sum)
	}
}
