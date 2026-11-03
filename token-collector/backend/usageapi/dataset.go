// Package usageapi는 대시보드 UI(Token Usage 화면, 자산 그래프·상세의 사용량 표시)에
// 도구별 토큰 사용량을 JSON으로 주는 읽기 전용 HTTP API다.
//
// 데이터는 usage.json과 같은 계산(usagereport.Build)으로 만든 호출 단위 기록이다.
// 지금은 고정 응답 모드만 있다: 시작할 때 스팬 파일을 한 번 읽어 그 구간의 기록으로 답한다.
// 응답에는 도구 결과 내용, API 키, 사용자 경로를 넣지 않는다(파일 이름만).
package usageapi

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/pbh0330/2026-Agent_Scope/token-collector/backend/attribution"
	"github.com/pbh0330/2026-Agent_Scope/token-collector/backend/usagereport"
)

// 귀속 방식 묶음(summary.by_method, records[].method).
const (
	MethodSequential  = "sequential"   // 순차 구간 실측(앞뒤 모델 호출 입력 차이)
	MethodAllocated   = "allocated"    // 병렬·배치 구간 증가분을 결과별 토큰 수 비율로 배분
	MethodNotComputed = "not_computed" // 토큰을 계산하지 못함(배분 근거 없음, 꼬리 도구 등)
)

// Record는 기록 하나와 화면용으로 미리 계산한 값이다.
type Record struct {
	usagereport.UsageRecord
	Start     time.Time
	Method    string
	MCPServer string // MCP 도구면 노출 이름의 서버 부분(fs__read_text_file → fs)
	ServerRef string // 매핑된 Tool의 소속 MCP 서버 asset_id(모르면 "")
}

// Tokens는 귀속 토큰(계산 못 했으면 0, ok=false).
func (r Record) Tokens() (int64, bool) {
	if r.ApproxInputTokens == nil {
		return 0, false
	}
	return *r.ApproxInputTokens, true
}

// Dataset은 API가 답하는 기록 묶음이다. 만든 뒤에는 바꾸지 않는다(동시 읽기 안전).
type Dataset struct {
	Start, End          time.Time // 데이터 구간 [Start, End)
	InventorySnapshotID *string
	Records             []Record // 시작 시각 오름차순
	Sources             []string // 입력 파일 이름(경로 제외)
	LoadedAt            time.Time
	Limitations         []string

	BrakeEvents    []BrakeEvent // 플러그인 기록의 소비 브레이크(시각 오름차순)
	BrakeAvailable bool         // 플러그인 기록 파일을 읽었는지(없으면 브레이크 정보 자체가 없음)
}

// NewDataset은 UsageReport를 API용 묶음으로 바꾼다. inv는 서버 단위 묶음에만 쓰며 nil이어도 된다.
func NewDataset(rep *usagereport.UsageReport, inv *usagereport.Inventory, sources []string, loadedAt time.Time) (*Dataset, error) {
	if rep == nil {
		return nil, errors.New("usage report가 없음")
	}
	start, err := time.Parse(time.RFC3339Nano, rep.Window.Start)
	if err != nil {
		return nil, fmt.Errorf("window.start: %w", err)
	}
	end, err := time.Parse(time.RFC3339Nano, rep.Window.End)
	if err != nil {
		return nil, fmt.Errorf("window.end: %w", err)
	}
	ds := &Dataset{
		Start: start.UTC(), End: end.UTC(),
		InventorySnapshotID: rep.InventorySnapshotID,
		Sources:             append([]string(nil), sources...),
		LoadedAt:            loadedAt.UTC(),
		Limitations:         append([]string(nil), rep.Limitations...),
	}
	for _, u := range rep.Records {
		r := Record{UsageRecord: u, Start: u.ToolStart().UTC(), Method: methodOf(u)}
		if u.ToolSource == "mcp" {
			if srv, _, ok := strings.Cut(u.ToolName, "__"); ok {
				r.MCPServer = srv
			}
		}
		if u.AssetRef != nil {
			if owner, ok := inv.ToolOwner(*u.AssetRef); ok {
				r.ServerRef = owner
			}
		}
		ds.Records = append(ds.Records, r)
	}
	sort.SliceStable(ds.Records, func(i, j int) bool {
		if !ds.Records[i].Start.Equal(ds.Records[j].Start) {
			return ds.Records[i].Start.Before(ds.Records[j].Start)
		}
		return ds.Records[i].UsageID < ds.Records[j].UsageID
	})
	return ds, nil
}

func methodOf(u usagereport.UsageRecord) string {
	switch {
	case u.ApproxInputTokens == nil:
		return MethodNotComputed
	case u.AttributionMethod == usagereport.AttributionMethodParallelCount, u.AttributionMethod == usagereport.AttributionMethodBatchCount:
		return MethodAllocated
	default:
		return MethodSequential
	}
}

// LoadConfig는 agentscope-usage CLI와 같은 입력을 받는다.
type LoadConfig struct {
	EnvironmentID, ProfileID string
	Inputs                   []string // 스팬 파일(OTLP JSON 줄 단위)
	ToolResults              []string // 결과 기록 플러그인 JSONL(선택, 스팬 파일의 카운트 스팬보다 우선)
	Inventory                string   // InventorySnapshot(선택)
	OpenClawConfig           string   // 단가를 읽을 openclaw.json(선택)
	ReferencePricing         bool     // 설정 단가가 없으면 공식 정가(참고용)
	IncludeCacheInPrompt     bool
	From, To                 time.Time // 둘 다 zero면 데이터에서 잡음
	Now                      func() time.Time
	// AllowMissing: 입력 파일이 아직 없어도 오류로 보지 않음(실시간 모드: Collector가 첫 요청 뒤에 파일을 만듦).
	AllowMissing bool
}

// Load는 파일을 읽어 Dataset을 만든다. 경고(단가 로딩 실패 등)는 warn으로 알린다.
func Load(cfg LoadConfig, warn func(string)) (*Dataset, error) {
	if len(cfg.Inputs) == 0 {
		return nil, errors.New("스팬 파일(--input)이 하나 이상 필요")
	}
	if warn == nil {
		warn = func(string) {}
	}
	now := time.Now
	if cfg.Now != nil {
		now = cfg.Now
	}
	opt := usagereport.Options{
		EnvironmentID: cfg.EnvironmentID,
		ProfileID:     cfg.ProfileID,
		WindowStart:   cfg.From,
		WindowEnd:     cfg.To,
		GeneratedAt:   now(),
		Attribution:   attribution.Options{IncludeCacheInPrompt: cfg.IncludeCacheInPrompt},
		Pricing:       attribution.Pricing{Models: map[string]attribution.Rate{}},
	}
	if cfg.OpenClawConfig != "" {
		models, err := attribution.LoadPricingFromOpenClawConfig(cfg.OpenClawConfig)
		if err != nil {
			warn("openclaw.json 단가 로딩 실패, 설정 단가 없이 진행: " + err.Error())
		} else {
			opt.Pricing.Models = models
			opt.ConfigPricingVersion = usagereport.ConfigPricingVersion(models)
		}
	}
	if cfg.ReferencePricing {
		opt.Pricing.Reference = attribution.AnthropicListPricingReference
	}
	if cfg.Inventory != "" {
		inv, err := usagereport.LoadInventory(cfg.Inventory)
		if err != nil {
			return nil, err
		}
		opt.Inventory = inv
	}
	inputs, err := expandInputs(cfg.Inputs, cfg.AllowMissing)
	if err != nil {
		return nil, err
	}
	toolResults, err := expandInputs(cfg.ToolResults, cfg.AllowMissing)
	if err != nil {
		return nil, err
	}
	var brakes []BrakeEvent
	if len(toolResults) > 0 {
		counts := map[string]int64{}
		refs := make([]string, 0, len(toolResults))
		for _, p := range toolResults {
			st, err := usagereport.ReadToolResultCounts(p, counts)
			if err != nil {
				return nil, fmt.Errorf("결과 기록 %s: %w", filepath.Base(p), err)
			}
			if st.Malformed > 0 {
				warn(fmt.Sprintf("%s 에서 읽지 못한 줄 %d개", filepath.Base(p), st.Malformed))
			}
			ev, err := ReadBrakeEvents(p)
			if err != nil {
				return nil, fmt.Errorf("결과 기록 %s: %w", filepath.Base(p), err)
			}
			brakes = append(brakes, ev...)
			refs = append(refs, filepath.Base(p))
		}
		opt.ToolResultCounts = counts
		opt.ToolResultsRef = strings.Join(refs, "+")
	}
	var spans []attribution.Span
	names := make([]string, 0, len(inputs))
	for _, p := range inputs {
		s, err := readSpans(p, cfg.AllowMissing)
		if err != nil {
			return nil, fmt.Errorf("%s: %w", filepath.Base(p), err)
		}
		spans = append(spans, s...)
		names = append(names, filepath.Base(p)) // 사용자 이름이 든 전체 경로는 응답에 남기지 않음
	}
	opt.EvidencePrefix = "otlp-json:" + strings.Join(names, "+")

	rep, err := usagereport.Build(spans, opt)
	if err != nil {
		return nil, err
	}
	ds, err := NewDataset(rep, opt.Inventory, names, now())
	if err != nil {
		return nil, err
	}
	ds.BrakeAvailable = len(toolResults) > 0
	ds.BrakeEvents = sortBrakes(brakes)
	return ds, nil
}

// readSpans는 스팬 파일을 읽는다. tolerateTail이면(실시간 모드) Collector가 아직 쓰는 중인
// 마지막 줄(줄바꿈 전)은 빼고 읽어, 쓰는 도중에 읽어도 실패하지 않게 한다.
func readSpans(path string, tolerateTail bool) ([]attribution.Span, error) {
	if !tolerateTail {
		return usagereport.ReadSpansFile(path)
	}
	b, err := os.ReadFile(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil, nil // 로테이션 중 사라진 파일
		}
		return nil, err
	}
	if i := bytes.LastIndexByte(b, '\n'); i >= 0 {
		b = b[:i+1]
	} else {
		b = nil
	}
	return usagereport.ReadSpans(bytes.NewReader(b))
}
