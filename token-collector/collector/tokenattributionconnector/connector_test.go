package tokenattributionconnector

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"testing"
	"time"

	"go.opentelemetry.io/collector/component/componenttest"
	"go.opentelemetry.io/collector/connector/connectortest"
	"go.opentelemetry.io/collector/consumer/consumertest"
	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/pmetric"
	"go.opentelemetry.io/collector/pdata/ptrace"
	"go.uber.org/zap"
)

// 테스트 데이터는 attribution 패키지의 실제 캡처 로그 픽스처를 그대로 쓴다.
const fixtureDir = "../attribution/testdata"

type fixtureSpan struct {
	TraceID  string         `json:"trace_id"`
	ParentID string         `json:"parent_id"`
	SpanID   string         `json:"span_id"`
	Name     string         `json:"name"`
	StartNs  int64          `json:"start_unix_nano"`
	EndNs    int64          `json:"end_unix_nano"`
	Attrs    map[string]any `json:"attrs"`
}

type expected struct {
	Pattern      string `json:"pattern"`
	ApproxTokens *int64 `json:"approx_tokens"`
}

func mustHex(t *testing.T, s string, n int) []byte {
	t.Helper()
	b, err := hex.DecodeString(s)
	if err != nil || len(b) != n {
		t.Fatalf("bad hex id %q", s)
	}
	return b
}

// loadTraces는 픽스처 스팬을 OTLP ptrace 형태로 바꾼다(OpenClaw가 보내는 것과 같은 구조).
func loadTraces(t *testing.T, name string) ptrace.Traces {
	t.Helper()
	f, err := os.Open(filepath.Join(fixtureDir, name+".spans.json"))
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	dec := json.NewDecoder(f)
	dec.UseNumber()
	var raw []fixtureSpan
	if err := dec.Decode(&raw); err != nil {
		t.Fatal(err)
	}
	td := ptrace.NewTraces()
	rs := td.ResourceSpans().AppendEmpty()
	rs.Resource().Attributes().PutStr("service.name", "openclaw")
	ss := rs.ScopeSpans().AppendEmpty()
	for _, r := range raw {
		sp := ss.Spans().AppendEmpty()
		var tid pcommon.TraceID
		copy(tid[:], mustHex(t, r.TraceID, 16))
		var sid pcommon.SpanID
		copy(sid[:], mustHex(t, r.SpanID, 8))
		sp.SetTraceID(tid)
		sp.SetSpanID(sid)
		if r.ParentID != "" {
			var pid pcommon.SpanID
			copy(pid[:], mustHex(t, r.ParentID, 8))
			sp.SetParentSpanID(pid)
		}
		sp.SetName(r.Name)
		sp.SetStartTimestamp(pcommon.Timestamp(r.StartNs))
		sp.SetEndTimestamp(pcommon.Timestamp(r.EndNs))
		for k, v := range r.Attrs {
			switch x := v.(type) {
			case json.Number:
				if i, err := x.Int64(); err == nil {
					sp.Attributes().PutInt(k, i)
				} else if fl, err := x.Float64(); err == nil {
					sp.Attributes().PutDouble(k, fl)
				}
			case string:
				sp.Attributes().PutStr(k, x)
			case bool:
				sp.Attributes().PutBool(k, x)
			}
		}
	}
	return td
}

func loadExpected(t *testing.T, name string) []expected {
	t.Helper()
	b, err := os.ReadFile(filepath.Join(fixtureDir, name+".expected.json"))
	if err != nil {
		t.Fatal(err)
	}
	var out []expected
	if err := json.Unmarshal(b, &out); err != nil {
		t.Fatal(err)
	}
	return out
}

type fakeClock struct{ t time.Time }

func (c *fakeClock) now() time.Time { return c.t }

func newTestConnector(t *testing.T, cfg *Config, sink *consumertest.MetricsSink) (*tokenConnector, *fakeClock) {
	t.Helper()
	c, err := newConnector(zap.NewNop(), cfg, sink)
	if err != nil {
		t.Fatal(err)
	}
	clk := &fakeClock{t: time.Date(2026, 9, 28, 0, 0, 0, 0, time.UTC)}
	c.now = clk.now
	c.agg.start = clk.t
	return c, clk
}

func lastMetrics(t *testing.T, sink *consumertest.MetricsSink) map[string]pmetric.Metric {
	t.Helper()
	all := sink.AllMetrics()
	if len(all) == 0 {
		t.Fatal("no metrics exported")
	}
	md := all[len(all)-1]
	out := map[string]pmetric.Metric{}
	ms := md.ResourceMetrics().At(0).ScopeMetrics().At(0).Metrics()
	for i := 0; i < ms.Len(); i++ {
		out[ms.At(i).Name()] = ms.At(i)
	}
	return out
}

func sumBy(m pmetric.Metric, attr string) map[string]float64 {
	out := map[string]float64{}
	dps := m.Sum().DataPoints()
	for i := 0; i < dps.Len(); i++ {
		dp := dps.At(i)
		v, _ := dp.Attributes().Get(attr)
		if dp.ValueType() == pmetric.NumberDataPointValueTypeInt {
			out[v.Str()] += float64(dp.IntValue())
		} else {
			out[v.Str()] += dp.DoubleValue()
		}
	}
	return out
}

// 실제 로그 3개를 커넥터에 흘려보내면, 내보낸 메트릭의 패턴별 호출 수와 토큰 합계가
// 파이썬 프로토타입 결과와 같아야 한다.
func TestConnectorRealLogsMatchPython(t *testing.T) {
	for _, name := range []string{"week1-sequential", "week3-sequential-batch", "week3-parallel"} {
		t.Run(name, func(t *testing.T) {
			sink := new(consumertest.MetricsSink)
			c, clk := newTestConnector(t, createDefaultConfig(), sink)
			if err := c.ConsumeTraces(context.Background(), loadTraces(t, name)); err != nil {
				t.Fatal(err)
			}
			clk.t = clk.t.Add(5 * time.Second) // grace(2s) 경과, openclaw.run 스팬도 이미 도착
			c.flush(context.Background())

			wantCalls := map[string]float64{}
			var wantTokens float64
			for _, e := range loadExpected(t, name) {
				wantCalls[e.Pattern]++
				if e.ApproxTokens != nil {
					wantTokens += float64(*e.ApproxTokens)
				}
			}
			ms := lastMetrics(t, sink)
			gotCalls := sumBy(ms[metricCalls], attrPattern)
			for p, n := range wantCalls {
				if gotCalls[p] != n {
					t.Errorf("calls[%s]: got %v want %v", p, gotCalls[p], n)
				}
			}
			var gotTokens float64
			if tm, ok := ms[metricTokens]; ok {
				for _, v := range sumBy(tm, attrToolName) {
					gotTokens += v
				}
			}
			if gotTokens != wantTokens {
				t.Errorf("tokens: got %v want %v", gotTokens, wantTokens)
			}
			if wantTokens > 0 {
				// school-gateway 단가는 설정에 없으므로 참고용 정가(input $1/1M)로 환산돼야 한다.
				cost := sumBy(ms[metricCost], attrPriceSource)
				if math.Abs(cost["reference_list_price"]-wantTokens/1e6) > 1e-12 {
					t.Errorf("cost: got %v want %v", cost, wantTokens/1e6)
				}
			}
			if c.tracker.PendingRuns() != 0 {
				t.Errorf("pending runs left: %d", c.tracker.PendingRuns())
			}
		})
	}
}

// 누적(cumulative) 값은 flush를 반복해도 줄거나 중복 집계되면 안 된다.
func TestConnectorCumulativeNoDoubleCount(t *testing.T) {
	sink := new(consumertest.MetricsSink)
	c, clk := newTestConnector(t, createDefaultConfig(), sink)
	_ = c.ConsumeTraces(context.Background(), loadTraces(t, "week3-parallel"))
	for i := 0; i < 3; i++ {
		clk.t = clk.t.Add(5 * time.Second)
		c.flush(context.Background())
	}
	got := sumBy(lastMetrics(t, sink)[metricCalls], attrPattern)
	if got["parallel"] != 4 {
		t.Fatalf("parallel calls after repeated flush: %v", got)
	}
}

// exemplar에 원래 도구 스팬의 traceId/spanId가 실려야 Grafana에서 트레이스로 넘어갈 수 있다.
func TestConnectorExemplarsCarryTraceIDs(t *testing.T) {
	sink := new(consumertest.MetricsSink)
	c, clk := newTestConnector(t, createDefaultConfig(), sink)
	_ = c.ConsumeTraces(context.Background(), loadTraces(t, "week1-sequential"))
	clk.t = clk.t.Add(5 * time.Second)
	c.flush(context.Background())
	dp := lastMetrics(t, sink)[metricTokens].Sum().DataPoints().At(0)
	if dp.Exemplars().Len() != 1 {
		t.Fatalf("exemplars: %d", dp.Exemplars().Len())
	}
	ex := dp.Exemplars().At(0)
	if ex.TraceID().IsEmpty() || ex.SpanID().IsEmpty() || ex.IntValue() != dp.IntValue() {
		t.Fatalf("bad exemplar: trace=%s span=%s val=%d", ex.TraceID(), ex.SpanID(), ex.IntValue())
	}
	// 다음 flush에는 새 exemplar가 없어야 한다(한 번만 붙음).
	clk.t = clk.t.Add(5 * time.Second)
	c.flush(context.Background())
	if n := lastMetrics(t, sink)[metricTokens].Sum().DataPoints().At(0).Exemplars().Len(); n != 0 {
		t.Fatalf("exemplars should be cleared, got %d", n)
	}
}

func TestConnectorPricingFromOpenClawConfig(t *testing.T) {
	path := filepath.Join(t.TempDir(), "openclaw.json")
	os.WriteFile(path, []byte(`{"models":{"providers":{"p":{"models":[
		{"id":"claude-haiku-4-5-20251001","cost":{"input":3,"output":15}}]}}}}`), 0o600)
	cfg := createDefaultConfig()
	cfg.OpenClawConfigPath = path
	sink := new(consumertest.MetricsSink)
	c, clk := newTestConnector(t, cfg, sink)
	_ = c.ConsumeTraces(context.Background(), loadTraces(t, "week1-sequential"))
	clk.t = clk.t.Add(5 * time.Second)
	c.flush(context.Background())
	cost := sumBy(lastMetrics(t, sink)[metricCost], attrPriceSource)
	if math.Abs(cost["config"]-264*3/1e6) > 1e-12 {
		t.Fatalf("config pricing not applied: %v", cost)
	}
}

func TestFactoryLifecycle(t *testing.T) {
	f := NewFactory()
	cfg := f.CreateDefaultConfig().(*Config)
	if err := cfg.Validate(); err != nil {
		t.Fatal(err)
	}
	if err := componenttest.CheckConfigStruct(cfg); err != nil {
		t.Fatal(err)
	}
	cfg.MetricsFlushInterval = 10 * time.Millisecond
	sink := new(consumertest.MetricsSink)
	conn, err := f.CreateTracesToMetrics(context.Background(), connectortest.NewNopSettings(f.Type()), cfg, sink)
	if err != nil {
		t.Fatal(err)
	}
	if err := conn.Start(context.Background(), componenttest.NewNopHost()); err != nil {
		t.Fatal(err)
	}
	if err := conn.ConsumeTraces(context.Background(), loadTraces(t, "week3-parallel")); err != nil {
		t.Fatal(err)
	}
	time.Sleep(50 * time.Millisecond)
	if err := conn.Shutdown(context.Background()); err != nil {
		t.Fatal(err)
	}
	if len(sink.AllMetrics()) == 0 {
		t.Fatal("ticker did not export any metrics")
	}
}

func TestConfigValidate(t *testing.T) {
	cfg := createDefaultConfig()
	cfg.MetricsFlushInterval = 0
	cfg.MaxRuns = -1
	if err := cfg.Validate(); err == nil {
		t.Fatal("expected validation error")
	}
}
