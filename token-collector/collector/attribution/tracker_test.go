package attribution

import (
	"path/filepath"
	"testing"
	"time"
)

// 실제 로그를 "받은 순서대로" 한 스팬씩 넣으면서 Flush를 반복해도, 최종 결과가
// 오프라인 판정(=파이썬)과 같아야 한다. 스트리밍 확정 로직이 판정을 바꾸지 않는지 확인.
func TestTrackerStreamingMatchesPython(t *testing.T) {
	for _, name := range fixtures {
		t.Run(name, func(t *testing.T) {
			spans := loadFixtureSpans(t, filepath.Join("testdata", name+".spans.json"))
			want := loadExpected(t, filepath.Join("testdata", name+".expected.json"))

			tr := NewTracker(TrackerConfig{Grace: time.Second})
			now := t0
			var got []Result
			for _, s := range spans {
				now = now.Add(100 * time.Millisecond)
				tr.Add(s, now)
				got = append(got, tr.Flush(now)...)
			}
			now = now.Add(2 * time.Second)
			got = append(got, tr.Flush(now)...)

			compareToPython(t, got, want)
			if n := tr.PendingRuns(); n != 0 {
				t.Fatalf("runs left in memory: %d", n)
			}
		})
	}
}

// 순차 구간은 다음 model.call 도착 + Grace 뒤에 확정되고, 꼬리 도구는 run이 끝나야 확정된다.
func TestTrackerFinalizationTiming(t *testing.T) {
	tr := NewTracker(TrackerConfig{Grace: time.Second, RunIdleTimeout: time.Minute})
	base := t0
	tr.Add(mc("m1", 0, 2, 1000, 50), base)
	tr.Add(tool("t1", 2, 3, "toolA"), base)
	if rs := tr.Flush(base.Add(5 * time.Second)); len(rs) != 0 {
		t.Fatalf("t1 must wait for next model.call, got %+v", rs)
	}
	tr.Add(mc("m2", 3, 5, 1300, 40), base.Add(6*time.Second))
	if rs := tr.Flush(base.Add(6*time.Second + 500*time.Millisecond)); len(rs) != 0 {
		t.Fatalf("must wait grace, got %+v", rs)
	}
	rs := tr.Flush(base.Add(7 * time.Second))
	if len(rs) != 1 || rs[0].Pattern != Sequential || rs[0].ApproxTokens != 250 {
		t.Fatalf("got %+v", rs)
	}
	// 꼬리 도구: 다음 model.call 없음 → run 종료 스팬 도착 + grace 뒤 unattributed
	tr.Add(tool("t2", 5, 6, "toolB"), base.Add(8*time.Second))
	if rs := tr.Flush(base.Add(20 * time.Second)); len(rs) != 0 {
		t.Fatalf("tail must wait for run end, got %+v", rs)
	}
	tr.Add(Span{TraceID: "tr", SpanID: "run", Name: SpanRun}, base.Add(21*time.Second))
	rs = tr.Flush(base.Add(22 * time.Second))
	if len(rs) != 1 || rs[0].ToolSpanID != "t2" || rs[0].Pattern != Unattributed {
		t.Fatalf("got %+v", rs)
	}
	if tr.PendingRuns() != 0 {
		t.Fatal("run should be removed after end")
	}
}

func TestTrackerIdleTimeoutAndDedup(t *testing.T) {
	tr := NewTracker(TrackerConfig{Grace: time.Second, RunIdleTimeout: time.Minute})
	tr.Add(mc("m1", 0, 2, 1000, 50), t0)
	tr.Add(tool("t1", 2, 3, "toolA"), t0)
	tr.Add(tool("t1", 2, 3, "toolA"), t0) // 재전송된 중복 스팬
	rs := tr.Flush(t0.Add(2 * time.Minute))
	if len(rs) != 1 || rs[0].Pattern != Unattributed {
		t.Fatalf("got %+v", rs)
	}
	if tr.PendingRuns() != 0 {
		t.Fatal("idle run should be removed")
	}
}

func TestTrackerMaxRuns(t *testing.T) {
	tr := NewTracker(TrackerConfig{Grace: time.Second, RunIdleTimeout: time.Hour, MaxRuns: 1})
	a := tool("t1", 0, 1, "toolA")
	a.ParentID = "runA"
	b := tool("t2", 0, 1, "toolB")
	b.ParentID = "runB"
	tr.Add(a, t0)
	tr.Add(b, t0.Add(time.Second))
	rs := tr.Flush(t0.Add(2 * time.Second))
	if len(rs) != 1 || rs[0].ToolSpanID != "t1" || tr.PendingRuns() != 1 {
		t.Fatalf("oldest run should be evicted, got %+v pending=%d", rs, tr.PendingRuns())
	}
}

// PR 리뷰 회귀 테스트: 완료·삭제된 run의 스팬 묶음이 통째로 재전송돼도 다시 집계되면 안 된다.
// (기존 중복 테스트는 삭제 전 재수신만 확인했음)
func TestTrackerReplayAfterCompletionIsIgnored(t *testing.T) {
	for _, name := range fixtures {
		t.Run(name, func(t *testing.T) {
			spans := loadFixtureSpans(t, filepath.Join("testdata", name+".spans.json"))
			tr := NewTracker(TrackerConfig{Grace: time.Second})
			now := t0
			var first []Result
			for _, s := range spans {
				tr.Add(s, now)
			}
			now = now.Add(2 * time.Second)
			first = tr.Flush(now)
			if len(first) == 0 || tr.PendingRuns() != 0 {
				t.Fatalf("first pass: results=%d pending=%d", len(first), tr.PendingRuns())
			}
			// 같은 묶음 재전송
			for _, s := range spans {
				tr.Add(s, now)
			}
			now = now.Add(15 * time.Minute) // 재전송분이 새 run으로 남았다면 idle 만료(10분)로 확정됐을 시점
			if again := tr.Flush(now); len(again) != 0 {
				t.Fatalf("replayed spans were counted again: %d results", len(again))
			}
			if tr.DroppedSpans() == 0 {
				t.Fatal("dropped counter should record the replay")
			}
		})
	}
}

// 보관 기간이 지나면 완료 기록은 지워져 메모리가 계속 늘지 않는다.
func TestTrackerCompletedRetentionPrunes(t *testing.T) {
	tr := NewTracker(TrackerConfig{Grace: time.Second, RunIdleTimeout: time.Minute, CompletedRetention: 10 * time.Minute})
	tr.Add(tool("t1", 0, 1, "toolA"), t0)
	tr.Flush(t0.Add(2 * time.Minute)) // idle 만료로 완료
	tr.Add(tool("t1", 0, 1, "toolA"), t0.Add(3*time.Minute))
	if tr.DroppedSpans() != 1 || tr.PendingRuns() != 0 {
		t.Fatalf("within retention the span must be dropped: dropped=%d pending=%d", tr.DroppedSpans(), tr.PendingRuns())
	}
	tr.Flush(t0.Add(20 * time.Minute))
	tr.mu.Lock()
	n := len(tr.completed)
	tr.mu.Unlock()
	if n != 0 {
		t.Fatalf("completed records should be pruned after retention, got %d", n)
	}
}
