package attribution

import (
	"sort"
	"sync"
	"time"
)

// TrackerConfig는 실시간(스트리밍) 귀속 설정이다.
type TrackerConfig struct {
	// Grace: 구간을 닫는 model.call(또는 openclaw.run)이 도착한 뒤 늦게 오는 도구 스팬을
	// 기다리는 시간. 도구 스팬은 다음 model.call보다 먼저 끝나므로 보통 같은 전송 묶음이나
	// 그 이전에 도착하지만, 전송 순서가 뒤바뀌는 경우를 대비한 여유분이다.
	Grace time.Duration
	// RunIdleTimeout: 이 시간 동안 새 스팬이 없으면 openclaw.run 스팬을 못 받았더라도 run을
	// 끝난 것으로 보고 남은 도구를 확정(unattributed 포함)한 뒤 메모리에서 지운다.
	RunIdleTimeout time.Duration
	// MaxRuns: 동시에 들고 있는 run 수 상한. 넘으면 가장 오래 조용한 run부터 확정·삭제한다.
	MaxRuns int
	// CompletedRetention: 확정·삭제한 run의 식별자를 기억해 두는 시간. 이 안에 같은 run의
	// 스팬이 다시 들어오면(Collector·SDK 재전송 등) 새 run으로 세지 않고 버린다.
	// 0이면 RunIdleTimeout과 30분 중 큰 값.
	CompletedRetention time.Duration
	Options            Options
}

// DefaultTrackerConfig는 기본 설정이다.
func DefaultTrackerConfig() TrackerConfig {
	return TrackerConfig{Grace: 2 * time.Second, RunIdleTimeout: 10 * time.Minute, MaxRuns: 10000}
}

type runState struct {
	key      RunKey
	spans    []Span
	seen     map[string]bool      // 중복 수신(재전송) 방지
	arrival  map[string]time.Time // spanID -> 커넥터 도착 시각
	emitted  map[string]bool      // 이미 확정한 도구 spanID
	lastSeen time.Time
	endedAt  time.Time // openclaw.run 스팬 도착 시각(zero = 아직)
}

// Tracker는 스팬을 도착하는 대로 받아 run별로 모으고, 확정 가능한 도구 구간의 결과를
// Flush 때마다 내보낸다. 판정 자체는 매번 ClassifyRun으로 run 전체를 다시 계산하므로
// 오프라인 분석(Classify)과 결과가 같다.
//
// 도구 결과가 확정되는 시점:
//   - 그 구간을 닫는 다음 model.call이 도착하고 Grace가 지났을 때
//   - openclaw.run 스팬이 도착하고 Grace가 지났을 때(나머지 전부, 꼬리 도구는 unattributed)
//   - RunIdleTimeout 동안 새 스팬이 없을 때(나머지 전부)
type Tracker struct {
	mu   sync.Mutex
	cfg  TrackerConfig
	runs map[RunKey]*runState
	// completed: 이미 확정·삭제한 run → 삭제 시각. 삭제 후 같은 스팬 묶음이 재전송되면
	// 새 run으로 다시 집계되던 문제(PR 리뷰)를 막는다.
	completed map[RunKey]time.Time
	dropped   uint64 // 완료된 run으로 늦게(또는 중복으로) 들어와 버린 스팬 수
}

// NewTracker는 Tracker를 만든다. 0인 설정값은 기본값으로 채운다.
func NewTracker(cfg TrackerConfig) *Tracker {
	d := DefaultTrackerConfig()
	if cfg.Grace <= 0 {
		cfg.Grace = d.Grace
	}
	if cfg.RunIdleTimeout <= 0 {
		cfg.RunIdleTimeout = d.RunIdleTimeout
	}
	if cfg.MaxRuns <= 0 {
		cfg.MaxRuns = d.MaxRuns
	}
	if cfg.CompletedRetention <= 0 {
		cfg.CompletedRetention = 30 * time.Minute
		if cfg.RunIdleTimeout > cfg.CompletedRetention {
			cfg.CompletedRetention = cfg.RunIdleTimeout
		}
	}
	return &Tracker{cfg: cfg, runs: map[RunKey]*runState{}, completed: map[RunKey]time.Time{}}
}

func (t *Tracker) state(k RunKey, now time.Time) *runState {
	st, ok := t.runs[k]
	if !ok {
		st = &runState{key: k, seen: map[string]bool{}, arrival: map[string]time.Time{}, emitted: map[string]bool{}}
		t.runs[k] = st
	}
	st.lastSeen = now
	return st
}

// Add는 스팬 하나를 넣는다. 관련 없는 스팬 이름은 무시한다.
func (t *Tracker) Add(s Span, now time.Time) {
	t.mu.Lock()
	defer t.mu.Unlock()
	var k RunKey
	switch s.Name {
	case SpanModelCall, SpanToolExec:
		k = RunKey{TraceID: s.TraceID, RunID: s.ParentID}
	case SpanRun:
		k = RunKey{TraceID: s.TraceID, RunID: s.SpanID}
	default:
		return
	}
	if _, done := t.completed[k]; done {
		t.dropped++
		return
	}
	switch s.Name {
	case SpanModelCall, SpanToolExec:
		st := t.state(k, now)
		if st.seen[s.SpanID] {
			return
		}
		st.seen[s.SpanID] = true
		st.arrival[s.SpanID] = now
		st.spans = append(st.spans, s)
	case SpanRun:
		st := t.state(k, now)
		if st.endedAt.IsZero() {
			st.endedAt = now
		}
	}
}

// Flush는 지금 확정 가능한 도구 결과를 돌려주고, 끝난 run은 메모리에서 지운다.
func (t *Tracker) Flush(now time.Time) []Result {
	t.mu.Lock()
	defer t.mu.Unlock()

	var out []Result
	for k, st := range t.runs {
		done := (!st.endedAt.IsZero() && now.Sub(st.endedAt) >= t.cfg.Grace) ||
			now.Sub(st.lastSeen) >= t.cfg.RunIdleTimeout
		out = append(out, t.collect(st, now, done)...)
		if done {
			t.complete(k, now)
		}
	}

	if over := len(t.runs) - t.cfg.MaxRuns; over > 0 {
		states := make([]*runState, 0, len(t.runs))
		for _, st := range t.runs {
			states = append(states, st)
		}
		sort.Slice(states, func(i, j int) bool { return states[i].lastSeen.Before(states[j].lastSeen) })
		for _, st := range states[:over] {
			out = append(out, t.collect(st, now, true)...)
			t.complete(st.key, now)
		}
	}
	t.pruneCompleted(now)
	return out
}

// complete는 run을 메모리에서 지우고, 재전송에 대비해 식별자를 기억해 둔다.
func (t *Tracker) complete(k RunKey, now time.Time) {
	delete(t.runs, k)
	t.completed[k] = now
}

// pruneCompleted는 보관 기간이 지난 완료 기록을 지우고, 개수도 MaxRuns 이내로 유지한다.
func (t *Tracker) pruneCompleted(now time.Time) {
	for k, at := range t.completed {
		if now.Sub(at) >= t.cfg.CompletedRetention {
			delete(t.completed, k)
		}
	}
	if over := len(t.completed) - t.cfg.MaxRuns; over > 0 {
		keys := make([]RunKey, 0, len(t.completed))
		for k := range t.completed {
			keys = append(keys, k)
		}
		sort.Slice(keys, func(i, j int) bool { return t.completed[keys[i]].Before(t.completed[keys[j]]) })
		for _, k := range keys[:over] {
			delete(t.completed, k)
		}
	}
}

func (t *Tracker) collect(st *runState, now time.Time, done bool) []Result {
	var out []Result
	for _, r := range ClassifyRun(st.key, st.spans, t.cfg.Options) {
		if st.emitted[r.ToolSpanID] {
			continue
		}
		final := done
		if !final && r.ClosingModelSpanID != "" {
			if at, ok := st.arrival[r.ClosingModelSpanID]; ok && now.Sub(at) >= t.cfg.Grace {
				final = true
			}
		}
		if final {
			st.emitted[r.ToolSpanID] = true
			out = append(out, r)
		}
	}
	return out
}

// DroppedSpans는 이미 완료된 run으로 들어와서 버린 스팬 수(누적, 모니터링용).
func (t *Tracker) DroppedSpans() uint64 {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.dropped
}

// PendingRuns는 아직 메모리에 있는 run 수(모니터링·테스트용).
func (t *Tracker) PendingRuns() int {
	t.mu.Lock()
	defer t.mu.Unlock()
	return len(t.runs)
}
