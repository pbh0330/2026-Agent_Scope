package usagereport

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
)

// ToolResultKindTokenCount는 결과 기록 플러그인(agentscope-token-guard)이 남기는 JSONL 줄 중
// "도구 결과 하나의 토큰 수를 토큰 계산 API로 센 결과" 줄의 kind 값이다.
const ToolResultKindTokenCount = "token_count"

// toolResultLine은 플러그인 JSONL 한 줄 중 배분에 필요한 필드만 읽는다.
// 결과 내용은 플러그인이 기록하지 않으므로 여기에도 없다.
type toolResultLine struct {
	Kind          string `json:"kind"`
	ToolCallID    string `json:"toolCallId"`
	CountedTokens *int64 `json:"countedTokens"`
}

// ToolResultStats는 플러그인 기록 파일을 읽은 결과 요약이다.
type ToolResultStats struct {
	Lines     int // 전체 줄 수(빈 줄 제외)
	Counts    int // 사용한 token_count 줄 수
	Malformed int // JSON이 아니거나 필수 필드가 없는 줄
}

// ReadToolResultCounts는 플러그인 기록 파일(JSONL)에서 tool_call_id → 결과 토큰 수를 읽어 dst에 더한다.
// 같은 tool_call_id가 여러 번 나오면 마지막 값을 쓴다. token_count 외의 줄(tool_result, brake 등)은 건너뛴다.
func ReadToolResultCounts(path string, dst map[string]int64) (ToolResultStats, error) {
	var st ToolResultStats
	f, err := os.Open(path)
	if err != nil {
		return st, err
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 64*1024), 4*1024*1024)
	for sc.Scan() {
		line := sc.Bytes()
		if len(line) == 0 {
			continue
		}
		st.Lines++
		var l toolResultLine
		if err := json.Unmarshal(line, &l); err != nil {
			st.Malformed++
			continue
		}
		if l.Kind != ToolResultKindTokenCount {
			continue
		}
		if l.ToolCallID == "" || l.CountedTokens == nil || *l.CountedTokens < 0 {
			st.Malformed++
			continue
		}
		dst[l.ToolCallID] = *l.CountedTokens
		st.Counts++
	}
	if err := sc.Err(); err != nil {
		return st, fmt.Errorf("%s: %w", path, err)
	}
	return st, nil
}
