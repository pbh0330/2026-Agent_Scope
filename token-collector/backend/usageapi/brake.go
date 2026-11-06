package usageapi

import (
	"bufio"
	"encoding/json"
	"os"
	"sort"
	"time"
)

// BrakeEvent는 token-guard 플러그인이 남긴 소비 브레이크 기록 하나다(kind:"brake").
// 플러그인 기록에서 아래 필드만 읽는다(도구 인자·결과 내용은 원래 없음).
type BrakeEvent struct {
	Time       time.Time
	Level      string // warn / approve / block
	Mode       string // warn / enforce
	Enforced   bool
	RunID      string // OpenClaw run id(플러그인 기준. 스팬의 run_id와는 다른 값)
	ToolCallID string
	ToolName   string
	Reasons    []BrakeReason
	RunUsage   *BrakeRunUsage
	Resolution *BrakeResolution // 승인 요청(approve)에 대한 응답. 없으면 nil
}

// BrakeReason은 넘은 기준 하나다(예: run.toolCalls 3 ≥ 3).
type BrakeReason struct {
	Scope  string  `json:"scope"`
	Metric string  `json:"metric"`
	Value  float64 `json:"value"`
	Limit  float64 `json:"limit"`
}

// BrakeRunUsage는 판정 시점의 실행(run) 누적값이다.
type BrakeRunUsage struct {
	ResultBytes    int64 `json:"result_bytes"`
	CountedTokens  int64 `json:"counted_tokens"`
	ToolCalls      int64 `json:"tool_calls"`
	SameToolStreak int64 `json:"same_tool_streak"`
}

// BrakeResolution은 승인 요청에 사용자가 어떻게 답했는지다(allow-once / allow-always / deny / timeout / cancelled).
type BrakeResolution struct {
	Decision string
	Time     time.Time
}

type brakeLine struct {
	Kind       string        `json:"kind"`
	TS         string        `json:"ts"`
	Level      string        `json:"level"`
	Mode       string        `json:"mode"`
	Enforced   bool          `json:"enforced"`
	RunID      string        `json:"runId"`
	ToolCallID string        `json:"toolCallId"`
	ToolName   string        `json:"toolName"`
	Reasons    []BrakeReason `json:"reasons"`
	Run        *struct {
		ResultBytes    int64 `json:"resultBytes"`
		CountedTokens  int64 `json:"countedTokens"`
		ToolCalls      int64 `json:"toolCalls"`
		SameToolStreak int64 `json:"sameToolStreak"`
	} `json:"run"`
	Decision string `json:"decision"`
}

// ReadBrakeEvents는 플러그인 JSONL에서 brake / brake_resolution 줄을 읽어 짝지어 돌려준다.
// 다른 kind와 읽지 못한 줄은 건너뛴다(카운트는 usagereport.ReadToolResultCounts가 따로 셈).
func ReadBrakeEvents(path string) ([]BrakeEvent, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	var events []BrakeEvent
	type res struct {
		decision string
		at       time.Time
	}
	var resolutions []struct {
		toolCallID string
		r          res
	}
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 64*1024), 16*1024*1024)
	for sc.Scan() {
		line := sc.Bytes()
		var l brakeLine
		if json.Unmarshal(line, &l) != nil || (l.Kind != "brake" && l.Kind != "brake_resolution") {
			continue
		}
		at, err := time.Parse(time.RFC3339Nano, l.TS)
		if err != nil {
			continue
		}
		at = at.UTC()
		if l.Kind == "brake_resolution" {
			resolutions = append(resolutions, struct {
				toolCallID string
				r          res
			}{l.ToolCallID, res{l.Decision, at}})
			continue
		}
		ev := BrakeEvent{Time: at, Level: l.Level, Mode: l.Mode, Enforced: l.Enforced, RunID: l.RunID,
			ToolCallID: l.ToolCallID, ToolName: l.ToolName, Reasons: l.Reasons}
		if ev.Reasons == nil {
			ev.Reasons = []BrakeReason{}
		}
		if l.Run != nil {
			ev.RunUsage = &BrakeRunUsage{ResultBytes: l.Run.ResultBytes, CountedTokens: l.Run.CountedTokens,
				ToolCalls: l.Run.ToolCalls, SameToolStreak: l.Run.SameToolStreak}
		}
		events = append(events, ev)
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	// 응답은 같은 도구 호출의 가장 최근 승인 요청에 붙인다.
	for _, rs := range resolutions {
		for i := len(events) - 1; i >= 0; i-- {
			e := &events[i]
			if e.ToolCallID == rs.toolCallID && e.Level == "approve" && !e.Time.After(rs.r.at) {
				if e.Resolution == nil {
					e.Resolution = &BrakeResolution{Decision: rs.r.decision, Time: rs.r.at}
				}
				break
			}
		}
	}
	return events, nil
}

func sortBrakes(ev []BrakeEvent) []BrakeEvent {
	sort.SliceStable(ev, func(i, j int) bool { return ev[i].Time.Before(ev[j].Time) })
	return ev
}
