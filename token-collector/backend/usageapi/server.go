package usageapi

import (
	"encoding/json"
	"math"
	"net/http"
	"sort"
	"strconv"
	"time"
)

const timeFormat = "2006-01-02T15:04:05.000Z07:00"

// Mode는 health에 표시하는 동작 방식이다.
const ModeFixed = "fixed"

// Server는 Dataset 하나로 답하는 HTTP 핸들러다.
type Server struct {
	ds  *Dataset
	now func() time.Time // range 기준 시각. 고정 응답 모드는 데이터 구간 끝
	mux *http.ServeMux
}

// NewFixedServer는 고정 응답 모드 서버를 만든다(range 기준 시각 = 데이터 구간 끝).
func NewFixedServer(ds *Dataset) *Server {
	s := &Server{ds: ds, now: func() time.Time { return ds.End }, mux: http.NewServeMux()}
	s.mux.HandleFunc("GET /api/v1/usage/summary", s.summary)
	s.mux.HandleFunc("GET /api/v1/usage/by-asset", s.byAsset)
	s.mux.HandleFunc("GET /api/v1/usage/records", s.records)
	s.mux.HandleFunc("GET /api/v1/usage/health", s.health)
	s.mux.HandleFunc("GET /", func(w http.ResponseWriter, r *http.Request) {
		writeError(w, http.StatusNotFound, "없는 경로")
	})
	return s
}

func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	h := w.Header()
	h.Set("Cache-Control", "no-store")
	h.Set("X-Content-Type-Options", "nosniff")
	s.mux.ServeHTTP(w, r)
}

// ---- 공통 ----

type windowJSON struct {
	Start string `json:"start"`
	End   string `json:"end"`
}

func (w window) json() windowJSON {
	return windowJSON{Start: w.start.Format(timeFormat), End: w.end.Format(timeFormat)}
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	enc := json.NewEncoder(w)
	enc.SetEscapeHTML(false)
	_ = enc.Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func (s *Server) window(w http.ResponseWriter, r *http.Request) (window, bool) {
	win, err := parseWindow(r.URL.Query(), s.ds, s.now())
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return window{}, false
	}
	return win, true
}

func (s *Server) inWindow(win window) []Record {
	var out []Record
	for _, r := range s.ds.Records {
		if win.contains(r.Start) {
			out = append(out, r)
		}
	}
	return out
}

func roundUSD(v float64) float64  { return math.Round(v*1e9) / 1e9 }
func round4(v float64) float64    { return math.Round(v*1e4) / 1e4 }
func timePtr(t time.Time) *string { s := t.Format(timeFormat); return &s }

// costSum은 비용이 있는 기록만 더한다. 하나도 없으면 nil(0과 구분).
type costSum struct {
	total float64
	n     int
}

func (c *costSum) add(v *float64) {
	if v != nil {
		c.total += *v
		c.n++
	}
}

func (c costSum) value() *float64 {
	if c.n == 0 {
		return nil
	}
	v := roundUSD(c.total)
	return &v
}

// ---- summary ----

type methodStat struct {
	Calls  int    `json:"calls"`
	Tokens *int64 `json:"tokens,omitempty"`
}

type summaryResp struct {
	Window           windowJSON            `json:"window"`
	Estimated        bool                  `json:"estimated"`
	Calls            int                   `json:"calls"`
	AttributedTokens int64                 `json:"attributed_tokens"`
	EstimatedCostUSD *float64              `json:"estimated_cost_usd"`
	Pricing          pricingSummary        `json:"pricing"`
	ByMethod         map[string]methodStat `json:"by_method"`
	ByMapping        map[string]int        `json:"by_mapping"`
	DataQuality      dataQuality           `json:"data_quality"`
}

type pricingSummary struct {
	Currency string   `json:"currency"`
	Sources  []string `json:"sources"`
}

type dataQuality struct {
	MissingCounts       int     `json:"missing_counts"`
	NotComputed         int     `json:"not_computed"`
	NegativeDelta       int     `json:"negative_delta"`
	CallsWithoutCost    int     `json:"calls_without_cost"`
	InventorySnapshotID *string `json:"inventory_snapshot_id"`
}

func (s *Server) summary(w http.ResponseWriter, r *http.Request) {
	win, ok := s.window(w, r)
	if !ok {
		return
	}
	resp := summaryResp{
		Window: win.json(), Estimated: true,
		Pricing:     pricingSummary{Currency: "USD", Sources: []string{}},
		ByMapping:   map[string]int{"matched": 0, "ambiguous": 0, "unmatched": 0},
		DataQuality: dataQuality{InventorySnapshotID: s.ds.InventorySnapshotID},
	}
	var seqTok, allocTok int64
	var seqN, allocN, ncN int
	var cost costSum
	sources := map[string]bool{}
	for _, rec := range s.inWindow(win) {
		resp.Calls++
		tok, has := rec.Tokens()
		switch rec.Method {
		case MethodSequential:
			seqN++
			seqTok += tok
		case MethodAllocated:
			allocN++
			allocTok += tok
		default:
			ncN++
			if rec.Pattern == "parallel" || rec.Pattern == "batch" {
				resp.DataQuality.MissingCounts++
			}
		}
		if has {
			resp.AttributedTokens += tok
		}
		cost.add(rec.EstimatedCostUSD)
		if has && rec.EstimatedCostUSD == nil {
			resp.DataQuality.CallsWithoutCost++
		}
		if rec.EstimatedCostUSD != nil {
			sources[rec.Pricing.Source] = true
		}
		if rec.NegativeDelta {
			resp.DataQuality.NegativeDelta++
		}
		resp.ByMapping[rec.MappingStatus]++
	}
	resp.EstimatedCostUSD = cost.value()
	for k := range sources {
		resp.Pricing.Sources = append(resp.Pricing.Sources, k)
	}
	sort.Strings(resp.Pricing.Sources)
	resp.DataQuality.NotComputed = ncN
	resp.ByMethod = map[string]methodStat{
		MethodSequential:  {Calls: seqN, Tokens: &seqTok},
		MethodAllocated:   {Calls: allocN, Tokens: &allocTok},
		MethodNotComputed: {Calls: ncN},
	}
	writeJSON(w, http.StatusOK, resp)
}

// ---- by-asset ----

type assetItem struct {
	Key              string   `json:"key"`
	Label            string   `json:"label"`
	AssetID          *string  `json:"asset_id"`
	AssetType        *string  `json:"asset_type"`
	MappingStatus    *string  `json:"mapping_status,omitempty"`
	ToolSource       *string  `json:"tool_source,omitempty"`
	MCPServer        *string  `json:"mcp_server,omitempty"`
	Calls            int      `json:"calls"`
	CallsNotComputed int      `json:"calls_not_computed"`
	Tokens           int64    `json:"tokens"`
	TokensSequential int64    `json:"tokens_sequential"`
	TokensAllocated  int64    `json:"tokens_allocated"`
	EstimatedCostUSD *float64 `json:"estimated_cost_usd"`
	Share            float64  `json:"share"`
	Relative         float64  `json:"relative"`
	LastUsedAt       *string  `json:"last_used_at"`
	LastTraceID      *string  `json:"last_trace_id"`

	cost costSum
	last time.Time
}

type byAssetResp struct {
	Window              windowJSON  `json:"window"`
	Estimated           bool        `json:"estimated"`
	Group               string      `json:"group"`
	TotalTokens         int64       `json:"total_tokens"`
	InventorySnapshotID *string     `json:"inventory_snapshot_id"`
	Items               []assetItem `json:"items"`
}

func str(s string) *string { return &s }

// groupKey는 기록 하나가 들어갈 묶음과 그 묶음의 고정 정보를 정한다.
func groupKey(rec Record, group string) (key string, base assetItem) {
	switch group {
	case GroupTool:
		return "tool:" + rec.ToolName, assetItem{Label: rec.ToolName, ToolSource: str(rec.ToolSource), MCPServer: nonEmpty(rec.MCPServer)}
	case GroupPattern:
		return "pattern:" + rec.Pattern, assetItem{Label: rec.Pattern}
	case GroupServer:
		switch {
		case rec.ServerRef != "":
			return rec.ServerRef, assetItem{Label: rec.MCPServer, AssetID: str(rec.ServerRef), AssetType: str("mcp_server"),
				MappingStatus: str("matched"), ToolSource: str("mcp"), MCPServer: nonEmpty(rec.MCPServer)}
		case rec.MCPServer != "":
			return "mcp:" + rec.MCPServer, assetItem{Label: rec.MCPServer, MappingStatus: str("unmatched"),
				ToolSource: str("mcp"), MCPServer: str(rec.MCPServer)}
		default:
			return "source:" + rec.ToolSource, assetItem{Label: rec.ToolSource, ToolSource: str(rec.ToolSource)}
		}
	default: // GroupAsset
		if rec.MappingStatus == "matched" && rec.AssetRef != nil {
			return *rec.AssetRef, assetItem{Label: rec.ToolName, AssetID: str(*rec.AssetRef), AssetType: str("tool"),
				MappingStatus: str("matched"), ToolSource: str(rec.ToolSource), MCPServer: nonEmpty(rec.MCPServer)}
		}
		return "tool:" + rec.ToolName, assetItem{Label: rec.ToolName, MappingStatus: str(rec.MappingStatus),
			ToolSource: str(rec.ToolSource), MCPServer: nonEmpty(rec.MCPServer)}
	}
}

func nonEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

func (s *Server) byAsset(w http.ResponseWriter, r *http.Request) {
	win, ok := s.window(w, r)
	if !ok {
		return
	}
	group, err := parseGroup(r.URL.Query())
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	items := map[string]*assetItem{}
	var order []string
	var total int64
	for _, rec := range s.inWindow(win) {
		key, base := groupKey(rec, group)
		it, ok := items[key]
		if !ok {
			base.Key = key
			it = &base
			items[key] = it
			order = append(order, key)
		}
		it.Calls++
		tok, has := rec.Tokens()
		if !has {
			it.CallsNotComputed++
		}
		it.Tokens += tok
		total += tok
		switch rec.Method {
		case MethodSequential:
			it.TokensSequential += tok
		case MethodAllocated:
			it.TokensAllocated += tok
		}
		it.cost.add(rec.EstimatedCostUSD)
		if !rec.Start.Before(it.last) {
			it.last = rec.Start
			it.LastTraceID = str(rec.TraceID)
		}
	}
	resp := byAssetResp{Window: win.json(), Estimated: true, Group: group, TotalTokens: total,
		InventorySnapshotID: s.ds.InventorySnapshotID, Items: []assetItem{}}
	var maxTok int64
	for _, k := range order {
		if items[k].Tokens > maxTok {
			maxTok = items[k].Tokens
		}
	}
	for _, k := range order {
		it := items[k]
		it.EstimatedCostUSD = it.cost.value()
		if total > 0 {
			it.Share = round4(float64(it.Tokens) / float64(total))
		}
		if maxTok > 0 {
			it.Relative = round4(float64(it.Tokens) / float64(maxTok))
		}
		if !it.last.IsZero() {
			it.LastUsedAt = timePtr(it.last)
		}
		resp.Items = append(resp.Items, *it)
	}
	sort.SliceStable(resp.Items, func(i, j int) bool {
		if resp.Items[i].Tokens != resp.Items[j].Tokens {
			return resp.Items[i].Tokens > resp.Items[j].Tokens
		}
		return resp.Items[i].Key < resp.Items[j].Key
	})
	writeJSON(w, http.StatusOK, resp)
}

// ---- records ----

type recordItem struct {
	UsageID            string   `json:"usage_id"`
	Time               *string  `json:"time"`
	ToolName           string   `json:"tool_name"`
	ToolSource         string   `json:"tool_source"`
	MCPServer          *string  `json:"mcp_server"`
	AssetID            *string  `json:"asset_id"`
	MappingStatus      string   `json:"mapping_status"`
	Pattern            string   `json:"pattern"`
	Method             string   `json:"method"`
	AttributionMethod  string   `json:"attribution_method"`
	Tokens             *int64   `json:"tokens"`
	EstimatedCostUSD   *float64 `json:"estimated_cost_usd"`
	DurationMs         *float64 `json:"duration_ms"`
	Model              *string  `json:"model"`
	TraceID            string   `json:"trace_id"`
	ToolSpanID         string   `json:"tool_span_id"`
	ToolCallID         *string  `json:"tool_call_id"`
	EvidenceSourceRefs []string `json:"evidence_source_refs"`
}

type recordsResp struct {
	Window     windowJSON   `json:"window"`
	Estimated  bool         `json:"estimated"`
	Total      int          `json:"total"`
	Items      []recordItem `json:"items"`
	NextCursor *string      `json:"next_cursor"`
}

func (s *Server) records(w http.ResponseWriter, r *http.Request) {
	win, ok := s.window(w, r)
	if !ok {
		return
	}
	q := r.URL.Query()
	limit, err := parseLimit(q)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	offset, err := parseCursor(q)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	recs := s.inWindow(win)
	// 최신순
	for i, j := 0, len(recs)-1; i < j; i, j = i+1, j-1 {
		recs[i], recs[j] = recs[j], recs[i]
	}
	resp := recordsResp{Window: win.json(), Estimated: true, Total: len(recs), Items: []recordItem{}}
	if offset > len(recs) {
		offset = len(recs)
	}
	end := min(offset+limit, len(recs))
	for _, rec := range recs[offset:end] {
		it := recordItem{
			UsageID: rec.UsageID, ToolName: rec.ToolName, ToolSource: rec.ToolSource, MCPServer: nonEmpty(rec.MCPServer),
			AssetID: rec.AssetRef, MappingStatus: rec.MappingStatus, Pattern: rec.Pattern, Method: rec.Method,
			AttributionMethod: rec.AttributionMethod, Tokens: rec.ApproxInputTokens, EstimatedCostUSD: rec.EstimatedCostUSD,
			DurationMs: rec.DurationMs, Model: rec.Model, TraceID: rec.TraceID, ToolSpanID: rec.ToolSpanID,
			ToolCallID: rec.ToolCallID, EvidenceSourceRefs: rec.EvidenceSourceRefs,
		}
		if rec.MappingStatus != "matched" {
			it.AssetID = nil
		}
		if !rec.Start.IsZero() {
			it.Time = timePtr(rec.Start)
		}
		if it.EvidenceSourceRefs == nil {
			it.EvidenceSourceRefs = []string{}
		}
		resp.Items = append(resp.Items, it)
	}
	if end < len(recs) {
		resp.NextCursor = str(strconv.Itoa(end))
	}
	writeJSON(w, http.StatusOK, resp)
}

// ---- health ----

type healthResp struct {
	Status              string     `json:"status"`
	Mode                string     `json:"mode"`
	DataWindow          windowJSON `json:"data_window"`
	Records             int        `json:"records"`
	Sources             []string   `json:"sources"`
	LoadedAt            string     `json:"loaded_at"`
	InventorySnapshotID *string    `json:"inventory_snapshot_id"`
	MissingCounts       int        `json:"missing_counts"`
	Limitations         []string   `json:"limitations"`
}

func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	all := window{start: s.ds.Start, end: s.ds.End}
	resp := healthResp{
		Status: "ok", Mode: ModeFixed, DataWindow: all.json(), Records: len(s.ds.Records),
		Sources: s.ds.Sources, LoadedAt: s.ds.LoadedAt.Format(timeFormat),
		InventorySnapshotID: s.ds.InventorySnapshotID, Limitations: s.ds.Limitations,
	}
	if resp.Sources == nil {
		resp.Sources = []string{}
	}
	if resp.Limitations == nil {
		resp.Limitations = []string{}
	}
	for _, rec := range s.ds.Records {
		if rec.Method == MethodNotComputed && (rec.Pattern == "parallel" || rec.Pattern == "batch") {
			resp.MissingCounts++
		}
	}
	writeJSON(w, http.StatusOK, resp)
}
