"""명령행 진입점.

    python -m asset_scanner --config <설정 파일> --output <결과 JSON>

종료 코드
    0  완전 수집 (complete)
    1  부분 수집 (partial) — 결과 파일은 저장됨
    2  인자 오류 (argparse)
    3  수집 실패 (failed: 파일 없음·읽기 실패·파싱 실패·잘못된 구조) — 결과 파일은 저장됨
    4  결과 파일 저장 실패
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .collector import collect
from .report import build_report

EXIT_BY_STATUS = {"complete": 0, "partial": 1, "failed": 3}
EXIT_OUTPUT_ERROR = 4


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="asset_scanner",
        description="OpenClaw 설정 파일의 mcp.servers 등록 항목을 읽어 개발용 JSON으로 저장합니다 (협의용 초안).",
    )
    p.add_argument("--config", required=True, type=Path, help="읽을 OpenClaw 설정 파일 (JSON/JSON5)")
    p.add_argument("--output", required=True, type=Path, help="결과 JSON을 저장할 경로")
    return p


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve() or (b.exists() and a.exists() and a.samefile(b))
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if _same_file(args.config, args.output):
        print("오류: --output이 --config와 같은 파일입니다. 원본 설정을 덮어쓰지 않습니다.", file=sys.stderr)
        return EXIT_OUTPUT_ERROR

    report = build_report(collect(args.config))

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"오류: 결과 파일을 저장하지 못했습니다 ({type(exc).__name__}).", file=sys.stderr)
        return EXIT_OUTPUT_ERROR

    col = report["collection"]
    print(f"수집 상태: {col['status']} ({col['outcome']})")
    if col["server_count"] is not None:
        print(f"등록 항목: {col['server_count']}개")
    for s in report["servers"]:
        enabled = json.dumps(s["declared"]["enabled"]) if "enabled" in s["declared"] else "미선언"
        print(f"  - {s['declaration_path']}  [항목 상태: {s['collection_status']}, enabled: {enabled}]")
    for r in col["reasons"]:
        print(f"  사유: {r['code']} — {r['message']}")
    print(f"결과 저장: {args.output}")
    return EXIT_BY_STATUS[col["status"]]
