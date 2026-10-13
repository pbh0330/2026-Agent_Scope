"""스캐너 검증용 개발 MCP 서버 (stdio). 외부 계정·인증정보·네트워크 없이 실행된다.

    python -m asset_scanner.dev_mcp_server [--scenario NAME]

이 서버는 **직접 만든 검증 대상 하나**일 뿐이며 팀 테스트베드의 서버가 아니다. 공식 MCP Python SDK(`mcp`)의
저수준 `Server`로 만들었고, `tools/list`에 서로 다른 Tool 2개를 광고한다(`examples/dev-server-ground-truth.json`의
정답 목록과 별개로 손으로 정의했다). `tools/call`은 어떤 시나리오에서도 처리하지 않고 오류를 돌려준다.

요청 기록: 환경변수 `DEV_MCP_SERVER_LOG`에 파일 경로가 있으면 JSON 한 줄씩 남긴다. 내용은 시작(pid·시나리오), 요청의
메서드 이름과 `tools/list` 커서 상태(없음/빈 문자열/있음)뿐이다. 응답 내용·커서 값·인증정보는 기록하지 않는다.

시나리오(스캐너의 실패·경계 처리를 실제 통신으로 검증하기 위한 동작):
    two-tools      Tool 2개, 한 페이지 (기본)
    empty          성공한 빈 목록
    error          tools/list마다 서버 오류를 돌려준다 (빈 목록과의 구분 검증)
    paginated      두 페이지 (Tool 1개씩, 커서 `page-2`)
    empty-cursor   첫 페이지가 빈 문자열 커서를 돌려주고 두 번째 페이지가 이어진다
    big-first-page 첫 페이지에 Tool 2개와 다음 커서, 두 번째(마지막) 페이지에 Tool 1개 (--max-tools 검증)
    uneven-pages   첫 페이지에 Tool 1개와 다음 커서, 두 번째(마지막) 페이지에 Tool 2개 (--max-tools 누적 검증)
    fail-second    두 번째 페이지 요청에 서버 오류를 돌려준다
    slow           tools/list에 응답하지 않는다 (시간 초과 검증)
    exit-early     tools/list를 받으면 응답 없이 프로세스를 끝낸다
    cursor-loop    항상 같은 커서를 돌려준다 (반복 방지 검증)
    endless        끝나지 않는 페이지를 돌려준다 (최대 페이지 수 검증)
    secrets        가짜 인증정보가 든 설명·스키마·메타데이터 (가림 검증)
    unicode        한글·이모지·유럽 문자가 든 설명
    sparse         선택 필드(description·annotations 등)가 없는 Tool (SDK 기본값 보충과 구분 검증)
    bad-header     잘못된 x-mcp-header 주석이 든 Tool (SDK 클라이언트가 조용히 제외하는 경우)
    invalid-schema 전송 직전에 응답의 inputSchema 루트 type을 규격 위반 값으로 바꾼다 (서버 SDK의 자체 검증은 통과한 뒤이므로
                   클라이언트 SDK의 응답 검증 거부 경로를 실제 통신으로 만든다)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import anyio
import mcp_types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError

SERVER_NAME = "asset-scanner-dev-server"
SERVER_VERSION = "0.0.1"
LOG_ENV = "DEV_MCP_SERVER_LOG"
SCENARIOS = ("two-tools", "empty", "error", "paginated", "empty-cursor", "big-first-page", "uneven-pages", "fail-second", "slow", "exit-early",
             "cursor-loop", "endless", "secrets", "unicode", "sparse", "bad-header", "invalid-schema")


def _echo_tool() -> types.Tool:
    return types.Tool(
        name="echo_text",
        description="Echo the given text back unchanged.",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Text to echo back"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    )


def _add_tool() -> types.Tool:
    return types.Tool(
        name="add_numbers",
        description="Add two integers and return their sum.",
        input_schema={
            "type": "object",
            "properties": {
                "a": {"type": "integer", "description": "First addend"},
                "b": {"type": "integer", "description": "Second addend"},
            },
            "required": ["a", "b"],
            "additionalProperties": False,
        },
    )


def _plain(name: str, **kw: Any) -> types.Tool:
    return types.Tool(name=name, input_schema={"type": "object"}, **kw)


def _log(event: dict[str, Any]) -> None:
    path = os.environ.get(LOG_ENV)
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
        f.flush()


def _pages(scenario: str) -> list[tuple[list[types.Tool], str | None]]:
    """시나리오가 돌려줄 페이지 목록: (Tool 목록, 다음 커서)."""
    if scenario == "empty":
        return [([], None)]
    if scenario == "paginated":
        return [([_echo_tool()], "page-2"), ([_add_tool()], None)]
    if scenario == "empty-cursor":
        return [([_echo_tool()], ""), ([_add_tool()], None)]
    if scenario == "fail-second":
        return [([_echo_tool()], "page-2"), ([_add_tool()], None)]
    if scenario == "big-first-page":
        return [([_echo_tool(), _add_tool()], "page-2"), ([_plain("third_tool", description="Third tool used only by limit scenarios.")], None)]
    if scenario == "uneven-pages":
        return [([_echo_tool()], "page-2"),
                ([_add_tool(), _plain("third_tool", description="Third tool used only by limit scenarios.")], None)]
    if scenario == "unicode":
        return [([types.Tool(name="read_notes", description="노트를 읽습니다 😀 café — 한글·이모지·é 보존 확인",
                             input_schema={"type": "object", "properties": {"제목": {"type": "string", "description": "노트 제목 😀"}}}),
                  _add_tool()], None)]
    if scenario == "sparse":
        return [([_plain("bare_tool"), _echo_tool()], None)]
    if scenario == "bad-header":
        bad = types.Tool(name="bad_header_tool", description="Tool whose x-mcp-header annotation is invalid.", input_schema={
            "type": "object", "properties": {"region": {"type": "string", "x-mcp-header": "Bad Header"}}})
        return [([bad, _add_tool()], None)]
    if scenario == "secrets":
        tool = types.Tool(
            name="deploy_service",
            description="Deploy using Bearer FAKE_LIVE_BEARER and ghp_FAKELIVEGITHUBTOKEN12345 (https://u:FAKE_LIVE_URLPASS@api.example.test/x?token=FAKE_LIVE_QUERY).",
            input_schema={
                "$id": "https://u:FAKE_LIVE_ID_PASS@example.test/schema?token=FAKE_LIVE_ID_QUERY",
                "type": "object",
                "properties": {"api_key": {"type": "string", "default": "FAKE_LIVE_DEFAULT_SECRET"},
                               "ghp_FAKELIVEPROPERTY1234567890123456": {"type": "string"}},
            },
            meta={"api_key": "FAKE_LIVE_META_SECRET", "vendor": "acme"},
        )
        return [([tool, _add_tool()], None)]
    return [([_echo_tool(), _add_tool()], None)]


def build_server(scenario: str) -> Server[Any]:
    pages = _pages(scenario)

    async def on_list_tools(ctx: Any, params: types.PaginatedRequestParams | None) -> types.ListToolsResult:
        cursor = params.cursor if params is not None else None
        if scenario == "error":
            raise MCPError(types.INTERNAL_ERROR, "simulated server error")
        if scenario == "slow":
            await anyio.sleep(3600)
        if scenario == "exit-early":
            os._exit(3)
        if scenario == "cursor-loop":
            return types.ListToolsResult(tools=[_plain(f"loop_tool_{0 if cursor is None else 1}")], next_cursor="same-cursor",
                                         ttl_ms=0, cache_scope="private")
        if scenario == "endless":
            n = 0 if cursor is None else int(cursor.removeprefix("n-"))
            return types.ListToolsResult(tools=[_plain(f"endless_tool_{n}")], next_cursor=f"n-{n + 1}",
                                         ttl_ms=0, cache_scope="private")
        if cursor is None:
            index = 0
        elif scenario in ("paginated", "empty-cursor", "fail-second", "big-first-page", "uneven-pages") and cursor in ("page-2", ""):
            index = 1
        else:
            raise MCPError(types.INVALID_PARAMS, "Invalid cursor")
        if scenario == "fail-second" and index == 1:
            raise MCPError(types.INTERNAL_ERROR, "simulated failure on the second page")
        tools, next_cursor = pages[index]
        return types.ListToolsResult(tools=tools, next_cursor=next_cursor, ttl_ms=0, cache_scope="private")

    async def on_call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        # 스캐너는 tools/call을 보내지 않아야 한다. 오면 기록(미들웨어)하고 오류를 돌려준다.
        raise MCPError(types.METHOD_NOT_FOUND, "tools/call is not supported by this development server")

    server: Server[Any] = Server(SERVER_NAME, version=SERVER_VERSION, on_list_tools=on_list_tools, on_call_tool=on_call_tool)

    async def log_request(ctx: Any, call_next: Any) -> Any:
        event: dict[str, Any] = {"event": "request", "method": ctx.method}
        if ctx.method == "tools/list":
            raw = (ctx.params or {}).get("cursor") if ctx.params else None
            event["cursor"] = "absent" if raw is None else ("empty" if raw == "" else "present")
        _log(event)
        return await call_next(ctx)

    server.middleware.insert(0, log_request)
    return server


class _TamperWrite:
    """`invalid-schema` 시나리오 전용: 서버 SDK가 응답을 검증한 **뒤** 전송 직전에 응답을 규격 위반으로 바꾼다."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def send(self, item: Any) -> None:
        message = getattr(item, "message", None)
        result = getattr(message, "result", None)
        if isinstance(result, dict) and isinstance(result.get("tools"), list) and result["tools"]:
            result["tools"][0]["inputSchema"]["type"] = "string"
        await self._inner.send(item)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def __aenter__(self) -> "_TamperWrite":
        await self._inner.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> Any:
        return await self._inner.__aexit__(*exc)


async def _serve(scenario: str) -> None:
    _log({"event": "start", "pid": os.getpid(), "scenario": scenario})
    server = build_server(scenario)
    try:
        async with stdio_server() as (read_stream, write_stream):
            if scenario == "invalid-schema":
                write_stream = _TamperWrite(write_stream)
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        _log({"event": "stop", "pid": os.getpid()})


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m asset_scanner.dev_mcp_server",
                                description="스캐너 검증용 개발 MCP 서버 (stdio, 외부 접근 없음)")
    p.add_argument("--scenario", choices=SCENARIOS, default="two-tools", help="검증용 동작 (기본: two-tools)")
    args = p.parse_args(argv)
    anyio.run(_serve, args.scenario)
    return 0


if __name__ == "__main__":
    sys.exit(main())
