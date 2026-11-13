package usageapi

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestTimeseries(t *testing.T) {
	s := load(t, LoadConfig{})
	var got timeseriesResp
	get(t, s, "/api/v1/usage/timeseries", 200, &got)
	if got.Group != GroupTool || got.Step != "1m0s" {
		t.Fatalf("group/step: %s %s", got.Group, got.Step)
	}
	// 05:24:02 ~ 05:29:03 → 1분 구간 05:24 ~ 05:29 (6개)
	if len(got.Total.Points) != 6 || got.Total.Points[0].T != "2026-10-29T05:24:00.000Z" {
		t.Fatalf("points: %+v", got.Total.Points)
	}
	var tok int64
	calls := 0
	for _, p := range got.Total.Points {
		tok += p.Tokens
		calls += p.Calls
	}
	if tok != 15769 || calls != 16 || got.Total.Tokens != 15769 {
		t.Fatalf("total: %d tokens %d calls", tok, calls)
	}
	var seriesSum int64
	for _, sr := range got.Series {
		seriesSum += sr.Tokens
		if len(sr.Points) != 6 {
			t.Fatalf("%s points %d", sr.Key, len(sr.Points))
		}
	}
	if seriesSum != 15769 || got.Series[0].Key != "tool:read" {
		t.Fatalf("series: %+v", got.Series)
	}

	get(t, s, "/api/v1/usage/timeseries?top=1", 200, &got)
	if len(got.Series) != 2 || got.Series[0].Key != "tool:read" || got.Series[1].Key != "other" || got.Series[1].Tokens != 3979 {
		t.Fatalf("top=1: %+v", got.Series)
	}
	get(t, s, "/api/v1/usage/timeseries?step=1h&group=pattern", 200, &got)
	if len(got.Total.Points) != 1 || len(got.Series) != 2 {
		t.Fatalf("1h: %+v", got)
	}
	// 하루 단위는 한국 자정 기준: 10.29 05:24Z(한국 14:24)는 10.28 15:00Z(한국 10.29 00:00)에 시작하는 구간.
	get(t, s, "/api/v1/usage/timeseries?step=1d", 200, &got)
	if len(got.Total.Points) != 1 || got.Total.Points[0].T != "2026-10-28T15:00:00.000Z" || got.Total.Tokens != 15769 {
		t.Fatalf("1d: %+v", got.Total)
	}
	get(t, s, "/api/v1/usage/timeseries?step=6h", 200, &got)
	if got.Total.Points[0].T != "2026-10-29T03:00:00.000Z" { // 한국 12:00 시작 구간
		t.Fatalf("6h: %+v", got.Total.Points)
	}
	for _, p := range []string{"step=abc", "step=30s", "top=0",
		"from=2026-10-22T06:00:00Z&to=2026-10-29T06:00:00Z&step=1m", "group=user"} {
		get(t, s, "/api/v1/usage/timeseries?"+p, 400, nil)
	}
}

func TestAssetDetail(t *testing.T) {
	s := load(t, LoadConfig{Inventory: "testdata/inventory-pc-fs.json"})
	var got assetResp
	get(t, s, "/api/v1/usage/assets/tool-fs-read", 200, &got)
	if !got.Runtime.Used || got.Runtime.Calls != 2 || got.Usage == nil || got.Usage.Tokens != 3920 ||
		*got.Usage.AssetID != "tool-fs-read" || len(got.Recent) != 2 || got.Runtime.LastTraceID == nil {
		t.Fatalf("fs: %+v", got)
	}
	get(t, s, "/api/v1/usage/assets/tool:read", 200, &got)
	if got.Runtime.Calls != 13 || got.Usage.Tokens != 11790 || len(got.Recent) != recentLimit {
		t.Fatalf("read: %+v", got)
	}
	if got.Recent[0].Time == nil || *got.Recent[0].Time < *got.Recent[1].Time {
		t.Fatal("recent는 최신순")
	}
	if got.BrakeEvents != nil {
		t.Fatal("플러그인 기록이 없으면 brake_events는 null")
	}
	get(t, s, "/api/v1/usage/assets/tool-docs-read", 200, &got)
	if got.Runtime.Used || got.Runtime.Calls != 0 || got.Usage != nil || len(got.Recent) != 0 {
		t.Fatalf("미사용 자산: %+v", got)
	}
}

// 10.29 enforce 테스트와 같은 흐름(승인 요청 → 한 번 허용 → 차단)을 fixture 시간대에 맞춰 만든 플러그인 기록.
// 첫 줄의 toolCallId는 fixture에 있는 실제 호출이라 trace_id가 붙어야 한다.
const brakeJSONL = `{"v":1,"kind":"tool_result","ts":"2026-10-29T05:25:00.000Z","toolCallId":"x","toolName":"read","textBytes":10}
{"v":1,"kind":"brake","ts":"2026-10-29T05:25:36.217Z","level":"warn","mode":"warn","enforced":false,"runId":"r1","toolCallId":"toolu_01SzaxkCdxBCGSgMpbxQPz1C","toolName":"read","reasons":[{"scope":"run","metric":"toolCalls","value":3,"limit":3}],"run":{"resultBytes":0,"countedTokens":0,"toolCalls":2,"sameToolStreak":3}}
{"v":1,"kind":"brake","ts":"2026-10-29T05:28:09.188Z","level":"approve","mode":"enforce","enforced":true,"runId":"r2","toolCallId":"c3","toolName":"exec","reasons":[{"scope":"run","metric":"toolCalls","value":3,"limit":3}],"run":{"resultBytes":2,"countedTokens":4,"toolCalls":2,"sameToolStreak":3}}
not json
{"v":1,"kind":"brake_resolution","ts":"2026-10-29T05:28:35.722Z","runId":"r2","toolCallId":"c3","toolName":"exec","decision":"allow-once"}
{"v":1,"kind":"brake","ts":"2026-10-29T05:28:40.288Z","level":"block","mode":"enforce","enforced":true,"runId":"r2","toolCallId":"c5","toolName":"exec","reasons":[{"scope":"run","metric":"toolCalls","value":5,"limit":5}],"run":{"resultBytes":4,"countedTokens":8,"toolCalls":4,"sameToolStreak":5}}
`

func TestBrakeEvents(t *testing.T) {
	p := filepath.Join(t.TempDir(), "agentscope-tool-results.jsonl")
	if err := os.WriteFile(p, []byte(brakeJSONL), 0o644); err != nil {
		t.Fatal(err)
	}
	s := load(t, LoadConfig{ToolResults: []string{p}})
	var got brakeResp
	body := get(t, s, "/api/v1/usage/brake-events", 200, &got)
	if !got.Available || got.Total != 3 || got.ByLevel["warn"] != 1 || got.ByLevel["approve"] != 1 || got.ByLevel["block"] != 1 {
		t.Fatalf("brakes: %+v", got)
	}
	if got.Items[0].Level != "block" || got.Items[2].Level != "warn" {
		t.Fatalf("최신순이어야 함: %+v", got.Items)
	}
	ap := got.Items[1]
	if ap.Level != "approve" || ap.Resolution == nil || ap.Resolution.Decision != "allow-once" || !ap.Enforced {
		t.Fatalf("approve: %+v", ap)
	}
	if w := got.Items[2]; w.TraceID == nil || *w.TraceID != "78f1519286fc431fe44ec8345e5d3e79" {
		t.Fatalf("trace_id 연결: %+v", w)
	}
	if got.Items[0].TraceID != nil {
		t.Fatal("사용 기록에 없는 호출은 trace_id null")
	}
	if strings.Contains(body, "textBytes") {
		t.Fatal("브레이크 외 기록 필드가 나옴")
	}
	get(t, s, "/api/v1/usage/brake-events?level=block", 200, &got)
	if got.Total != 1 || len(got.Items) != 1 {
		t.Fatalf("level=block: %+v", got)
	}
	get(t, s, "/api/v1/usage/brake-events?level=stop", 400, nil)

	var a assetResp
	get(t, s, "/api/v1/usage/assets/tool:read", 200, &a)
	if a.BrakeEvents == nil || *a.BrakeEvents != 1 {
		t.Fatalf("자산 브레이크 수: %v", a.BrakeEvents)
	}
	var h healthResp
	get(t, s, "/api/v1/usage/health", 200, &h)
	if h.BrakeEvents == nil || *h.BrakeEvents != 3 {
		t.Fatalf("health brake: %v", h.BrakeEvents)
	}

	plain := load(t, LoadConfig{})
	get(t, plain, "/api/v1/usage/brake-events", 200, &got)
	if got.Available || len(got.Items) != 0 {
		t.Fatalf("기록 없음: %+v", got)
	}
}
