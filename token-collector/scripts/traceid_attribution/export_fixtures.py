"""Go 이식 검증용: 실제 캡처 로그를 파싱해서 (1) 스팬 JSON (2) 파이썬 귀속 결과 JSON을 만든다.
Go 테스트가 같은 스팬을 넣었을 때 파이썬과 똑같은 결과가 나오는지 비교하는 기준으로 쓴다."""
import json, sys
from datetime import timezone
from otel_log_parser import parse_spans
from attribution import group_runs, classify_segments

KEEP = {"openclaw.model.call", "openclaw.tool.execution", "openclaw.run"}
# 저장소에 올라가는 픽스처라서 스팬 속성 중 openclaw.* / gen_ai.* 만 남긴다.
# (파서가 리소스 속성(host.name, process.owner, 실행 경로 등)을 인접 스팬에 붙이는 경우가 있어
#  PC 이름·사용자 이름이 섞여 들어갈 수 있음)
ATTR_PREFIXES = ("openclaw.", "gen_ai.")

def ns(dt):
    if dt is None:
        return 0
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1_000_000) * 1000

def main(log_path, out_prefix):
    spans = parse_spans(log_path)
    out = []
    for s in spans:
        if s.name not in KEEP:
            continue
        out.append({"trace_id": s.trace_id, "parent_id": s.parent_id, "span_id": s.span_id,
                    "name": s.name, "start_unix_nano": ns(s.start), "end_unix_nano": ns(s.end),
                    "attrs": {k: v for k, v in s.attrs.items() if k.startswith(ATTR_PREFIXES)}})
    with open(out_prefix + ".spans.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    res = classify_segments(group_runs(spans))
    exp = [{"trace_id": r.trace_id, "run_id": r.run_parent_id, "tool_span_id": r.tool_span_id,
            "tool_name": r.tool_name, "pattern": r.pattern, "approx_tokens": r.approx_tokens,
            "duration_ms": r.duration_ms} for r in res]
    with open(out_prefix + ".expected.json", "w", encoding="utf-8") as f:
        json.dump(exp, f, ensure_ascii=False, indent=1)
    print(out_prefix, len(out), "spans,", len(exp), "results")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
