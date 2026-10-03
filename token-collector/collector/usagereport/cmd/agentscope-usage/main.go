// agentscope-usage는 Collector가 파일로 남긴 OpenClaw 트레이스(OTLP JSON)를 읽어
// 통합 스키마 14절 형식의 usage.json(UsageReport)을 만든다.
//
//	agentscope-usage --env env-test-01 --profile profile-test-01 \
//	  --input telemetry/traces.jsonl [--input 이전파일 ...] \
//	  [--inventory snapshot.json] [--openclaw-config openclaw.json] \
//	  [--from 2026-10-02T00:00:00Z --to 2026-10-03T00:00:00Z] --out usage.json
package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/pbh0330/2026-Agent_Scope/token-collector/collector/attribution"
	"github.com/pbh0330/2026-Agent_Scope/token-collector/collector/usagereport"
)

type multi []string

func (m *multi) String() string     { return strings.Join(*m, ",") }
func (m *multi) Set(v string) error { *m = append(*m, v); return nil }

func main() {
	if err := run(os.Args[1:], os.Stdout, os.Stderr); err != nil {
		fmt.Fprintln(os.Stderr, "agentscope-usage:", err)
		os.Exit(1)
	}
}

func run(args []string, stdout, stderr io.Writer) error {
	fs := flag.NewFlagSet("agentscope-usage", flag.ContinueOnError)
	fs.SetOutput(stderr)
	var inputs multi
	fs.Var(&inputs, "input", "스팬 파일(OTLP JSON 줄 단위 또는 픽스처 배열). 여러 번 지정 가능")
	env := fs.String("env", "", "environment_id (필수)")
	profile := fs.String("profile", "", "profile_id (필수)")
	inventory := fs.String("inventory", "", "자산 매핑에 쓸 InventorySnapshot(snapshot.json). 없으면 전부 unmatched")
	ocConfig := fs.String("openclaw-config", "", "모델 단가를 읽을 openclaw.json (선택)")
	refPricing := fs.Bool("reference-pricing", true, "설정 단가가 0이거나 없으면 Anthropic 공식 정가(참고용)를 쓴다")
	includeCache := fs.Bool("include-cache-in-prompt", false, "프롬프트 토큰에 cache read/write를 포함(커넥터 옵션과 같게 맞출 것)")
	from := fs.String("from", "", "집계 구간 시작(RFC3339, 포함). --to와 함께")
	to := fs.String("to", "", "집계 구간 끝(RFC3339, 미포함)")
	out := fs.String("out", "", "출력 파일(기본: 표준 출력)")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if len(inputs) == 0 {
		return errors.New("--input이 하나 이상 필요")
	}

	opt := usagereport.Options{
		EnvironmentID: *env,
		ProfileID:     *profile,
		Attribution:   attribution.Options{IncludeCacheInPrompt: *includeCache},
		Pricing:       attribution.Pricing{Models: map[string]attribution.Rate{}},
	}
	var err error
	if *from != "" || *to != "" {
		if opt.WindowStart, err = time.Parse(time.RFC3339Nano, *from); err != nil {
			return fmt.Errorf("--from: %w", err)
		}
		if opt.WindowEnd, err = time.Parse(time.RFC3339Nano, *to); err != nil {
			return fmt.Errorf("--to: %w", err)
		}
	}
	if *ocConfig != "" {
		models, err := attribution.LoadPricingFromOpenClawConfig(*ocConfig)
		if err != nil {
			fmt.Fprintln(stderr, "경고: openclaw.json 단가 로딩 실패 — 설정 단가 없이 진행:", err)
		} else {
			opt.Pricing.Models = models
			opt.ConfigPricingVersion = usagereport.ConfigPricingVersion(models)
		}
	}
	if *refPricing {
		opt.Pricing.Reference = attribution.AnthropicListPricingReference
	}
	if *inventory != "" {
		if opt.Inventory, err = usagereport.LoadInventory(*inventory); err != nil {
			return err
		}
	}

	var spans []attribution.Span
	names := make([]string, 0, len(inputs))
	for _, p := range inputs {
		s, err := usagereport.ReadSpansFile(p)
		if err != nil {
			return fmt.Errorf("%s: %w", p, err)
		}
		spans = append(spans, s...)
		names = append(names, filepath.Base(p)) // 사용자 이름이 든 전체 경로는 출력에 남기지 않는다
	}
	opt.EvidencePrefix = "otlp-json:" + strings.Join(names, "+")

	rep, err := usagereport.Build(spans, opt)
	if err != nil {
		return err
	}
	b, err := json.MarshalIndent(rep, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	if *out == "" {
		_, err = stdout.Write(b)
		return err
	}
	if err := os.WriteFile(*out, b, 0o644); err != nil {
		return err
	}
	fmt.Fprintf(stderr, "%s: 레코드 %d건 (구간 %s ~ %s)\n", *out, len(rep.Records), rep.Window.Start, rep.Window.End)
	return nil
}
