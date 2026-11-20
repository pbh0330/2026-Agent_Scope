package attribution

import "sort"

// AllocationTokenCount는 결과별 토큰 수(토큰 계산 API로 센 값)를 근거로 병렬·배치 구간 증가분을
// 나누는 방식 이름이다.
const AllocationTokenCount = "token-count"

const (
	noteAllocated     = "병렬/배치 구간 — 결과마다 고정분 k를 먼저 주고 나머지를 결과별 토큰 수 비율로 배분(구간 합계 보존)"
	noteAllocNoK      = " | 고정분 k를 정할 근거가 없거나 구간 증가분이 결과 수×k보다 작아 토큰 수 비율로만 배분"
	noteCountMissing  = " | 구간 일부 도구의 결과별 토큰 수가 없어 배분하지 않음"
	noteNoSegDelta    = " | 구간 앞뒤 model.call에 토큰 속성이 없어 배분하지 않음"
	noteZeroCountSum  = " | 결과별 토큰 수 합이 0이라 배분하지 않음"
	noteAllocNegDelta = " | 구간 증가분이 음수(컨텍스트 압축 등)라 0으로 배분"
)

// 고정분 추정에 쓰는 순차 표본 조건. 토큰 계산 API는 기준 요청(빈 결과)을 빼서 세므로
// 아주 작은 결과는 0 근처로 잘려(11.05 exec "hello": 0) 표본에서 뺀다.
const overheadMinCounted = 50

// DefaultResultOverhead는 데이터 안에 순차 표본이 없을 때 쓰는 모델별 결과당 고정분이다.
// Anthropic API 직접 연결 실측값(11.05, OpenClaw 2026.9.6). 표에 없는 모델은 0(토큰 수 비율로만 배분).
var DefaultResultOverhead = map[string]int64{
	"claude-haiku-5-5": 26,
}

// Overhead는 모델 하나의 결과당 고정분 k와 그 근거다.
type Overhead struct {
	Tokens  int64
	Samples int    // 추정에 쓴 순차 구간 수(0이면 기본값 또는 없음)
	Source  string // "sequential-median" | "default" | "none"
}

// EstimateOverheads는 순차 구간마다 (실측 증가분 − 결과별 토큰 수)를 모아 모델별 중앙값을 낸다.
// 결과마다 붙는 고정 부분(도구 호출 ID·결과 태그 등)의 크기이며, 병렬·배치 배분에서 결과마다 먼저 준다.
// 표본: 순차, 토큰 있음, 음수로 자르지 않음, 결과별 토큰 수 ≥ overheadMinCounted, 차이 ≥ 0.
func EstimateOverheads(results []Result, counts map[string]int64) map[string]Overhead {
	samples := map[string][]int64{}
	for _, r := range results {
		if r.Pattern != Sequential || !r.HasTokens || r.NegativeDelta || r.ToolCallID == "" {
			continue
		}
		c, ok := counts[r.ToolCallID]
		if !ok || c < overheadMinCounted {
			continue
		}
		if d := r.ApproxTokens - c; d >= 0 {
			samples[r.Model] = append(samples[r.Model], d)
		}
	}
	out := map[string]Overhead{}
	for m, xs := range samples {
		sort.Slice(xs, func(i, j int) bool { return xs[i] < xs[j] })
		mid := xs[len(xs)/2]
		if len(xs)%2 == 0 {
			mid = (xs[len(xs)/2-1] + xs[len(xs)/2]) / 2
		}
		out[m] = Overhead{Tokens: mid, Samples: len(xs), Source: "sequential-median"}
	}
	return out
}

func overheadFor(model string, est map[string]Overhead) Overhead {
	if o, ok := est[model]; ok {
		return o
	}
	if k, ok := DefaultResultOverhead[model]; ok {
		return Overhead{Tokens: k, Source: "default"}
	}
	return Overhead{Source: "none"}
}

type segKey struct{ trace, run, closing string }

// AllocateByCounts는 병렬·배치 구간마다 측정된 입력 증가분(SegmentDelta)을 결과별 토큰 수
// (counts: tool_call_id → 토큰 수)를 근거로 나눠 ApproxTokens에 채운다.
//
//	k = 결과당 고정분(EstimateOverheads: 같은 데이터 순차 구간의 중앙값, 없으면 DefaultResultOverhead)
//	도구 i 귀속 토큰 = k + (Δ − n·k) × c_i ÷ Σc   (최대 잔여 방식으로 반올림해 합이 항상 Δ와 같다)
//
// k가 0이거나 Δ < n·k면 k 없이 Δ × c_i ÷ Σc로 나눈다(10.29까지의 방식).
// 고정분까지 크기 비율로 나누면 작은 결과가 늘 적게 잡혀서(11.05 Haiku 5.5: −4.9%) k를 먼저 준다.
//
// 구간의 도구 하나라도 토큰 수가 없거나, 구간 증가분을 계산할 수 없거나, Σc가 0이면 그 구간은
// 배분하지 않고 그대로 둔다(근거 없이 나누지 않음). 순차·귀속 불가 결과는 바꾸지 않는다.
// 입력 슬라이스는 수정하지 않고 새 슬라이스를 돌려준다.
func AllocateByCounts(results []Result, counts map[string]int64) []Result {
	out := make([]Result, len(results))
	copy(out, results)
	if len(counts) == 0 {
		return out
	}
	est := EstimateOverheads(out, counts)
	groups := map[segKey][]int{}
	var order []segKey
	for i, r := range out {
		if r.Pattern != Parallel && r.Pattern != Batch {
			continue
		}
		if c, ok := counts[r.ToolCallID]; ok && r.ToolCallID != "" && c >= 0 {
			out[i].CountedTokens, out[i].HasCount = c, true
		}
		k := segKey{r.TraceID, r.RunID, r.ClosingModelSpanID}
		if _, seen := groups[k]; !seen {
			order = append(order, k)
		}
		groups[k] = append(groups[k], i)
	}
	for _, k := range order {
		idx := groups[k]
		first := out[idx[0]]
		if !first.HasSegmentDelta {
			appendNote(out, idx, noteNoSegDelta)
			continue
		}
		var sum int64
		complete := true
		for _, i := range idx {
			if !out[i].HasCount {
				complete = false
				break
			}
			sum += out[i].CountedTokens
		}
		if !complete {
			appendNote(out, idx, noteCountMissing)
			continue
		}
		if sum <= 0 {
			appendNote(out, idx, noteZeroCountSum)
			continue
		}
		oh := overheadFor(first.Model, est)
		n := int64(len(idx))
		base, note := oh.Tokens, noteAllocated
		if base <= 0 || first.SegmentDelta < n*base {
			base, note = 0, noteAllocated+noteAllocNoK
		}
		shares := largestRemainder(first.SegmentDelta-n*base, idx, out, sum)
		residual := first.SegmentDelta - sum - n*oh.Tokens
		for j, i := range idx {
			out[i].ApproxTokens = base + shares[j]
			out[i].HasTokens = true
			out[i].AllocationMethod = AllocationTokenCount
			out[i].AllocOverhead = base
			out[i].SegmentResidual, out[i].HasResidual = residual, true
			out[i].Note = note
			if out[i].SegmentNegative {
				out[i].NegativeDelta = true
				out[i].Note += noteAllocNegDelta
			}
		}
	}
	return out
}

func appendNote(out []Result, idx []int, s string) {
	for _, i := range idx {
		out[i].Note += s
	}
}

// largestRemainder는 total을 weights 비율로 나눈 정수 몫을 돌려준다(합 = total).
func largestRemainder(total int64, idx []int, out []Result, sum int64) []int64 {
	type frac struct {
		pos int
		rem int64 // total*c mod sum (0 ≤ rem < sum)
	}
	shares := make([]int64, len(idx))
	fr := make([]frac, len(idx))
	var given int64
	for j, i := range idx {
		num := total * out[i].CountedTokens
		shares[j] = num / sum
		given += shares[j]
		fr[j] = frac{pos: j, rem: num % sum}
	}
	sort.SliceStable(fr, func(a, b int) bool { return fr[a].rem > fr[b].rem })
	for j := int64(0); j < total-given; j++ {
		shares[fr[j].pos]++
	}
	return shares
}
