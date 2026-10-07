package attribution

import "sort"

// AllocationTokenCount는 결과별 토큰 수(토큰 계산 API로 센 값) 비율로 병렬·배치 구간 증가분을
// 나누는 방식 이름이다(정확도 개선 방안 B).
const AllocationTokenCount = "token-count"

const (
	noteAllocated     = "병렬/배치 구간 — 토큰 계산 API로 센 결과별 토큰 수 비율로 구간 입력 증가분을 배분(구간 합계 보존)"
	noteCountMissing  = " | 구간 일부 도구의 결과별 토큰 수가 없어 배분하지 않음"
	noteNoSegDelta    = " | 구간 앞뒤 model.call에 토큰 속성이 없어 배분하지 않음"
	noteZeroCountSum  = " | 결과별 토큰 수 합이 0이라 배분하지 않음"
	noteAllocNegDelta = " | 구간 증가분이 음수(컨텍스트 압축 등)라 0으로 배분"
)

type segKey struct{ trace, run, closing string }

// AllocateByCounts는 병렬·배치 구간마다 측정된 입력 증가분(SegmentDelta)을, 구간 안 도구 결과별
// 토큰 수(counts: tool_call_id → 토큰 수) 비율로 나눠 ApproxTokens에 채운다.
//
//	도구 i 귀속 토큰 = Δ × c_i ÷ Σc   (최대 잔여 방식으로 반올림해 합이 항상 Δ와 같다)
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
		shares := largestRemainder(first.SegmentDelta, idx, out, sum)
		for j, i := range idx {
			out[i].ApproxTokens = shares[j]
			out[i].HasTokens = true
			out[i].AllocationMethod = AllocationTokenCount
			out[i].Note = noteAllocated
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
