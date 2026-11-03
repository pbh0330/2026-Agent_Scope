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
	fs.Var(&inputs, "input", "스팬 파일(OTLP JSON 줄 단위). 여러 번 지정 가능")
	fs.Var(&toolResults, "tool-results", "결과 기록 플러그인 JSONL(선택). 여러 번 지정 가능")
	env := fs.String("env", "", "environment_id (필수)")
	profile := fs.String("profile", "", "profile_id (필수)")
	inventory := fs.String("inventory", "", "자산 매핑에 쓸 InventorySnapshot(선택)")
	ocConfig := fs.String("openclaw-config", "", "모델 단가를 읽을 openclaw.json(선택)")
	refPricing := fs.Bool("reference-pricing", true, "설정 단가가 없으면 Anthropic 공식 정가(참고용)를 쓴다")
	includeCache := fs.Bool("include-cache-in-prompt", false, "프롬프트 토큰에 cache read/write 포함(캐시 토큰을 따로 보고하는 프로바이더용)")
	from := fs.String("from", "", "데이터 구간 시작(RFC3339, 포함). --to와 함께")
	to := fs.String("to", "", "데이터 구간 끝(RFC3339, 미포함)")
	addr := fs.String("addr", "127.0.0.1:8088", "듣는 주소. 컨테이너에서는 0.0.0.0:8088")
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg := usageapi.LoadConfig{
		EnvironmentID: *env, ProfileID: *profile, Inputs: inputs, ToolResults: toolResults,
		Inventory: *inventory, OpenClawConfig: *ocConfig, ReferencePricing: *refPricing,
		IncludeCacheInPrompt: *includeCache,
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
	ds, err := usageapi.Load(cfg, func(msg string) { fmt.Fprintln(stderr, "경고:", msg) })
	if err != nil {
		return err
	}

	srv := &http.Server{
		Addr:              *addr,
		Handler:           usageapi.NewFixedServer(ds),
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
	fmt.Fprintf(stderr, "고정 응답 모드: 기록 %d건, 구간 %s ~ %s, http://%s/api/v1/usage/health\n",
		len(ds.Records), ds.Start.Format(time.RFC3339), ds.End.Format(time.RFC3339), ln.Addr())
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
