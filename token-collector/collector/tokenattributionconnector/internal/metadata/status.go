// Package metadata는 커넥터 타입 이름과 안정성 단계를 정의한다.
// (contrib 컴포넌트는 mdatagen으로 생성하지만, 이 커넥터는 단순해서 직접 작성)
package metadata

import "go.opentelemetry.io/collector/component"

var (
	Type      = component.MustNewType("tokenattribution")
	ScopeName = "github.com/pbh0330/2026-Agent_Scope/token-collector/collector/tokenattributionconnector"
)

const TracesToMetricsStability = component.StabilityLevelDevelopment
