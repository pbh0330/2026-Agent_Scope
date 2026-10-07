package tokenattributionconnector

import (
	"errors"
	"time"

	"github.com/pbh0330/2026-Agent_Scope/token-collector/collector/attribution"
)

// Config는 tokenattribution 커넥터 설정이다. 모든 항목은 생략 가능하다.
//
//	connectors:
//	  tokenattribution:
//	    metrics_flush_interval: 5s
//	    grace: 2s
//	    run_idle_timeout: 10m
//	    openclaw_config_path: C:\Users\me\.openclaw\openclaw.json
type Config struct {
	// MetricsFlushInterval: 확정된 결과를 누적 메트릭으로 내보내는 주기.
	MetricsFlushInterval time.Duration `mapstructure:"metrics_flush_interval"`
	// Grace: 구간을 닫는 다음 model.call(또는 run 종료) 도착 후, 늦게 오는 도구 스팬을 기다리는 시간.
	Grace time.Duration `mapstructure:"grace"`
	// RunIdleTimeout: 새 스팬 없이 이 시간이 지나면 run을 끝난 것으로 보고 정리한다.
	RunIdleTimeout time.Duration `mapstructure:"run_idle_timeout"`
	// MaxRuns: 메모리에 동시에 들고 있는 run 수 상한.
	MaxRuns int `mapstructure:"max_runs"`
	// IncludeCacheInPrompt: 캐시 토큰을 input_tokens와 따로 보고하는 프로바이더라면 true.
	IncludeCacheInPrompt bool `mapstructure:"include_cache_in_prompt"`

	// OpenClawConfigPath: 지정하면 openclaw.json의 models.providers.*.models[].cost 단가를 읽는다.
	OpenClawConfigPath string `mapstructure:"openclaw_config_path"`
	// Pricing: 모델별 단가(1M 토큰당 USD)를 직접 지정. openclaw.json 값보다 우선한다.
	Pricing map[string]attribution.Rate `mapstructure:"pricing"`
	// UseReferencePricing: 단가가 없거나 전부 0인 모델에 Anthropic 공식 정가(참고용)를 쓸지.
	UseReferencePricing bool `mapstructure:"use_reference_pricing"`

	Exemplars ExemplarsConfig `mapstructure:"exemplars"`

	// prevent unkeyed literal initialization
	_ struct{}
}

// ExemplarsConfig: 메트릭 데이터포인트에 해당 도구 스팬의 traceId/spanId를 exemplar로 붙인다.
// Grafana에서 메트릭 → 트레이스로 바로 넘어갈 수 있게 해준다.
type ExemplarsConfig struct {
	Enabled         bool `mapstructure:"enabled"`
	MaxPerDataPoint int  `mapstructure:"max_per_data_point"`

	_ struct{}
}

func createDefaultConfig() *Config {
	return &Config{
		MetricsFlushInterval: 5 * time.Second,
		Grace:                2 * time.Second,
		RunIdleTimeout:       10 * time.Minute,
		MaxRuns:              10000,
		UseReferencePricing:  true,
		Exemplars:            ExemplarsConfig{Enabled: true, MaxPerDataPoint: 5},
	}
}

// Validate는 설정값을 검사한다.
func (c *Config) Validate() error {
	var errs []error
	if c.MetricsFlushInterval <= 0 {
		errs = append(errs, errors.New("metrics_flush_interval must be > 0"))
	}
	if c.Grace < 0 {
		errs = append(errs, errors.New("grace must be >= 0"))
	}
	if c.RunIdleTimeout <= 0 {
		errs = append(errs, errors.New("run_idle_timeout must be > 0"))
	}
	if c.MaxRuns <= 0 {
		errs = append(errs, errors.New("max_runs must be > 0"))
	}
	if c.Exemplars.MaxPerDataPoint < 0 {
		errs = append(errs, errors.New("exemplars.max_per_data_point must be >= 0"))
	}
	return errors.Join(errs...)
}
