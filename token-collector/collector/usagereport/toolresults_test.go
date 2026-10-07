package usagereport

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/pbh0330/2026-Agent_Scope/token-collector/collector/attribution"
)

// week3-parallel 픽스처: 같은 구간에서 fs__read_text_file 4개가 동시에 실행된 실제 사례.
var parallelCalls = []string{
	"toolu_01LtgUGj9AyYDKJVudpFuyrR", "toolu_0163uF6CK7DVJST6steW349q",
	"toolu_01JCweQwC2bbvQTpkzns4qPZ", "toolu_01CGZFfaQ4YUzqt98nAYSry6",
}

func writeToolResults(t *testing.T, lines ...string) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "agentscope-tool-results.jsonl")
	if err := os.WriteFile(p, []byte(strings.Join(lines, "\n")+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestReadToolResultCounts(t *testing.T) {
	p := writeToolResults(t,
		`{"v":1,"kind":"tool_result","toolCallId":"a","textBytes":10}`,
		`{"v":1,"kind":"token_count","toolCallId":"a","countedTokens":12}`,
		`{"v":1,"kind":"token_count","toolCallId":"a","countedTokens":15}`,
		`{"v":1,"kind":"token_count","toolCallId":"b"}`,
		`not json`,
		``,
		`{"v":1,"kind":"brake","toolCallId":"c","level":"warn"}`,
	)
	counts := map[string]int64{}
	st, err := ReadToolResultCounts(p, counts)
	if err != nil {
		t.Fatal(err)
	}
	if counts["a"] != 15 || len(counts) != 1 {
		t.Fatalf("counts=%v", counts)
	}
	if st.Lines != 6 || st.Counts != 2 || st.Malformed != 2 {
		t.Fatalf("stats=%+v", st)
	}
}

func TestParallelSegmentAllocatedByCounts(t *testing.T) {
	spans := loadFixture(t, "week3-parallel")
	// 배분 전: 구간 증가분 확인
	var seg int64 = -1
	for _, r := range attribution.Classify(spans, attribution.Options{}) {
		if r.Pattern == attribution.Parallel && r.HasSegmentDelta {
			seg = r.SegmentDelta
		}
	}
	if seg <= 0 {
		t.Fatalf("픽스처 병렬 구간 증가분을 못 구함: %d", seg)
	}

	opt := baseOpts()
	opt.ToolResultCounts = map[string]int64{parallelCalls[0]: 100, parallelCalls[1]: 200, parallelCalls[2]: 300, parallelCalls[3]: 400}
	opt.ToolResultsRef = "agentscope-tool-results.jsonl"
	rep := mustBuild(t, spans, opt)

	var sum int64
	n := 0
	for _, r := range rep.Records {
		if r.Pattern != string(attribution.Parallel) {
			continue
		}
		n++
		if r.ApproxInputTokens == nil || r.EstimatedCostUSD == nil {
			t.Fatalf("%s: 배분 토큰·비용이 비어 있음", deref(r.ToolCallID))
		}
		if r.AttributionMethod != AttributionMethodParallelCount || !r.Estimated {
			t.Fatalf("method=%s estimated=%v", r.AttributionMethod, r.Estimated)
		}
		if len(r.EvidenceSourceRefs) != 2 || !strings.HasPrefix(r.EvidenceSourceRefs[1], "tool-results:agentscope-tool-results.jsonl#toolCallId=") {
			t.Fatalf("근거 참조 누락: %v", r.EvidenceSourceRefs)
		}
		sum += *r.ApproxInputTokens
	}
	if n != 4 || sum != seg {
		t.Fatalf("병렬 %d건, 배분 합 %d ≠ 구간 증가분 %d", n, sum, seg)
	}
	if !hasLimitation(rep, "per-result token counts") {
		t.Fatalf("limitations에 배분 설명 없음: %v", rep.Limitations)
	}
}

func TestParallelSegmentWithMissingCountStaysNull(t *testing.T) {
	opt := baseOpts()
	opt.ToolResultCounts = map[string]int64{parallelCalls[0]: 100, parallelCalls[1]: 200}
	rep := mustBuild(t, loadFixture(t, "week3-parallel"), opt)
	for _, r := range rep.Records {
		if r.Pattern == string(attribution.Parallel) && (r.ApproxInputTokens != nil || r.AttributionMethod != AttributionMethod) {
			t.Fatalf("토큰 수가 빠진 구간이 배분됨: %+v", r)
		}
	}
	if !hasLimitation(rep, "keep null tokens because a per-result token count was missing") {
		t.Fatalf("limitations에 누락 안내 없음: %v", rep.Limitations)
	}
}

func TestWithoutToolResultsBehaviourUnchanged(t *testing.T) {
	rep := mustBuild(t, loadFixture(t, "week3-parallel"), baseOpts())
	if !hasLimitation(rep, "Only sequential segments carry tokens") {
		t.Fatalf("기존 안내 문구가 바뀜: %v", rep.Limitations)
	}
}

func hasLimitation(rep *UsageReport, sub string) bool {
	for _, l := range rep.Limitations {
		if strings.Contains(l, sub) {
			return true
		}
	}
	return false
}
