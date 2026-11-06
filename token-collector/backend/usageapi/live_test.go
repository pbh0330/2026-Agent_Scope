package usageapi

import (
	"bufio"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func fixtureLines(t *testing.T) []string {
	t.Helper()
	f, err := os.Open(fixture)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	var out []string
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<24)
	for sc.Scan() {
		out = append(out, sc.Text())
	}
	return out
}

func writeLines(t *testing.T, path string, lines []string, appendMode bool) {
	t.Helper()
	flag := os.O_CREATE | os.O_WRONLY | os.O_TRUNC
	if appendMode {
		flag = os.O_CREATE | os.O_WRONLY | os.O_APPEND
	}
	f, err := os.OpenFile(path, flag, 0o644)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	for _, l := range lines {
		if _, err := f.WriteString(l + "\n"); err != nil {
			t.Fatal(err)
		}
	}
}

// 10.29 데이터가 끝난 직후(05:30Z)를 현재 시각으로 둔다. 기본 조회 구간 1시간 안에 16건이 다 들어간다.
var liveNow = func() time.Time { return time.Date(2026, 10, 29, 5, 30, 0, 0, time.UTC) }

func newLive(t *testing.T, inputs ...string) *LiveSource {
	t.Helper()
	return NewLiveSource(LoadConfig{EnvironmentID: "env-pc", ProfileID: "profile-pc", Inputs: inputs, ReferencePricing: true},
		LiveOptions{Now: liveNow, DefaultRange: time.Hour}, func(m string) { t.Log("warn:", m) })
}

// 파일이 아직 없어도 시작하고(0건), 파일이 생기고 늘어나면 다시 계산한다. 바뀐 게 없으면 다시 계산하지 않는다.
func TestLiveReloadsWhenFileGrows(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "agentscope-traces.jsonl")
	src := newLive(t, path)
	if changed, err := src.Reload(); err != nil || !changed {
		t.Fatalf("first reload: %v %v", changed, err)
	}
	if n := len(src.Current().Records); n != 0 {
		t.Fatalf("파일 없을 때 %d건", n)
	}
	lines := fixtureLines(t)
	half := len(lines) / 2
	writeLines(t, path, lines[:half], false)
	if changed, err := src.Reload(); err != nil || !changed {
		t.Fatalf("after half: %v %v", changed, err)
	}
	n1 := len(src.Current().Records)
	writeLines(t, path, lines[half:], true)
	if changed, err := src.Reload(); err != nil || !changed {
		t.Fatalf("after all: %v %v", changed, err)
	}
	if n := len(src.Current().Records); n != 16 || n1 >= 16 {
		t.Fatalf("records: half %d, all %d", n1, n)
	}
	if changed, _ := src.Reload(); changed {
		t.Fatal("바뀐 게 없는데 다시 계산함")
	}
	var got summaryResp
	get(t, NewServer(src), "/api/v1/usage/summary", 200, &got)
	if got.Calls != 16 || got.AttributedTokens != 15769 || got.Window.Start != "2026-10-29T04:30:00.000Z" {
		t.Fatalf("summary: %+v", got)
	}
	var h healthResp
	get(t, NewServer(src), "/api/v1/usage/health", 200, &h)
	if h.Mode != ModeLive || h.Status != "ok" || h.Records != 16 {
		t.Fatalf("health: %+v", h)
	}
}

// Collector가 쓰는 중인 마지막 줄(줄바꿈 전)은 건너뛰고, 다음 확인 때 읽는다.
func TestLiveIgnoresPartialLastLine(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "agentscope-traces.jsonl")
	lines := fixtureLines(t)
	writeLines(t, path, lines[:len(lines)-1], false)
	last := lines[len(lines)-1]
	f, _ := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0o644)
	f.WriteString(last[:len(last)/2]) // 반쯤 쓴 줄
	f.Close()
	src := newLive(t, path)
	if _, err := src.Reload(); err != nil {
		t.Fatalf("반쯤 쓴 줄 때문에 실패: %v", err)
	}
	f, _ = os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0o644)
	f.WriteString(last[len(last)/2:] + "\n")
	f.Close()
	if _, err := src.Reload(); err != nil {
		t.Fatal(err)
	}
	if n := len(src.Current().Records); n != 16 {
		t.Fatalf("records %d", n)
	}
}

// 다시 읽기가 실패하면 이전 데이터로 계속 답하고 health는 degraded + last_error.
func TestLiveKeepsOldDataOnError(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "agentscope-traces.jsonl")
	writeLines(t, path, fixtureLines(t), false)
	src := newLive(t, path)
	if _, err := src.Reload(); err != nil {
		t.Fatal(err)
	}
	writeLines(t, path, []string{"{ broken json"}, true)
	if _, err := src.Reload(); err == nil {
		t.Fatal("깨진 줄인데 오류 없음")
	}
	s := NewServer(src)
	var h healthResp
	get(t, s, "/api/v1/usage/health", 200, &h)
	if h.Status != "degraded" || h.LastError == nil || h.Records != 16 {
		t.Fatalf("health: %+v", h)
	}
	if strings.Contains(*h.LastError, dir) {
		t.Fatalf("오류에 경로가 나옴: %s", *h.LastError)
	}
	var sum summaryResp
	get(t, s, "/api/v1/usage/summary", 200, &sum)
	if sum.Calls != 16 {
		t.Fatalf("이전 데이터로 답해야 함: %+v", sum)
	}
}

// 로테이션된 파일까지 패턴(*)으로 읽는다.
func TestLiveGlobInputs(t *testing.T) {
	dir := t.TempDir()
	lines := fixtureLines(t)
	half := len(lines) / 2
	writeLines(t, filepath.Join(dir, "agentscope-traces-2026-10-29T05-27-00.000.jsonl"), lines[:half], false)
	writeLines(t, filepath.Join(dir, "agentscope-traces.jsonl"), lines[half:], false)
	src := newLive(t, filepath.Join(dir, "agentscope-traces*.jsonl"))
	if _, err := src.Reload(); err != nil {
		t.Fatal(err)
	}
	if n := len(src.Current().Records); n != 16 {
		t.Fatalf("records %d", n)
	}
	var h healthResp
	get(t, NewServer(src), "/api/v1/usage/health", 200, &h)
	if len(h.Sources) != 2 {
		t.Fatalf("sources: %v", h.Sources)
	}
}

func TestNoDataYetReturns503(t *testing.T) {
	src := newLive(t, filepath.Join(t.TempDir(), "x.jsonl"))
	rec := httptest.NewRecorder()
	NewServer(src).ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/api/v1/usage/summary", nil))
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("Reload 전: %d", rec.Code)
	}
	var h healthResp
	get(t, NewServer(src), "/api/v1/usage/health", 200, &h)
	if h.Status != "loading" {
		t.Fatalf("health: %+v", h)
	}
}
