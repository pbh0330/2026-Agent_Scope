package tokenattributionconnector

import (
	"context"
	"sync"
	"time"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/pdata/pcommon"
	"go.opentelemetry.io/collector/pdata/ptrace"
	"go.uber.org/zap"

	"github.com/pbh0330/2026-Agent_Scope/token-collector/collector/attribution"
)

type tokenConnector struct {
	logger  *zap.Logger
	cfg     *Config
	next    consumer.Metrics
	tracker *attribution.Tracker
	pricing attribution.Pricing

	mu  sync.Mutex // agg 보호
	agg *aggregator

	now      func() time.Time
	done     chan struct{}
	wg       sync.WaitGroup
	stopOnce sync.Once
}

func newConnector(logger *zap.Logger, cfg *Config, next consumer.Metrics) (*tokenConnector, error) {
	pricing := attribution.Pricing{Models: map[string]attribution.Rate{}}
	if cfg.OpenClawConfigPath != "" {
		models, err := attribution.LoadPricingFromOpenClawConfig(cfg.OpenClawConfigPath)
		if err != nil {
			// 단가를 못 읽어도 토큰 귀속은 계속 동작해야 하므로 경고만 남긴다.
			logger.Warn("openclaw.json 단가 로딩 실패 — 설정 단가 없이 진행", zap.Error(err))
		} else {
			for m, r := range models {
				pricing.Models[m] = r
				if r.IsZero() {
					logger.Info("openclaw.json 단가가 전부 0인 모델 — 참고용 정가로 대체될 수 있음", zap.String("model", m))
				}
			}
		}
	}
	for m, r := range cfg.Pricing {
		pricing.Models[m] = r
	}
	if cfg.UseReferencePricing {
		pricing.Reference = attribution.AnthropicListPricingReference
	}

	maxEx := 0
	if cfg.Exemplars.Enabled {
		maxEx = cfg.Exemplars.MaxPerDataPoint
	}
	now := time.Now
	return &tokenConnector{
		logger: logger,
		cfg:    cfg,
		next:   next,
		tracker: attribution.NewTracker(attribution.TrackerConfig{
			Grace:          cfg.Grace,
			RunIdleTimeout: cfg.RunIdleTimeout,
			MaxRuns:        cfg.MaxRuns,
			Options:        attribution.Options{IncludeCacheInPrompt: cfg.IncludeCacheInPrompt},
		}),
		pricing: pricing,
		agg:     newAggregator(now(), maxEx),
		now:     now,
		done:    make(chan struct{}),
	}, nil
}

// Capabilities: 입력 트레이스를 수정하지 않는다.
func (*tokenConnector) Capabilities() consumer.Capabilities {
	return consumer.Capabilities{MutatesData: false}
}

// Start는 주기적으로 확정 결과를 메트릭으로 내보내는 고루틴을 띄운다.
func (c *tokenConnector) Start(_ context.Context, _ component.Host) error {
	c.wg.Add(1)
	go func() {
		defer c.wg.Done()
		t := time.NewTicker(c.cfg.MetricsFlushInterval)
		defer t.Stop()
		for {
			select {
			case <-c.done:
				return
			case <-t.C:
				c.flush(context.Background())
			}
		}
	}()
	return nil
}

// Shutdown은 고루틴을 멈추고 마지막으로 한 번 내보낸다.
func (c *tokenConnector) Shutdown(ctx context.Context) error {
	c.stopOnce.Do(func() {
		close(c.done)
		c.wg.Wait()
		c.flush(ctx)
	})
	return nil
}

// ConsumeTraces는 관련 스팬(model.call / tool.execution / openclaw.run)만 골라 Tracker에 넣는다.
func (c *tokenConnector) ConsumeTraces(_ context.Context, td ptrace.Traces) error {
	now := c.now()
	rss := td.ResourceSpans()
	for i := 0; i < rss.Len(); i++ {
		sss := rss.At(i).ScopeSpans()
		for j := 0; j < sss.Len(); j++ {
			spans := sss.At(j).Spans()
			for k := 0; k < spans.Len(); k++ {
				sp := spans.At(k)
				switch sp.Name() {
				case attribution.SpanModelCall, attribution.SpanToolExec, attribution.SpanRun:
					c.tracker.Add(toSpan(sp), now)
				}
			}
		}
	}
	return nil
}

func tsTime(ts pcommon.Timestamp) time.Time {
	if ts == 0 {
		return time.Time{}
	}
	return ts.AsTime()
}

func toSpan(sp ptrace.Span) attribution.Span {
	attrs := make(map[string]any, sp.Attributes().Len())
	sp.Attributes().Range(func(k string, v pcommon.Value) bool {
		switch v.Type() {
		case pcommon.ValueTypeInt:
			attrs[k] = v.Int()
		case pcommon.ValueTypeDouble:
			attrs[k] = v.Double()
		case pcommon.ValueTypeBool:
			attrs[k] = v.Bool()
		case pcommon.ValueTypeStr:
			attrs[k] = v.Str()
		}
		return true
	})
	parent := ""
	if !sp.ParentSpanID().IsEmpty() {
		parent = sp.ParentSpanID().String()
	}
	return attribution.Span{
		TraceID:  sp.TraceID().String(),
		ParentID: parent,
		SpanID:   sp.SpanID().String(),
		Name:     sp.Name(),
		Start:    tsTime(sp.StartTimestamp()),
		End:      tsTime(sp.EndTimestamp()),
		Attrs:    attrs,
	}
}

// flush는 확정된 결과를 누적하고, 누적 메트릭 전체를 다음 컨슈머(보통 prometheus 익스포터)로 보낸다.
func (c *tokenConnector) flush(ctx context.Context) {
	now := c.now()
	results := c.tracker.Flush(now)

	c.mu.Lock()
	for _, r := range results {
		c.agg.record(r, c.pricing, now)
		c.logger.Debug("tool attribution",
			zap.String("tool", r.ToolName), zap.String("pattern", string(r.Pattern)),
			zap.Int64("tokens", r.ApproxTokens), zap.Bool("has_tokens", r.HasTokens),
			zap.String("trace_id", r.TraceID), zap.String("note", r.Note))
	}
	md := c.agg.build(now, c.tracker.PendingRuns(), c.tracker.DroppedSpans())
	c.mu.Unlock()

	if err := c.next.ConsumeMetrics(ctx, md); err != nil {
		c.logger.Error("tokenattribution: 메트릭 전달 실패", zap.Error(err))
	}
}
