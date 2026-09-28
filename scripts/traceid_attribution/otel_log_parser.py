"""
OTel Collector debug 익스포터(verbosity: detailed) 로그 파서.

입력: `otelcol.exe --config=... 2>&1 | Tee-Object -FilePath ...` 로 캡처한 텍스트 로그
      (UTF-16LE, CRLF — Windows PowerShell Tee-Object 기본 인코딩)

출력: Span 객체 리스트. 각 Span은 다음 필드를 가짐:
    trace_id, parent_id, span_id, name, start (datetime), end (datetime), attrs (dict)

파싱 전략:
  - "Span #N" 라인을 만나면 새 스팬 레코드 시작, 직전 스팬은 리스트에 push.
  - 헤더 필드(Trace ID / Parent ID / ID / Name / Kind / Start time / End time)는
    고정폭 라벨 뒤 콜론(:)으로 파싱.
  - "Attributes:" 이후 "     -> key: Type(value)" 라인을 attrs 딕셔너리로 파싱.
  - 콘솔 폭 때문에 긴 문자열 값이 줄바꿈되는 경우(예: 파일 경로)가 실제로 있는데,
    이번에 필요한 필드(트레이스ID/토큰수/툴이름 등)는 전부 짧은 값이라 줄바꿈되지 않음을
    실제 로그에서 확인함 — 매칭 안 되는 라인은 그냥 스킵(연속줄 취급)해서 안전하게 넘어감.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


SPAN_START_RE = re.compile(r"^Span #\d+\s*$")

HEADER_FIELD_RE = re.compile(
    r"^\s{4}(Trace ID|Parent ID|ID|Name|Kind|Start time|End time|Status code|Status message)"
    r"\s*:\s?(.*?)\s*$"
)

ATTRIBUTES_MARKER_RE = re.compile(r"^Attributes:\s*$")

# "     -> key: Type(value)"  — value may itself contain parentheses (e.g. a path),
# so we match the LAST ")" on the line as the closer.
ATTR_LINE_RE = re.compile(r"^\s*->\s*([^:]+):\s*(\w+)\((.*)\)\s*$")

# Lines that signal "we've left the current span's attribute block" even though
# they don't start a new Span — used so we don't accidentally swallow unrelated
# content into the previous span's attrs.
SECTION_BOUNDARY_RE = re.compile(
    r"^(ResourceSpans #\d+|ScopeSpans #\d+|InstrumentationScope\b|Metric #\d+|"
    r"ResourceMetrics #\d+|NumberDataPoints #\d+|HistogramDataPoints #\d+|"
    r"Data point attributes:|StartTimestamp:|Timestamp:|Value:)"
)

# 2026-09-22 05:46:04.143 +0000 UTC   (nanosecond-precision variant also seen:
# 2026-09-22 05:44:25.960581787 +0000 UTC)
TIME_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}):(\d{2})\.(\d+) \+0000 UTC$"
)


def _parse_time(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    m = TIME_RE.match(raw.strip())
    if not m:
        return None
    date_s, hh, mm, ss, frac = m.groups()
    # frac can be 3 digits (ms) up to 9 digits (ns) — normalize to microseconds for datetime.
    frac = (frac + "000000")[:6]
    iso = f"{date_s}T{hh}:{mm}:{ss}.{frac}+00:00"
    return datetime.fromisoformat(iso)


def _coerce(type_name: str, raw_value: str) -> Any:
    if type_name == "Int":
        try:
            return int(raw_value)
        except ValueError:
            return raw_value
    if type_name == "Double":
        try:
            return float(raw_value)
        except ValueError:
            return raw_value
    if type_name == "Bool":
        return raw_value.strip().lower() == "true"
    # Str and anything else: keep as string
    return raw_value


@dataclass
class Span:
    trace_id: str = ""
    parent_id: str = ""
    span_id: str = ""
    name: str = ""
    kind: str = ""
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    attrs: dict = field(default_factory=dict)

    @property
    def duration_ms(self) -> Optional[float]:
        if self.start is None or self.end is None:
            return None
        return (self.end - self.start).total_seconds() * 1000.0


def parse_spans(path: str) -> list[Span]:
    """Parse every Span block out of an OTel Collector `debug` (detailed) log file."""
    spans: list[Span] = []
    current: Optional[Span] = None
    in_attrs = False

    with open(path, encoding="utf-16") as f:
        for raw_line in f:
            line = raw_line.rstrip("\r\n")

            if SPAN_START_RE.match(line):
                if current is not None:
                    spans.append(current)
                current = Span()
                in_attrs = False
                continue

            if current is None:
                continue  # haven't hit a Span block yet

            if ATTRIBUTES_MARKER_RE.match(line):
                in_attrs = True
                continue

            if SECTION_BOUNDARY_RE.match(line):
                # Left this span's block entirely without a new "Span #" line
                # (e.g. end of file, or a Metric section follows).
                spans.append(current)
                current = None
                in_attrs = False
                continue

            if in_attrs:
                m = ATTR_LINE_RE.match(line)
                if m:
                    key, type_name, raw_value = m.groups()
                    current.attrs[key.strip()] = _coerce(type_name, raw_value)
                # non-matching lines while in_attrs (wrapped continuations) are skipped
                continue

            m = HEADER_FIELD_RE.match(line)
            if m:
                field_name, value = m.groups()
                if field_name == "Trace ID":
                    current.trace_id = value
                elif field_name == "Parent ID":
                    current.parent_id = value
                elif field_name == "ID":
                    current.span_id = value
                elif field_name == "Name":
                    current.name = value
                elif field_name == "Kind":
                    current.kind = value
                elif field_name == "Start time":
                    current.start = _parse_time(value)
                elif field_name == "End time":
                    current.end = _parse_time(value)
                continue
            # else: ignore (DroppedXCount lines, blank lines, wrapped continuations, etc.)

    if current is not None:
        spans.append(current)

    return spans


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "otel-debug-log.utf8.txt"
    # NOTE: this __main__ block expects the ORIGINAL utf-16 file, not the .utf8 copy,
    # since parse_spans() opens with encoding="utf-16". Pass the raw uploaded file.
    all_spans = parse_spans(path)
    print(f"총 파싱된 Span 수: {len(all_spans)}")
    by_name: dict[str, int] = {}
    for s in all_spans:
        by_name[s.name] = by_name.get(s.name, 0) + 1
    for name, count in sorted(by_name.items(), key=lambda kv: -kv[1]):
        print(f"  {count:4d}  {name}")
