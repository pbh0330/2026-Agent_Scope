"""스캐너 검증용 로컬 MCP 시험 서버 2 (Tool·Resource·ResourceTemplate·Prompt 목록, stdio 또는 로컬 HTTP + 가짜 인증).

    python -m asset_scanner.dev_lists_server [--scenario NAME] [--transport stdio]
    python -m asset_scanner.dev_lists_server --transport http --port N [--require-bearer]

**직접 만든 검증 대상일 뿐** 팀 테스트베드의 서버가 아니다. 외부 계정·인증정보·네트워크 없이 실행되며 HTTP는 `127.0.0.1`에만 바인딩한다.
`tools/call`·`resources/read`·`prompts/get`을 처리하는 핸들러가 없다(스캐너가 보내면 SDK가 오류를 돌려주고 요청 기록에 남는다).

요청 기록: 환경변수 `DEV_MCP_SERVER_LOG`에 파일 경로가 있으면 JSON 한 줄씩 남긴다. 내용은 시작(pid·시나리오·전송 방식),
요청의 메서드 이름과 커서 상태(없음/빈 문자열/있음), HTTP 요청의 인증 결과(ok/missing/bad)뿐이다. 응답 내용·커서 값·토큰은 기록하지 않는다.

가짜 인증: `--require-bearer`이면 환경변수 `DEV_MCP_SERVER_TOKEN`의 값과 같은 `Authorization: Bearer <토큰>` 헤더가 없는 HTTP 요청을
401로 거부한다. 토큰은 스캐너가 실행 때 임의로 만들어 환경변수로만 전달하며 파일·로그에 남지 않는다.

시나리오 (스캐너의 상태 구분·한도·정리를 실제 통신으로 검증하기 위한 동작)
    full             Tool 2, Resource 2(두 페이지), ResourceTemplate 2, Prompt 2 (기본)
    empty-all        네 목록 모두 성공한 빈 목록
    no-prompts       prompts 능력을 광고하지 않는다 (prompts/list 핸들러 없음)
    only-tools       tools 능력만 광고한다
    resources-error  resources/list마다 서버 오류
    templates-mnf    resources 능력은 있으나 resources/templates/list가 Method not found
    fail-second      prompts/list 두 번째 페이지에서 서버 오류
    many             Resource 7개(페이지당 3개), Prompt 5개 (항목·페이지 한도 검증)
    secrets          URI·설명·인자·메타데이터에 가짜 인증정보
    slow-resources   resources/list에 응답하지 않는다 (시간 초과)
    exit-resources   resources/list를 받으면 프로세스를 끝낸다 (연결 끊김)
    same-names       Resource·Template·Prompt·Tool이 같은 이름 `shared`를 쓴다 (합치지 않음 검증)
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import sys
from typing import Any

import anyio
import mcp_types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError

SERVER_NAME = "asset-scanner-dev-lists-server"
SERVER_VERSION = "0.0.1"
LOG_ENV = "DEV_MCP_SERVER_LOG"
TOKEN_ENV = "DEV_MCP_SERVER_TOKEN"
SCENARIOS = ("full", "empty-all", "no-prompts", "only-tools", "resources-error", "templates-mnf", "fail-second", "many", "secrets",
             "slow-resources", "exit-resources", "same-names")


def _log(event: dict[str, Any]) -> None:
    path = os.environ.get(LOG_ENV)
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
        f.flush()


def _tool(name: str, desc: str | None = None) -> types.Tool:
    return types.Tool(name=name, description=desc, input_schema={"type": "object"})


def _tools(sc: str) -> list[types.Tool]:
    if sc == "empty-all":
        return []
    if sc == "same-names":
        return [_tool("shared", "A tool named shared.")]
    return [_tool("echo_text", "Echo the given text back unchanged."), _tool("add_numbers", "Add two integers.")]


def _resource_pages(sc: str) -> list[tuple[list[types.Resource], str | None]]:
    if sc == "empty-all":
        return [([], None)]
    if sc == "many":
        rs = [types.Resource(uri=f"file:///many/{i}.txt", name=f"many-{i}") for i in range(7)]
        return [(rs[0:3], "p2"), (rs[3:6], "p3"), (rs[6:], None)]
    if sc == "same-names":
        return [([types.Resource(uri="file:///shared", name="shared")], None)]
    if sc == "secrets":
        return [([types.Resource(
            uri="https://u:FAKE_LISTS_URLPASS@docs.example.test/x?token=FAKE_LISTS_QUERY", name="secret-doc",
            description="Use Bearer FAKE_LISTS_BEARER and ghp_FAKELISTSGITHUBTOKEN12345 to read.",
            meta={"api_key": "FAKE_LISTS_META_SECRET", "owner": "docs"})], None)]
    return [([types.Resource(uri="file:///docs/readme.md", name="readme", title="README", description="Project README.", mime_type="text/markdown", size=2048)], "page-2"),
            ([types.Resource(uri="file:///docs/guide.md", name="guide", mime_type="text/markdown")], None)]


def _template_pages(sc: str) -> list[tuple[list[types.ResourceTemplate], str | None]]:
    if sc == "empty-all":
        return [([], None)]
    if sc == "same-names":
        return [([types.ResourceTemplate(uri_template="file:///shared/{id}", name="shared")], None)]
    if sc == "secrets":
        return [([types.ResourceTemplate(uri_template="https://u:FAKE_LISTS_TPLPASS@api.example.test/items/{id}{?token}", name="secret-tpl",
                                         description="ghp_FAKELISTSTEMPLATETOKEN123 in text")], None)]
    return [([types.ResourceTemplate(uri_template="file:///docs/{path}", name="docs-by-path", description="Any file under docs.", mime_type="text/plain"),
              types.ResourceTemplate(uri_template="https://api.example.test/items/{id}{?fields}", name="item")], None)]


def _prompt_pages(sc: str) -> list[tuple[list[types.Prompt], str | None]]:
    if sc == "empty-all":
        return [([], None)]
    if sc == "many":
        ps = [types.Prompt(name=f"many-{i}") for i in range(5)]
        return [(ps[0:2], "p2"), (ps[2:4], "p3"), (ps[4:], None)]
    if sc == "same-names":
        return [([types.Prompt(name="shared", description="A prompt named shared.")], None)]
    if sc == "secrets":
        return [([types.Prompt(
            name="secret-prompt", description="Summarize with ghp_FAKELISTSPROMPTTOKEN12345",
            arguments=[types.PromptArgument(name="ghp_FAKELISTSARGNAME1234567890123", description="https://u:FAKE_LISTS_ARGPASS@h.test/x?k=FAKE_LISTS_ARGQ", required=True),
                       types.PromptArgument(name="api_key", description="the key")],
            meta={"token": "FAKE_LISTS_PROMPT_META"})], None)]
    return [([types.Prompt(name="summarize_doc", title="Summarize a document", description="Summarize the given document.",
                           arguments=[types.PromptArgument(name="uri", description="Resource URI", required=True),
                                      types.PromptArgument(name="style", description="Tone", required=False)]),
              types.Prompt(name="plain_prompt")], None)]


def build_server(scenario: str) -> Server[Any]:
    tools_pages = [(_tools(scenario), None)]
    res_pages, tpl_pages, prm_pages = _resource_pages(scenario), _template_pages(scenario), _prompt_pages(scenario)

    def index_for(cursor: str | None, pages: list) -> int:
        """페이지 번호. 두 페이지 목록의 커서는 `page-2`, 세 페이지 목록의 커서는 `p2`·`p3`이다. 그 밖의 커서는 오류."""
        if cursor is None:
            return 0
        labels = ["page-2"] if len(pages) == 2 else ["p2", "p3"] if len(pages) == 3 else []
        if cursor in labels:
            return labels.index(cursor) + 1
        raise MCPError(types.INVALID_PARAMS, "Invalid cursor")

    async def on_list_tools(ctx: Any, params: types.PaginatedRequestParams | None) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tools_pages[0][0], ttl_ms=0, cache_scope="private")

    async def on_list_resources(ctx: Any, params: types.PaginatedRequestParams | None) -> types.ListResourcesResult:
        if scenario == "resources-error":
            raise MCPError(types.INTERNAL_ERROR, "simulated resources/list failure")
        if scenario == "slow-resources":
            await anyio.sleep(3600)
        if scenario == "exit-resources":
            os._exit(3)
        items, nxt = res_pages[index_for(params.cursor if params else None, res_pages)]
        return types.ListResourcesResult(resources=items, next_cursor=nxt, ttl_ms=0, cache_scope="private")

    async def on_list_resource_templates(ctx: Any, params: types.PaginatedRequestParams | None) -> types.ListResourceTemplatesResult:
        if scenario == "templates-mnf":
            raise MCPError(types.METHOD_NOT_FOUND, "resources/templates/list is not supported")
        items, nxt = tpl_pages[index_for(params.cursor if params else None, tpl_pages)]
        return types.ListResourceTemplatesResult(resource_templates=items, next_cursor=nxt, ttl_ms=0, cache_scope="private")

    async def on_list_prompts(ctx: Any, params: types.PaginatedRequestParams | None) -> types.ListPromptsResult:
        idx = index_for(params.cursor if params else None, prm_pages)
        if scenario == "fail-second" and idx >= 1:
            raise MCPError(types.INTERNAL_ERROR, "simulated failure on the second prompts page")
        items, nxt = prm_pages[idx]
        return types.ListPromptsResult(prompts=items, next_cursor=nxt, ttl_ms=0, cache_scope="private")

    if scenario == "fail-second":
        prm_pages = [([types.Prompt(name="first")], "page-2"), ([types.Prompt(name="second")], None)]
    kwargs: dict[str, Any] = {"on_list_tools": on_list_tools}
    if scenario != "only-tools":
        kwargs.update(on_list_resources=on_list_resources, on_list_resource_templates=on_list_resource_templates)
        if scenario != "no-prompts":
            kwargs["on_list_prompts"] = on_list_prompts
    server: Server[Any] = Server(SERVER_NAME, version=SERVER_VERSION, **kwargs)

    async def log_request(ctx: Any, call_next: Any) -> Any:
        event: dict[str, Any] = {"event": "request", "method": ctx.method}
        if ctx.method.endswith("/list"):
            raw = (ctx.params or {}).get("cursor") if ctx.params else None
            event["cursor"] = "absent" if raw is None else ("empty" if raw == "" else "present")
        _log(event)
        return await call_next(ctx)

    server.middleware.insert(0, log_request)
    return server


class _BearerGate:
    """HTTP 요청에 가짜 Bearer 토큰이 있는지 검사하는 ASGI 래퍼. 토큰은 기록하지 않고 결과(ok/missing/bad)만 기록한다."""

    def __init__(self, app: Any, token: str | None) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        auth = headers.get(b"authorization", b"").decode("latin-1")
        if self.token is None:
            verdict = "not_required"
        elif not auth:
            verdict = "missing"
        elif hmac.compare_digest(auth, f"Bearer {self.token}"):
            verdict = "ok"
        else:
            verdict = "bad"
        _log({"event": "http", "http_method": scope.get("method"), "auth": verdict})
        if verdict in ("missing", "bad"):
            body = b'{"error":"unauthorized"}'
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer"),
                                    (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


async def _serve_stdio(scenario: str) -> None:
    _log({"event": "start", "pid": os.getpid(), "scenario": scenario, "transport": "stdio"})
    server = build_server(scenario)
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        _log({"event": "stop", "pid": os.getpid()})


def _serve_http(scenario: str, port: int, require_bearer: bool) -> None:
    import uvicorn
    token = os.environ.get(TOKEN_ENV) if require_bearer else None
    if require_bearer and not token:
        raise SystemExit("--require-bearer에는 환경변수 DEV_MCP_SERVER_TOKEN이 필요합니다.")
    _log({"event": "start", "pid": os.getpid(), "scenario": scenario, "transport": "http", "auth_required": bool(token)})
    app = _BearerGate(build_server(scenario).streamable_http_app(host="127.0.0.1"), token)
    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    finally:
        _log({"event": "stop", "pid": os.getpid()})


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m asset_scanner.dev_lists_server", description="스캐너 검증용 로컬 MCP 시험 서버 2 (외부 접근 없음)")
    p.add_argument("--scenario", choices=SCENARIOS, default="full")
    p.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    p.add_argument("--port", type=int, default=0, help="--transport http일 때 127.0.0.1에서 들을 포트")
    p.add_argument("--require-bearer", action="store_true", help="가짜 Bearer 토큰(환경변수 DEV_MCP_SERVER_TOKEN)이 없는 HTTP 요청을 401로 거부")
    args = p.parse_args(argv)
    if args.transport == "http":
        if not (1 <= args.port <= 65535):
            p.error("--transport http에는 --port (1~65535)가 필요합니다.")
        _serve_http(args.scenario, args.port, args.require_bearer)
    else:
        anyio.run(_serve_stdio, args.scenario)
    return 0


if __name__ == "__main__":
    sys.exit(main())
