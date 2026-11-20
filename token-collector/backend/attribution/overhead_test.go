package attribution

import (
	"testing"
	"time"
)

// runOf는 trace 하나에 model.call → 도구 len(calls)개 → model.call 구간을 만든다(도구 1개면 순차).
func runOf(trace, model string, prevIn, prevOut, nextIn int64, calls ...string) []Span {
	t0 := time.Date(2026, 11, 5, 0, 0, 0, 0, time.UTC)
	ms := func(n int) time.Time { return t0.Add(time.Duration(n) * time.Millisecond) }
	spans := []Span{
		{TraceID: trace, ParentID: "run", SpanID: "m1", Name: SpanModelCall, Start: ms(0), End: ms(100),
			Attrs: map[string]any{AttrInputTokens: prevIn, AttrOutputTokens: prevOut, AttrModel: model}},
		{TraceID: trace, ParentID: "run", SpanID: "m2", Name: SpanModelCall, Start: ms(1000), End: ms(1100),
			Attrs: map[string]any{AttrInputTokens: nextIn, AttrOutputTokens: int64(10), AttrModel: model}},
	}
	for i, id := range calls {
		spans = append(spans, Span{TraceID: trace, ParentID: "run", SpanID: "s" + id, Name: SpanToolExec,
			Start: ms(200 + i), End: ms(500), Attrs: map[string]any{AttrToolName: "read", AttrToolCallID: id}})
	}
	return spans
}

// 11.05 PC 실측(OpenClaw 2026.9.6 + Haiku 5.5 직접 등록): 순차 USER 391(토큰 수 365), AGENTS 2,246(2,220),
// 병렬 두 파일 Δ 2,634. 고정분 k = 26 → 391 / 2,243(순차 대비 0% / −0.1%). 비율로만 나누면 372 / 2,262.
func TestAllocateOverheadFromSequential(t *testing.T) {
	const m = "claude-haiku-5-5"
	var spans []Span
	spans = append(spans, runOf("seq1", m, 20000, 69, 20460, "u1")...)       // Δ 391
	spans = append(spans, runOf("seq2", m, 20000, 72, 22318, "a1")...)       // Δ 2,246
	spans = append(spans, runOf("par", m, 23000, 178, 25812, "u2", "a2")...) // Δ 2,634
	counts := map[string]int64{"u1": 365, "a1": 2220, "u2": 365, "a2": 2220}
	rs := Classify(spans, Options{})

	est := EstimateOverheads(rs, counts)
	if o := est[m]; o.Tokens != 26 || o.Samples != 2 || o.Source != "sequential-median" {
		t.Fatalf("고정분 추정: %+v", o)
	}
	got := byCall(AllocateByCounts(rs, counts))
	u, a := got["u2"], got["a2"]
	if u.ApproxTokens != 391 || a.ApproxTokens != 2243 || u.ApproxTokens+a.ApproxTokens != 2634 {
		t.Fatalf("배분: %d / %d", u.ApproxTokens, a.ApproxTokens)
	}
	if u.AllocOverhead != 26 || !u.HasResidual || u.SegmentResidual != -3 {
		t.Fatalf("근거 기록: %+v", u)
	}
	if s := got["u1"]; s.ApproxTokens != 391 || s.AllocationMethod != "" {
		t.Fatalf("순차는 그대로: %+v", s)
	}
}

func TestAllocateOverheadDefaultAndFallback(t *testing.T) {
	// 순차 표본이 없으면 모델 기본값(Haiku 5.5 = 26)을 쓴다.
	rs := Classify(runOf("par", "claude-haiku-5-5", 23000, 178, 25812, "u", "a"), Options{})
	got := byCall(AllocateByCounts(rs, map[string]int64{"u": 365, "a": 2220}))
	if got["u"].ApproxTokens != 391 || got["a"].ApproxTokens != 2243 || got["u"].AllocOverhead != 26 {
		t.Fatalf("기본값 배분: %+v", got)
	}
	// 구간 증가분이 결과 수×k보다 작으면 k 없이 비율로만 나눈다(합계 보존).
	rs = Classify(runOf("tiny", "claude-haiku-5-5", 1000, 10, 1050, "x", "y"), Options{})
	got = byCall(AllocateByCounts(rs, map[string]int64{"x": 10, "y": 30}))
	x, y := got["x"], got["y"]
	if x.AllocOverhead != 0 || x.ApproxTokens+y.ApproxTokens != 40 || x.ApproxTokens != 10 {
		t.Fatalf("작은 구간: %+v %+v", x, y)
	}
	// 표에 없는 모델은 k = 0(10.29까지와 같은 비율 배분).
	rs = Classify(runOf("other", "some-model", 10000, 50, 13930, "a", "b"), Options{})
	got = byCall(AllocateByCounts(rs, map[string]int64{"a": 600, "b": 3265}))
	if got["a"].ApproxTokens != 602 || got["a"].AllocOverhead != 0 {
		t.Fatalf("기본값 없음: %+v", got["a"])
	}
}

func TestEstimateOverheadsSkipsTinyAndNegative(t *testing.T) {
	const m = "claude-haiku-5-5"
	var spans []Span
	spans = append(spans, runOf("tiny", m, 1000, 80, 1090, "e")...)   // exec "hello": Δ 10, 토큰 수 0 → 제외
	spans = append(spans, runOf("think", m, 1000, 138, 3042, "t")...) // 생각을 많이 한 구간: Δ 1,904 < 토큰 수 → 제외
	spans = append(spans, runOf("ok1", m, 1000, 70, 1490, "o1")...)   // Δ 420, 토큰 수 390 → 30
	spans = append(spans, runOf("ok2", m, 1000, 70, 1650, "o2")...)   // Δ 580, 토큰 수 554 → 26
	spans = append(spans, runOf("ok3", m, 1000, 70, 1800, "o3")...)   // Δ 730, 토큰 수 702 → 28
	rs := Classify(spans, Options{})
	est := EstimateOverheads(rs, map[string]int64{"e": 0, "t": 1920, "o1": 390, "o2": 554, "o3": 702})
	if o := est[m]; o.Tokens != 28 || o.Samples != 3 {
		t.Fatalf("표본 거르기: %+v", o)
	}
}
