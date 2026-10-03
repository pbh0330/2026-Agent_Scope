"""
3주차 "정확도 검증"용 감사(audit) 스크립트.

배경: 순차/병렬/배치 "패턴 판별"은 사람이 직접 검증 가능한 근거(ground truth)가 있음 —
tool.execution 스팬들의 실제 시작/종료 시각이 겹치는지 여부는 objective한 사실이라서,
classify_segments()가 내린 판정이 맞는지 사람이 원본 타임스탬프를 보고 눈으로 확인할 수 있음.

반면 "토큰 귀속 값"(순차 구간의 diff 근사치)은 그 자체가 근사 공식으로 만든 값이라서
독립적인 정답(ground truth)이 없음 — 도구별로 실제 몇 토큰이 들어갔는지 알려주는 별도
계측이 OpenClaw에 없기 때문(개발계획서/1주차 milestone 0에서 이미 확인함).

그래서 이 스크립트는 두 가지를 함:
  1) 패턴 판별 결과 옆에 "근거"(원본 스팬 시작/종료 시각, 겹침 여부)를 나란히 출력해서
     classify_segments()의 판정을 사람이 감사(audit)할 수 있게 함.
  2) 구조적으로 의심스러운 부분(모델 호출 없이 끝난 run, 타임스탬프 누락, delta<0)을
     별도 섹션으로 모아서 "이 근사치를 얼마나 믿어도 되는지" 한눈에 보이게 함.

사용법: python3 audit_attribution.py <otel-debug-log.txt>
"""

from __future__ import annotations

import sys

from otel_log_parser import parse_spans
from attribution import group_runs, classify_segments, RUN_SCOPED_NAMES


def fmt_ts(dt):
    return dt.strftime("%H:%M:%S.%f")[:-3] if dt else "(없음)"


def main(path: str) -> None:
    spans = parse_spans(path)
    runs = group_runs(spans)
    results = classify_segments(runs)

    print(f"=== 원본 로그: {path} ===")
    print(f"파싱된 전체 스팬 수: {len(spans)}")
    run_scoped = [s for s in spans if s.name in RUN_SCOPED_NAMES]
    print(f"  - openclaw.model.call: {sum(1 for s in run_scoped if s.name=='openclaw.model.call')}건")
    print(f"  - openclaw.tool.execution: {sum(1 for s in run_scoped if s.name=='openclaw.tool.execution')}건")
    print(f"run(=openclaw.run 하나) 개수: {len(runs)}\n")

    print("=== run별 근거(evidence) — 패턴 판정을 원본 타임스탬프로 감사 ===\n")
    for parent_id, group in runs.items():
        model_calls = [s for s in group if s.name == "openclaw.model.call"]
        tool_execs = [s for s in group if s.name == "openclaw.tool.execution"]
        if not tool_execs:
            continue
        print(f"--- run(parent={parent_id[:16]}...) ---")
        print(f"  model.call {len(model_calls)}건, tool.execution {len(tool_execs)}건")
        for m in model_calls:
            it = m.attrs.get("openclaw.model_call.usage.input_tokens", "?")
            ot = m.attrs.get("openclaw.model_call.usage.output_tokens", "?")
            print(f"    [model.call] {fmt_ts(m.start)} ~ {fmt_ts(m.end)}  in={it} out={ot}")
        for t in tool_execs:
            name = t.attrs.get("openclaw.toolName", "unknown")
            print(f"    [tool.exec ] {fmt_ts(t.start)} ~ {fmt_ts(t.end)}  {name}")
        print()

    print("=== 귀속(attribution) 결과 ===\n")
    for a in results:
        cost_note = f"  tokens={a.approx_tokens}" if a.approx_tokens is not None else ""
        print(f"[{a.pattern:12s}] {a.tool_name:35s} duration={a.duration_ms or 0:8.2f}ms{cost_note}")
        if a.note:
            print(f"             note: {a.note}")

    print("\n=== 신뢰도 낮음/감사 필요 항목 요약 ===")
    suspicious = [a for a in results if a.note]
    if not suspicious:
        print("  (없음 — 이번 로그에서는 전부 note 없이 깔끔하게 귀속됨)")
    else:
        by_reason: dict[str, int] = {}
        for a in suspicious:
            key = (
                "unattributed(모델 재호출 없음)" if a.pattern == "unattributed" else
                "delta<0(컨텍스트 압축 의심)" if "delta<0" in a.note else
                "타임스탬프 누락(병렬 오분류 가능성)" if "타임스탬프 누락" in a.note else
                "기타"
            )
            by_reason[key] = by_reason.get(key, 0) + 1
        for reason, count in by_reason.items():
            print(f"  - {reason}: {count}건")

    print("\n=== 이번 로그로 검증 가능/불가능한 것 ===")
    has_parallel = any(a.pattern == "parallel" for a in results)
    has_batch = any(a.pattern == "batch" for a in results)
    has_sequential = any(a.pattern == "sequential" for a in results)
    print(f"  순차(sequential) 실사례: {'있음 — 토큰 diff 공식 검증 가능' if has_sequential else '없음'}")
    print(f"  병렬(parallel) 실사례:   {'있음 — 겹침 판정 로직 검증 가능' if has_parallel else '없음 (합성 테스트로만 검증됨, 실사례 필요)'}")
    print(f"  배치(batch) 실사례:      {'있음 — 개수 기반 판정 로직 검증 가능' if has_batch else '없음 (합성 테스트로만 검증됨, 실사례 필요)'}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/.openclaw/otel-debug-log.txt"
    main(path)
