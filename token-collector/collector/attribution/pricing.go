package attribution

import (
	"encoding/json"
	"fmt"
	"os"
)

// Rate는 1M 토큰당 USD 단가다(openclaw.json models.providers.*.models[].cost와 같은 단위).
type Rate struct {
	Input      float64 `json:"input" mapstructure:"input"`
	Output     float64 `json:"output" mapstructure:"output"`
	CacheRead  float64 `json:"cacheRead" mapstructure:"cache_read"`
	CacheWrite float64 `json:"cacheWrite" mapstructure:"cache_write"`
}

// IsZero는 네 단가가 전부 0인지 본다(학교 게이트웨이처럼 종량제 과금을 안 하는 경우).
func (r Rate) IsZero() bool {
	return r.Input == 0 && r.Output == 0 && r.CacheRead == 0 && r.CacheWrite == 0
}

// 가격 출처 라벨. 대시보드에서 "실제 청구 단가"와 "참고용 정가"를 구분하는 데 쓴다.
const (
	PriceSourceConfig    = "config"
	PriceSourceReference = "reference_list_price"
)

// AnthropicListPricingReference는 Anthropic 공식 API 정가(참고용, 실제 청구액 아님).
// 2026-09-28 확인, https://platform.claude.com/docs/en/about-claude/pricing
// cacheWrite는 1시간 TTL 기준(보수적으로 더 비싼 쪽).
var AnthropicListPricingReference = map[string]Rate{
	"claude-haiku-4-5-20251001": {Input: 1.00, Output: 5.00, CacheRead: 0.10, CacheWrite: 2.00},
}

// Pricing은 모델별 단가표다. Models(설정 단가)가 없거나 전부 0이면 Reference로 대체한다.
type Pricing struct {
	Models    map[string]Rate
	Reference map[string]Rate
}

// InputCost는 도구에 귀속된 토큰(=다음 model.call의 입력으로 들어간 토큰)의 비용이다.
func (p Pricing) InputCost(model string, tokens int64) (usd float64, source string, ok bool) {
	rate, src, ok := p.rate(model)
	if !ok {
		return 0, "", false
	}
	return float64(tokens) / 1e6 * rate.Input, src, true
}

func (p Pricing) rate(model string) (Rate, string, bool) {
	if r, ok := p.Models[model]; ok && !r.IsZero() {
		return r, PriceSourceConfig, true
	}
	if r, ok := p.Reference[model]; ok {
		return r, PriceSourceReference, true
	}
	return Rate{}, "", false
}

// LoadPricingFromOpenClawConfig는 openclaw.json의 models.providers.<id>.models[].cost를 읽는다.
// 파이썬 load_pricing_from_config()와 같은 규칙: provider 구분 없이 모델 id로 평평하게 모은다.
func LoadPricingFromOpenClawConfig(path string) (map[string]Rate, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var cfg struct {
		Models struct {
			Providers map[string]struct {
				Models []struct {
					ID   string `json:"id"`
					Cost *Rate  `json:"cost"`
				} `json:"models"`
			} `json:"providers"`
		} `json:"models"`
	}
	if err := json.Unmarshal(b, &cfg); err != nil {
		return nil, fmt.Errorf("%s 파싱 실패: %w", path, err)
	}
	out := map[string]Rate{}
	for _, prov := range cfg.Models.Providers {
		for _, m := range prov.Models {
			if m.ID == "" || m.Cost == nil {
				continue
			}
			out[m.ID] = *m.Cost
		}
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("%s에 cost가 붙은 모델이 없음", path)
	}
	return out, nil
}
