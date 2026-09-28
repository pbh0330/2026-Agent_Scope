// Package tokenattributionconnector는 OpenClaw 트레이스(openclaw.model.call /
// openclaw.tool.execution 스팬)를 받아 도구별 토큰·비용 귀속 메트릭을 만드는
// OpenTelemetry Collector 커넥터(traces → metrics)다.
package tokenattributionconnector

import (
	"context"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/connector"
	"go.opentelemetry.io/collector/consumer"

	"github.com/pbh0330/2026-Agent_Scope/token-collector/collector/tokenattributionconnector/internal/metadata"
)

// NewFactory는 커넥터 팩토리를 만든다(OCB 빌드 설정에서 이 함수를 등록한다).
func NewFactory() connector.Factory {
	return connector.NewFactory(
		metadata.Type,
		func() component.Config { return createDefaultConfig() },
		connector.WithTracesToMetrics(createTracesToMetrics, metadata.TracesToMetricsStability),
	)
}

func createTracesToMetrics(_ context.Context, set connector.Settings, cfg component.Config, next consumer.Metrics) (connector.Traces, error) {
	return newConnector(set.Logger, cfg.(*Config), next)
}
