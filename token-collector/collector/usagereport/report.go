// Package usagereport는 도구별 토큰·비용 귀속 결과(attribution.Result)를 통합 스키마 14절의
// UsageReport(usage.json)로 바꾸는 어댑터다.
//
// 메트릭(Prometheus)은 누적값이라 호출별 기록을 되살릴 수 없으므로(스키마 14.2-6), 이 어댑터는
// Collector가 파일로 남긴 원본 스팬(OTLP JSON)을 다시 읽어 호출 단위 UsageRecord를 만든다.
// 판정 로직은 커넥터와 같은 attribution.Classify를 그대로 쓴다.
//
// 지키는 규칙(스키마 14.2):
//   - 병렬·배치·귀속불가 도구는 토큰·비용을 null로 둔다(균등 배분 안 함).
//   - 단가를 모르면 비용은 null(0으로 바꾸지 않음), 단가 출처·버전을 항상 같이 적는다.
//   - 자산 연결은 서버+도구 이름이 스냅샷의 Tool 하나와만 맞을 때 matched. 이름만으로 다른 서버의
//     동명 Tool에 연결하지 않고, 내장(core) 도구에는 가짜 MCP 자산을 만들지 않는다.
//   - usage_id(환경·프로필·trace·tool span 기반)로 재전송 중복을 없앤다.
package usagereport

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"math"
	"sort"
	"strings"
	"time"

	"github.com/pbh0330/2026-Agent_Scope/token-collector/collector/attribution"
)

const (
	// SchemaVersion은 이 출력이 따르는 통합 스키마 문서 버전(PR #1 schema-design-draft).
	SchemaVersion = "0.6.0-draft"
	// ProducerName / ProducerVersion은 usage.json의 producer.
	ProducerName    = "agentscope-usage"
	ProducerVersion = "0.1.0"
	// AttributionMethod는 순차 구간 근사식 이름: next.input - prev.input - prev.output.
	AttributionMethod = "sequential-input-delta"
	// AttributionMethodParallelCount / BatchCount는 병렬·배치 구간 증가분을 토큰 계산 API로 센
	// 결과별 토큰 수 비율로 나눈 경우(정확도 개선 방안 B)의 이름이다.
	AttributionMethodParallelCount = "parallel-token-count"
	AttributionMethodBatchCount    = "batch-token-count"
	// AttributionVersion은 귀속 구현 버전. 판정 규칙을 바꾸면 올린다.
	// (0.2.0: 꼬리 도구 unattributed, 시간대 정렬 수정, 모델별 단가 / 0.3.0: 병렬·배치 구간 토큰 수 비율 배분)
	AttributionVersion = "attribution-go/0.3.0"
	// PricingSourceUnavailable은 단가를 찾지 못한 경우의 pricing.source.
	PricingSourceUnavailable = "unavailable"
)

// UsageReport는 스키마 14.1의 최상위 객체다.
type UsageReport struct {
	SchemaVersion       string        `json:"schema_version"`
	UsageReportID       string        `json:"usage_report_id"`
	EnvironmentID       string        `json:"environment_id"`
	ProfileID           string        `json:"profile_id"`
	GeneratedAt         string        `json:"generated_at"`
	Producer            Producer      `json:"producer"`
	Window              Window        `json:"window"`
	InventorySnapshotID *string       `json:"inventory_snapshot_id"`
	Records             []UsageRecord `json:"records"`
	Limitations         []string      `json:"limitations"`
}

// Producer는 출력 생성기 정보.
type Producer struct {
	Name    string `json:"name"`
	Version string `json:"version"`
}

// Window는 도구 시작 시각 기준 집계 구간(UTC, start 포함·end 미포함).
type Window struct {
	Start string `json:"start"`
	End   string `json:"end"`
}

// UsageRecord는 도구 호출 하나의 사용량 기록(스키마 14.1 표).
type UsageRecord struct {
	UsageID              string      `json:"usage_id"`
	TraceID              string      `json:"trace_id"`
	RunID                string      `json:"run_id"`
	ToolSpanID           string      `json:"tool_span_id"`
	ToolCallID           *string     `json:"tool_call_id"`
	ToolName             string      `json:"tool_name"`
	ToolSource           string      `json:"tool_source"`
	AssetRef             *string     `json:"asset_ref"`
	MappingStatus        string      `json:"mapping_status"`
	MappingReason        string      `json:"mapping_reason"`
	MappingEvidenceRefs  []string    `json:"mapping_evidence_refs"`
	Pattern              string      `json:"pattern"`
	DurationMs           *float64    `json:"duration_ms"`
	ApproxInputTokens    *int64      `json:"approx_input_tokens"`
	NegativeDelta        bool        `json:"negative_delta"`
	MissingTimestamps    bool        `json:"missing_timestamps"`
	Model                *string     `json:"model"`
	Provider             *string     `json:"provider"`
	ClosingModelSpanID   *string     `json:"closing_model_span_id"`
	AttributionMethod    string      `json:"attribution_method"`
	AttributionVersion   string      `json:"attribution_version"`
	IncludeCacheInPrompt bool        `json:"include_cache_in_prompt"`
	Estimated            bool        `json:"estimated"`
	EstimatedCostUSD     *float64    `json:"estimated_cost_usd"`
	Pricing              PricingInfo `json:"pricing"`
	EvidenceSourceRefs   []string    `json:"evidence_source_refs"`
	Note                 string      `json:"note"`

	toolStart time.Time // 집계 구간 판단·정렬용(출력 안 함)
}

// PricingInfo는 레코드 비용 계산에 쓴 단가 메타데이터.
type PricingInfo struct {
	Source          string   `json:"source"`
	Version         *string  `json:"version"`
	Currency        string   `json:"currency"`
	InputPerMillion *float64 `json:"input_per_million"`
	SourceRef       string   `json:"source_ref,omitempty"`
}

// Options는 Build 설정이다.
type Options struct {
	EnvironmentID string // 필수: 테스트베드 논리 환경 ID(텔레메트리에 없어서 주입)
	ProfileID     string // 필수: 설치·프로필 ID

	// WindowStart/WindowEnd: 도구 시작 시각 기준 [start, end). 둘 다 zero면 데이터에서 초 단위로 잡는다.
	WindowStart time.Time
	WindowEnd   time.Time
	GeneratedAt time.Time // zero면 time.Now()

	Attribution attribution.Options
	Pricing     attribution.Pricing
	// ConfigPricingVersion: openclaw.json에서 읽은 단가표의 불변 버전(ConfigPricingVersion 함수로 계산).
	ConfigPricingVersion string

	Inventory *Inventory // nil이면 inventory_snapshot_id=null, 전부 unmatched

	// ToolResultCounts: tool_call_id → 토큰 계산 API로 센 도구 결과 토큰 수(결과 기록 플러그인 기록).
	// 주어지면 병렬·배치 구간 증가분을 이 비율로 나눈다. nil이면 병렬·배치는 지금처럼 null.
	ToolResultCounts map[string]int64
	// ToolResultsRef: evidence_source_refs에 붙일 플러그인 기록 파일 이름(경로 제외).
	ToolResultsRef string

	// EvidencePrefix: evidence_source_refs 앞부분(예: "otlp-json:traces.jsonl"). 사용자 경로를 넣지 말 것.
	EvidencePrefix string
}

// Build는 스팬 묶음을 판정하고 UsageReport를 만든다.
func Build(spans []attribution.Span, opt Options) (*UsageReport, error) {
	if opt.EnvironmentID == "" || opt.ProfileID == "" {
		return nil, errors.New("environment_id와 profile_id는 필수")
	}
	if opt.Inventory != nil {
		if err := opt.Inventory.checkContext(opt.EnvironmentID, opt.ProfileID); err != nil {
			return nil, err
		}
	}
	if (opt.WindowStart.IsZero()) != (opt.WindowEnd.IsZero()) {
		return nil, errors.New("window start/end는 둘 다 주거나 둘 다 비워야 함")
	}
	if !opt.WindowStart.IsZero() && !opt.WindowStart.Before(opt.WindowEnd) {
		return nil, errors.New("window start는 end보다 앞이어야 함")
	}
	if opt.EvidencePrefix == "" {
		opt.EvidencePrefix = "otlp"
	}
	gen := opt.GeneratedAt
	if gen.IsZero() {
		gen = time.Now()
	}

	spans = dedupeSpans(spans)
	toolStart := map[string]time.Time{}
	for _, s := range spans {
		if s.Name == attribution.SpanToolExec {
			toolStart[s.TraceID+"/"+s.SpanID] = s.Start
		}
	}

	var (
		records         []UsageRecord
		noStart         int
		outOfWindow     int
		seen            = map[string]bool{}
		usedRef         bool
		unmatchedSuffix bool
	)
	results := attribution.Classify(spans, opt.Attribution)
	if opt.ToolResultCounts != nil {
		results = attribution.AllocateByCounts(results, opt.ToolResultCounts)
	}
	var parBatchNull int
	for _, r := range results {
		rec := newRecord(r, opt)
		if seen[rec.UsageID] {
			continue
		}
		seen[rec.UsageID] = true
		rec.toolStart = toolStart[r.TraceID+"/"+r.ToolSpanID]
		if rec.toolStart.IsZero() {
			noStart++
			continue
		}
		if rec.Pricing.Source == attribution.PriceSourceReference {
			usedRef = true
		}
		if r.AllocationMethod == "" && (r.Pattern == attribution.Parallel || r.Pattern == attribution.Batch) {
			parBatchNull++
		}
		if rec.MappingStatus == MappingUnmatched && rec.ToolSource == "mcp" && collisionSuffix.MatchString(rec.ToolName) {
			unmatchedSuffix = true
		}
		records = append(records, rec)
	}

	start, end := opt.WindowStart, opt.WindowEnd
	if start.IsZero() {
		if len(records) == 0 {
			start = gen.UTC().Truncate(time.Second)
			end = start.Add(time.Second)
		} else {
			lo, hi := records[0].toolStart, records[0].toolStart
			for _, r := range records[1:] {
				if r.toolStart.Before(lo) {
					lo = r.toolStart
				}
				if r.toolStart.After(hi) {
					hi = r.toolStart
				}
			}
			start = lo.UTC().Truncate(time.Second)
			end = hi.UTC().Truncate(time.Second).Add(time.Second)
		}
	}
	kept := records[:0]
	for _, r := range records {
		if r.toolStart.Before(start) || !r.toolStart.Before(end) {
			outOfWindow++
			continue
		}
		kept = append(kept, r)
	}
	records = kept
	sort.SliceStable(records, func(i, j int) bool {
		if !records[i].toolStart.Equal(records[j].toolStart) {
			return records[i].toolStart.Before(records[j].toolStart)
		}
		return records[i].UsageID < records[j].UsageID
	})
	if records == nil {
		records = []UsageRecord{}
	}

	lim := []string{
		"approx_input_tokens is an estimate of how much a tool result added to the next model input; it is not billed usage and must not be added to model-level input/output/cache totals.",
		"environment_id and profile_id are injected by the adapter because the telemetry carries only host-level resource attributes.",
	}
	switch {
	case opt.ToolResultCounts == nil:
		lim = append(lim, "Only sequential segments carry tokens and cost; parallel, batch and unattributed calls keep call count and duration only.")
	default:
		lim = append(lim, "Parallel and batch segments split their measured input increase in proportion to per-result token counts from the token-count API (attribution_method=parallel-token-count / batch-token-count); the split preserves the segment total.")
		if parBatchNull > 0 {
			lim = append(lim, fmt.Sprintf("%d parallel/batch call(s) keep null tokens because a per-result token count was missing for their segment.", parBatchNull))
		}
	}
	var snapID *string
	if opt.Inventory == nil {
		lim = append(lim, "inventory_snapshot_id is null: no InventorySnapshot was provided, so every record is unmatched.")
	} else {
		id := opt.Inventory.SnapshotID
		snapID = &id
		lim = append(lim, "Tool mapping reproduces OpenClaw's provider-safe tool names (<server>__<tool>, 64-char limit) from the snapshot; names that OpenClaw de-duplicated with a -N suffix cannot be resolved statically.")
	}
	if unmatchedSuffix {
		lim = append(lim, "Some MCP tool names end in a -N suffix that may come from OpenClaw collision handling; they were left unmatched.")
	}
	if usedRef {
		lim = append(lim, "pricing.source=reference_list_price uses public list prices for reference because the configured price is zero or missing; it is not the actual bill.")
	}
	if noStart > 0 {
		lim = append(lim, fmt.Sprintf("%d tool call(s) excluded because the tool span has no start time, so the window cannot be decided.", noStart))
	}
	if outOfWindow > 0 {
		lim = append(lim, fmt.Sprintf("%d tool call(s) outside the window were excluded.", outOfWindow))
	}
	lim = append(lim, "A run cut off at the end of the capture can leave its last tools unattributed; re-run the adapter on a later capture that contains the whole run.")

	rep := &UsageReport{
		SchemaVersion:       SchemaVersion,
		EnvironmentID:       opt.EnvironmentID,
		ProfileID:           opt.ProfileID,
		GeneratedAt:         gen.UTC().Format(time.RFC3339),
		Producer:            Producer{Name: ProducerName, Version: ProducerVersion},
		Window:              Window{Start: start.UTC().Format(time.RFC3339Nano), End: end.UTC().Format(time.RFC3339Nano)},
		InventorySnapshotID: snapID,
		Records:             records,
		Limitations:         lim,
	}
	rep.UsageReportID = reportID(rep, opt)
	return rep, nil
}

func newRecord(r attribution.Result, opt Options) UsageRecord {
	rec := UsageRecord{
		UsageID:              UsageID(opt.EnvironmentID, opt.ProfileID, r.TraceID, r.ToolSpanID),
		TraceID:              r.TraceID,
		RunID:                r.RunID,
		ToolSpanID:           r.ToolSpanID,
		ToolCallID:           strPtr(r.ToolCallID),
		ToolName:             r.ToolName,
		ToolSource:           r.ToolSource,
		Pattern:              string(r.Pattern),
		NegativeDelta:        r.NegativeDelta,
		MissingTimestamps:    r.MissingTimestamps,
		Model:                strPtr(r.Model),
		Provider:             strPtr(r.Provider),
		ClosingModelSpanID:   strPtr(r.ClosingModelSpanID),
		AttributionMethod:    attributionMethod(r),
		AttributionVersion:   AttributionVersion,
		IncludeCacheInPrompt: opt.Attribution.IncludeCacheInPrompt,
		Estimated:            true,
		EvidenceSourceRefs:   []string{fmt.Sprintf("%s#trace=%s&span=%s", opt.EvidencePrefix, r.TraceID, r.ToolSpanID)},
		Note:                 r.Note,
	}
	if r.HasDuration {
		d := r.DurationMs
		rec.DurationMs = &d
	}

	rec.Pricing = PricingInfo{Source: PricingSourceUnavailable, Currency: "USD"}
	rate, src, havePrice := opt.Pricing.RateFor(r.Model)
	if havePrice {
		in := rate.Input
		rec.Pricing.Source = src
		rec.Pricing.InputPerMillion = &in
		switch src {
		case attribution.PriceSourceConfig:
			if opt.ConfigPricingVersion != "" {
				v := opt.ConfigPricingVersion
				rec.Pricing.Version = &v
			}
			rec.Pricing.SourceRef = "openclaw.json#models.providers.*.models[].cost"
		case attribution.PriceSourceReference:
			v := attribution.AnthropicListPricingVersion
			rec.Pricing.Version = &v
			rec.Pricing.SourceRef = "https://platform.claude.com/docs/en/about-claude/pricing"
		}
	}

	if r.HasCount && opt.ToolResultsRef != "" && r.ToolCallID != "" {
		rec.EvidenceSourceRefs = append(rec.EvidenceSourceRefs, fmt.Sprintf("tool-results:%s#toolCallId=%s", opt.ToolResultsRef, r.ToolCallID))
	}
	if (r.Pattern == attribution.Sequential || r.AllocationMethod != "") && r.HasTokens {
		tok := r.ApproxTokens
		rec.ApproxInputTokens = &tok
		if havePrice {
			usd := roundUSD(float64(tok) / 1e6 * rate.Input)
			rec.EstimatedCostUSD = &usd
		}
	}

	m := opt.Inventory.Map(r.ToolName, r.ToolSource)
	rec.AssetRef, rec.MappingStatus, rec.MappingReason, rec.MappingEvidenceRefs = m.AssetRef, m.Status, m.Reason, m.EvidenceRefs
	if rec.MappingEvidenceRefs == nil {
		rec.MappingEvidenceRefs = []string{}
	}
	return rec
}

// attributionMethod는 레코드의 귀속 방식 이름이다.
func attributionMethod(r attribution.Result) string {
	if r.AllocationMethod == attribution.AllocationTokenCount {
		if r.Pattern == attribution.Batch {
			return AttributionMethodBatchCount
		}
		return AttributionMethodParallelCount
	}
	return AttributionMethod
}

// UsageID는 재전송 중복 방지 ID다. 같은 환경·프로필의 같은 도구 스팬이면 항상 같다.
func UsageID(env, profile, traceID, toolSpanID string) string {
	return "use-" + hashParts(env, profile, traceID, toolSpanID)[:32]
}

// reportID는 같은 입력(환경·프로필·구간·스냅샷·계산 옵션·단가표·레코드)이면 같은 ID를 낸다
// (재전송 시 중복 저장 방지). 생성 시각은 넣지 않는다. 단가표나 옵션이 바뀌면 값이 달라지므로 ID도 바뀐다.
func reportID(r *UsageReport, opt Options) string {
	refPricing := "no-reference"
	if len(opt.Pricing.Reference) > 0 {
		refPricing = attribution.AnthropicListPricingVersion
	}
	parts := []string{r.SchemaVersion, r.EnvironmentID, r.ProfileID, r.Window.Start, r.Window.End, AttributionVersion,
		fmt.Sprint(opt.Attribution.IncludeCacheInPrompt), opt.ConfigPricingVersion, refPricing}
	if r.InventorySnapshotID != nil {
		parts = append(parts, *r.InventorySnapshotID)
	}
	for _, rec := range r.Records {
		parts = append(parts, rec.UsageID)
	}
	return "usage-" + hashParts(parts...)[:24]
}

func hashParts(parts ...string) string {
	h := sha256.New()
	for _, p := range parts {
		h.Write([]byte(p))
		h.Write([]byte{0})
	}
	return hex.EncodeToString(h.Sum(nil))
}

// ConfigPricingVersion은 설정 단가표(모델 → 단가)의 내용 해시로 불변 버전을 만든다.
// 원천(openclaw.json)에 단가 버전이 없어서 어댑터가 버전을 붙인다(스키마 14.1). 단가만 해시하므로
// API 키 등 설정의 다른 값은 들어가지 않는다.
func ConfigPricingVersion(models map[string]attribution.Rate) string {
	if len(models) == 0 {
		return ""
	}
	ids := make([]string, 0, len(models))
	for id := range models {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	var b strings.Builder
	for _, id := range ids {
		r := models[id]
		fmt.Fprintf(&b, "%s|%g|%g|%g|%g\n", id, r.Input, r.Output, r.CacheRead, r.CacheWrite)
	}
	return "openclaw-config-sha256:" + hashParts(b.String())[:12]
}

func dedupeSpans(in []attribution.Span) []attribution.Span {
	seen := map[string]bool{}
	out := make([]attribution.Span, 0, len(in))
	for _, s := range in {
		k := s.TraceID + "/" + s.SpanID
		if s.SpanID != "" && seen[k] {
			continue
		}
		seen[k] = true
		out = append(out, s)
	}
	return out
}

func strPtr(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

func roundUSD(v float64) float64 { return math.Round(v*1e9) / 1e9 }
