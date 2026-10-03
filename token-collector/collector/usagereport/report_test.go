package usagereport

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/pbh0330/2026-Agent_Scope/token-collector/collector/attribution"
)

const fixtureDir = "../attribution/testdata"

var fixtures = []string{"week1-sequential", "week3-sequential-batch", "week3-parallel"}

func loadFixture(t *testing.T, name string) []attribution.Span {
	t.Helper()
	spans, err := ReadSpansFile(filepath.Join(fixtureDir, name+".spans.json"))
	if err != nil {
		t.Fatal(err)
	}
	return spans
}

type pyExpected struct {
	ToolSpanID   string   `json:"tool_span_id"`
	ToolName     string   `json:"tool_name"`
	Pattern      string   `json:"pattern"`
	ApproxTokens *int64   `json:"approx_tokens"`
	DurationMs   *float64 `json:"duration_ms"`
}

func loadExpected(t *testing.T, name string) map[string]pyExpected {
	t.Helper()
	b, err := os.ReadFile(filepath.Join(fixtureDir, name+".expected.json"))
	if err != nil {
		t.Fatal(err)
	}
	var list []pyExpected
	if err := json.Unmarshal(b, &list); err != nil {
		t.Fatal(err)
	}
	m := map[string]pyExpected{}
	for _, e := range list {
		m[e.ToolSpanID] = e
	}
	return m
}

func baseOpts() Options {
	return Options{
		EnvironmentID: "env-test-01",
		ProfileID:     "profile-test-01",
		GeneratedAt:   time.Date(2026, 10, 2, 0, 0, 0, 0, time.UTC),
		Pricing:       attribution.Pricing{Reference: attribution.AnthropicListPricingReference},
	}
}

func mustBuild(t *testing.T, spans []attribution.Span, opt Options) *UsageReport {
	t.Helper()
	rep, err := Build(spans, opt)
	if err != nil {
		t.Fatal(err)
	}
	return rep
}

// 실제 로그 3개: usage.json 레코드가 파이썬 기준 결과(판정·토큰·시간)와 같아야 한다(QA-USE-01/02).
func TestFixturesMatchPythonReference(t *testing.T) {
	for _, name := range fixtures {
		t.Run(name, func(t *testing.T) {
			rep := mustBuild(t, loadFixture(t, name), baseOpts())
			want := loadExpected(t, name)
			if len(rep.Records) != len(want) {
				t.Fatalf("records=%d python=%d", len(rep.Records), len(want))
			}
			for _, r := range rep.Records {
				e, ok := want[r.ToolSpanID]
				if !ok {
					t.Fatalf("unexpected tool span %s", r.ToolSpanID)
				}
				if r.Pattern != e.Pattern || r.ToolName != e.ToolName {
					t.Errorf("%s: pattern/name %s/%s, python %s/%s", r.ToolSpanID, r.Pattern, r.ToolName, e.Pattern, e.ToolName)
				}
				if (r.ApproxInputTokens == nil) != (e.ApproxTokens == nil) ||
					(r.ApproxInputTokens != nil && *r.ApproxInputTokens != *e.ApproxTokens) {
					t.Errorf("%s: tokens %v, python %v", r.ToolSpanID, deref(r.ApproxInputTokens), deref(e.ApproxTokens))
				}
				if e.DurationMs != nil && (r.DurationMs == nil || math.Abs(*r.DurationMs-*e.DurationMs) > 1e-6) {
					t.Errorf("%s: duration %v, python %v", r.ToolSpanID, r.DurationMs, *e.DurationMs)
				}
				if !r.Estimated || r.AttributionMethod == "" || r.AttributionVersion == "" || len(r.EvidenceSourceRefs) == 0 {
					t.Errorf("%s: required metadata missing: %+v", r.ToolSpanID, r)
				}
			}
		})
	}
}

func deref[T any](p *T) any {
	if p == nil {
		return nil
	}
	return *p
}

// 병렬·배치·귀속불가는 토큰·비용 null(균등 배분 안 함), 호출·시간은 유지(QA-USE-02, 스키마 14.2-2).
func TestNonSequentialHasNullTokensAndCost(t *testing.T) {
	for _, name := range fixtures {
		rep := mustBuild(t, loadFixture(t, name), baseOpts())
		for _, r := range rep.Records {
			if r.Pattern == string(attribution.Sequential) {
				continue
			}
			if r.ApproxInputTokens != nil || r.EstimatedCostUSD != nil {
				t.Errorf("%s %s(%s): tokens/cost must be null, got %v/%v", name, r.ToolName, r.Pattern, deref(r.ApproxInputTokens), deref(r.EstimatedCostUSD))
			}
			if r.DurationMs == nil {
				t.Errorf("%s %s: duration should be kept", name, r.ToolName)
			}
		}
	}
}

// 단가 출처: 설정 단가 > 0이면 config(+버전), 0이면 참고 정가, 모르는 모델이면 unavailable + 비용 null(0 아님)(QA-USE-06).
func TestPricingSourceAndNullCost(t *testing.T) {
	spans := loadFixture(t, "week1-sequential")
	const model = "claude-haiku-4-5-20251001"

	cfgModels := map[string]attribution.Rate{model: {Input: 3, Output: 15}}
	opt := baseOpts()
	opt.Pricing.Models = cfgModels
	opt.ConfigPricingVersion = ConfigPricingVersion(cfgModels)
	r := mustBuild(t, spans, opt).Records[0]
	if r.Pricing.Source != attribution.PriceSourceConfig || r.Pricing.Version == nil || !strings.HasPrefix(*r.Pricing.Version, "openclaw-config-sha256:") {
		t.Fatalf("config pricing: %+v", r.Pricing)
	}
	if r.EstimatedCostUSD == nil || math.Abs(*r.EstimatedCostUSD-264*3/1e6) > 1e-12 {
		t.Fatalf("config cost = %v", deref(r.EstimatedCostUSD))
	}

	opt.Pricing.Models = map[string]attribution.Rate{model: {}} // 학교 게이트웨이처럼 전부 0
	r = mustBuild(t, spans, opt).Records[0]
	if r.Pricing.Source != attribution.PriceSourceReference || *r.Pricing.Version != attribution.AnthropicListPricingVersion {
		t.Fatalf("reference pricing: %+v", r.Pricing)
	}

	opt = baseOpts()
	opt.Pricing = attribution.Pricing{} // 단가표 없음
	rep := mustBuild(t, spans, opt)
	r = rep.Records[0]
	if r.Pricing.Source != PricingSourceUnavailable || r.Pricing.InputPerMillion != nil || r.Pricing.Version != nil {
		t.Fatalf("unavailable pricing: %+v", r.Pricing)
	}
	if r.EstimatedCostUSD != nil {
		t.Fatalf("unknown price must give null cost, got %v", *r.EstimatedCostUSD)
	}
	if r.ApproxInputTokens == nil || *r.ApproxInputTokens != 264 {
		t.Fatalf("tokens should not depend on pricing: %v", deref(r.ApproxInputTokens))
	}
	b, _ := json.Marshal(r)
	if !bytes.Contains(b, []byte(`"estimated_cost_usd":null`)) {
		t.Fatalf("cost must serialize as null: %s", b)
	}
}

// 같은 스팬이 두 번 들어와도(재전송) 레코드·리포트 ID가 같아야 한다(QA-USE-04).
func TestResentSpansAreDeduplicated(t *testing.T) {
	spans := loadFixture(t, "week3-sequential-batch")
	once := mustBuild(t, spans, baseOpts())
	twice := mustBuild(t, append(append([]attribution.Span{}, spans...), spans...), baseOpts())
	if len(once.Records) != len(twice.Records) || once.UsageReportID != twice.UsageReportID {
		t.Fatalf("resend changed output: %d/%d records, id %s vs %s", len(once.Records), len(twice.Records), once.UsageReportID, twice.UsageReportID)
	}
	var sum1, sum2 int64
	for i := range once.Records {
		if once.Records[i].ApproxInputTokens != nil {
			sum1 += *once.Records[i].ApproxInputTokens
			sum2 += *twice.Records[i].ApproxInputTokens
		}
	}
	if sum1 != 668 || sum2 != sum1 {
		t.Fatalf("token sums once=%d twice=%d, want 668", sum1, sum2)
	}
}

func TestReportIDChangesWithPricingAndOptions(t *testing.T) {
	spans := loadFixture(t, "week1-sequential")
	base := mustBuild(t, spans, baseOpts()).UsageReportID
	opt := baseOpts()
	opt.GeneratedAt = opt.GeneratedAt.Add(time.Hour)
	if mustBuild(t, spans, opt).UsageReportID != base {
		t.Fatal("generated_at must not change the report id")
	}
	opt = baseOpts()
	opt.ConfigPricingVersion = "openclaw-config-sha256:abc"
	if mustBuild(t, spans, opt).UsageReportID == base {
		t.Fatal("pricing table change must change the report id")
	}
	opt = baseOpts()
	opt.Attribution.IncludeCacheInPrompt = true
	if mustBuild(t, spans, opt).UsageReportID == base {
		t.Fatal("calculation option change must change the report id")
	}
}

func TestUsageIDStableAndScopedByEnvironment(t *testing.T) {
	a := UsageID("env-a", "p", "t", "s")
	if a != UsageID("env-a", "p", "t", "s") {
		t.Fatal("usage_id not deterministic")
	}
	if a == UsageID("env-b", "p", "t", "s") || a == UsageID("env-a", "p2", "t", "s") {
		t.Fatal("usage_id must include environment and profile")
	}
	// 구분자 덕분에 경계가 달라도 충돌하지 않아야 한다.
	if UsageID("ab", "c", "t", "s") == UsageID("a", "bc", "t", "s") {
		t.Fatal("usage_id collides across field boundaries")
	}
}

// 집계 구간은 도구 시작 시각 기준 [start, end), 시작 시각 없는 도구는 제외하고 사유를 남긴다.
func TestWindowAndMissingStart(t *testing.T) {
	spans := loadFixture(t, "week3-sequential-batch")
	full := mustBuild(t, spans, baseOpts())
	first := full.Records[0]

	// 첫 도구 시작 시각에서 끝나는 구간 → 첫 도구는 end 미포함이라 빠지고, 그 전 도구는 없음.
	var firstStart time.Time
	for _, s := range spans {
		if s.SpanID == first.ToolSpanID {
			firstStart = s.Start
		}
	}
	opt := baseOpts()
	opt.WindowStart, opt.WindowEnd = firstStart.Add(-time.Hour), firstStart
	rep := mustBuild(t, spans, opt)
	if len(rep.Records) != 0 || !containsLimitation(rep, "outside the window") {
		t.Fatalf("end must be exclusive: %d records, limitations %v", len(rep.Records), rep.Limitations)
	}
	opt.WindowStart, opt.WindowEnd = firstStart, firstStart.Add(time.Nanosecond)
	if rep = mustBuild(t, spans, opt); len(rep.Records) != 1 || rep.Records[0].ToolSpanID != first.ToolSpanID {
		t.Fatalf("start must be inclusive: %+v", rep.Records)
	}

	// 첫 도구의 시작 시각을 지우면 제외되고 사유가 남는다.
	cut := append([]attribution.Span{}, spans...)
	for i := range cut {
		if cut[i].SpanID == first.ToolSpanID {
			cut[i].Start = time.Time{}
		}
	}
	rep = mustBuild(t, cut, baseOpts())
	if len(rep.Records) != len(full.Records)-1 || !containsLimitation(rep, "no start time") {
		t.Fatalf("missing start: %d records, limitations %v", len(rep.Records), rep.Limitations)
	}
}

func containsLimitation(rep *UsageReport, s string) bool {
	for _, l := range rep.Limitations {
		if strings.Contains(l, s) {
			return true
		}
	}
	return false
}

func TestBuildValidatesContext(t *testing.T) {
	spans := loadFixture(t, "week1-sequential")
	if _, err := Build(spans, Options{ProfileID: "p"}); err == nil {
		t.Fatal("missing environment_id must fail")
	}
	inv, err := LoadInventory("testdata/inventory-fs.json")
	if err != nil {
		t.Fatal(err)
	}
	opt := baseOpts()
	opt.EnvironmentID = "env-other"
	opt.Inventory = inv
	if _, err := Build(spans, opt); err == nil {
		t.Fatal("inventory from another environment must be rejected")
	}
	opt = baseOpts()
	opt.WindowStart = time.Now()
	if _, err := Build(spans, opt); err == nil {
		t.Fatal("half-open window flag must fail")
	}
}

// JSON 모양: 스키마 14.1 필수 필드가 모두 있고 null 허용 필드는 null로 직렬화.
func TestJSONShape(t *testing.T) {
	inv, err := LoadInventory("testdata/inventory-fs.json")
	if err != nil {
		t.Fatal(err)
	}
	opt := baseOpts()
	opt.Inventory = inv
	rep := mustBuild(t, loadFixture(t, "week3-sequential-batch"), opt)
	b, err := json.Marshal(rep)
	if err != nil {
		t.Fatal(err)
	}
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		t.Fatal(err)
	}
	for _, k := range []string{"schema_version", "usage_report_id", "environment_id", "profile_id", "generated_at",
		"producer", "window", "inventory_snapshot_id", "records", "limitations"} {
		if _, ok := m[k]; !ok {
			t.Errorf("report missing %s", k)
		}
	}
	if m["inventory_snapshot_id"] != "snap-test-fs" {
		t.Errorf("inventory_snapshot_id = %v", m["inventory_snapshot_id"])
	}
	recs := m["records"].([]any)
	for _, raw := range recs {
		rec := raw.(map[string]any)
		for _, k := range []string{"usage_id", "trace_id", "run_id", "tool_span_id", "tool_call_id", "tool_name", "tool_source",
			"asset_ref", "mapping_status", "mapping_reason", "mapping_evidence_refs", "pattern", "duration_ms",
			"approx_input_tokens", "negative_delta", "missing_timestamps", "model", "provider", "closing_model_span_id",
			"attribution_method", "attribution_version", "include_cache_in_prompt", "estimated", "estimated_cost_usd",
			"pricing", "evidence_source_refs", "note"} {
			if _, ok := rec[k]; !ok {
				t.Errorf("record missing %s", k)
			}
		}
		p := rec["pricing"].(map[string]any)
		for _, k := range []string{"source", "version", "currency", "input_per_million"} {
			if _, ok := p[k]; !ok {
				t.Errorf("pricing missing %s", k)
			}
		}
		if rec["mapping_status"] == MappingMatched && len(rec["mapping_evidence_refs"].([]any)) == 0 {
			t.Errorf("matched record needs evidence refs: %v", rec)
		}
	}
	if _, err := time.Parse(time.RFC3339, m["generated_at"].(string)); err != nil {
		t.Error(err)
	}
	fmt.Fprint(new(bytes.Buffer), len(recs))
}

// 판정 결과에 토큰 값이 실려 와도 순차가 아니면 레코드에는 null로 둔다(방어적 규칙).
func TestNonSequentialResultNeverCarriesTokens(t *testing.T) {
	for _, p := range []attribution.Pattern{attribution.Parallel, attribution.Batch, attribution.Unattributed} {
		r := newRecord(attribution.Result{TraceID: "t", ToolSpanID: "s", Pattern: p, HasTokens: true, ApproxTokens: 50,
			Model: "claude-haiku-4-5-20251001"}, baseOpts())
		if r.ApproxInputTokens != nil || r.EstimatedCostUSD != nil {
			t.Errorf("%s: tokens/cost must be null", p)
		}
	}
}
