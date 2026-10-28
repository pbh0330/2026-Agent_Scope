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
	// CountWait: 병렬·배치 구간을 닫는 model.call 도착(+Grace) 뒤, 구간 도구들의 결과별 토큰 수
	// (결과 기록 플러그인이 보내는 agentscope.tool_result.count 스팬)를 기다리는 최대 시간.
	// 다 모이면 바로 배분해 확정하고, 이 시간이 지나도 모자라면 배분 없이 확정한다.
	// 0이면 기다리지 않는다(그 시점에 가진 토큰 수로만 배분).
	CountWait time.Duration
	// CountTTL: 받은 결과별 토큰 수를 보관하는 시간(도구 스팬보다 먼저 도착할 수 있음). 0이면 10분.
	CountTTL time.Duration
	Options  Options
}

// DefaultTrackerConfig는 기본 설정이다.
func DefaultTrackerConfig() TrackerConfig {
	return TrackerConfig{Grace: 2 * time.Second, RunIdleTimeout: 10 * time.Minute, MaxRuns: 10000}
}

// maxCounts는 보관하는 결과별 토큰 수의 상한(메모리 보호). 넘으면 오래된 것부터 지운다.
const maxCounts = 100000

type countEntry struct {
	tokens  int64
	partial bool // 결과 일부(이미지 등)를 세지 못한 값: 배분에 쓰지 않고, 기다리지도 않는다
	at      time.Time
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

	// 결과별 토큰 수(tool_call_id 기준). usable은 AllocateByCounts에 그대로 넘기는 사본.
	counts map[string]countEntry
	usable map[string]int64
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
	if cfg.CountWait < 0 {
		cfg.CountWait = 0
	}
	if cfg.CountTTL <= 0 {
		cfg.CountTTL = 10 * time.Minute
	}
	return &Tracker{cfg: cfg, runs: map[RunKey]*runState{}, completed: map[RunKey]time.Time{},
		counts: map[string]countEntry{}, usable: map[string]int64{}}
}

// AddCount는 도구 결과 하나의 토큰 수(토큰 계산 API로 센 값)를 넣는다. 도구 스팬보다 먼저 와도 된다.
// partial이면 결과 일부만 센 값이라 배분에 쓰지 않고, 그 구간은 기다리지 않고 배분 없이 확정한다.
// 같은 tool_call_id가 다시 오면(재전송) 마지막 값을 쓴다.
func (t *Tracker) AddCount(toolCallID string, tokens int64, partial bool, now time.Time) {
	if toolCallID == "" || tokens < 0 {
		return
	}
	t.mu.Lock()
	defer t.mu.Unlock()
	t.counts[toolCallID] = countEntry{tokens: tokens, partial: partial, at: now}
	if partial {
		delete(t.usable, toolCallID)
	} else {
		t.usable[toolCallID] = tokens
	}
}

// pruneCounts는 보관 기간이 지난 토큰 수를 지우고, 개수도 maxCounts 이내로 유지한다.
func (t *Tracker) pruneCounts(now time.Time) {
	for id, c := range t.counts {
		if now.Sub(c.at) >= t.cfg.CountTTL {
			delete(t.counts, id)
			delete(t.usable, id)
		}
	}
	if over := len(t.counts) - maxCounts; over > 0 {
		ids := make([]string, 0, len(t.counts))
		for id := range t.counts {
			ids = append(ids, id)
		}
		sort.Slice(ids, func(i, j int) bool { return t.counts[ids[i]].at.Before(t.counts[ids[j]].at) })
		for _, id := range ids[:over] {
			delete(t.counts, id)
			delete(t.usable, id)
		}
	}
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
		ended := !st.endedAt.IsZero() && now.Sub(st.endedAt) >= t.cfg.Grace
		forced := now.Sub(st.lastSeen) >= t.cfg.RunIdleTimeout
		rs, waiting := t.collect(st, now, ended, forced)
		out = append(out, rs...)
		// run이 끝났어도 결과별 토큰 수를 기다리는 병렬·배치 구간이 있으면 메모리에 남겨 둔다(최대 CountWait).
		if forced || (ended && !waiting) {
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
			rs, _ := t.collect(st, now, true, true)
			out = append(out, rs...)
			t.complete(st.key, now)
		}
	}
	t.pruneCompleted(now)
	t.pruneCounts(now)
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

// collect는 run에서 지금 확정할 수 있는 도구 결과를 돌려준다. waiting은 아직 확정하지 않은 결과가
// 남았는지(결과별 토큰 수를 기다리는 병렬·배치 구간 등)이다.
//
//   - 순차·귀속 불가: 닫는 model.call 도착 + Grace 뒤, 또는 run 종료(ended) 시 확정(기존과 같음)
//   - 병렬·배치: 구간 단위로 함께 확정. 닫는 model.call 도착 + Grace 뒤에
//     구간 도구의 토큰 수가 다 모였거나(→ 배분) 기다릴 필요가 없으면(일부만 센 값, 구간 증가분 없음)
//     바로, 아니면 CountWait까지 기다렸다가 배분 없이 확정한다. run이 끝나도 이 대기는 유지한다.
//   - forced(유휴 시간 초과·메모리 상한): 기다리지 않고 지금 가진 값으로 확정
func (t *Tracker) collect(st *runState, now time.Time, ended, forced bool) ([]Result, bool) {
	results := ClassifyRun(st.key, st.spans, t.cfg.Options)
	if len(t.usable) > 0 {
		results = AllocateByCounts(results, t.usable)
	}

	// 병렬·배치 구간별 확정 가능 여부
	segReady := map[segKey]bool{}
	segments := map[segKey][]Result{}
	for _, r := range results {
		if (r.Pattern == Parallel || r.Pattern == Batch) && r.ClosingModelSpanID != "" {
			k := segKey{r.TraceID, r.RunID, r.ClosingModelSpanID}
			segments[k] = append(segments[k], r)
		}
	}
	for k, members := range segments {
		if forced {
			segReady[k] = true
			continue
		}
		closingAt, ok := st.arrival[k.closing]
		if !ok || (!ended && now.Sub(closingAt) < t.cfg.Grace) {
			continue
		}
		noWait := !members[0].HasSegmentDelta || t.cfg.CountWait <= 0
		allCounted := true
		for _, m := range members {
			if c, has := t.counts[m.ToolCallID]; has && c.partial {
				noWait = true
			}
			if !m.HasCount {
				allCounted = false
			}
		}
		segReady[k] = noWait || allCounted || now.Sub(closingAt) >= t.cfg.Grace+t.cfg.CountWait
	}

	var out []Result
	waiting := false
	for _, r := range results {
		if st.emitted[r.ToolSpanID] {
			continue
		}
		var final bool
		if (r.Pattern == Parallel || r.Pattern == Batch) && r.ClosingModelSpanID != "" {
			final = segReady[segKey{r.TraceID, r.RunID, r.ClosingModelSpanID}]
		} else {
			final = ended || forced
			if !final && r.ClosingModelSpanID != "" {
				if at, ok := st.arrival[r.ClosingModelSpanID]; ok && now.Sub(at) >= t.cfg.Grace {
					final = true
				}
			}
		}
		if final {
			st.emitted[r.ToolSpanID] = true
			out = append(out, r)
		} else {
			waiting = true
		}
	}
	return out, waiting
}

// PendingCounts는 보관 중인 결과별 토큰 수 개수(모니터링·테스트용).
func (t *Tracker) PendingCounts() int {
	t.mu.Lock()
	defer t.mu.Unlock()
	return len(t.counts)
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
