// Package attribution은 OpenClaw 텔레메트리 스팬(openclaw.model.call /
// openclaw.tool.execution)으로 도구별 토큰·비용을 근사 귀속하는 핵심 로직이다.
//
// 파이썬 프로토타입(attribution.py, 작성자 개인 저장소 보관)을 그대로 옮긴 것이며,
// 외부 라이브러리 없이 표준 라이브러리만 사용한다. OTel Collector 커넥터
// (tokenattributionconnector)는 이 패키지를 감싸서 스팬을 넣고 결과를 메트릭으로 내보낸다.
//
// 귀속 공식(순차 구간):
//
//	tool_tokens = next.input_tokens - prev.input_tokens - prev.output_tokens
//
// 직전 model.call 자신의 응답(output)이 다음 호출의 입력 히스토리로 다시 들어가는 몫을
// 빼서 도구 결과만의 기여분을 근사한다. 병렬·배치 구간은 여러 도구 결과가 한 번의
// 입력 증가분에 섞여 있으므로, 구간 증가분만 계산해 두고(SegmentDelta) 결과별 토큰 수가
// 있을 때 AllocateByCounts로 그 비율대로 나눈다(합계 보존). 토큰 수가 없으면 귀속하지 않는다.
package attribution

import "time"

// OpenClaw 스팬 이름.
const (
	SpanModelCall = "openclaw.model.call"
	SpanToolExec  = "openclaw.tool.execution"
	SpanRun       = "openclaw.run"
)

// OpenClaw 스팬 속성 키.
const (
	AttrToolName        = "openclaw.toolName"
	AttrToolSource      = "openclaw.tool.source"
	AttrToolCallID      = "gen_ai.tool.call.id"
	AttrModel           = "openclaw.model"
	AttrProvider        = "openclaw.provider"
	AttrInputTokens     = "openclaw.model_call.usage.input_tokens"
	AttrOutputTokens    = "openclaw.model_call.usage.output_tokens"
	AttrCacheReadTokens = "openclaw.model_call.usage.cache_read_input_tokens"
	AttrCacheWriteToken = "openclaw.model_call.usage.cache_creation_input_tokens"
)

// Pattern은 도구 호출 구간의 판정 결과다.
type Pattern string

const (
	Sequential   Pattern = "sequential"
	Parallel     Pattern = "parallel"
	Batch        Pattern = "batch"
	Unattributed Pattern = "unattributed"
)

// Span은 귀속 계산에 필요한 스팬 정보만 담는다. Start/End가 zero면 "시각 없음"이다.
// Attrs 값은 int64, float64, string, bool 중 하나다(pdata 속성을 변환한 형태).
type Span struct {
	TraceID  string
	ParentID string
	SpanID   string
	Name     string
	Start    time.Time
	End      time.Time
	Attrs    map[string]any
}

// DurationMs는 스팬 실행 시간(ms)이다. 시각이 하나라도 없으면 ok=false.
func (s Span) DurationMs() (float64, bool) {
	if s.Start.IsZero() || s.End.IsZero() {
		return 0, false
	}
	return float64(s.End.Sub(s.Start)) / float64(time.Millisecond), true
}

// Str은 문자열 속성을 돌려준다. 없으면 def.
func (s Span) Str(key, def string) string {
	if v, ok := s.Attrs[key].(string); ok && v != "" {
		return v
	}
	return def
}

// Int는 정수 속성을 돌려준다. 없거나 정수가 아니면 ok=false.
func (s Span) Int(key string) (int64, bool) {
	switch v := s.Attrs[key].(type) {
	case int64:
		return v, true
	case int:
		return int64(v), true
	case float64:
		if v == float64(int64(v)) {
			return int64(v), true
		}
	}
	return 0, false
}

// Result는 도구 호출 하나의 귀속 결과다.
type Result struct {
	TraceID    string
	RunID      string // 부모 openclaw.run 스팬 ID
	ToolName   string
	ToolSource string // mcp / builtin 등 (openclaw.tool.source)
	ToolSpanID string
	ToolCallID string
	Pattern    Pattern

	DurationMs    float64
	HasDuration   bool
	ApproxTokens  int64 // HasTokens일 때만 의미 있음(순차 실측 또는 AllocateByCounts 배분)
	HasTokens     bool
	NegativeDelta bool // 공식 결과가 음수여서 0으로 잘랐는지(컨텍스트 압축 등)
	// MissingTimestamps: 이 구간 도구 스팬 중 시각이 없는 게 있어서 batch 판정을 확신할 수 없음.
	MissingTimestamps bool

	// 병렬·배치 구간의 입력 증가분(순차와 같은 공식, 구간 전체 값). 구간의 모든 도구가 같은 값을 가진다.
	// 토큰은 AllocateByCounts가 결과별 토큰 수 비율로 나눌 때만 채운다.
	SegmentDelta    int64
	HasSegmentDelta bool
	SegmentNegative bool // 구간 증가분이 음수여서 0으로 잘랐는지(배분하면 NegativeDelta로 옮김)
	// AllocationMethod: 병렬·배치 구간 배분 방식. 빈 문자열이면 배분 안 함.
	AllocationMethod string
	// CountedTokens: 토큰 계산 API로 센 이 도구 결과의 토큰 수(배분 근거). HasCount=false면 없음.
	CountedTokens int64
	HasCount      bool

	// 이 도구 구간을 닫는(=바로 다음) model.call. 없으면 빈 문자열(귀속 불가 구간).
	ClosingModelSpanID string
	// 비용 환산에 쓸 모델/프로바이더(닫는 model.call 기준, 없으면 직전 model.call).
	Model    string
	Provider string

	Note string
}
