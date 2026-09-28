package tokenattributionconnector

import (
	"encoding/hex"
	"sort"
	"strings"
	"time"

	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/pmetric"

	"github.com/pbh0330/2026-Agent_Scope/token-collector/collector/attribution"
	"github.com/pbh0330/2026-Agent_Scope/token-collector/collector/tokenattributionconnector/internal/metadata"
)

// 내보내는 메트릭 이름. Prometheus에서는 점(.)이 밑줄(_)로 바뀌고 카운터에 _total이 붙는다.
const (
	metricCalls     = "openclaw.tool.attribution.calls"
	metricDuration  = "openclaw.tool.attribution.duration"
	metricTokens    = "openclaw.tool.attribution.tokens"
	metricCost      = "openclaw.tool.attribution.cost_usd"
	metricAnomalies = "openclaw.tool.attribution.anomalies"
	metricPending   = "openclaw.tool.attribution.pending_runs"
)

// 메트릭 속성 키.
const (
	attrToolName    = "tool.name"
	attrToolSource  = "tool.source"
	attrMCPServer   = "mcp.server"
	attrPattern     = "attribution.pattern"
	attrModel       = "gen_ai.request.model"
	attrProvider    = "openclaw.provider"
	attrPriceSource = "pricing.source"
	attrReason      = "reason"
	attrEstimated   = "attribution.estimated"
)

// 도구 실행 시간 히스토그램 경계(ms).
var durationBounds = []float64{5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000}

type kv struct{ k, v string }

type exemplar struct {
	traceID pcommon.TraceID
	spanID  pcommon.SpanID
	ts      time.Time
	value   float64
}

type series struct {
	attrs     []kv
	intVal    int64
	dblVal    float64
	counts    []uint64 // 히스토그램 버킷(len = len(durationBounds)+1)
	count     uint64
	sum       float64
	exemplars []exemplar
}

// aggregator는 확정된 귀속 결과를 누적(cumulative) 메트릭으로 모은다.
// Prometheus 익스포터는 누적값을 기대하므로, 시작 이후 합계를 계속 들고 있다가 주기마다 전부 내보낸다.
type aggregator struct {
	start     time.Time
	maxEx     int
	calls     map[string]*series
	duration  map[string]*series
	tokens    map[string]*series
	cost      map[string]*series
	anomalies map[string]*series
}

func newAggregator(start time.Time, maxExemplars int) *aggregator {
	return &aggregator{
		start: start, maxEx: maxExemplars,
		calls: map[string]*series{}, duration: map[string]*series{}, tokens: map[string]*series{},
		cost: map[string]*series{}, anomalies: map[string]*series{},
	}
}

func key(attrs []kv) string {
	var b strings.Builder
	for _, a := range attrs {
		b.WriteString(a.k)
		b.WriteByte(0)
		b.WriteString(a.v)
		b.WriteByte(0)
	}
	return b.String()
}

func get(m map[string]*series, attrs []kv) *series {
	k := key(attrs)
	s, ok := m[k]
	if !ok {
		s = &series{attrs: attrs}
		m[k] = s
	}
	return s
}

// mcpServer는 MCP 도구 이름("<server>__<tool>")에서 서버 이름을 뽑는다.
func mcpServer(r attribution.Result) string {
	if r.ToolSource != "mcp" {
		return ""
	}
	if i := strings.Index(r.ToolName, "__"); i > 0 {
		return r.ToolName[:i]
	}
	return ""
}

func (a *aggregator) addExemplar(s *series, r attribution.Result, now time.Time, value float64) {
	if a.maxEx <= 0 {
		return
	}
	var ex exemplar
	if b, err := hex.DecodeString(r.TraceID); err == nil && len(b) == 16 {
		copy(ex.traceID[:], b)
	}
	if b, err := hex.DecodeString(r.ToolSpanID); err == nil && len(b) == 8 {
		copy(ex.spanID[:], b)
	}
	ex.ts, ex.value = now, value
	if len(s.exemplars) >= a.maxEx {
		s.exemplars = s.exemplars[1:]
	}
	s.exemplars = append(s.exemplars, ex)
}

// record는 확정된 도구 결과 하나를 누적한다.
func (a *aggregator) record(r attribution.Result, pricing attribution.Pricing, now time.Time) {
	base := []kv{{attrToolName, r.ToolName}, {attrToolSource, r.ToolSource}, {attrMCPServer, mcpServer(r)}}
	withPattern := append(append([]kv{}, base...), kv{attrPattern, string(r.Pattern)})

	c := get(a.calls, withPattern)
	c.intVal++
	a.addExemplar(c, r, now, 1)

	if r.HasDuration {
		h := get(a.duration, withPattern)
		if h.counts == nil {
			h.counts = make([]uint64, len(durationBounds)+1)
		}
		h.counts[sort.SearchFloat64s(durationBounds, r.DurationMs)]++
		h.count++
		h.sum += r.DurationMs
		a.addExemplar(h, r, now, r.DurationMs)
	}

	if r.Pattern == attribution.Sequential && r.HasTokens {
		modelAttrs := append(append([]kv{}, base...), kv{attrModel, r.Model}, kv{attrProvider, r.Provider}, kv{attrEstimated, "true"})
		t := get(a.tokens, modelAttrs)
		t.intVal += r.ApproxTokens
		a.addExemplar(t, r, now, float64(r.ApproxTokens))

		if usd, src, ok := pricing.InputCost(r.Model, r.ApproxTokens); ok {
			cs := get(a.cost, append(append([]kv{}, modelAttrs...), kv{attrPriceSource, src}))
			cs.dblVal += usd
			a.addExemplar(cs, r, now, usd)
		}
	}

	var reasons []string
	if r.NegativeDelta {
		reasons = append(reasons, "negative_delta")
	}
	if r.Pattern == attribution.Sequential && !r.HasTokens {
		reasons = append(reasons, "missing_tokens")
	}
	if r.MissingTimestamps {
		reasons = append(reasons, "missing_timestamps")
	}
	for _, reason := range reasons {
		s := get(a.anomalies, []kv{{attrToolName, r.ToolName}, {attrReason, reason}})
		s.intVal++
		a.addExemplar(s, r, now, 1)
	}
}

func sortedSeries(m map[string]*series) []*series {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	out := make([]*series, len(keys))
	for i, k := range keys {
		out[i] = m[k]
	}
	return out
}

func putAttrs(dst pcommon.Map, attrs []kv) {
	for _, a := range attrs {
		dst.PutStr(a.k, a.v)
	}
}

func putExemplars(dst pmetric.ExemplarSlice, exs []exemplar, asInt bool) {
	for _, ex := range exs {
		e := dst.AppendEmpty()
		e.SetTraceID(ex.traceID)
		e.SetSpanID(ex.spanID)
		e.SetTimestamp(pcommon.NewTimestampFromTime(ex.ts))
		if asInt {
			e.SetIntValue(int64(ex.value))
		} else {
			e.SetDoubleValue(ex.value)
		}
	}
}

// build는 지금까지의 누적값 전체를 pmetric으로 만든다. exemplar는 내보낸 뒤 비운다.
func (a *aggregator) build(now time.Time, pendingRuns int) pmetric.Metrics {
	md := pmetric.NewMetrics()
	rm := md.ResourceMetrics().AppendEmpty()
	rm.Resource().Attributes().PutStr("service.name", "openclaw-token-attribution")
	sm := rm.ScopeMetrics().AppendEmpty()
	sm.Scope().SetName(metadata.ScopeName)
	start, ts := pcommon.NewTimestampFromTime(a.start), pcommon.NewTimestampFromTime(now)

	addSum := func(name, desc, unit string, m map[string]*series, isInt bool) {
		if len(m) == 0 {
			return
		}
		met := sm.Metrics().AppendEmpty()
		met.SetName(name)
		met.SetDescription(desc)
		met.SetUnit(unit)
		sum := met.SetEmptySum()
		sum.SetIsMonotonic(true)
		sum.SetAggregationTemporality(pmetric.AggregationTemporalityCumulative)
		for _, s := range sortedSeries(m) {
			dp := sum.DataPoints().AppendEmpty()
			dp.SetStartTimestamp(start)
			dp.SetTimestamp(ts)
			putAttrs(dp.Attributes(), s.attrs)
			if isInt {
				dp.SetIntValue(s.intVal)
			} else {
				dp.SetDoubleValue(s.dblVal)
			}
			putExemplars(dp.Exemplars(), s.exemplars, isInt)
			s.exemplars = nil
		}
	}

	addSum(metricCalls, "도구 호출 수(귀속 패턴별: sequential/parallel/batch/unattributed)", "{call}", a.calls, true)
	addSum(metricTokens, "순차 구간에서 도구에 귀속된 근사 입력 토큰 수(추정치)", "{token}", a.tokens, true)
	addSum(metricCost, "도구에 귀속된 근사 비용(USD, 추정치; pricing.source=reference_list_price면 참고용 정가)", "{USD}", a.cost, false)
	addSum(metricAnomalies, "근사치 신뢰도를 낮추는 이상 사례 수(음수 delta, 토큰 누락, 시각 누락)", "{event}", a.anomalies, true)

	if len(a.duration) > 0 {
		met := sm.Metrics().AppendEmpty()
		met.SetName(metricDuration)
		met.SetDescription("도구 실행 시간(귀속 패턴별)")
		met.SetUnit("ms")
		h := met.SetEmptyHistogram()
		h.SetAggregationTemporality(pmetric.AggregationTemporalityCumulative)
		for _, s := range sortedSeries(a.duration) {
			dp := h.DataPoints().AppendEmpty()
			dp.SetStartTimestamp(start)
			dp.SetTimestamp(ts)
			putAttrs(dp.Attributes(), s.attrs)
			dp.SetCount(s.count)
			dp.SetSum(s.sum)
			dp.ExplicitBounds().FromRaw(durationBounds)
			dp.BucketCounts().FromRaw(s.counts)
			putExemplars(dp.Exemplars(), s.exemplars, false)
			s.exemplars = nil
		}
	}

	met := sm.Metrics().AppendEmpty()
	met.SetName(metricPending)
	met.SetDescription("아직 확정 대기 중인 run 수")
	met.SetUnit("{run}")
	dp := met.SetEmptyGauge().DataPoints().AppendEmpty()
	dp.SetTimestamp(ts)
	dp.SetIntValue(int64(pendingRuns))
	return md
}
