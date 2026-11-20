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

// Server는 Source가 주는 Dataset으로 답하는 HTTP 핸들러다. 요청마다 그 시점의 Dataset 하나를 잡아 쓰므로
// 실시간 모드에서 다시 읽는 중이어도 한 응답 안의 값은 서로 맞는다.
type Server struct {
	src Source
	mux *http.ServeMux
}

// NewFixedServer는 고정 응답 모드 서버를 만든다(range 기준 시각 = 데이터 구간 끝).
func NewFixedServer(ds *Dataset) *Server { return NewServer(FixedSource(ds)) }

// NewServer는 Source(고정 또는 실시간)로 서버를 만든다.
func NewServer(src Source) *Server {
	s := &Server{src: src, mux: http.NewServeMux()}
	s.mux.HandleFunc("GET /api/v1/usage/summary", s.summary)
	s.mux.HandleFunc("GET /api/v1/usage/by-asset", s.byAsset)
	s.mux.HandleFunc("GET /api/v1/usage/records", s.records)
	s.mux.HandleFunc("GET /api/v1/usage/timeseries", s.timeseries)
	s.mux.HandleFunc("GET /api/v1/usage/assets/{asset_id}", s.asset)
	s.mux.HandleFunc("GET /api/v1/usage/brake-events", s.brakeEvents)
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

// view는 요청 하나가 쓰는 Dataset과 조회 구간이다.
type view struct {
	ds  *Dataset
	win window
}

func (s *Server) view(w http.ResponseWriter, r *http.Request) (view, bool) {
	ds := s.src.Current()
	if ds == nil {
		writeError(w, http.StatusServiceUnavailable, "아직 데이터를 읽지 못함(health 참고)")
		return view{}, false
	}
	now, def := s.src.Now(ds)
	win, err := parseWindow(r.URL.Query(), def, now)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return view{}, false
	}
	return view{ds: ds, win: win}, true
}

func (v view) records() []Record {
	var out []Record
	for _, r := range v.ds.Records {
		if v.win.contains(r.Start) {
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
	v, ok := s.view(w, r)
	if !ok {
		return
	}
	win := v.win
	resp := summaryResp{
		Window: win.json(), Estimated: true,
		Pricing:     pricingSummary{Currency: "USD", Sources: []string{}},
		ByMapping:   map[string]int{"matched": 0, "ambiguous": 0, "unmatched": 0},
		DataQuality: dataQuality{InventorySnapshotID: v.ds.InventorySnapshotID},
	}
	var seqTok, allocTok int64
	var seqN, allocN, ncN int
	var cost costSum
	sources := map[string]bool{}
	for _, rec := range v.records() {
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
	v, ok := s.view(w, r)
	if !ok {
		return
	}
	group, err := parseGroup(r.URL.Query())
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	items, total := aggregate(v.records(), group)
	resp := byAssetResp{Window: v.win.json(), Estimated: true, Group: group, TotalTokens: total,
		InventorySnapshotID: v.ds.InventorySnapshotID, Items: items}
	writeJSON(w, http.StatusOK, resp)
}

// aggregate는 기록을 group 기준으로 묶어 토큰 많은 순으로 돌려준다(share·relative 포함).
func aggregate(recs []Record, group string) ([]assetItem, int64) {
	items := map[string]*assetItem{}
	var order []string
	var total int64
	for _, rec := range recs {
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
	var maxTok int64
	for _, k := range order {
		if items[k].Tokens > maxTok {
			maxTok = items[k].Tokens
		}
	}
	out := []assetItem{}
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
		out = append(out, *it)
	}
	sort.SliceStable(out, func(i, j int) bool {
		if out[i].Tokens != out[j].Tokens {
			return out[i].Tokens > out[j].Tokens
		}
		return out[i].Key < out[j].Key
	})
	return out, total
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
	v, ok := s.view(w, r)
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
	recs := newestFirst(v.records())
	resp := recordsResp{Window: v.win.json(), Estimated: true, Total: len(recs), Items: []recordItem{}}
	if offset > len(recs) {
		offset = len(recs)
	}
	end := min(offset+limit, len(recs))
	for _, rec := range recs[offset:end] {
		resp.Items = append(resp.Items, toRecordItem(rec))
	}
	if end < len(recs) {
		resp.NextCursor = str(strconv.Itoa(end))
	}
	writeJSON(w, http.StatusOK, resp)
}

func newestFirst(recs []Record) []Record {
	for i, j := 0, len(recs)-1; i < j; i, j = i+1, j-1 {
		recs[i], recs[j] = recs[j], recs[i]
	}
	return recs
}

func toRecordItem(rec Record) recordItem {
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
	return it
}

// ---- health ----

type healthResp struct {
	Status              string      `json:"status"`
	Mode                string      `json:"mode"`
	DataWindow          *windowJSON `json:"data_window"`
	Records             int         `json:"records"`
	BrakeEvents         *int        `json:"brake_events"`
	Sources             []string    `json:"sources"`
	LoadedAt            *string     `json:"loaded_at"`
	LastError           *string     `json:"last_error"`
	InventorySnapshotID *string     `json:"inventory_snapshot_id"`
	MissingCounts       int         `json:"missing_counts"`
	Limitations         []string    `json:"limitations"`
}

func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	st := s.src.Status()
	resp := healthResp{Status: "ok", Mode: st.Mode, Sources: []string{}, Limitations: []string{}}
	if st.LastError != "" {
		resp.LastError = str(st.LastError)
	}
	ds := s.src.Current()
	if ds == nil {
		resp.Status = "loading"
		if st.LastError != "" {
			resp.Status = "error"
		}
		writeJSON(w, http.StatusOK, resp)
		return
	}
	all := window{start: ds.Start, end: ds.End}.json()
	resp.DataWindow = &all
	resp.Records = len(ds.Records)
	resp.LoadedAt = timePtr(ds.LoadedAt)
	resp.InventorySnapshotID = ds.InventorySnapshotID
	if ds.Sources != nil {
		resp.Sources = ds.Sources
	}
	if ds.Limitations != nil {
		resp.Limitations = ds.Limitations
	}
	if ds.BrakeAvailable {
		n := len(ds.BrakeEvents)
		resp.BrakeEvents = &n
	}
	if st.LastError != "" {
		resp.Status = "degraded" // 마지막 다시 읽기는 실패, 이전 데이터로 답하는 중
	}
	for _, rec := range ds.Records {
		if rec.Method == MethodNotComputed && (rec.Pattern == "parallel" || rec.Pattern == "batch") {
			resp.MissingCounts++
		}
	}
	writeJSON(w, http.StatusOK, resp)
}
