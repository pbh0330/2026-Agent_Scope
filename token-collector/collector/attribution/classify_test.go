package attribution

import (
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

var t0 = time.Date(2026, 9, 22, 10, 0, 0, 0, time.UTC)

func sec(s float64) time.Time { return t0.Add(time.Duration(s * float64(time.Second))) }

func mc(id string, start, end float64, in, out int64) Span {
	return Span{TraceID: "tr", ParentID: "run", SpanID: id, Name: SpanModelCall,
		Start: sec(start), End: sec(end),
		Attrs: map[string]any{AttrInputTokens: in, AttrOutputTokens: out, AttrModel: "m"}}
}

func tool(id string, start, end float64, name string) Span {
	return Span{TraceID: "tr", ParentID: "run", SpanID: id, Name: SpanToolExec,
		Start: sec(start), End: sec(end), Attrs: map[string]any{AttrToolName: name}}
}

func patterns(rs []Result) map[Pattern]int {
	m := map[Pattern]int{}
	for _, r := range rs {
		m[r.Pattern]++
	}
	return m
}

// ---- 파이썬 test_attribution.py 9건을 그대로 옮긴 테스트 ----

func TestSequential(t *testing.T) {
	rs := Classify([]Span{mc("m1", 0, 2, 1000, 50), tool("t1", 2, 3, "toolA"), mc("m2", 3, 5, 1300, 40)}, Options{})
	if len(rs) != 1 || rs[0].Pattern != Sequential || !rs[0].HasTokens || rs[0].ApproxTokens != 250 {
		t.Fatalf("got %+v", rs)
	}
	if rs[0].ClosingModelSpanID != "m2" || rs[0].Model != "m" {
		t.Fatalf("closing/model wrong: %+v", rs[0])
	}
}

func TestParallel(t *testing.T) {
	rs := Classify([]Span{mc("m1", 0, 2, 1000, 50), tool("t1", 2, 5, "toolA"), tool("t2", 3, 6, "toolB"), mc("m2", 6, 8, 1800, 30)}, Options{})
	if p := patterns(rs); len(rs) != 2 || p[Parallel] != 2 {
		t.Fatalf("got %+v", rs)
	}
	for _, r := range rs {
		if r.HasTokens {
			t.Fatalf("parallel must not attribute tokens: %+v", r)
		}
	}
}

func TestBatch(t *testing.T) {
	rs := Classify([]Span{mc("m1", 0, 2, 1000, 50), tool("t1", 2, 3, "toolA"), tool("t2", 3, 4, "toolB"), mc("m2", 4, 6, 1600, 20)}, Options{})
	if p := patterns(rs); len(rs) != 2 || p[Batch] != 2 {
		t.Fatalf("got %+v", rs)
	}
}

func TestNegativeDeltaFlagged(t *testing.T) {
	rs := Classify([]Span{mc("m1", 0, 2, 5000, 50), tool("t1", 2, 3, "toolA"), mc("m2", 3, 5, 1200, 40)}, Options{})
	if len(rs) != 1 || rs[0].Pattern != Sequential || rs[0].ApproxTokens != 0 || !rs[0].NegativeDelta || !strings.Contains(rs[0].Note, "delta<0") {
		t.Fatalf("got %+v", rs)
	}
}

func TestBoundaryTouchIsNotParallel(t *testing.T) {
	rs := Classify([]Span{mc("m1", 0, 2, 1000, 50), tool("t1", 2, 3, "toolA"), tool("t2", 3, 4, "toolB"), mc("m2", 4, 6, 1600, 20)}, Options{})
	if p := patterns(rs); p[Batch] != 2 {
		t.Fatalf("got %+v", rs)
	}
}

func TestNoModelCallMarkedUnattributed(t *testing.T) {
	rs := Classify([]Span{tool("t1", 0, 1, "toolA")}, Options{})
	if len(rs) != 1 || rs[0].Pattern != Unattributed || rs[0].HasTokens {
		t.Fatalf("got %+v", rs)
	}
}

func TestMissingTimestampFlagsBatchConfidence(t *testing.T) {
	t2 := tool("t2", 2, 0, "toolB")
	t2.End = time.Time{}
	rs := Classify([]Span{mc("m1", 0, 2, 1000, 50), tool("t1", 2, 3, "toolA"), t2, mc("m2", 4, 6, 1600, 20)}, Options{})
	if p := patterns(rs); p[Batch] != 2 {
		t.Fatalf("got %+v", rs)
	}
	for _, r := range rs {
		if !strings.Contains(r.Note, "⚠") {
			t.Fatalf("missing warning: %+v", r)
		}
	}
}

func TestToolAfterLastModelCallIsUnattributed(t *testing.T) {
	rs := Classify([]Span{mc("m1", 0, 2, 1000, 50), tool("t1", 2, 3, "toolA")}, Options{})
	if len(rs) != 1 || rs[0].Pattern != Unattributed || rs[0].ClosingModelSpanID != "" {
		t.Fatalf("got %+v", rs)
	}
}

func TestToolStartedDuringModelCallIsUnattributed(t *testing.T) {
	rs := Classify([]Span{mc("m1", 0, 2, 1000, 50), tool("t1", 1, 3, "toolA"), mc("m2", 3, 5, 1300, 40)}, Options{})
	if len(rs) != 1 || rs[0].Pattern != Unattributed {
		t.Fatalf("got %+v", rs)
	}
}

// ---- Go 전용 추가 테스트 ----

func TestIncludeCacheInPrompt(t *testing.T) {
	m1 := mc("m1", 0, 2, 100, 50)
	m1.Attrs[AttrCacheReadTokens] = int64(5000)
	m2 := mc("m2", 3, 5, 100, 40)
	m2.Attrs[AttrCacheReadTokens] = int64(5300)
	spans := []Span{m1, tool("t1", 2, 3, "toolA"), m2}
	if rs := Classify(spans, Options{}); rs[0].ApproxTokens != 0 || !rs[0].NegativeDelta {
		t.Fatalf("without cache option expected clamp, got %+v", rs[0])
	}
	if rs := Classify(spans, Options{IncludeCacheInPrompt: true}); rs[0].ApproxTokens != 250 {
		t.Fatalf("with cache option expected 250, got %+v", rs[0])
	}
}

// ---- 실제 캡처 로그 3개로 파이썬과 결과가 같은지 비교 ----

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
	TraceID      string   `json:"trace_id"`
	RunID        string   `json:"run_id"`
	ToolSpanID   string   `json:"tool_span_id"`
	ToolName     string   `json:"tool_name"`
	Pattern      Pattern  `json:"pattern"`
	ApproxTokens *int64   `json:"approx_tokens"`
	DurationMs   *float64 `json:"duration_ms"`
}

func nsTime(ns int64) time.Time {
	if ns == 0 {
		return time.Time{}
	}
	return time.Unix(0, ns).UTC()
}

// loadFixtureSpans는 파일에 적힌 순서(=Collector가 받은 순서) 그대로 스팬을 돌려준다.
func loadFixtureSpans(t *testing.T, path string) []Span {
	t.Helper()
	f, err := os.Open(path)
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
	out := make([]Span, 0, len(raw))
	for _, r := range raw {
		attrs := map[string]any{}
		for k, v := range r.Attrs {
			if n, ok := v.(json.Number); ok {
				if i, err := n.Int64(); err == nil {
					attrs[k] = i
				} else if fl, err := n.Float64(); err == nil {
					attrs[k] = fl
				}
				continue
			}
			attrs[k] = v
		}
		out = append(out, Span{TraceID: r.TraceID, ParentID: r.ParentID, SpanID: r.SpanID, Name: r.Name,
			Start: nsTime(r.StartNs), End: nsTime(r.EndNs), Attrs: attrs})
	}
	return out
}

func loadExpected(t *testing.T, path string) map[string]expected {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var list []expected
	if err := json.Unmarshal(b, &list); err != nil {
		t.Fatal(err)
	}
	m := map[string]expected{}
	for _, e := range list {
		m[e.ToolSpanID] = e
	}
	return m
}

func compareToPython(t *testing.T, got []Result, want map[string]expected) {
	t.Helper()
	if len(got) != len(want) {
		t.Fatalf("result count: go=%d python=%d", len(got), len(want))
	}
	for _, r := range got {
		e, ok := want[r.ToolSpanID]
		if !ok {
			t.Fatalf("go produced unexpected tool span %s", r.ToolSpanID)
		}
		if r.Pattern != e.Pattern || r.ToolName != e.ToolName || r.RunID != e.RunID || r.TraceID != e.TraceID {
			t.Errorf("%s: go=(%s,%s) python=(%s,%s)", r.ToolSpanID, r.Pattern, r.ToolName, e.Pattern, e.ToolName)
		}
		if (e.ApproxTokens == nil) == r.HasTokens {
			t.Errorf("%s: token presence differs go=%v python=%v", r.ToolSpanID, r.HasTokens, e.ApproxTokens)
		} else if e.ApproxTokens != nil && *e.ApproxTokens != r.ApproxTokens {
			t.Errorf("%s: tokens go=%d python=%d", r.ToolSpanID, r.ApproxTokens, *e.ApproxTokens)
		}
		if e.DurationMs != nil && math.Abs(*e.DurationMs-r.DurationMs) > 1e-6 {
			t.Errorf("%s: duration go=%f python=%f", r.ToolSpanID, r.DurationMs, *e.DurationMs)
		}
	}
}

var fixtures = []string{"week1-sequential", "week3-sequential-batch", "week3-parallel"}

func TestRealLogsMatchPython(t *testing.T) {
	for _, name := range fixtures {
		t.Run(name, func(t *testing.T) {
			spans := loadFixtureSpans(t, filepath.Join("testdata", name+".spans.json"))
			want := loadExpected(t, filepath.Join("testdata", name+".expected.json"))
			compareToPython(t, Classify(spans, Options{}), want)
		})
	}
}

func TestPricing(t *testing.T) {
	p := Pricing{
		Models:    map[string]Rate{"claude-haiku-4-5-20251001": {}, "paid": {Input: 3}},
		Reference: AnthropicListPricingReference,
	}
	if usd, src, ok := p.InputCost("claude-haiku-4-5-20251001", 1_000_000); !ok || src != PriceSourceReference || usd != 1.0 {
		t.Fatalf("zero-rate model should use reference: %v %s %v", usd, src, ok)
	}
	if usd, src, ok := p.InputCost("paid", 500_000); !ok || src != PriceSourceConfig || usd != 1.5 {
		t.Fatalf("configured rate: %v %s %v", usd, src, ok)
	}
	if _, _, ok := p.InputCost("unknown", 1); ok {
		t.Fatal("unknown model must not be priced")
	}
}

func TestLoadPricingFromOpenClawConfig(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "openclaw.json")
	os.WriteFile(path, []byte(`{"models":{"providers":{"school-gateway":{"models":[
		{"id":"claude-haiku-4-5-20251001","cost":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0}},
		{"id":"no-cost"}]}}}}`), 0o600)
	m, err := LoadPricingFromOpenClawConfig(path)
	if err != nil {
		t.Fatal(err)
	}
	if r, ok := m["claude-haiku-4-5-20251001"]; !ok || !r.IsZero() || len(m) != 1 {
		t.Fatalf("got %+v", m)
	}
}
