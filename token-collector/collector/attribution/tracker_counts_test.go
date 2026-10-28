package attribution

import (
	"testing"
	"time"
)

// 병렬 구간 하나(도구 a·b가 겹침)를 만든다. 구간 증가분 = 1500 - 1000 - 100 = 400.
func toolc(id string, start, end float64, name, callID string) Span {
	s := tool(id, start, end, name)
	s.Attrs[AttrToolCallID] = callID
	return s
}

func addParallelRun(tr *Tracker, at time.Time) {
	tr.Add(mc("m1", 0, 1, 1000, 100), at)
	tr.Add(toolc("ta", 1, 3, "read", "call-a"), at)
	tr.Add(toolc("tb", 1.5, 2.5, "ls", "call-b"), at)
	tr.Add(mc("m2", 3, 4, 1500, 20), at)
}

func countCfg() TrackerConfig {
	return TrackerConfig{Grace: time.Second, CountWait: 15 * time.Second, RunIdleTimeout: 10 * time.Minute}
}

func byCallID(rs []Result) map[string]Result {
	m := map[string]Result{}
	for _, r := range rs {
		m[r.ToolCallID] = r
	}
	return m
}

// 토큰 수가 도구 스팬보다 먼저 와도, 닫는 model.call + Grace 뒤에 바로 배분해 확정한다.
func TestTrackerCountsBeforeSpansAllocateImmediately(t *testing.T) {
	tr := NewTracker(countCfg())
	tr.AddCount("call-a", 300, false, t0)
	tr.AddCount("call-b", 100, false, t0)
	addParallelRun(tr, t0)
	if rs := tr.Flush(t0.Add(500 * time.Millisecond)); len(rs) != 0 {
		t.Fatalf("grace 전에는 확정하지 않음: %+v", rs)
	}
	rs := byCallID(tr.Flush(t0.Add(time.Second)))
	if len(rs) != 2 || rs["call-a"].ApproxTokens != 300 || rs["call-b"].ApproxTokens != 100 {
		t.Fatalf("got %+v", rs)
	}
	for _, r := range rs {
		if !r.HasTokens || r.AllocationMethod != AllocationTokenCount || r.Pattern != Parallel {
			t.Fatalf("배분 결과가 아님: %+v", r)
		}
	}
}

// 토큰 수가 늦게 오면 CountWait 안에서는 기다렸다가, 다 모이는 순간 배분해 확정한다.
func TestTrackerWaitsForLateCounts(t *testing.T) {
	tr := NewTracker(countCfg())
	addParallelRun(tr, t0)
	tr.AddCount("call-a", 300, false, t0.Add(2*time.Second))
	if rs := tr.Flush(t0.Add(3 * time.Second)); len(rs) != 0 {
		t.Fatalf("한 도구 토큰 수가 아직 없으면 기다려야 함: %+v", rs)
	}
	tr.AddCount("call-b", 100, false, t0.Add(4*time.Second))
	rs := byCallID(tr.Flush(t0.Add(4 * time.Second)))
	if rs["call-a"].ApproxTokens != 300 || rs["call-b"].ApproxTokens != 100 {
		t.Fatalf("got %+v", rs)
	}
}

// CountWait가 지나도 모자라면 배분 없이 확정한다(지금까지와 같이 호출 수·시간만).
func TestTrackerCountWaitExpires(t *testing.T) {
	tr := NewTracker(countCfg())
	addParallelRun(tr, t0)
	tr.AddCount("call-a", 300, false, t0)
	if rs := tr.Flush(t0.Add(15 * time.Second)); len(rs) != 0 {
		t.Fatalf("Grace+CountWait(16s) 전에는 기다려야 함: %+v", rs)
	}
	rs := tr.Flush(t0.Add(16 * time.Second))
	if len(rs) != 2 {
		t.Fatalf("got %+v", rs)
	}
	for _, r := range rs {
		if r.HasTokens || r.AllocationMethod != "" {
			t.Fatalf("일부만 있으면 배분하면 안 됨: %+v", r)
		}
	}
}

// run이 끝나도(openclaw.run 도착) 토큰 수를 기다리는 구간이 있으면 run을 지우지 않고 기다린다.
func TestTrackerRunEndKeepsWaitingForCounts(t *testing.T) {
	tr := NewTracker(countCfg())
	addParallelRun(tr, t0)
	tr.Add(Span{TraceID: "tr", SpanID: "run", Name: SpanRun}, t0)
	if rs := tr.Flush(t0.Add(2 * time.Second)); len(rs) != 0 {
		t.Fatalf("got %+v", rs)
	}
	if tr.PendingRuns() != 1 {
		t.Fatalf("기다리는 동안 run을 지우면 안 됨")
	}
	tr.AddCount("call-a", 300, false, t0.Add(3*time.Second))
	tr.AddCount("call-b", 100, false, t0.Add(3*time.Second))
	rs := byCallID(tr.Flush(t0.Add(3 * time.Second)))
	if rs["call-a"].ApproxTokens != 300 || rs["call-b"].ApproxTokens != 100 {
		t.Fatalf("got %+v", rs)
	}
	if tr.PendingRuns() != 0 {
		t.Fatalf("다 확정한 run은 지워야 함")
	}
}

// 결과 일부만 센 값(이미지 등)이 있으면 기다리지 않고 배분 없이 확정한다.
func TestTrackerPartialCountFinalizesWithoutAllocation(t *testing.T) {
	tr := NewTracker(countCfg())
	tr.AddCount("call-a", 300, false, t0)
	tr.AddCount("call-b", 5, true, t0)
	addParallelRun(tr, t0)
	rs := tr.Flush(t0.Add(time.Second))
	if len(rs) != 2 {
		t.Fatalf("got %+v", rs)
	}
	for _, r := range rs {
		if r.HasTokens {
			t.Fatalf("일부만 센 도구가 있는 구간은 배분하지 않음: %+v", r)
		}
	}
}

// 유휴 시간 초과(forced)면 기다리지 않는다.
func TestTrackerIdleForcesFinalization(t *testing.T) {
	cfg := countCfg()
	cfg.RunIdleTimeout = 5 * time.Second
	tr := NewTracker(cfg)
	addParallelRun(tr, t0)
	if rs := tr.Flush(t0.Add(5 * time.Second)); len(rs) != 2 {
		t.Fatalf("got %+v", rs)
	}
	if tr.PendingRuns() != 0 {
		t.Fatalf("run left")
	}
}

// 순차 구간은 토큰 수와 상관없이 지금처럼 확정한다.
func TestTrackerSequentialUnaffectedByCountWait(t *testing.T) {
	tr := NewTracker(countCfg())
	tr.Add(mc("m1", 0, 1, 1000, 100), t0)
	tr.Add(toolc("ta", 1, 2, "read", "call-a"), t0)
	tr.Add(mc("m2", 2, 3, 1300, 20), t0)
	rs := tr.Flush(t0.Add(time.Second))
	if len(rs) != 1 || rs[0].Pattern != Sequential || rs[0].ApproxTokens != 200 {
		t.Fatalf("got %+v", rs)
	}
}

// 토큰 수는 CountTTL 뒤에 지운다. 재전송된 값은 마지막 값을 쓴다.
func TestTrackerCountTTLAndOverwrite(t *testing.T) {
	cfg := countCfg()
	cfg.CountTTL = time.Minute
	tr := NewTracker(cfg)
	tr.AddCount("x", 10, false, t0)
	tr.AddCount("x", 12, false, t0.Add(time.Second))
	tr.AddCount("", 5, false, t0)
	tr.AddCount("neg", -1, false, t0)
	if tr.PendingCounts() != 1 {
		t.Fatalf("counts=%d", tr.PendingCounts())
	}
	tr.Flush(t0.Add(30 * time.Second))
	if tr.PendingCounts() != 1 {
		t.Fatalf("TTL 전에 지우면 안 됨")
	}
	tr.Flush(t0.Add(61 * time.Second))
	if tr.PendingCounts() != 0 {
		t.Fatalf("TTL 뒤에는 지워야 함")
	}
}

func TestToolResultCountSpan(t *testing.T) {
	s := Span{Name: SpanToolResultCount, Attrs: map[string]any{AttrToolCallID: "c1", AttrCountedTokens: int64(42), AttrCountSkippedBlocks: int64(0)}}
	if id, n, partial, ok := ToolResultCount(s); !ok || id != "c1" || n != 42 || partial {
		t.Fatalf("got %v %v %v %v", id, n, partial, ok)
	}
	s.Attrs[AttrCountSkippedBlocks] = int64(1)
	if _, _, partial, ok := ToolResultCount(s); !ok || !partial {
		t.Fatalf("partial 표시가 안 됨")
	}
	if _, _, _, ok := ToolResultCount(Span{Name: SpanToolExec}); ok {
		t.Fatalf("다른 스팬은 무시")
	}
	if _, _, _, ok := ToolResultCount(Span{Name: SpanToolResultCount, Attrs: map[string]any{AttrToolCallID: "c1"}}); ok {
		t.Fatalf("토큰 수 없으면 무시")
	}
}
