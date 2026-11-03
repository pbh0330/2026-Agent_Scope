package usageapi

import (
	"fmt"
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"time"
)

// ---- timeseries ----

var steps = []time.Duration{time.Minute, 5 * time.Minute, 15 * time.Minute, 30 * time.Minute,
	time.Hour, 6 * time.Hour, 24 * time.Hour}

const (
	autoMaxBuckets = 120  // step을 안 주면 이 수 이하가 되는 가장 작은 step
	maxBuckets     = 1000 // step을 줘도 이보다 많으면 400
	defaultTop     = 8
	maxTop         = 50
)

func parseStep(q url.Values, w window) (time.Duration, error) {
	span := w.end.Sub(w.start)
	if s := q.Get("step"); s != "" {
		d, err := parseRange(s)
		if err != nil {
			return 0, fmt.Errorf("step: %q를 읽을 수 없음(예: 1m, 5m, 1h, 1d)", s)
		}
		if d < time.Minute {
			return 0, fmt.Errorf("step: 1m 이상")
		}
		if int(span/d)+1 > maxBuckets {
			return 0, fmt.Errorf("step: 구간이 %d개를 넘음(더 큰 step을 쓸 것)", maxBuckets)
		}
		return d, nil
	}
	for _, d := range steps {
		if int(span/d)+1 <= autoMaxBuckets {
			return d, nil
		}
	}
	return steps[len(steps)-1], nil
}

func parseTop(q url.Values) (int, error) {
	s := q.Get("top")
	if s == "" {
		return defaultTop, nil
	}
	n, err := strconv.Atoi(s)
	if err != nil || n < 1 || n > maxTop {
		return 0, fmt.Errorf("top: 1~%d", maxTop)
	}
	return n, nil
}

type point struct {
	T      string `json:"t"`
	Tokens int64  `json:"tokens"`
	Calls  int    `json:"calls"`
}

type series struct {
	Key    string  `json:"key"`
	Label  string  `json:"label"`
	Tokens int64   `json:"tokens"`
	Points []point `json:"points"`
}

type timeseriesResp struct {
	Window    windowJSON `json:"window"`
	Estimated bool       `json:"estimated"`
	Group     string     `json:"group"`
	Step      string     `json:"step"`
	Total     series     `json:"total"`
	Series    []series   `json:"series"`
}

// timeseries는 구간(step)별 토큰·호출 수다. 묶음은 토큰 많은 순 top개, 나머지는 key "other" 하나로 합친다.
// 구간 시작은 step 단위로 맞추고(UTC), 기록이 없는 구간도 0으로 채운다.
func (s *Server) timeseries(w http.ResponseWriter, r *http.Request) {
	v, ok := s.view(w, r)
	if !ok {
		return
	}
	q := r.URL.Query()
	group := GroupTool // 차트는 기본으로 도구별
	var err error
	if q.Get("group") != "" {
		group, err = parseGroup(q)
	}
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	step, err := parseStep(q, v.win)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	top, err := parseTop(q)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	recs := v.records()
	first := v.win.start.Truncate(step)
	n := int(v.win.end.Sub(first)/step) + 1
	if !first.Add(time.Duration(n-1) * step).Before(v.win.end) {
		n--
	}
	if n < 1 {
		n = 1
	}
	newPoints := func() []point {
		pts := make([]point, n)
		for i := range pts {
			pts[i].T = first.Add(time.Duration(i) * step).Format(timeFormat)
		}
		return pts
	}

	items, _ := aggregate(recs, group)
	keep := map[string]string{} // key → label
	for i, it := range items {
		if i < top {
			keep[it.Key] = it.Label
		}
	}
	byKey := map[string]*series{}
	var order []string
	total := series{Key: "total", Label: "total", Points: newPoints()}
	for _, rec := range recs {
		idx := int(rec.Start.Sub(first) / step)
		if idx < 0 || idx >= n {
			continue
		}
		tok, _ := rec.Tokens()
		key, base := groupKey(rec, group)
		label := base.Label
		if _, ok := keep[key]; !ok {
			key, label = "other", "other"
		}
		sr, ok := byKey[key]
		if !ok {
			sr = &series{Key: key, Label: label, Points: newPoints()}
			byKey[key] = sr
			order = append(order, key)
		}
		sr.Points[idx].Tokens += tok
		sr.Points[idx].Calls++
		sr.Tokens += tok
		total.Points[idx].Tokens += tok
		total.Points[idx].Calls++
		total.Tokens += tok
	}
	out := []series{}
	for _, k := range order {
		out = append(out, *byKey[k])
	}
	sort.SliceStable(out, func(i, j int) bool {
		if (out[i].Key == "other") != (out[j].Key == "other") {
			return out[j].Key == "other" // other는 맨 뒤
		}
		if out[i].Tokens != out[j].Tokens {
			return out[i].Tokens > out[j].Tokens
		}
		return out[i].Key < out[j].Key
	})
	writeJSON(w, http.StatusOK, timeseriesResp{Window: v.win.json(), Estimated: true, Group: group,
		Step: step.String(), Total: total, Series: out})
}

// ---- assets/{asset_id} ----

type runtimeInfo struct {
	Used        bool    `json:"used"`
	Calls       int     `json:"calls"`
	LastUsedAt  *string `json:"last_used_at"`
	LastTraceID *string `json:"last_trace_id"`
}

type assetResp struct {
	Window      windowJSON   `json:"window"`
	Estimated   bool         `json:"estimated"`
	Key         string       `json:"key"`
	Usage       *assetItem   `json:"usage"`
	Runtime     runtimeInfo  `json:"runtime"`
	Recent      []recordItem `json:"recent"`
	BrakeEvents *int         `json:"brake_events"`
}

const recentLimit = 10

// asset은 자산 하나(또는 연결 안 된 도구 "tool:<이름>")의 사용량이다. 기록이 없으면 used=false, calls=0(404 아님).
// runtime은 스캐너 state(선언·노출 등)를 바꾸지 않고 따로 붙이는 실제 사용 정보다(스키마 14.2-8).
func (s *Server) asset(w http.ResponseWriter, r *http.Request) {
	v, ok := s.view(w, r)
	if !ok {
		return
	}
	key := r.PathValue("asset_id")
	if key == "" || len(key) > 512 {
		writeError(w, http.StatusBadRequest, "asset_id가 비었거나 너무 김")
		return
	}
	var mine []Record
	names := map[string]bool{}
	for _, rec := range v.records() {
		if k, _ := groupKey(rec, GroupAsset); k == key {
			mine = append(mine, rec)
			names[rec.ToolName] = true
		}
	}
	resp := assetResp{Window: v.win.json(), Estimated: true, Key: key, Recent: []recordItem{}}
	if len(mine) > 0 {
		items, _ := aggregate(mine, GroupAsset)
		it := items[0]
		it.Share, it.Relative = 0, 0 // 자산 하나만 보므로 의미 없음
		resp.Usage = &it
		resp.Runtime = runtimeInfo{Used: true, Calls: it.Calls, LastUsedAt: it.LastUsedAt, LastTraceID: it.LastTraceID}
		for i, rec := range newestFirst(mine) {
			if i == recentLimit {
				break
			}
			resp.Recent = append(resp.Recent, toRecordItem(rec))
		}
	}
	if v.ds.BrakeAvailable {
		n := 0
		for _, b := range v.ds.BrakeEvents {
			if v.win.contains(b.Time) && names[b.ToolName] {
				n++
			}
		}
		resp.BrakeEvents = &n
	}
	writeJSON(w, http.StatusOK, resp)
}

// ---- brake-events ----

type brakeItem struct {
	Time       string          `json:"time"`
	Level      string          `json:"level"`
	Mode       string          `json:"mode"`
	Enforced   bool            `json:"enforced"`
	ToolName   string          `json:"tool_name"`
	ToolCallID *string         `json:"tool_call_id"`
	RunID      *string         `json:"run_id"`
	Reasons    []BrakeReason   `json:"reasons"`
	RunUsage   *BrakeRunUsage  `json:"run_usage"`
	Resolution *resolutionJSON `json:"resolution"`
	TraceID    *string         `json:"trace_id"`
}

type resolutionJSON struct {
	Decision string `json:"decision"`
	Time     string `json:"time"`
}

type brakeResp struct {
	Window     windowJSON     `json:"window"`
	Available  bool           `json:"available"`
	ByLevel    map[string]int `json:"by_level"`
	Total      int            `json:"total"`
	Items      []brakeItem    `json:"items"`
	NextCursor *string        `json:"next_cursor"`
}

// brakeEvents는 소비 브레이크 기록(경고·승인 요청·차단)이다. 플러그인 기록 파일을 주지 않았으면 available=false.
// trace_id는 같은 도구 호출 ID의 사용 기록에서 찾는다(플러그인 기록의 trace id는 실행 기록 id와 다를 수 있어서).
func (s *Server) brakeEvents(w http.ResponseWriter, r *http.Request) {
	v, ok := s.view(w, r)
	if !ok {
		return
	}
	q := r.URL.Query()
	level := q.Get("level")
	if level != "" && level != "warn" && level != "approve" && level != "block" {
		writeError(w, http.StatusBadRequest, "level: warn, approve, block 중 하나")
		return
	}
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
	resp := brakeResp{Window: v.win.json(), Available: v.ds.BrakeAvailable,
		ByLevel: map[string]int{"warn": 0, "approve": 0, "block": 0}, Items: []brakeItem{}}
	trace := map[string]string{}
	for _, rec := range v.ds.Records {
		if rec.ToolCallID != nil {
			trace[*rec.ToolCallID] = rec.TraceID
		}
	}
	var sel []BrakeEvent
	for i := len(v.ds.BrakeEvents) - 1; i >= 0; i-- { // 최신순
		b := v.ds.BrakeEvents[i]
		if !v.win.contains(b.Time) {
			continue
		}
		resp.ByLevel[b.Level]++
		if level == "" || b.Level == level {
			sel = append(sel, b)
		}
	}
	resp.Total = len(sel)
	if offset > len(sel) {
		offset = len(sel)
	}
	end := min(offset+limit, len(sel))
	for _, b := range sel[offset:end] {
		it := brakeItem{Time: b.Time.Format(timeFormat), Level: b.Level, Mode: b.Mode, Enforced: b.Enforced,
			ToolName: b.ToolName, ToolCallID: nonEmpty(b.ToolCallID), RunID: nonEmpty(b.RunID),
			Reasons: b.Reasons, RunUsage: b.RunUsage}
		if b.Resolution != nil {
			it.Resolution = &resolutionJSON{Decision: b.Resolution.Decision, Time: b.Resolution.Time.Format(timeFormat)}
		}
		if t, ok := trace[b.ToolCallID]; ok && b.ToolCallID != "" {
			it.TraceID = str(t)
		}
		resp.Items = append(resp.Items, it)
	}
	if end < len(sel) {
		resp.NextCursor = str(strconv.Itoa(end))
	}
	writeJSON(w, http.StatusOK, resp)
}
