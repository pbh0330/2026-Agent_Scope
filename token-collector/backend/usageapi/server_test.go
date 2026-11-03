package usageapi

import (
	"bufio"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// pc-1029.traces.jsonl: 10.29 PC 재검증의 원본 스팬에서 귀속에 필요한 스팬만 남기고
// 리소스 속성(호스트·경로)은 service.name 외에 지운 것. 병렬 13건, 순차 3건.
const fixture = "testdata/pc-1029.traces.jsonl"

var fixedNow = func() time.Time { return time.Date(2026, 10, 30, 0, 0, 0, 0, time.UTC) }

func load(t *testing.T, cfg LoadConfig) *Server {
	t.Helper()
	if cfg.EnvironmentID == "" {
		cfg.EnvironmentID, cfg.ProfileID = "env-pc", "profile-pc"
	}
	if len(cfg.Inputs) == 0 {
		cfg.Inputs = []string{fixture}
	}
	cfg.ReferencePricing = true
	cfg.Now = fixedNow
	ds, err := Load(cfg, func(m string) { t.Log("warn:", m) })
	if err != nil {
		t.Fatal(err)
	}
	return NewFixedServer(ds)
}

func get(t *testing.T, h http.Handler, path string, wantStatus int, out any) string {
	t.Helper()
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, path, nil))
	if rec.Code != wantStatus {
		t.Fatalf("%s: status %d, want %d, body %s", path, rec.Code, wantStatus, rec.Body.String())
	}
	if ct := rec.Header().Get("Content-Type"); !strings.HasPrefix(ct, "application/json") {
		t.Fatalf("%s: content-type %q", path, ct)
	}
	if out != nil {
		if err := json.Unmarshal(rec.Body.Bytes(), out); err != nil {
			t.Fatalf("%s: %v", path, err)
		}
	}
	return rec.Body.String()
}

// 10.29 재검증 값(대시보드·usage.json과 같은 값)이 그대로 나오는지.
func TestSummaryMatchesPCRetest(t *testing.T) {
	s := load(t, LoadConfig{})
	var got summaryResp
	get(t, s, "/api/v1/usage/summary", 200, &got)
	if got.Calls != 16 || got.AttributedTokens != 15769 {
		t.Fatalf("calls/tokens: %d/%d", got.Calls, got.AttributedTokens)
	}
	seq, alloc := got.ByMethod[MethodSequential], got.ByMethod[MethodAllocated]
	if seq.Calls != 3 || *seq.Tokens != 2268 || alloc.Calls != 13 || *alloc.Tokens != 13501 {
		t.Fatalf("by_method: %+v %+v", seq, alloc)
	}
	if got.ByMethod[MethodNotComputed].Calls != 0 || got.DataQuality.MissingCounts != 0 {
		t.Fatalf("not computed: %+v", got.DataQuality)
	}
	if got.EstimatedCostUSD == nil || *got.EstimatedCostUSD != 0.015769 {
		t.Fatalf("cost: %v", got.EstimatedCostUSD)
	}
	if got.ByMapping["unmatched"] != 16 || got.DataQuality.InventorySnapshotID != nil {
		t.Fatalf("mapping: %v", got.ByMapping)
	}
	if !got.Estimated || len(got.Pricing.Sources) != 1 || got.Pricing.Sources[0] != "reference_list_price" {
		t.Fatalf("pricing: %+v", got.Pricing)
	}
}

func TestByAssetWithoutInventory(t *testing.T) {
	s := load(t, LoadConfig{})
	var got byAssetResp
	get(t, s, "/api/v1/usage/by-asset", 200, &got)
	want := []struct {
		key      string
		tokens   int64
		seq      int64
		relative float64
	}{
		{"tool:read", 11805, 2268, 1},
		{"tool:fs__read_text_file", 3920, 0, 0.3321},
		{"tool:ls", 44, 0, 0.0037},
	}
	if len(got.Items) != len(want) {
		t.Fatalf("items: %+v", got.Items)
	}
	var sum int64
	for i, w := range want {
		it := got.Items[i]
		if it.Key != w.key || it.Tokens != w.tokens || it.TokensSequential != w.seq || it.Relative != w.relative {
			t.Fatalf("item %d: %+v, want %+v", i, it, w)
		}
		if it.TokensSequential+it.TokensAllocated != it.Tokens {
			t.Fatalf("%s: sequential+allocated != tokens", it.Key)
		}
		if it.AssetID != nil || *it.MappingStatus != "unmatched" || it.LastTraceID == nil || it.LastUsedAt == nil {
			t.Fatalf("%s: %+v", it.Key, it)
		}
		sum += it.Tokens
	}
	if sum != got.TotalTokens || got.TotalTokens != 15769 {
		t.Fatalf("total %d, sum %d", got.TotalTokens, sum)
	}
	if got.Items[1].MCPServer == nil || *got.Items[1].MCPServer != "fs" {
		t.Fatalf("mcp_server: %+v", got.Items[1])
	}
}

// 스냅샷이 있으면 MCP 도구는 Tool 자산 ID로, 서버 묶음은 소속 서버 자산 ID로 묶는다. 내장 도구는 unmatched 그대로.
func TestByAssetWithInventory(t *testing.T) {
	s := load(t, LoadConfig{Inventory: "testdata/inventory-pc-fs.json"})
	var got byAssetResp
	get(t, s, "/api/v1/usage/by-asset?group=asset", 200, &got)
	if got.InventorySnapshotID == nil || *got.InventorySnapshotID != "snap-test-pc-fs" {
		t.Fatalf("snapshot: %v", got.InventorySnapshotID)
	}
	byKey := map[string]assetItem{}
	for _, it := range got.Items {
		byKey[it.Key] = it
	}
	fs, ok := byKey["tool-fs-read"]
	if !ok || fs.AssetID == nil || *fs.AssetID != "tool-fs-read" || *fs.AssetType != "tool" || *fs.MappingStatus != "matched" || fs.Tokens != 3920 {
		t.Fatalf("fs tool: %+v (items %v)", fs, byKey)
	}
	if rd := byKey["tool:read"]; rd.AssetID != nil || *rd.MappingStatus != "unmatched" {
		t.Fatalf("read: %+v", rd)
	}

	var srv byAssetResp
	get(t, s, "/api/v1/usage/by-asset?group=server", 200, &srv)
	keys := map[string]assetItem{}
	for _, it := range srv.Items {
		keys[it.Key] = it
	}
	if it := keys["srv-fs"]; it.AssetID == nil || *it.AssetType != "mcp_server" || it.Tokens != 3920 {
		t.Fatalf("server: %+v", srv.Items)
	}
	if it := keys["source:core"]; it.Tokens != 11849 || it.Calls != 14 {
		t.Fatalf("core: %+v", it)
	}

	var sum summaryResp
	get(t, s, "/api/v1/usage/summary", 200, &sum)
	if sum.ByMapping["matched"] != 2 || sum.ByMapping["unmatched"] != 14 {
		t.Fatalf("by_mapping: %v", sum.ByMapping)
	}
}

func TestByAssetPatternGroup(t *testing.T) {
	s := load(t, LoadConfig{})
	var got byAssetResp
	get(t, s, "/api/v1/usage/by-asset?group=pattern", 200, &got)
	if len(got.Items) != 2 || got.Items[0].Key != "pattern:parallel" || got.Items[0].Tokens != 13501 || got.Items[1].Tokens != 2268 {
		t.Fatalf("pattern: %+v", got.Items)
	}
}

func TestRecordsPagingNewestFirst(t *testing.T) {
	s := load(t, LoadConfig{})
	seen := map[string]bool{}
	var times []string
	cursor := ""
	for page := 0; page < 10; page++ {
		path := "/api/v1/usage/records?limit=5"
		if cursor != "" {
			path += "&cursor=" + cursor
		}
		var got recordsResp
		get(t, s, path, 200, &got)
		if got.Total != 16 {
			t.Fatalf("total %d", got.Total)
		}
		for _, it := range got.Items {
			if seen[it.UsageID] {
				t.Fatalf("duplicate %s", it.UsageID)
			}
			seen[it.UsageID] = true
			times = append(times, *it.Time)
			if it.Tokens == nil || it.TraceID == "" || len(it.EvidenceSourceRefs) == 0 {
				t.Fatalf("record: %+v", it)
			}
			if it.Method == MethodAllocated && it.Pattern != "parallel" {
				t.Fatalf("method/pattern: %+v", it)
			}
		}
		if got.NextCursor == nil {
			break
		}
		cursor = *got.NextCursor
	}
	if len(seen) != 16 {
		t.Fatalf("seen %d", len(seen))
	}
	for i := 1; i < len(times); i++ {
		if times[i] > times[i-1] {
			t.Fatalf("not newest first: %v", times)
		}
	}
}

func TestWindowFilter(t *testing.T) {
	s := load(t, LoadConfig{})
	// 데이터 구간 끝(05:29:03) 기준 최근 2분 = 05:27:03부터: 순차 SOUL·AGENTS·USER 3건만
	var got summaryResp
	get(t, s, "/api/v1/usage/summary?range=2m", 200, &got)
	if got.Calls != 3 || got.AttributedTokens != 2268 || got.Window.Start != "2026-10-29T05:27:03.000Z" {
		t.Fatalf("range=2m: %+v", got)
	}
	get(t, s, "/api/v1/usage/summary?from=2026-10-29T05:26:00Z&to=2026-10-29T05:27:00Z", 200, &got)
	if got.Calls != 4 { // 병렬 혼합 2건 + 병렬 MCP 2건
		t.Fatalf("from/to: %+v", got)
	}
	get(t, s, "/api/v1/usage/summary?from=2026-10-28T00:00:00Z&to=2026-10-28T01:00:00Z", 200, &got)
	if got.Calls != 0 || got.EstimatedCostUSD != nil {
		t.Fatalf("empty window: %+v", got)
	}
}

func TestBadRequests(t *testing.T) {
	s := load(t, LoadConfig{})
	for _, p := range []string{
		"/api/v1/usage/summary?range=1h&from=2026-10-29T05:00:00Z",
		"/api/v1/usage/summary?range=abc",
		"/api/v1/usage/summary?range=8d",
		"/api/v1/usage/summary?from=yesterday",
		"/api/v1/usage/summary?from=2026-10-29T06:00:00Z&to=2026-10-29T05:00:00Z",
		"/api/v1/usage/summary?from=2026-10-01T00:00:00Z&to=2026-10-29T00:00:00Z",
		"/api/v1/usage/by-asset?group=user",
		"/api/v1/usage/records?limit=0",
		"/api/v1/usage/records?limit=501",
		"/api/v1/usage/records?cursor=-1",
	} {
		var e map[string]string
		get(t, s, p, 400, &e)
		if e["error"] == "" {
			t.Fatalf("%s: no error message", p)
		}
	}
	get(t, s, "/api/v1/usage/nothing", 404, nil)
	rec := httptest.NewRecorder()
	s.ServeHTTP(rec, httptest.NewRequest(http.MethodPost, "/api/v1/usage/summary", nil))
	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("POST: %d", rec.Code)
	}
}

// 토큰 수 스팬이 없으면 병렬 구간은 계산 못 함으로 남고(0으로 채우지 않음) missing_counts로 센다.
func TestMissingCountsAreNotZeroFilled(t *testing.T) {
	dir := t.TempDir()
	in := filepath.Join(dir, "no-counts.jsonl")
	writeWithoutCountSpans(t, fixture, in)
	s := load(t, LoadConfig{Inputs: []string{in}})
	var got summaryResp
	get(t, s, "/api/v1/usage/summary", 200, &got)
	if got.Calls != 16 || got.AttributedTokens != 2268 || got.DataQuality.MissingCounts != 13 || got.ByMethod[MethodNotComputed].Calls != 13 {
		t.Fatalf("summary: %+v", got)
	}
	var recs recordsResp
	get(t, s, "/api/v1/usage/records?limit=500", 200, &recs)
	nulls := 0
	for _, it := range recs.Items {
		if it.Tokens == nil {
			nulls++
			if it.EstimatedCostUSD != nil || it.Method != MethodNotComputed {
				t.Fatalf("not computed record: %+v", it)
			}
		}
	}
	if nulls != 13 {
		t.Fatalf("null tokens %d", nulls)
	}
	var h healthResp
	get(t, s, "/api/v1/usage/health", 200, &h)
	if h.MissingCounts != 13 {
		t.Fatalf("health: %+v", h)
	}
}

// 응답에는 입력 파일 이름만 나가고 디렉터리(사용자 이름이 들어갈 수 있음)는 나가지 않는다.
func TestResponsesDoNotLeakPaths(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "Users", "someone-private")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	b, err := os.ReadFile(fixture)
	if err != nil {
		t.Fatal(err)
	}
	in := filepath.Join(dir, "traces.jsonl")
	if err := os.WriteFile(in, b, 0o644); err != nil {
		t.Fatal(err)
	}
	s := load(t, LoadConfig{Inputs: []string{in}})
	for _, p := range []string{"health", "summary", "by-asset", "records?limit=500"} {
		body := get(t, s, "/api/v1/usage/"+p, 200, nil)
		if strings.Contains(body, "someone-private") || strings.Contains(body, dir) {
			t.Fatalf("%s leaks path: %s", p, body)
		}
	}
}

func writeWithoutCountSpans(t *testing.T, src, dst string) {
	t.Helper()
	f, err := os.Open(src)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	out, err := os.Create(dst)
	if err != nil {
		t.Fatal(err)
	}
	defer out.Close()
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<24)
	for sc.Scan() {
		var req map[string]any
		if err := json.Unmarshal(sc.Bytes(), &req); err != nil {
			t.Fatal(err)
		}
		for _, rs := range req["resourceSpans"].([]any) {
			for _, ss := range rs.(map[string]any)["scopeSpans"].([]any) {
				m := ss.(map[string]any)
				var keep []any
				for _, sp := range m["spans"].([]any) {
					if sp.(map[string]any)["name"] != "agentscope.tool_result.count" {
						keep = append(keep, sp)
					}
				}
				m["spans"] = keep
			}
		}
		b, _ := json.Marshal(req)
		out.Write(append(b, '\n'))
	}
	if err := sc.Err(); err != nil {
		t.Fatal(err)
	}
}
