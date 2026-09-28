"""
개발계획서 2.2절 "단계별 로직"의 1~5단계를 구현한 traceId 기반 귀속(attribution) 엔진.

    1) 스팬 수집        -> group_runs()
    2) 패턴 판별        -> classify_segments()   (순차 / 병렬 / 배치)
    3) 귀속 계산        -> classify_segments()   (순차 구간 diff 근사)
    4) 연결 방식        -> (해당 없음: exemplar 대신, 이 로그는 model.call 스팬 자체에
                            input/output 토큰이 이미 속성으로 박혀 있어서 메트릭 조인이
                            애초에 불필요함 — otel_log_parser.py 조사 결과 참고)
    5) 비용 환산        -> apply_pricing()

중요한 설계 결정 (계획서 원문보다 한 단계 더 정밀화한 부분):
    순차 구간의 "직전 대비 증분"을 그대로 도구 기여분으로 쓰면 안 됨.
    다음 model.call의 입력 토큰에는 (a) 도구 실행 결과뿐 아니라
    (b) 직전 model.call이 만들어낸 어시스턴트 응답(출력 토큰)도 히스토리로 다시
    얹혀서 들어가기 때문. 그래서:

        tool_delta_tokens = next_call.input_tokens
                             - prev_call.input_tokens
                             - prev_call.output_tokens

    로 계산해서 "직전 모델 자신의 응답이 재편입된 몫"을 빼고 순수 도구 기여분만 근사함.
    이 보정을 안 하면 도구 기여분이 항상 과대추정됨.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from otel_log_parser import Span, parse_spans

RUN_SCOPED_NAMES = {"openclaw.model.call", "openclaw.tool.execution"}


# ---------------------------------------------------------------------------
# 1) 스팬 수집: model.call / tool.execution 스팬을 부모(=openclaw.run) 단위로 묶기
# ---------------------------------------------------------------------------

def group_runs(spans: list[Span]) -> dict[str, list[Span]]:
    """parent_id(=하나의 openclaw.run) 기준으로 model.call/tool.execution 스팬을 묶는다."""
    runs: dict[str, list[Span]] = {}
    for s in spans:
        if s.name in RUN_SCOPED_NAMES:
            runs.setdefault(s.parent_id, []).append(s)
    for group in runs.values():
        group.sort(key=lambda s: s.start or datetime.min)
    return runs


# ---------------------------------------------------------------------------
# 2)+3) 패턴 판별 + 귀속 계산
# ---------------------------------------------------------------------------

@dataclass
class ToolAttribution:
    trace_id: str
    run_parent_id: str
    tool_name: str
    tool_span_id: str
    pattern: str                     # "sequential" | "parallel" | "batch" | "unattributed"
    duration_ms: Optional[float]
    approx_tokens: Optional[int]     # None when pattern != sequential
    note: str = ""


def _overlaps(a: Span, b: Span) -> bool:
    if a.start is None or a.end is None or b.start is None or b.end is None:
        return False
    return a.start < b.end and b.start < a.end


def classify_segments(runs: dict[str, list[Span]]) -> list[ToolAttribution]:
    results: list[ToolAttribution] = []

    for parent_id, group in runs.items():
        model_calls = [s for s in group if s.name == "openclaw.model.call"]
        tool_execs = [s for s in group if s.name == "openclaw.tool.execution"]
        if not tool_execs:
            continue
        trace_id = group[0].trace_id

        # --- 병렬 판정: 같은 run 안에서 tool.execution 스팬끼리 시간이 겹치는가 ---
        parallel_ids: set[str] = set()
        for i in range(len(tool_execs)):
            for j in range(i + 1, len(tool_execs)):
                if _overlaps(tool_execs[i], tool_execs[j]):
                    parallel_ids.add(tool_execs[i].span_id)
                    parallel_ids.add(tool_execs[j].span_id)

        # --- 순차/배치 판정: 연속된 두 model.call 사이에 tool.execution이 몇 개인가 ---
        # model.call이 하나도 없거나 하나뿐이면(=도구 실행 후 모델을 다시 안 불렀거나,
        # 애초에 비교할 짝이 없으면) 귀속 불가로 표시.
        for k in range(len(model_calls)):
            prev = model_calls[k]
            nxt = model_calls[k + 1] if k + 1 < len(model_calls) else None

            window_start = prev.end
            window_end = nxt.start if nxt else None

            between = [
                t for t in tool_execs
                if window_start is not None and t.start is not None
                and t.start >= window_start
                and (window_end is None or t.start <= window_end)
            ]
            if not between:
                continue

            if any(t.span_id in parallel_ids for t in between):
                pattern = "parallel"
            elif len(between) == 1:
                pattern = "sequential"
            else:
                pattern = "batch"

            if pattern == "sequential" and nxt is not None:
                prev_in = prev.attrs.get("openclaw.model_call.usage.input_tokens")
                prev_out = prev.attrs.get("openclaw.model_call.usage.output_tokens")
                next_in = nxt.attrs.get("openclaw.model_call.usage.input_tokens")
                tool = between[0]
                tool_name = tool.attrs.get("openclaw.toolName", "unknown")

                if None in (prev_in, prev_out, next_in):
                    results.append(ToolAttribution(
                        trace_id=trace_id, run_parent_id=parent_id,
                        tool_name=tool_name, tool_span_id=tool.span_id,
                        pattern="sequential", duration_ms=tool.duration_ms,
                        approx_tokens=None,
                        note="model.call 스팬에 토큰 속성 누락 — 귀속 불가",
                    ))
                    continue

                delta = next_in - prev_in - prev_out
                note = ""
                if delta < 0:
                    note = "delta<0 (컨텍스트 압축/요약 등으로 오히려 줄어든 구간 — 근사치 신뢰 낮음)"
                results.append(ToolAttribution(
                    trace_id=trace_id, run_parent_id=parent_id,
                    tool_name=tool_name, tool_span_id=tool.span_id,
                    pattern="sequential", duration_ms=tool.duration_ms,
                    approx_tokens=max(delta, 0), note=note,
                ))
            else:
                # 병렬/배치: 도구별 정밀 토큰 귀속은 포기, 대리 지표만 기록
                for tool in between:
                    tool_name = tool.attrs.get("openclaw.toolName", "unknown")
                    results.append(ToolAttribution(
                        trace_id=trace_id, run_parent_id=parent_id,
                        tool_name=tool_name, tool_span_id=tool.span_id,
                        pattern=pattern, duration_ms=tool.duration_ms,
                        approx_tokens=None,
                        note="병렬/배치 구간 — duration_ms만 대리 지표로 기록, 토큰 귀속 안 함",
                    ))

    return results


# ---------------------------------------------------------------------------
# 5) 비용 환산
# ---------------------------------------------------------------------------

# 자리표시자(fallback) — 실제 openclaw.json을 못 구했을 때만 쓰임.
# load_pricing_from_config()가 성공하면 이 값은 무시됨.
# 단위: USD / 1M tokens
PRICING_PLACEHOLDER: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00, "cacheRead": 0.0, "cacheWrite": 0.0},
}


def load_pricing_from_config(openclaw_json_path: str) -> dict[str, dict[str, float]]:
    """openclaw.json에서 실제 단가표를 읽어온다.

    OpenClaw 공식 문서(Token use and costs) 기준 스키마:
        {
          "models": {
            "providers": {
              "<provider-id>": {                 예: "school-gateway"
                "models": [
                  {
                    "id": "<model-id>",           예: "claude-haiku-4-5-20251001"
                    "cost": {
                      "input":      <USD / 1M tokens>,
                      "output":     <USD / 1M tokens>,
                      "cacheRead":  <USD / 1M tokens>,   # 없으면 0
                      "cacheWrite": <USD / 1M tokens>    # 없으면 0
                    }
                  },
                  ...
                ]
              }
            }
          }
        }

    반환값 키는 model id, provider 구분 없이 평평하게(flat) 모음 — 같은 모델 id가
    provider 두 개에서 다른 단가로 나오면 나중에 읽은 provider 값으로 덮어써짐
    (이런 경우가 있으면 print로 경고).
    """
    import json as _json

    with open(openclaw_json_path, encoding="utf-8") as f:
        config = _json.load(f)

    providers = (
        config.get("models", {})
        .get("providers", {})
    )
    if not providers:
        raise ValueError(
            f"'{openclaw_json_path}'에서 models.providers를 못 찾음 — "
            f"파일이 openclaw.json 전체가 맞는지, 아니면 그 일부 스니펫만 있는 건지 확인 필요."
        )

    pricing: dict[str, dict[str, float]] = {}
    for provider_id, provider_cfg in providers.items():
        for model_cfg in provider_cfg.get("models", []):
            model_id = model_cfg.get("id")
            cost = model_cfg.get("cost")
            if not model_id or not cost:
                continue
            if model_id in pricing and pricing[model_id] != cost:
                print(f"[경고] 모델 '{model_id}' 단가가 provider마다 달라서 "
                      f"'{provider_id}' 값으로 덮어씀: {cost}")
            pricing[model_id] = {
                "input": float(cost.get("input", 0.0)),
                "output": float(cost.get("output", 0.0)),
                "cacheRead": float(cost.get("cacheRead", 0.0)),
                "cacheWrite": float(cost.get("cacheWrite", 0.0)),
            }

    if not pricing:
        raise ValueError(f"'{openclaw_json_path}'에 단가(cost)가 붙은 모델이 하나도 없음.")

    return pricing


def apply_pricing(
    model_name: str,
    input_tokens: int,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    pricing_table: Optional[dict[str, dict[str, float]]] = None,
) -> Optional[float]:
    table = pricing_table if pricing_table is not None else PRICING_PLACEHOLDER
    rate = table.get(model_name)
    if rate is None:
        return None
    return (
        (input_tokens / 1_000_000) * rate["input"]
        + (output_tokens / 1_000_000) * rate["output"]
        + (cache_read_tokens / 1_000_000) * rate.get("cacheRead", 0.0)
        + (cache_write_tokens / 1_000_000) * rate.get("cacheWrite", 0.0)
    )


# ---------------------------------------------------------------------------
# 실행부
# ---------------------------------------------------------------------------

def run(path: str) -> list[ToolAttribution]:
    spans = parse_spans(path)
    runs = group_runs(spans)
    return classify_segments(runs)


if __name__ == "__main__":
    import sys
    import json

    # 사용법: python attribution.py <otel-debug-log.txt> [openclaw.json]
    #   openclaw.json 경로를 주면 거기서 실제 단가표를 읽어오고,
    #   안 주거나 로딩 실패하면 PRICING_PLACEHOLDER로 폴백(경고 출력).
    path = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/.openclaw/otel-debug-log.txt"
    config_path = sys.argv[2] if len(sys.argv) > 2 else None

    pricing_table = PRICING_PLACEHOLDER
    pricing_source = "PRICING_PLACEHOLDER (자리표시자 — 실제 금액 아님)"
    if config_path:
        try:
            pricing_table = load_pricing_from_config(config_path)
            pricing_source = f"'{config_path}'에서 로드한 실제 단가"
        except (OSError, ValueError, KeyError) as e:
            print(f"[경고] openclaw.json 단가 로딩 실패 ({e}) — PRICING_PLACEHOLDER로 폴백")

    attributions = run(path)

    print(f"단가표 출처: {pricing_source}")
    print(f"귀속 결과 {len(attributions)}건\n")
    for a in attributions:
        cost_str = ""
        if a.approx_tokens is not None:
            cost = apply_pricing(
                "claude-haiku-4-5-20251001", a.approx_tokens, pricing_table=pricing_table
            )
            if cost is not None:
                cost_str = f"  (~${cost:.6f})"
        print(
            f"[{a.pattern:10s}] {a.tool_name:35s} "
            f"duration={a.duration_ms or 0:8.2f}ms "
            f"tokens={a.approx_tokens if a.approx_tokens is not None else '-':>6}"
            f"{cost_str}"
        )
        if a.note:
            print(f"             note: {a.note}")

    out_path = path.rsplit("/", 1)[0] + "/attribution_report.json" if "/" in path else "attribution_report.json"
    with open("attribution_report.json", "w", encoding="utf-8") as f:
        json.dump([a.__dict__ for a in attributions], f, ensure_ascii=False, indent=2, default=str)
    print("\n→ attribution_report.json 저장 완료")
