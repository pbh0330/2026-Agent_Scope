package usagereport

import (
	"fmt"
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

// 이미지 등 결과 일부를 세지 못한 기록(skippedBlocks > 0)은 쓰지 않는다. 앞서 온전한 값이 있었어도 지운다.
func TestReadToolResultCountsSkipsPartial(t *testing.T) {
	p := writeToolResults(t,
		`{"v":1,"kind":"token_count","toolCallId":"img","countedTokens":40,"skippedBlocks":0}`,
		`{"v":1,"kind":"token_count","toolCallId":"img","countedTokens":12,"skippedBlocks":1}`,
		`{"v":1,"kind":"token_count","toolCallId":"txt","countedTokens":300,"skippedBlocks":0}`,
	)
	counts := map[string]int64{}
	st, err := ReadToolResultCounts(p, counts)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := counts["img"]; ok || counts["txt"] != 300 || len(counts) != 1 {
		t.Fatalf("counts=%v", counts)
	}
	if st.Partial != 1 || st.Counts != 2 {
		t.Fatalf("stats=%+v", st)
	}
}

// 구간 안 한 도구가 일부만 센 기록이면 그 구간은 배분하지 않는다(다른 도구에 몫을 넘기지 않음).
func TestParallelSegmentWithPartialCountNotAllocated(t *testing.T) {
	spans := loadFixture(t, "week3-parallel")
	lines := []string{}
	for i, id := range parallelCalls {
		skipped := 0
		if i == 0 {
			skipped = 1
		}
		lines = append(lines, fmt.Sprintf(`{"v":1,"kind":"token_count","toolCallId":"%s","countedTokens":%d,"skippedBlocks":%d}`, id, 100*(i+1), skipped))
	}
	counts := map[string]int64{}
	if _, err := ReadToolResultCounts(writeToolResults(t, lines...), counts); err != nil {
		t.Fatal(err)
	}
	opt := baseOpts()
	opt.ToolResultCounts = counts
	rep := mustBuild(t, spans, opt)
	n := 0
	for _, r := range rep.Records {
		if r.Pattern != string(attribution.Parallel) {
			continue
		}
		n++
		if r.ApproxInputTokens != nil {
			t.Fatalf("일부만 센 도구가 있는 구간이 배분됨: %+v", r)
		}
	}
	if n != len(parallelCalls) {
		t.Fatalf("병렬 레코드 %d개", n)
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

func countSpan(id string, n, skipped int64) attribution.Span {
	return attribution.Span{TraceID: "aa", SpanID: "cnt-" + id, Name: attribution.SpanToolResultCount,
		Attrs: map[string]any{attribution.AttrToolCallID: id, attribution.AttrCountedTokens: n, attribution.AttrCountSkippedBlocks: skipped}}
}

// 스팬 파일 안의 결과별 토큰 수 스팬(플러그인이 Collector로 보낸 것)만으로도 병렬 구간을 배분한다.
func TestParallelAllocatedFromCountSpansInTraceFile(t *testing.T) {
	spans := loadFixture(t, "week3-parallel")
	for i, id := range parallelCalls {
		spans = append(spans, countSpan(id, int64(100*(i+1)), 0))
	}
	rep := mustBuild(t, spans, baseOpts())
	var sum int64
	n := 0
	for _, r := range rep.Records {
		if r.Pattern != string(attribution.Parallel) {
			continue
		}
		n++
		if r.ApproxInputTokens == nil || r.AttributionMethod != "parallel-token-count" {
			t.Fatalf("배분 안 됨: %+v", r)
		}
		sum += *r.ApproxInputTokens
		found := false
		for _, ref := range r.EvidenceSourceRefs {
			if strings.Contains(ref, "span=cnt-") {
				found = true
			}
		}
		if !found {
			t.Fatalf("카운트 스팬 근거가 없음: %v", r.EvidenceSourceRefs)
		}
	}
	if n != len(parallelCalls) || sum <= 0 {
		t.Fatalf("n=%d sum=%d", n, sum)
	}
}

// --tool-results 파일 값이 스팬 값보다 우선하고, 스팬의 일부만 센 값은 배분에 쓰지 않는다.
func TestCountSourcesPrecedenceAndPartial(t *testing.T) {
	spans := loadFixture(t, "week3-parallel")
	for _, id := range parallelCalls {
		spans = append(spans, countSpan(id, 100, 0))
	}
	opt := baseOpts()
	opt.ToolResultCounts = map[string]int64{parallelCalls[0]: 700}
	opt.ToolResultsRef = "agentscope-tool-results.jsonl"
	rep := mustBuild(t, spans, opt)
	vals := map[string]int64{}
	for _, r := range rep.Records {
		if r.Pattern == string(attribution.Parallel) && r.ApproxInputTokens != nil {
			vals[*r.ToolCallID] = *r.ApproxInputTokens
		}
	}
	if !(vals[parallelCalls[0]] > 6*vals[parallelCalls[1]]) {
		t.Fatalf("파일 값(700)이 스팬 값(100)보다 우선해야 함: %v", vals)
	}

	partial := countSpan(parallelCalls[2], 50, 1) // 같은 도구의 일부만 센 값(다른 스팬)
	partial.SpanID = "cnt-partial"
	spans = append(spans, partial)
	rep = mustBuild(t, spans, baseOpts())
	for _, r := range rep.Records {
		if r.Pattern == string(attribution.Parallel) && r.ApproxInputTokens != nil {
			t.Fatalf("일부만 센 도구가 있는 구간은 배분하지 않음: %+v", r)
		}
	}
}
