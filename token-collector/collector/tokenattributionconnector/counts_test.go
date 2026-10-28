package tokenattributionconnector

import (
	"context"
	"testing"
	"time"

	"go.opentelemetry.io/collector/consumer/consumertest"
	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/ptrace"

	"github.com/pbh0330/2026-Agent_Scope/token-collector/collector/attribution"
)

// week3-parallel 픽스처: 같은 구간에서 fs__read_text_file 4개가 동시에 실행된 실제 사례.
var parallelCallIDs = []string{
	"toolu_01LtgUGj9AyYDKJVudpFuyrR", "toolu_0163uF6CK7DVJST6steW349q",
	"toolu_01JCweQwC2bbvQTpkzns4qPZ", "toolu_01CGZFfaQ4YUzqt98nAYSry6",
}

// countTraces는 결과 기록 플러그인이 보내는 것과 같은 결과별 토큰 수 스팬 묶음을 만든다.
func countTraces(counts map[string]int64, skipped map[string]int64) ptrace.Traces {
	td := ptrace.NewTraces()
	rs := td.ResourceSpans().AppendEmpty()
	rs.Resource().Attributes().PutStr("service.name", "agentscope-token-guard")
	ss := rs.ScopeSpans().AppendEmpty()
	i := byte(0)
	for id, n := range counts {
		i++
		sp := ss.Spans().AppendEmpty()
		sp.SetName(attribution.SpanToolResultCount)
		sp.SetTraceID(pcommon.TraceID{0xaa, i})
		sp.SetSpanID(pcommon.SpanID{0xbb, i})
		sp.Attributes().PutStr(attribution.AttrToolCallID, id)
		sp.Attributes().PutInt(attribution.AttrCountedTokens, n)
		sp.Attributes().PutInt(attribution.AttrCountSkippedBlocks, skipped[id])
		sp.Attributes().PutStr(attribution.AttrCountSource, "openai-usage")
	}
	return td
}

// 픽스처의 병렬 구간 증가분(배분 전 합계)을 오프라인 판정으로 구한다.
func parallelSegmentDelta(t *testing.T) int64 {
	t.Helper()
	td := loadTraces(t, "week3-parallel")
	var spans []attribution.Span
	ss := td.ResourceSpans().At(0).ScopeSpans().At(0).Spans()
	for i := 0; i < ss.Len(); i++ {
		spans = append(spans, toSpan(ss.At(i)))
	}
	for _, r := range attribution.Classify(spans, attribution.Options{}) {
		if r.Pattern == attribution.Parallel && r.HasSegmentDelta {
			return r.SegmentDelta
		}
	}
	t.Fatal("병렬 구간 증가분 없음")
	return 0
}

func sumTokensByPattern(t *testing.T, sink *consumertest.MetricsSink) map[string]float64 {
	t.Helper()
	tm, ok := lastMetrics(t, sink)[metricTokens]
	if !ok {
		return map[string]float64{}
	}
	return sumBy(tm, attrPattern)
}

// 결과별 토큰 수 스팬이 오면 병렬 구간 증가분을 그 비율로 나눠 토큰 메트릭에 넣는다(합계 = 구간 증가분).
// 토큰 수가 다 모였으므로 count_wait를 기다리지 않고 grace 뒤 바로 확정된다.
func TestConnectorAllocatesParallelFromCountSpans(t *testing.T) {
	seg := parallelSegmentDelta(t)
	sink := new(consumertest.MetricsSink)
	c, clk := newTestConnector(t, createDefaultConfig(), sink)
	counts := map[string]int64{}
	for i, id := range parallelCallIDs {
		counts[id] = int64(100 * (i + 1))
	}
	// 토큰 수가 OpenClaw 스팬보다 먼저 도착하는 실제 순서(10.12 PC 실측)를 흉내 낸다.
	if err := c.ConsumeTraces(context.Background(), countTraces(counts, nil)); err != nil {
		t.Fatal(err)
	}
	if err := c.ConsumeTraces(context.Background(), loadTraces(t, "week3-parallel")); err != nil {
		t.Fatal(err)
	}
	clk.t = clk.t.Add(3 * time.Second)
	c.flush(context.Background())

	got := sumTokensByPattern(t, sink)
	if got["parallel"] != float64(seg) {
		t.Fatalf("parallel tokens: got %v want %v (구간 증가분)", got["parallel"], seg)
	}
	calls := sumBy(lastMetrics(t, sink)[metricCalls], attrPattern)
	if calls["parallel"] != 4 {
		t.Fatalf("parallel calls: %v", calls)
	}
	if an, ok := lastMetrics(t, sink)[metricAnomalies]; ok {
		if n := sumBy(an, attrReason)["missing_counts"]; n != 0 {
			t.Fatalf("배분했는데 missing_counts %v", n)
		}
	}
	// 도구별 값은 100:200:300:400 비율
	tm := lastMetrics(t, sink)[metricTokens]
	dps := tm.Sum().DataPoints()
	var parallelSeries int
	for i := 0; i < dps.Len(); i++ {
		if v, _ := dps.At(i).Attributes().Get(attrPattern); v.Str() == "parallel" {
			parallelSeries++
			if dps.At(i).Exemplars().Len() == 0 {
				t.Fatalf("배분분에도 exemplar(trace_id)가 있어야 함")
			}
		}
	}
	if parallelSeries == 0 {
		t.Fatalf("parallel 토큰 시리즈 없음")
	}
}

// 결과별 토큰 수가 없으면 count_wait 뒤 배분 없이 확정하고 missing_counts로 센다(플러그인 미설치 환경).
func TestConnectorMissingCountsAfterWait(t *testing.T) {
	sink := new(consumertest.MetricsSink)
	c, clk := newTestConnector(t, createDefaultConfig(), sink)
	_ = c.ConsumeTraces(context.Background(), loadTraces(t, "week3-parallel"))
	clk.t = clk.t.Add(5 * time.Second)
	c.flush(context.Background())
	if m, ok := lastMetrics(t, sink)[metricCalls]; ok {
		if calls := sumBy(m, attrPattern); calls["parallel"] != 0 {
			t.Fatalf("count_wait 안에서는 병렬 구간을 기다려야 함: %v", calls)
		}
	}
	clk.t = clk.t.Add(15 * time.Second)
	c.flush(context.Background())
	ms := lastMetrics(t, sink)
	if calls := sumBy(ms[metricCalls], attrPattern); calls["parallel"] != 4 {
		t.Fatalf("calls: %v", calls)
	}
	if n := sumBy(ms[metricAnomalies], attrReason)["missing_counts"]; n != 4 {
		t.Fatalf("missing_counts: got %v want 4", n)
	}
	if got := sumTokensByPattern(t, sink)["parallel"]; got != 0 {
		t.Fatalf("배분 근거 없이 토큰을 넣으면 안 됨: %v", got)
	}
	if c.tracker.PendingRuns() != 0 {
		t.Fatalf("pending runs left")
	}
}

// 일부만 센 값(이미지 등, skipped_blocks > 0)이 섞이면 기다리지 않고 배분 없이 확정한다.
func TestConnectorPartialCountSkipsAllocation(t *testing.T) {
	sink := new(consumertest.MetricsSink)
	c, clk := newTestConnector(t, createDefaultConfig(), sink)
	counts := map[string]int64{}
	for _, id := range parallelCallIDs {
		counts[id] = 100
	}
	_ = c.ConsumeTraces(context.Background(), countTraces(counts, map[string]int64{parallelCallIDs[0]: 1}))
	_ = c.ConsumeTraces(context.Background(), loadTraces(t, "week3-parallel"))
	clk.t = clk.t.Add(3 * time.Second)
	c.flush(context.Background())
	if calls := sumBy(lastMetrics(t, sink)[metricCalls], attrPattern); calls["parallel"] != 4 {
		t.Fatalf("calls: %v", calls)
	}
	if got := sumTokensByPattern(t, sink)["parallel"]; got != 0 {
		t.Fatalf("일부만 센 도구가 있는 구간은 배분하지 않음: %v", got)
	}
}

func TestConfigValidateCountSettings(t *testing.T) {
	cfg := createDefaultConfig()
	cfg.CountWait = -time.Second
	if cfg.Validate() == nil {
		t.Fatal("음수 count_wait 허용 안 됨")
	}
	cfg = createDefaultConfig()
	cfg.CountTTL = time.Second
	if cfg.Validate() == nil {
		t.Fatal("count_ttl < count_wait 허용 안 됨")
	}
}
