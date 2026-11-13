package attribution

import (
	"sort"
	"time"
)

// Options는 귀속 계산 옵션이다.
type Options struct {
	// IncludeCacheInPrompt가 true면 "프롬프트 토큰"을 input + cache_read + cache_creation으로
	// 본다. 프로바이더가 캐시 토큰을 input_tokens와 따로 보고하는 경우(예: Anthropic API
	// 직접 호출 + 프롬프트 캐싱)에 켜야 캐시 적중 시 음수 delta가 나오지 않는다.
	// 기본값 false = 파이썬 프로토타입과 동일(input_tokens만 사용).
	IncludeCacheInPrompt bool
}

const (
	noteNoModelCall  = "이 run에 openclaw.model.call 스팬이 없음 (도구 실행 후 모델 재호출 없이 종료됐거나 스팬 캡처 누락) — 귀속 불가"
	noteTail         = "마지막 model.call 뒤에 실행된 도구 — 다음 model.call이 없어 귀속 불가"
	noteMissingTok   = "model.call 스팬에 토큰 속성 누락 — 귀속 불가"
	noteNegDelta     = "delta<0 (컨텍스트 압축/요약 등으로 오히려 줄어든 구간 — 근사치 신뢰 낮음)"
	noteParBatch     = "병렬/배치 구간 — 결과별 토큰 수가 없어 duration_ms만 대리 지표로 기록, 토큰 귀속 안 함"
	noteMissingTs    = " | ⚠ 이 구간 도구 스팬 중 일부에 시작/종료 시각이 없어서 실제로는 병렬인데 batch로 오분류됐을 수 있음 — 원본 로그의 해당 스팬 캡처 여부 확인 필요"
	noteNotInSegment = "어느 model.call 구간에도 속하지 않음(모델 응답 도중 시작됐거나 시작 시각 누락) — 귀속 불가"
)

// RunKey는 run(=openclaw.run 스팬 하나)을 식별한다.
type RunKey struct {
	TraceID string
	RunID   string
}

// GroupRuns는 model.call / tool.execution 스팬을 부모(openclaw.run) 단위로 묶는다.
func GroupRuns(spans []Span) map[RunKey][]Span {
	runs := map[RunKey][]Span{}
	for _, s := range spans {
		if s.Name != SpanModelCall && s.Name != SpanToolExec {
			continue
		}
		k := RunKey{TraceID: s.TraceID, RunID: s.ParentID}
		runs[k] = append(runs[k], s)
	}
	return runs
}

// Classify는 여러 run을 한꺼번에 판정한다(오프라인 분석용).
func Classify(spans []Span, opts Options) []Result {
	var out []Result
	for k, group := range GroupRuns(spans) {
		out = append(out, ClassifyRun(k, group, opts)...)
	}
	return out
}

func overlaps(a, b Span) bool {
	if a.Start.IsZero() || a.End.IsZero() || b.Start.IsZero() || b.End.IsZero() {
		return false
	}
	return a.Start.Before(b.End) && b.Start.Before(a.End)
}

func (o Options) promptTokens(m Span) (int64, bool) {
	in, ok := m.Int(AttrInputTokens)
	if !ok {
		return 0, false
	}
	if o.IncludeCacheInPrompt {
		if cr, ok := m.Int(AttrCacheReadTokens); ok {
			in += cr
		}
		if cw, ok := m.Int(AttrCacheWriteToken); ok {
			in += cw
		}
	}
	return in, true
}

func baseResult(k RunKey, t Span) Result {
	r := Result{
		TraceID:    k.TraceID,
		RunID:      k.RunID,
		ToolName:   t.Str(AttrToolName, "unknown"),
		ToolSource: t.Str(AttrToolSource, "unknown"),
		ToolSpanID: t.SpanID,
		ToolCallID: t.Str(AttrToolCallID, ""),
	}
	r.DurationMs, r.HasDuration = t.DurationMs()
	return r
}

func withModel(r Result, m *Span) Result {
	if m != nil {
		r.Model = m.Str(AttrModel, "")
		r.Provider = m.Str(AttrProvider, "")
	}
	return r
}

// ClassifyRun은 run 하나의 스팬들로 도구 호출마다 패턴을 판정하고 순차 구간 토큰을 귀속한다.
// 동작은 파이썬 attribution.classify_segments()와 같다.
func ClassifyRun(k RunKey, group []Span, opts Options) []Result {
	sorted := make([]Span, len(group))
	copy(sorted, group)
	sort.SliceStable(sorted, func(i, j int) bool { return sorted[i].Start.Before(sorted[j].Start) })

	var models, tools []Span
	for _, s := range sorted {
		switch s.Name {
		case SpanModelCall:
			models = append(models, s)
		case SpanToolExec:
			tools = append(tools, s)
		}
	}
	if len(tools) == 0 {
		return nil
	}

	var results []Result
	if len(models) == 0 {
		for _, t := range tools {
			r := baseResult(k, t)
			r.Pattern = Unattributed
			r.Note = noteNoModelCall
			results = append(results, r)
		}
		return results
	}

	// 병렬 판정: 같은 run 안에서 도구 스팬끼리 시간이 겹치는가.
	parallel := map[string]bool{}
	for i := 0; i < len(tools); i++ {
		for j := i + 1; j < len(tools); j++ {
			if overlaps(tools[i], tools[j]) {
				parallel[tools[i].SpanID] = true
				parallel[tools[j].SpanID] = true
			}
		}
	}

	assigned := map[string]bool{}
	for idx := range models {
		prev := &models[idx]
		var next *Span
		if idx+1 < len(models) {
			next = &models[idx+1]
		}
		winStart := prev.End
		var winEnd time.Time
		if next != nil {
			winEnd = next.Start
		}

		var between []Span
		for _, t := range tools {
			if winStart.IsZero() || t.Start.IsZero() {
				continue
			}
			if t.Start.Before(winStart) {
				continue
			}
			if next != nil && t.Start.After(winEnd) {
				continue
			}
			between = append(between, t)
		}
		if len(between) == 0 {
			continue
		}
		for _, t := range between {
			assigned[t.SpanID] = true
		}

		if next == nil {
			for _, t := range between {
				r := withModel(baseResult(k, t), prev)
				r.Pattern = Unattributed
				r.Note = noteTail
				results = append(results, r)
			}
			continue
		}

		missingTs := false
		anyParallel := false
		for _, t := range between {
			if t.Start.IsZero() || t.End.IsZero() {
				missingTs = true
			}
			if parallel[t.SpanID] {
				anyParallel = true
			}
		}
		pattern := Batch
		switch {
		case anyParallel:
			pattern = Parallel
		case len(between) == 1:
			pattern = Sequential
		}

		if pattern == Sequential {
			t := between[0]
			r := withModel(baseResult(k, t), next)
			r.Pattern = Sequential
			r.ClosingModelSpanID = next.SpanID
			prevIn, ok1 := opts.promptTokens(*prev)
			prevOut, ok2 := prev.Int(AttrOutputTokens)
			nextIn, ok3 := opts.promptTokens(*next)
			if !(ok1 && ok2 && ok3) {
				r.Note = noteMissingTok
				results = append(results, r)
				continue
			}
			delta := nextIn - prevIn - prevOut
			if delta < 0 {
				r.NegativeDelta = true
				r.Note = noteNegDelta
				delta = 0
			}
			r.ApproxTokens = delta
			r.HasTokens = true
			results = append(results, r)
			continue
		}

		note := noteParBatch
		if pattern == Batch && missingTs {
			note += noteMissingTs
		}
		// 구간 증가분(배분 전 합계). 순차와 같은 공식이며, 결과별 토큰 수가 있을 때 AllocateByCounts가 나눈다.
		var segDelta int64
		hasSeg, segNeg := false, false
		if prevIn, ok1 := opts.promptTokens(*prev); ok1 {
			if prevOut, ok2 := prev.Int(AttrOutputTokens); ok2 {
				if nextIn, ok3 := opts.promptTokens(*next); ok3 {
					segDelta = nextIn - prevIn - prevOut
					hasSeg = true
					if segDelta < 0 {
						segNeg = true
						segDelta = 0
					}
				}
			}
		}
		for _, t := range between {
			r := withModel(baseResult(k, t), next)
			r.Pattern = pattern
			r.ClosingModelSpanID = next.SpanID
			r.Note = note
			r.MissingTimestamps = pattern == Batch && missingTs
			r.SegmentDelta, r.HasSegmentDelta, r.SegmentNegative = segDelta, hasSeg, segNeg
			results = append(results, r)
		}
	}

	for _, t := range tools {
		if assigned[t.SpanID] {
			continue
		}
		r := baseResult(k, t)
		r.Pattern = Unattributed
		r.Note = noteNotInSegment
		results = append(results, r)
	}
	return results
}
