package usageapi

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// 동작 방식(health.mode).
const (
	ModeFixed = "fixed" // 시작할 때 한 번 읽은 데이터로 답함
	ModeLive  = "live"  // 입력 파일이 바뀌면 다시 계산
)

// Source는 서버가 답할 Dataset과 기준 시각을 준다.
type Source interface {
	// Current는 지금 답할 Dataset이다. 아직 읽지 못했으면 nil.
	Current() *Dataset
	// Now는 range의 기준 시각과, 인자가 없을 때 쓸 기본 조회 구간이다.
	Now(ds *Dataset) (now time.Time, def window)
	Status() SourceStatus
}

// SourceStatus는 health에 보여 줄 상태다.
type SourceStatus struct {
	Mode       string
	LastError  string
	LastReload time.Time
}

type fixedSource struct{ ds *Dataset }

// FixedSource는 고정 응답 모드: 기준 시각 = 데이터 구간 끝, 기본 구간 = 데이터 구간 전체.
func FixedSource(ds *Dataset) Source { return fixedSource{ds} }

func (f fixedSource) Current() *Dataset { return f.ds }
func (f fixedSource) Now(ds *Dataset) (time.Time, window) {
	return ds.End, window{start: ds.Start, end: ds.End}
}
func (f fixedSource) Status() SourceStatus {
	return SourceStatus{Mode: ModeFixed, LastReload: f.ds.LoadedAt}
}

// LiveOptions는 실시간 모드 설정이다.
type LiveOptions struct {
	Interval     time.Duration // 입력 파일 변경 확인 주기(기본 15초)
	Retain       time.Duration // 현재 기준 이만큼만 계산(기본 7일)
	DefaultRange time.Duration // 인자 없는 요청의 기본 조회 구간(기본 1시간)
	Now          func() time.Time
}

// LiveSource는 실시간 모드: Collector가 계속 쓰는 스팬 파일(과 플러그인 기록)이 바뀌면 다시 계산한다.
// 다시 읽기에 실패하면 이전 Dataset으로 계속 답하고 health에 오류를 보여 준다.
type LiveSource struct {
	cfg  LoadConfig
	opt  LiveOptions
	warn func(string)

	cur atomic.Pointer[Dataset]

	mu         sync.Mutex
	sig        string
	lastErr    string
	lastReload time.Time
}

// NewLiveSource는 실시간 모드 Source를 만든다. 첫 계산은 Reload로 한다.
func NewLiveSource(cfg LoadConfig, opt LiveOptions, warn func(string)) *LiveSource {
	if opt.Interval <= 0 {
		opt.Interval = 15 * time.Second
	}
	if opt.Retain <= 0 {
		opt.Retain = MaxWindow
	}
	if opt.DefaultRange <= 0 {
		opt.DefaultRange = time.Hour
	}
	if opt.Now == nil {
		opt.Now = time.Now
	}
	if warn == nil {
		warn = func(string) {}
	}
	cfg.AllowMissing = true
	return &LiveSource{cfg: cfg, opt: opt, warn: warn}
}

func (l *LiveSource) Current() *Dataset { return l.cur.Load() }

func (l *LiveSource) Now(*Dataset) (time.Time, window) {
	now := l.opt.Now().UTC()
	return now, window{start: now.Add(-l.opt.DefaultRange), end: now}
}

func (l *LiveSource) Status() SourceStatus {
	l.mu.Lock()
	defer l.mu.Unlock()
	return SourceStatus{Mode: ModeLive, LastError: l.lastErr, LastReload: l.lastReload}
}

// Reload는 입력 파일이 바뀌었으면(또는 아직 읽은 적 없으면) 다시 계산한다. 바뀐 게 없으면 false.
func (l *LiveSource) Reload() (bool, error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	sig, err := inputSignature(l.cfg)
	if err != nil {
		l.lastErr = err.Error()
		return false, err
	}
	if sig == l.sig && l.cur.Load() != nil {
		return false, nil
	}
	now := l.opt.Now().UTC()
	cfg := l.cfg
	cfg.From = now.Add(-l.opt.Retain).Truncate(time.Second)
	cfg.To = now.Add(time.Minute).Truncate(time.Second) // 시계가 조금 어긋난 기록도 받도록 여유
	cfg.Now = l.opt.Now
	ds, err := Load(cfg, l.warn)
	if err != nil {
		l.lastErr = err.Error()
		return false, err
	}
	l.cur.Store(ds)
	l.sig = sig
	l.lastErr = ""
	l.lastReload = now
	return true, nil
}

// Run은 done이 닫힐 때까지 주기적으로 Reload한다. 실패는 warn으로 알리고 계속 돈다.
func (l *LiveSource) Run(done <-chan struct{}) {
	t := time.NewTicker(l.opt.Interval)
	defer t.Stop()
	for {
		select {
		case <-done:
			return
		case <-t.C:
			if _, err := l.Reload(); err != nil {
				l.warn("다시 읽기 실패(이전 데이터로 계속): " + err.Error())
			}
		}
	}
}

// expandInputs는 glob 패턴(*, ?, [)을 펼친다. 패턴이 아닌 경로는 그대로(없으면 allowMissing에 따라).
func expandInputs(paths []string, allowMissing bool) ([]string, error) {
	var out []string
	seen := map[string]bool{}
	for _, p := range paths {
		var matches []string
		if strings.ContainsAny(p, "*?[") {
			m, err := filepath.Glob(p)
			if err != nil {
				return nil, fmt.Errorf("입력 패턴 %q: %w", filepath.Base(p), err)
			}
			sort.Strings(m)
			matches = m
		} else {
			if _, err := os.Stat(p); err != nil {
				if allowMissing && errors.Is(err, os.ErrNotExist) {
					continue
				}
				return nil, fmt.Errorf("%s: %w", filepath.Base(p), err)
			}
			matches = []string{p}
		}
		for _, m := range matches {
			if !seen[m] {
				seen[m] = true
				out = append(out, m)
			}
		}
	}
	return out, nil
}

// inputSignature는 입력 파일 목록·크기·수정 시각으로 변경 여부를 판단할 값을 만든다.
func inputSignature(cfg LoadConfig) (string, error) {
	var b strings.Builder
	for _, group := range [][]string{cfg.Inputs, cfg.ToolResults} {
		files, err := expandInputs(group, true)
		if err != nil {
			return "", err
		}
		for _, f := range files {
			st, err := os.Stat(f)
			if err != nil {
				continue // 로테이션 중 사라진 파일
			}
			fmt.Fprintf(&b, "%s|%d|%d;", f, st.Size(), st.ModTime().UnixNano())
		}
		b.WriteString("#")
	}
	if cfg.Inventory != "" {
		if st, err := os.Stat(cfg.Inventory); err == nil {
			fmt.Fprintf(&b, "inv|%d|%d", st.Size(), st.ModTime().UnixNano())
		}
	}
	return b.String(), nil
}
