"""개발용 MCP 서버 하나에서 실제 `tools/list` 응답을 stdio로 수집한다 (Tool 카탈로그 2단계, 내부 개발용 초안).

    python -m asset_scanner.live_tools --demo --output output/live-demo.result.json

**이 명령은 서버 프로세스를 실행한다.** 실행 대상은 프로젝트에 포함된 개발용 서버(`asset_scanner.dev_mcp_server`) 하나뿐이다.
OpenClaw 설정에 적힌 서버 명령을 자동으로 실행하는 기능은 이번 단계에 없다. 정적 수집 CLI(`python -m asset_scanner`,
`python -m asset_scanner.tools_catalog`)는 이 모듈과 분리돼 있으며 서버를 실행하거나 접속하지 않는다.

통신은 공식 MCP Python SDK(`mcp`)의 클라이언트를 사용한다. 버전 협상(`server/discover` 우선, 구형 서버는 `initialize`)은
SDK의 기본 흐름(`mode="auto"`)에 맡기며 이 모듈이 초기 통신을 구현하지 않는다. 협상 결과가 현재 카탈로그가 지원하는
2026-07-28이 아니면 응답을 읽지 않고 미지원 상태로 기록한다.

수집 방식
- 응답은 `session.send_request(..., TypeAdapter(dict))`로 받는다. SDK가 협상한 버전의 스키마로 검증한 **result dict 그대로**이며,
  SDK의 `Tool` 모델 변환(기본값 보충, 잘못된 x-mcp-header Tool 제외)을 거치지 않는다. 검증이 거부되면 실패로 기록한다.
- SDK 클라이언트의 응답 캐시는 끄고(`cache=None`) 매 페이지를 서버에 요청한다. 서버 도달은 테스트에서 개발용 서버의 요청 기록으로 확인한다.
- `tools/call`은 보내지 않는다. 서버 stderr는 버리며 내용도 크기도 저장하지 않는다.
- 파싱·가림·정규화·검사·저장은 정적 카탈로그(`tools_catalog`, `output`)의 코드를 그대로 쓴다. 가림 전 응답은 파일·로그에 쓰지 않고 메모리에서만 다룬다.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio
import mcp_types as types
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import MCPError
from pydantic import TypeAdapter, ValidationError

from . import __version__
from .cli import _make_console_output_safe
from .dev_mcp_server import SCENARIOS
from .output import OutputError, normalize_for_output, write_json_atomic
from .redaction import Redactor
from .tools_catalog import (EXIT_BY_STATUS, EXIT_OUTPUT_ERROR, MAX_TOOLS_PER_SERVER, SUPPORTED_PROTOCOL_VERSION,
                            _collect_server, _failed_server, _issue, _NonFinite, _sanitize, _seg, _short,
                            build_catalog_report, summarize_collection)

DEMO_SERVER_REF = "dev-demo-server"
DEMO_MODULE = "asset_scanner.dev_mcp_server"
_RAW_DICT = TypeAdapter(dict)

LIVE_NOT_VERIFIED = [
    "wire_level_raw_json",   # JSON 파싱은 SDK가 했으므로 중복 키·NaN 토큰 같은 전송 계층 원문은 확인하지 못함
    "team_testbed",          # 팀 테스트베드 서버가 아니라 직접 만든 개발용 서버
    "tools_call",            # tools/call을 보내지 않음
    "resources_prompts",
    "exposure",              # Agent 노출 여부
    "callability",           # 호출 가능 여부
    "authorization",
    "common_server_id",      # 팀 공통 server_id·asset_id 미확정
]


MAX_TIMEOUT_S = 86400.0  # 24시간. 이보다 큰 값은 이벤트 루프의 대기 시간 변환에서 오류가 날 수 있어 거부한다

# LiveLimits 필드 → CLI 옵션 이름 (검증 메시지에 쓴다)
_LIMIT_OPTIONS = {"total_timeout_s": "--timeout", "request_timeout_s": "--request-timeout",
                  "max_pages": "--max-pages", "max_tools": "--max-tools"}


@dataclass
class LiveLimits:
    total_timeout_s: float = 60.0      # 서버 실행부터 정리까지 전체 제한
    request_timeout_s: float = 15.0    # 요청 하나의 응답 대기 제한 (서버 기동 시간 포함될 수 있음)
    max_pages: int = 50
    # 서버 하나에서 보존할 Tool의 최대 수. 최종 페이지를 포함한 전체 누적에 적용한다. 정적 카탈로그의 고정 한도
    # (MAX_TOOLS_PER_SERVER=5000)를 넘을 수 없으므로 실제 한도는 항상 이 값이다.
    max_tools: int = MAX_TOOLS_PER_SERVER


def _is_real(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_limits(limits: LiveLimits) -> list[str]:
    """서버를 실행하기 **전에** 제한값을 검사한다. CLI와 공개 함수(`collect_live_demo`)가 같은 검사를 쓴다.

    문제가 없으면 빈 목록. 있으면 `"필드: 사유"` 문자열 목록(NaN·Infinity·0·음수·범위 밖 값 포함)을 돌려준다.
    """
    problems: list[str] = []
    for name in ("total_timeout_s", "request_timeout_s"):
        value = getattr(limits, name)
        if not (_is_real(value) and math.isfinite(value) and 0 < value <= MAX_TIMEOUT_S):
            problems.append(f"{name}: 0보다 크고 {MAX_TIMEOUT_S:g} 이하인 유한한 수여야 합니다 (NaN·Infinity·0·음수 불가)")
    if not (isinstance(limits.max_pages, int) and not isinstance(limits.max_pages, bool) and limits.max_pages >= 1):
        problems.append("max_pages: 1 이상의 정수여야 합니다")
    if not (isinstance(limits.max_tools, int) and not isinstance(limits.max_tools, bool)
            and 1 <= limits.max_tools <= MAX_TOOLS_PER_SERVER):
        problems.append(f"max_tools: 1 이상 {MAX_TOOLS_PER_SERVER} 이하의 정수여야 합니다 (정적 카탈로그 고정 한도)")
    return problems


@dataclass
class _State:
    pages: list[dict] = field(default_factory=list)
    tools_kept: int = 0
    exclusions: list[dict] = field(default_factory=list)   # 한도 때문에 보존하지 않은 Tool (페이지별 건수만, 정의 없음)
    requests_sent: int = 0
    negotiated: str | None = None
    server_info: Any = None
    capabilities: Any = None
    failure: dict | None = None
    finished_listing: bool = False
    teardown_error_types: list[str] = field(default_factory=list)

    def fail(self, code: str, message: str, **extra: Any) -> None:
        if self.failure is None:
            self.failure = {"code": code, "message": message, **extra}


def sdk_version() -> str | None:
    try:
        return importlib.metadata.version("mcp")
    except importlib.metadata.PackageNotFoundError:
        return None


def _leaf_error_types(exc: BaseException) -> list[str]:
    if isinstance(exc, BaseExceptionGroup):
        return [n for e in exc.exceptions for n in _leaf_error_types(e)]
    return [type(exc).__name__]


def _mcp_error_in(exc: BaseException) -> MCPError | None:
    if isinstance(exc, MCPError):
        return exc
    if isinstance(exc, BaseExceptionGroup):
        for e in exc.exceptions:
            found = _mcp_error_in(e)
            if found is not None:
                return found
    return None


def _mark_nonfinite(node: Any) -> Any:
    """SDK가 파싱한 float 중 NaN·Infinity는 정적 카탈로그와 같은 방식으로 숫자가 아닌 표식으로 바꾼다."""
    if isinstance(node, float) and not math.isfinite(node):
        return _NonFinite()
    if isinstance(node, dict):
        return {k: _mark_nonfinite(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_mark_nonfinite(v) for v in node]
    return node


def _validation_summary(exc: ValidationError) -> list[dict]:
    """SDK 검증 거부 근거. 입력 값은 서버가 보낸 임의 내용이라 넣지 않고 오류 종류와 위치만 남긴다."""
    out = []
    for e in exc.errors(include_input=False, include_url=False, include_context=False)[:10]:
        out.append({"type": str(e.get("type", "")), "loc": ".".join(_seg(p) for p in e.get("loc", ()))})
    return out


async def _list_pages(client: Client, limits: LiveLimits, state: _State) -> None:
    """`tools/list`를 `nextCursor`가 없을 때까지 요청한다. 빈 문자열 커서도 다음 페이지가 있다는 뜻이다."""
    cursor: str | None = None
    sent_cursors: set[str] = set()
    while True:
        if len(state.pages) >= limits.max_pages:
            state.fail("max_pages_reached", f"최대 페이지 수({limits.max_pages})에 도달해 나머지를 요청하지 않았습니다.")
            return
        params = types.PaginatedRequestParams(cursor=cursor) if cursor is not None else None
        state.requests_sent += 1
        try:
            raw = await client.session.send_request(types.ListToolsRequest(params=params), _RAW_DICT,
                                                    request_read_timeout_seconds=limits.request_timeout_s)
        except MCPError as exc:
            if exc.code == types.REQUEST_TIMEOUT:
                state.fail("request_timeout", "tools/list 응답을 시간 안에 받지 못했습니다.", page_index=len(state.pages))
            elif exc.code == types.CONNECTION_CLOSED:
                state.fail("connection_closed", "tools/list를 기다리는 중 서버 연결이 끊어졌습니다(서버가 먼저 종료했을 수 있음).",
                           page_index=len(state.pages))
            else:  # 서버가 보낸 JSON-RPC 오류: 정적 카탈로그와 같은 오류 응답 경로로 처리한다 (코드와 가린 메시지만 남음)
                state.pages.append({"error": {"code": exc.code, "message": exc.message}})
            return
        except ValidationError as exc:
            state.fail("sdk_validation_rejected", "SDK가 협상한 버전의 스키마로 검증하다 서버 응답을 거부했습니다. Tool 0개가 아닙니다.",
                       page_index=len(state.pages), validation_errors=_validation_summary(exc))
            return
        page = _mark_nonfinite(raw)
        page_index = len(state.pages)
        tools = page.get("tools")
        if isinstance(tools, list):
            # 사용자 한도(--max-tools)는 최종 페이지를 포함한 전체 누적에 적용한다. 응답 페이지 자체는 서버가 이미 보냈고 SDK가
            # 파싱했으므로(수신·파싱 메모리는 제한하지 못함) 한도를 넘는 Tool 정의를 **결과에 보존하지 않는다**.
            remaining = limits.max_tools - state.tools_kept
            if len(tools) > remaining:
                excluded = len(tools) - remaining
                state.exclusions.append({"page_index": page_index, "tools_in_response": len(tools),
                                         "tools_kept": remaining, "tools_excluded": excluded})
                page["tools"] = tools[:remaining]
                state.tools_kept += remaining
                state.pages.append(page)
                state.fail("tool_limit_reached",
                           f"Tool 수 한도({limits.max_tools})를 넘어 이 페이지의 Tool {excluded}개를 보존하지 않았습니다.",
                           page_index=page_index, excluded_tools=excluded)
                return
            state.tools_kept += len(tools)
        state.pages.append(page)
        next_cursor = raw.get("nextCursor")
        if not isinstance(next_cursor, str):
            return                                   # 마지막 페이지: 한도와 정확히 같아도 complete
        if next_cursor in sent_cursors:
            state.fail("cursor_repeated", "서버가 이미 사용한 nextCursor를 다시 돌려줘 반복을 멈췄습니다.", page_index=page_index)
            return
        if state.tools_kept >= limits.max_tools:
            state.fail("tool_limit_reached", f"Tool 수 한도({limits.max_tools})에 도달해 다음 페이지를 요청하지 않았습니다.",
                       page_index=page_index)
            return
        sent_cursors.add(next_cursor)
        cursor = next_cursor


async def _run_demo(scenario: str, limits: LiveLimits, request_log: Path | None, mode: str) -> _State:
    state = _State()
    root = Path(__file__).resolve().parent.parent
    env = {"PYTHONUTF8": "1"}
    if request_log is not None:
        env["DEV_MCP_SERVER_LOG"] = str(request_log)
    params = StdioServerParameters(command=sys.executable, args=["-m", DEMO_MODULE, "--scenario", scenario], env=env, cwd=str(root))
    errlog = open(os.devnull, "w")  # 서버 stderr는 버린다 (내용·크기 모두 저장하지 않음)
    try:
        try:
            with anyio.fail_after(limits.total_timeout_s):
                async with Client(stdio_client(params, errlog=errlog), cache=None, mode=mode,  # type: ignore[arg-type]
                                  read_timeout_seconds=limits.request_timeout_s) as client:
                    state.negotiated = client.protocol_version
                    state.server_info = client.server_info
                    state.capabilities = client.server_capabilities
                    if state.negotiated == SUPPORTED_PROTOCOL_VERSION:
                        await _list_pages(client, limits, state)
                    state.finished_listing = True
        except TimeoutError:
            state.fail("total_timeout", f"전체 제한 시간({limits.total_timeout_s:g}초)이 지나 조회를 중단하고 서버를 종료했습니다.")
        except Exception as exc:  # noqa: BLE001 - 서버 종료·연결 실패를 traceback 없이 상태로 남긴다
            types_seen = _leaf_error_types(exc)
            if state.finished_listing:
                state.teardown_error_types = types_seen          # 조회는 끝났고 정리 중 오류: 결과에는 영향 없음
            else:
                mcp_err = _mcp_error_in(exc)
                if state.negotiated is None:
                    code = "server_exited_before_ready" if mcp_err and mcp_err.code == types.CONNECTION_CLOSED else \
                        "connect_timeout" if mcp_err and mcp_err.code == types.REQUEST_TIMEOUT else "connect_failed"
                    state.fail(code, "개발용 서버에 연결하지 못했습니다 (프로세스 실행·버전 협상 실패).", error_types=types_seen)
                else:
                    state.fail("session_error", "조회 중 예기치 않은 오류가 발생했습니다.", error_types=types_seen)
    finally:
        errlog.close()
    return state


def _wire_dump(model: Any, path: str, red: Redactor) -> Any:
    """SDK가 서버 응답에서 파싱한 값 중 **서버가 실제로 보낸 필드만**(exclude_unset) 가림 후 옮긴다."""
    if model is None:
        return None
    return _sanitize(model.model_dump(by_alias=True, mode="json", exclude_unset=True), path, red)


def _would_sdk_drop(tool: Any) -> bool | None:
    """SDK 클라이언트의 `list_tools`가 2026-07-28에서 이 Tool을 조용히 제외했을지 (x-mcp-header 검사). 확인 불가면 None."""
    try:
        from mcp.shared.inbound import find_invalid_x_mcp_header
    except ImportError:
        return None
    schema = tool.get("inputSchema") if isinstance(tool, dict) else None
    try:
        return find_invalid_x_mcp_header(schema) is not None
    except Exception:  # noqa: BLE001
        return None


def _build_server(state: _State, scenario: str, limits: LiveLimits, elapsed_ms: int) -> dict:
    ref = DEMO_SERVER_REF
    failure = state.failure
    if state.negotiated is None or (not state.pages and state.negotiated == SUPPORTED_PROTOCOL_VERSION):
        code = failure["code"] if failure else "no_response"
        extra = {k: v for k, v in (failure or {}).items() if k not in ("code", "message")}
        server = _failed_server(0, ref, code, (failure or {}).get("message", "응답을 받지 못했습니다."), **extra)
        server["server_ref_kind"] = "live_session_label"
        server["negotiated_protocol_version"] = state.negotiated
    else:
        entry = {"server_ref": ref, "protocol_version": state.negotiated, "pages": state.pages}
        server = _collect_server(0, entry, set())
        server["server_ref_kind"] = "live_session_label"   # 이 조회 안에서만 쓰는 이름. 팀 공통 server_id가 아니다.
        server["negotiated_protocol_version"] = state.negotiated
        server.pop("declared_protocol_version", None)
        if failure is not None and server["collection_status"] != "failed":
            extra = {k: v for k, v in failure.items() if k not in ("code", "message")}
            server["issues"].append(_issue("error", failure["code"], failure["message"], **extra))
            if server["collection_status"] == "complete":
                server["collection_status"] = "partial"
                server["outcome"] = failure["code"]
        # SDK 클라이언트의 list_tools라면 조용히 제외했을 Tool을 표시한다 (우리는 원본 응답에서 그대로 보존한다)
        raw_tools: dict[tuple[int, int], Any] = {}
        for pi, page in enumerate(state.pages):
            for ti, tool in enumerate(page.get("tools") or []):
                raw_tools[(pi, ti)] = tool
        for t in server.get("tools", []):
            would_drop = _would_sdk_drop(raw_tools.get((t["page_index"], t["index_in_page"])))
            t["sdk_list_tools_would_drop"] = would_drop
            t["internal_ref"] = t["internal_ref"].replace("capture-server", "live-session", 1)  # 이 조회 안의 위치 (공통 ID 아님)
    for ex in state.exclusions:          # 잘라 낸 페이지의 기록에는 서버가 실제로 보낸 Tool 수를 함께 남긴다
        for rec in server.get("pages", []):
            if rec.get("page_index") == ex["page_index"]:
                rec["tools_in_response"] = ex["tools_in_response"]
    red = Redactor()
    server["live"] = {
        "transport": "stdio",
        "executed_process": True,
        "demo_scenario": scenario,
        "sdk": {"package": "mcp", "version": sdk_version()},
        "negotiation": {
            "requested_mode": "auto (SDK 기본 흐름: server/discover 우선, 구형 서버는 initialize)",
            "negotiated_protocol_version": state.negotiated,
            "supported_by_catalog": state.negotiated == SUPPORTED_PROTOCOL_VERSION,
        },
        # SDK가 서버 응답에서 파싱한 값 중 서버가 실제로 보낸 필드만. 서버가 보내지 않은 값은 만들지 않는다.
        "server_info_from_wire": _wire_dump(state.server_info, "live.server_info", red),
        "capabilities_from_wire": _wire_dump(state.capabilities, "live.capabilities", red),
        "requests": {"tools_list_sent": state.requests_sent, "tools_call_sent": 0},
        # --max-tools 때문에 보존하지 않은 Tool: 페이지별 응답 건수·보존 건수·제외 건수 (제외한 Tool의 정의는 저장하지 않음)
        "limit_exclusions": state.exclusions,
        "result_origin": "sdk_session_raw_result",
        "sdk_processing": {
            "json_parsed_by": "SDK (전송 계층의 중복 키·NaN 토큰 원문은 확인하지 못함)",
            "validated_against_negotiated_version": state.negotiated,
            "tool_models_used": False,
            "client_cache": "disabled (Client(cache=None), session.send_request 직접 사용)",
            "known_sdk_adjustments": ["음수 ttlMs는 SDK가 0으로 올린 뒤 검증함"],
            "x_mcp_header_filter": "SDK list_tools는 적용하지만 이 수집은 거치지 않음 (tools[].sdk_list_tools_would_drop 참조)",
        },
        "limits": {"total_timeout_s": limits.total_timeout_s, "request_timeout_s": limits.request_timeout_s,
                   "max_pages": limits.max_pages, "max_tools": limits.max_tools},
        "elapsed_ms": elapsed_ms,
    }
    if state.teardown_error_types:
        server["live"]["teardown_error_types"] = state.teardown_error_types
    server["redactions"] = list(server.get("redactions", [])) + red.redactions
    return server


def collect_live_demo(scenario: str = "two-tools", limits: LiveLimits | None = None, request_log: Path | None = None,
                      *, client_mode: str = "auto") -> dict:
    """개발용 서버를 별도 프로세스로 실행하고 stdio로 `tools/list`를 수집한다. `build_catalog_report`에 넘길 결과를 돌려준다."""
    limits = limits or LiveLimits()
    problems = validate_limits(limits)       # CLI와 같은 검사: 잘못된 제한값은 서버를 실행하기 전에 ValueError로 거부한다
    if problems:
        raise ValueError("잘못된 제한값: " + "; ".join(problems))
    started = time.monotonic()
    state = anyio.run(_run_demo, scenario, limits, request_log, client_mode)
    server = _build_server(state, scenario, limits, int((time.monotonic() - started) * 1000))
    return {
        "capture_path": None,
        "origin": "live_stdio_query",
        "collection": summarize_collection([server], None, []),
        "servers": [server],
        "source": {
            "source_kind": "live_stdio_query",
            "evidence_type": "live_protocol_response",
            "live_server_query": True,
            "transport": "stdio",
            "target": {"kind": "dev_demo_server", "module": DEMO_MODULE, "scenario": scenario, "team_testbed": False,
                       "command_origin": "스캐너에 내장된 개발용 서버 (OpenClaw 설정에서 읽은 명령이 아님)"},
        },
        "scope_overrides": {
            "method": f"공식 MCP Python SDK(mcp {sdk_version()}) 클라이언트로 개발용 서버를 stdio 프로세스로 실행해 tools/list 조회",
            "not_verified": LIVE_NOT_VERIFIED,
            "note": ("tools[]는 개발용 서버 하나에 실제로 stdio로 요청해 받은 tools/list 응답의 Tool 정의입니다. 팀 테스트베드 서버를 조회한 것이 아니며, "
                     "조회 성공은 Agent 노출이나 호출 가능을 뜻하지 않습니다(tools/call은 보내지 않았습니다). "
                     "서버가 제공한 설명·메타데이터는 비신뢰 데이터로만 저장하며 실행하지 않습니다."),
        },
    }


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m asset_scanner.live_tools",
        description="개발용 MCP 서버를 stdio 프로세스로 실행해 tools/list를 실제로 조회하고 Tool 정의 목록으로 저장합니다 "
                    "(내부 개발용 초안). 이 명령은 서버 프로세스를 실행합니다.",
    )
    p.add_argument("--demo", action="store_true",
                   help="프로젝트에 포함된 개발용 서버(asset_scanner.dev_mcp_server) 하나를 실행해 조회합니다. "
                        "OpenClaw 설정의 서버 명령 실행은 지원하지 않습니다.")
    p.add_argument("--output", required=True, type=Path, help="결과 JSON을 저장할 경로")
    p.add_argument("--scenario", choices=SCENARIOS, default="two-tools", help="개발용 서버의 동작 (검증용, 기본: two-tools)")
    p.add_argument("--timeout", type=float, default=60.0, help="서버 실행부터 정리까지 전체 제한 시간(초, 0 초과 86400 이하의 유한한 수, 기본 60)")
    p.add_argument("--request-timeout", type=float, default=15.0, help="요청 하나의 응답 대기 제한(초, 0 초과 86400 이하의 유한한 수, 기본 15)")
    p.add_argument("--max-pages", type=int, default=50, help="최대 페이지 수 (기본 50)")
    p.add_argument("--max-tools", type=int, default=MAX_TOOLS_PER_SERVER, help=f"보존할 최대 Tool 수 (최종 페이지를 포함한 전체 누적, 1~{MAX_TOOLS_PER_SERVER}, 기본 {MAX_TOOLS_PER_SERVER}). "
                        "넘는 Tool은 보존하지 않고 partial로 기록합니다")
    p.add_argument("--demo-request-log", type=Path, default=None,
                   help="개발용 서버가 받은 요청의 메서드 이름·횟수만 JSON 줄로 남길 파일 (검증용, 응답 내용은 기록하지 않음)")
    return p


def main(argv: list[str] | None = None) -> int:
    _make_console_output_safe()
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.demo:
        parser.error("이번 단계는 --demo(개발용 서버)만 지원합니다. OpenClaw 설정에 적힌 서버 명령을 자동으로 실행하는 기능은 아직 없습니다.")
    limits = LiveLimits(args.timeout, args.request_timeout, args.max_pages, args.max_tools)
    problems = validate_limits(limits)       # 서버 실행·출력 파일·요청 로그 생성 전에 검사한다 (잘못된 값은 종료 코드 2)
    if problems:
        parser.error("; ".join(_LIMIT_OPTIONS[p.split(":")[0]] + p[p.index(":"):] for p in problems))

    print("서버 프로세스를 실행합니다: 개발용 MCP 서버 (stdio, tools/list만 요청, tools/call 없음)")
    report = build_catalog_report(collect_live_demo(args.scenario, limits, args.demo_request_log))
    report, normalized = normalize_for_output(report)
    if normalized:
        report["collection"]["output_text_normalizations"] = normalized
    try:
        write_json_atomic(args.output, report)
    except OutputError as exc:
        print(f"오류: 결과 파일을 저장하지 못했습니다 ({exc.kind}). 기존 결과 파일은 바꾸지 않았습니다.", file=sys.stderr)
        return EXIT_OUTPUT_ERROR

    col = report["collection"]
    srv = report["servers"][0]
    live = srv["live"]
    print("실제 stdio 조회 결과 (개발용 서버, 팀 테스트베드 아님)")
    print(f"협상된 protocol_version: {live['negotiation']['negotiated_protocol_version']}")
    print(f"수집 상태: {col['status']} ({col['outcome']})")
    if normalized:
        print(f"출력 문자열 정규화: {normalized}건 (고립된 surrogate를 U+FFFD로 대체)")
    count = "미확인" if srv["tool_count"] is None else f"{srv['tool_count']}개"
    print(f"읽은 Tool: {count}" + ("" if col["tool_count_complete"] else " (전체 수가 아님)"))
    for t in srv.get("tools", []):
        # 서버가 제공한 문자열이므로 이스케이프한 짧은 형태로만 출력한다. 설명·메타데이터는 출력하지 않는다.
        print(f"  - {json.dumps(_short(t['definition'].get('name')))}")
    for r in col["reasons"]:
        print(f"  사유: {r['code']}")
    for i in srv["issues"]:
        if i["category"] == "completeness":
            print(f"  이슈: {i['code']}")
    print(f"결과 저장: {args.output}")
    return EXIT_BY_STATUS[col["status"]]


if __name__ == "__main__":
    sys.exit(main())
