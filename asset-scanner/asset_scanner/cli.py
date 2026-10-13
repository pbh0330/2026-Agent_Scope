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

from .collector import SUPPORTED_REGISTRY_PATHS, collect
from .output import OutputError, normalize_for_output, write_json_atomic
from .report import build_report

DEFAULT_REGISTRY = "mcp.servers"

EXIT_BY_STATUS = {"complete": 0, "partial": 1, "failed": 3}
EXIT_OUTPUT_ERROR = 4


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="asset_scanner",
        description="OpenClaw 설정 파일에서 선택한 등록 영역(기본 mcp.servers)의 MCP 서버 등록 항목을 읽어 "
                    "개발용 JSON으로 저장합니다 (협의용 초안).",
    )
    p.add_argument("--registry-path", choices=sorted(SUPPORTED_REGISTRY_PATHS), default=DEFAULT_REGISTRY,
                   help="수집할 등록 영역 (기본: mcp.servers). nodeHost.mcp.servers는 Node 설정 파일용입니다. "
                        "파일 전체를 파싱하되 고른 영역만 수집·보고합니다.")
    p.add_argument("--config", required=True, type=Path, help="읽을 OpenClaw 설정 파일 (JSON/JSON5)")
    p.add_argument("--output", required=True, type=Path, help="결과 JSON을 저장할 경로")
    return p


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve() or (b.exists() and a.exists() and a.samefile(b))
    except OSError:
        return False


def _make_console_output_safe() -> None:
    """콘솔 코드페이지(예: cp949)로 표현할 수 없는 문자 때문에 출력 중 종료되지 않게 한다.

    표현 가능한 문자는 그대로 두고, 표현할 수 없는 문자만 \\uXXXX 형태로 표시한다.
    인코딩을 바꾸거나 오류를 삼키지 않으며, 결과 JSON 파일은 항상 UTF-8 원문을 보존한다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")


def main(argv: list[str] | None = None) -> int:
    _make_console_output_safe()
    args = _parser().parse_args(argv)

    if _same_file(args.config, args.output):
        print("오류: --output이 --config와 같은 파일입니다. 원본 설정을 덮어쓰지 않습니다.", file=sys.stderr)
        return EXIT_OUTPUT_ERROR

    report = build_report(collect(args.config, SUPPORTED_REGISTRY_PATHS[args.registry_path]))

    # 저장 전에 직렬화할 수 없는 문자(고립된 surrogate)를 정리하고, 임시 파일에 완전히 쓴 뒤 교체한다.
    report, normalized = normalize_for_output(report)
    if normalized:
        report["collection"]["output_text_normalizations"] = normalized

    try:
        write_json_atomic(args.output, report)
    except OutputError as exc:
        print(f"오류: 결과 파일을 저장하지 못했습니다 ({exc.kind}). 기존 결과 파일은 바꾸지 않았습니다.", file=sys.stderr)
        return EXIT_OUTPUT_ERROR

    col = report["collection"]
    print(f"등록 영역: {report['source']['registry_path']}")
    print(f"수집 상태: {col['status']} ({col['outcome']})")
    if normalized:
        print(f"출력 문자열 정규화: {normalized}건 (고립된 surrogate를 U+FFFD로 대체)")
    if col["server_count"] is not None:
        print(f"등록 항목: {col['server_count']}개")
    for s in report["servers"]:
        enabled = json.dumps(s["declared"]["enabled"]) if "enabled" in s["declared"] else "미선언"
        print(f"  - {s['declaration_path']}  [항목 상태: {s['collection_status']}, enabled: {enabled}]")
    for r in col["reasons"]:
        print(f"  사유: {r['code']} — {r['message']}")
    print(f"결과 저장: {args.output}")
    return EXIT_BY_STATUS[col["status"]]
