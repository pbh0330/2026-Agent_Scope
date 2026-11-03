// agentscope-usage-api는 대시보드 UI에 도구별 토큰 사용량을 주는 읽기 전용 HTTP 서버다.
// 지금은 고정 응답 모드: 시작할 때 스팬 파일을 한 번 읽고 그 기록으로 답한다.
//
//	agentscope-usage-api --env env-pc --profile profile-pc \
//	  --input testdata/pc-1029.traces.jsonl [--input 다른파일 ...] \
//	  [--tool-results agentscope-tool-results.jsonl] [--inventory snapshot.json] \
//	  [--openclaw-config openclaw.json] [--from ... --to ...] [--addr 127.0.0.1:8088]
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/pbh0330/2026-Agent_Scope/token-collector/backend/usageapi"
)

type multi []string

func (m *multi) String() string     { return strings.Join(*m, ",") }
func (m *multi) Set(v string) error { *m = append(*m, v); return nil }

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := run(ctx, os.Args[1:], os.Stderr, nil); err != nil {
		fmt.Fprintln(os.Stderr, "agentscope-usage-api:", err)
		os.Exit(1)
	}
}

// run은 서버를 띄우고 ctx가 끝나면 닫는다. ready가 있으면 실제 주소를 보낸다(테스트용).
func run(ctx context.Context, args []string, stderr io.Writer, ready chan<- string) error {
	fs := flag.NewFlagSet("agentscope-usage-api", flag.ContinueOnError)
	fs.SetOutput(stderr)
	var inputs, toolResults multi
	fs.Var(&inputs, "input", "스팬 파일(OTLP JSON 줄 단위). 여러 번 지정 가능, *가 들어간 패턴 가능(로테이션된 파일 포함용)")
	fs.Var(&toolResults, "tool-results", "결과 기록 플러그인 JSONL(선택, 브레이크 기록 포함). 여러 번 지정 가능")
	env := fs.String("env", "", "environment_id (필수)")
	profile := fs.String("profile", "", "profile_id (필수)")
	inventory := fs.String("inventory", "", "자산 매핑에 쓸 InventorySnapshot(선택)")
	ocConfig := fs.String("openclaw-config", "", "모델 단가를 읽을 openclaw.json(선택)")
	refPricing := fs.Bool("reference-pricing", true, "설정 단가가 없으면 Anthropic 공식 정가(참고용)를 쓴다")
	includeCache := fs.Bool("include-cache-in-prompt", false, "프롬프트 토큰에 cache read/write 포함(캐시 토큰을 따로 보고하는 프로바이더용)")
	from := fs.String("from", "", "데이터 구간 시작(RFC3339, 포함). --to와 함께")
	to := fs.String("to", "", "데이터 구간 끝(RFC3339, 미포함)")
	addr := fs.String("addr", "127.0.0.1:8088", "듣는 주소. 테스트베드에서 호스트 PC가 접속하려면 0.0.0.0:8088")
	live := fs.Bool("live", false, "실시간 모드: 입력 파일이 바뀌면 다시 계산(테스트베드용)")
	interval := fs.Duration("reload-interval", 15*time.Second, "실시간 모드: 입력 파일 변경 확인 주기")
	retain := fs.String("retain", "7d", "실시간 모드: 현재 기준 이 기간만 계산(최대 7d)")
	defRange := fs.String("default-range", "1h", "실시간 모드: 인자 없는 요청의 기본 조회 구간")
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg := usageapi.LoadConfig{
		EnvironmentID: *env, ProfileID: *profile, Inputs: inputs, ToolResults: toolResults,
		Inventory: *inventory, OpenClawConfig: *ocConfig, ReferencePricing: *refPricing,
		IncludeCacheInPrompt: *includeCache,
	}
	if *live && (*from != "" || *to != "") {
		return errors.New("--live에서는 --from/--to를 쓰지 않음(--retain 사용)")
	}
	if *from != "" || *to != "" {
		var err error
		if cfg.From, err = time.Parse(time.RFC3339Nano, *from); err != nil {
			return fmt.Errorf("--from: %w", err)
		}
		if cfg.To, err = time.Parse(time.RFC3339Nano, *to); err != nil {
			return fmt.Errorf("--to: %w", err)
		}
	}
	warn := func(msg string) { fmt.Fprintln(stderr, "경고:", msg) }
	var (
		handler http.Handler
		banner  string
		liveSrc *usageapi.LiveSource
	)
	if *live {
		if len(inputs) == 0 {
			return errors.New("--input이 하나 이상 필요")
		}
		ret, err := usageapi.ParseRange(*retain)
		if err != nil {
			return fmt.Errorf("--retain: %w", err)
		}
		dr, err := usageapi.ParseRange(*defRange)
		if err != nil {
			return fmt.Errorf("--default-range: %w", err)
		}
		liveSrc = usageapi.NewLiveSource(cfg, usageapi.LiveOptions{Interval: *interval, Retain: ret, DefaultRange: dr}, warn)
		if _, err := liveSrc.Reload(); err != nil {
			return err // 시작할 때 못 읽으면(설정 오류 등) 바로 알림
		}
		handler = usageapi.NewServer(liveSrc)
		ds := liveSrc.Current()
		banner = fmt.Sprintf("실시간 모드: 기록 %d건(최근 %s), %s마다 확인", len(ds.Records), *retain, *interval)
	} else {
		ds, err := usageapi.Load(cfg, warn)
		if err != nil {
			return err
		}
		handler = usageapi.NewFixedServer(ds)
		banner = fmt.Sprintf("고정 응답 모드: 기록 %d건, 구간 %s ~ %s", len(ds.Records),
			ds.Start.Format(time.RFC3339), ds.End.Format(time.RFC3339))
	}

	srv := &http.Server{
		Addr:              *addr,
		Handler:           handler,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
		MaxHeaderBytes:    16 << 10,
	}
	ln, err := net.Listen("tcp", *addr)
	if err != nil {
		return err
	}
	fmt.Fprintf(stderr, "%s, http://%s/api/v1/usage/health\n", banner, ln.Addr())
	done := make(chan struct{})
	defer close(done)
	if liveSrc != nil {
		go liveSrc.Run(done)
	}
	if ready != nil {
		ready <- ln.Addr().String()
	}
	errc := make(chan error, 1)
	go func() { errc <- srv.Serve(ln) }()
	select {
	case err := <-errc:
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return err
	case <-ctx.Done():
		sctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		return srv.Shutdown(sctx)
	}
}
