"""명시적으로 선택한 MCP 서버 하나에 연결해 Tool·Resource·ResourceTemplate·Prompt **목록**을 실제로 조회한다 (4단계, 내부 개발용 초안).

    # 1) 내장 시험 서버 (stdio 또는 로컬 HTTP + 가짜 인증)
    python -m asset_scanner.live_discovery --demo-stdio [--scenario full] --output OUT
    python -m asset_scanner.live_discovery --demo-http [--scenario full] [--demo-auth fake|none] --output OUT
    # 2) OpenClaw 설정에 선언된 서버 하나를 **키로 지정**하고 실행·접속을 명시적으로 허용
    python -m asset_scanner.live_discovery --config FILE --server KEY --allow-launch --output OUT              # stdio 명령 실행
    python -m asset_scanner.live_discovery --config FILE --server KEY --allow-connect [--allow-host H] [--bearer-env VAR] --output OUT   # HTTP

**이 명령은 서버 프로세스를 실행하거나 네트워크에 접속한다.** 설정 안의 서버를 자동으로 고르거나 모두 실행하지 않는다.
설정 서버는 `--server`로 하나를 지정하고 `--allow-launch`(stdio) 또는 `--allow-connect`(HTTP)를 줘야만 움직인다. HTTP는 기본적으로
루프백(127.0.0.1·::1·localhost)만 허용하고 다른 호스트는 `--allow-host`로 정확히 그 호스트를 적어야 한다.

원격 HTTPS (Streamable HTTP): 루프백이 아닌 호스트는 **https만** 허용한다(평문 http로 인증정보를 보내지 않음). TLS 인증서 체인과 호스트 이름 검증은 항상
켜져 있고 끄는 옵션이 없다. 사설 CA는 `--ca-bundle`로 **추가 신뢰**할 수 있다(검증은 그대로 유지). 인증값은 `--bearer-env 환경변수이름`(Authorization: Bearer)
또는 `--auth-header-env 헤더이름=환경변수이름`으로 실행 중에만 환경에서 읽고 이름만 기록한다. 같은 출처(스킴·호스트·포트)가 아닌 요청은 보내기 전에 막고
(`cross_origin_request_blocked`), 서버의 리다이렉트는 따라가지 않아 인증 헤더가 다른 호스트로 전달되지 않는다. 프록시·인증서 관련 환경변수(HTTPS_PROXY,
SSL_CERT_FILE 등)는 읽지 않는다. OAuth 로그인과 SSE는 지원하지 않으며(`scope.support_status`) 후속 작업이다.

보내는 요청은 연결·초기화(SDK 기본 흐름)와 `tools/list`·`resources/list`·`resources/templates/list`·`prompts/list`뿐이다.
`tools/call`·`resources/read`·`prompts/get` 등 다른 요청은 코드의 허용 목록(`ALLOWED_LIST_METHODS`)이 보내기 전에 막는다.
서버가 `tools`/`resources`/`prompts` 능력을 선언하지 않은 목록은 요청하지 않고 `not_performed`로 둔다(`--request-undeclared`로 시도할 수 있음).

해석·가림·상태 구분은 저장된 응답 읽기와 같은 코드를 쓴다: Tool은 `tools_catalog`, 나머지는 `resources_prompts`.
상태: complete(빈 목록 포함) / partial / failed / unsupported(첫 응답이 -32601) / not_performed.
통신 지원 버전(SDK)과 응답을 읽을 수 있는 버전(파서)을 구분해 기록한다. 인증 토큰은 파일·로그·표준출력에 남기지 않는다.
종료 코드: 0 완전, 1 부분, 2 인자 오류, 3 실패(읽은 목록 없음 또는 대상 거부), 4 저장 실패.
"""

from __future__ import annotations

import argparse
import contextlib
import ipaddress
import json
import math
import os
import re
import secrets
import socket
import ssl
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import anyio
import httpx2
import mcp_types as types
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp_types import version as mcp_version
from pydantic import TypeAdapter, ValidationError

from . import __version__
from . import resources_prompts as rp
from .cli import _make_console_output_safe
from .collector import CollectionFailure, SUPPORTED_REGISTRY_PATHS, dotted_path, json_pointer, parse_config, read_config
from .dev_lists_server import SCENARIOS, TOKEN_ENV
from .live_tools import (LiveLimits as _ToolLimits, _leaf_error_types, _mark_nonfinite, _mcp_error_in, _validation_summary, sdk_version,
                         validate_limits as _validate_tool_limits)
from .output import OutputError, normalize_for_output, write_json_atomic
from .redaction import Redactor, classify_secret_ref
from .tools_catalog import (EXIT_BY_STATUS, EXIT_OUTPUT_ERROR, LEGACY_PROTOCOL_VERSION, MAX_TOOLS_PER_SERVER, SUPPORTED_PROTOCOL_VERSION,
                            SUPPORTED_PROTOCOL_VERSIONS, _collect_server as _collect_tools_server, _issue as _tools_issue, _sanitize, _short, _text,
                            build_catalog_report, summarize_collection as _summarize_catalog)

FORMAT_NAME = "agent-scope.scanner.mcp-live-discovery"
FORMAT_VERSION = "0.1.0-draft"
_RAW_DICT = TypeAdapter(dict)
LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")
DEMO_MODULE = "asset_scanner.dev_lists_server"
DEMO_REF = "dev-lists-server"

_HEADER_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,63}$")
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
# 프로토콜·전송 계층이 정하는 헤더는 사용자가 바꿀 수 없다.
FORBIDDEN_HEADER_NAMES = frozenset({"host", "content-length", "content-type", "transfer-encoding", "connection", "upgrade", "te", "trailer", "accept",
                                    "accept-encoding", "proxy-authorization", "proxy-authenticate", "mcp-session-id", "mcp-protocol-version", "origin"})
SUPPORT_STATUS = {
    "streamable_http": "supported",
    "https_tls_verification": "supported (always on; no option to disable)",
    "bearer_and_header_auth_from_environment": "supported",
    "oauth_login": "not_supported (follow-up work; refused with oauth_not_supported)",
    "sse_transport": "not_supported (follow-up work; refused with transport_not_supported)",
}

# 이 모듈이 서버에 보낼 수 있는 목록 요청. 이 밖의 요청 객체는 `_send`가 보내기 전에 막는다.
ALLOWED_LIST_METHODS = frozenset({"tools/list", "resources/list", "resources/templates/list", "prompts/list"})
FORBIDDEN_EXAMPLES = ("tools/call", "resources/read", "prompts/get", "resources/subscribe", "completion/complete")

# 목록 정의: (키, 요청 클래스, 결과 배열 이름, 능력 이름)
LIST_ORDER = (
    ("tools", types.ListToolsRequest, "tools", "tools"),
    ("resources", types.ListResourcesRequest, "resources", "resources"),
    ("resource_templates", types.ListResourceTemplatesRequest, "resourceTemplates", "resources"),
    ("prompts", types.ListPromptsRequest, "prompts", "prompts"),
)

NOT_VERIFIED = [
    "tools_call", "resources_read", "prompts_get",   # 이 모듈은 목록만 요청한다
    "authorization",                                  # 가짜/사용자 제공 Bearer 토큰으로 접속했을 뿐 권한 범위를 확인하지 않았다
    "server_authenticity_beyond_tls",                 # TLS는 인증서 체인·호스트 이름만 검증한다. 서버가 의도한 대상인지는 별도 확인 사항
    "oauth_flow",                                     # OAuth 대화형 흐름은 지원하지 않는다
    "wire_level_raw_json",                            # JSON 파싱은 SDK가 했으므로 중복 키·NaN 토큰 원문은 확인하지 못함
    "team_testbed",                                   # 팀 테스트베드 검증이 아니다
    "exposure", "callability",                        # Agent 노출·호출 가능 여부
    "current_server_state",                           # 조회 시점 이후의 변경
    "common_server_id",
]


@dataclass
class DiscoveryLimits:
    total_timeout_s: float = 60.0
    request_timeout_s: float = 15.0
    connect_timeout_s: float = 20.0     # 시험 HTTP 서버가 포트를 열 때까지 기다리는 시간
    max_pages: int = 50                 # 목록 하나당
    max_items: int = MAX_TOOLS_PER_SERVER   # 목록 하나당 보존할 항목 수 (최종 페이지 포함 누적)


def validate_limits(limits: DiscoveryLimits) -> list[str]:
    """서버를 실행·접속하기 **전에** 검사한다. `live_tools`와 같은 규칙을 그대로 쓴다."""
    problems = _validate_tool_limits(_ToolLimits(limits.total_timeout_s, limits.request_timeout_s, limits.max_pages, limits.max_items))
    problems = [p.replace("max_tools", "max_items") for p in problems]
    ct = limits.connect_timeout_s
    if not (isinstance(ct, (int, float)) and not isinstance(ct, bool) and math.isfinite(ct) and 0 < ct <= 3600):
        problems.append("connect_timeout_s: 0보다 크고 3600 이하인 유한한 수여야 합니다")
    return problems


@dataclass
class _ListState:
    pages: list = field(default_factory=list)
    kept: int = 0
    exclusions: list[dict] = field(default_factory=list)
    sent: int = 0
    failure: dict | None = None
    not_performed: str | None = None      # 요청하지 않은 이유
    finished: bool = False

    def fail(self, code: str, message: str, **extra: Any) -> None:
        if self.failure is None:
            self.failure = {"code": code, "message": message, **extra}


@dataclass
class _State:
    lists: dict[str, _ListState] = field(default_factory=lambda: {k: _ListState() for k, *_ in LIST_ORDER})
    negotiated: str | None = None
    server_info: Any = None
    capabilities: Any = None
    connect_failure: dict | None = None
    session_dead: bool = False
    http_statuses: list[int] = field(default_factory=list)   # HTTP 응답 상태 코드 숫자만 (본문·헤더는 보지 않는다)
    transport_error: dict | None = None                       # 전송 계층 오류 분류(TLS·연결). 예외 메시지 원문은 저장하지 않는다
    cross_origin_blocked: int = 0
    requests_by_method: dict[str, int] = field(default_factory=dict)
    teardown_error_types: list[str] = field(default_factory=list)
    finished_listing: bool = False


# ---- 대상 ---------------------------------------------------------------------------------

@dataclass
class Target:
    kind: str                   # demo_stdio | demo_http | config_stdio | config_http
    transport: str              # stdio | streamable-http
    description: dict
    refused: dict | None = None
    stdio: StdioServerParameters | None = None
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    child_cmd: list[str] | None = None
    child_env: dict[str, str] = field(default_factory=dict)
    declaration: dict | None = None
    link: dict | None = None
    ssl_context: ssl.SSLContext | None = None   # https 대상: 인증서 체인·호스트 이름 검증이 켜진 컨텍스트 (메모리에만 존재)


def _refuse(kind: str, code: str, message: str, description: dict | None = None, declaration: dict | None = None, followup: str | None = None) -> Target:
    refused = {"code": code, "message": message}
    if followup:
        refused["followup"] = followup      # 지원하지 않는 기능: 별도 후속 작업으로 남아 있음
    return Target(kind=kind, transport="unknown", description=description or {}, refused=refused, declaration=declaration)


def build_ssl_context(ca_bundle: Path | None) -> ssl.SSLContext:
    """TLS 검증이 켜진 컨텍스트. 시스템 신뢰 저장소에 선택적으로 사설 CA를 **더한다**. 검증을 끄는 경로는 없다."""
    ctx = ssl.create_default_context()      # CERT_REQUIRED + check_hostname=True
    if ca_bundle is not None:
        ctx.load_verify_locations(cafile=str(ca_bundle))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    if ctx.verify_mode != ssl.CERT_REQUIRED or not ctx.check_hostname:      # 방어: 기본값이 바뀌어도 검증이 꺼진 채 쓰지 않는다
        raise ssl.SSLError("TLS verification is not enabled")
    return ctx


def _set_header(headers: dict[str, str], name: str, value: str) -> None:
    for k in [k for k in headers if k.lower() == name.lower()]:
        del headers[k]
    headers[name] = value


def build_demo_target(http: bool, scenario: str, auth: str, request_log: Path | None) -> Target:
    env = {"PYTHONUTF8": "1"}
    if request_log is not None:
        env["DEV_MCP_SERVER_LOG"] = str(request_log)
    root = str(Path(__file__).resolve().parent.parent)
    desc = {"kind": "dev_lists_server", "module": DEMO_MODULE, "scenario": scenario, "team_testbed": False,
            "command_origin": "스캐너에 내장된 시험 서버 (OpenClaw 설정에서 읽은 명령이 아님)"}
    if not http:
        params = StdioServerParameters(command=sys.executable, args=["-m", DEMO_MODULE, "--scenario", scenario], env=env, cwd=root)
        return Target("demo_stdio", "stdio", desc, stdio=params)
    desc["host"] = "127.0.0.1"
    desc["auth"] = "fake_bearer_generated_at_run" if auth == "fake" else "none"
    headers: dict[str, str] = {}
    if auth == "fake":
        token = secrets.token_urlsafe(24)       # 실행 때 만든 가짜 토큰: 환경변수와 요청 헤더로만 쓰이고 어디에도 기록하지 않는다
        env[TOKEN_ENV] = token
        headers["Authorization"] = f"Bearer {token}"
    cmd = [sys.executable, "-m", DEMO_MODULE, "--scenario", scenario, "--transport", "http"] + (["--require-bearer"] if auth == "fake" else [])
    return Target("demo_http", "streamable-http", desc, headers=headers, child_cmd=cmd, child_env=env)


def _has_ref(value: Any) -> bool:
    """문자열의 `${...}`, SecretRef 모양 객체, `$include`가 있으면 True (해석하지 않으므로 실행·접속에 쓸 수 없다)."""
    if isinstance(value, str):
        return "${" in value
    if isinstance(value, dict):
        kind, _ = classify_secret_ref(value)
        if kind in ("valid", "invalid") or "$include" in value:
            return True
        return any(_has_ref(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_ref(v) for v in value)
    return False


def build_config_target(config: Path, key: str, registry_label: str, allow_launch: bool, allow_connect: bool,
                        allow_hosts: list[str], bearer_env: str | None, ca_bundle: Path | None = None,
                        auth_header_env: list[str] | None = None) -> Target:
    """설정에서 **지정한 키 하나**의 선언을 읽어 대상을 만든다. 해석할 수 없는 참조나 허용하지 않은 동작이면 거부한다(실행·접속 없음)."""
    reg = SUPPORTED_REGISTRY_PATHS[registry_label]
    try:
        root = parse_config(read_config(config))
    except CollectionFailure as fail:
        return _refuse("config", f"config_{fail.reason['code']}", fail.reason["message"])
    node: Any = root
    for p in reg:
        node = node.get(p) if isinstance(node, dict) else None
    entry = node.get(key) if isinstance(node, dict) else None
    decl_path = dotted_path(reg + (key,))
    declaration = {"basis": "operator_selected_declaration", "registry_path": registry_label, "registration_key": key,
                   "declaration_path": decl_path, "declaration_pointer": json_pointer(reg + (key,)),
                   "source_path": str(config), "name_matching_used": False,
                   "note": "사용자가 지정한 키의 선언이다. 이름이 같다는 이유로 다른 선언과 합치지 않았다."}
    if not isinstance(entry, dict):
        return _refuse("config", "declaration_not_found", "지정한 키의 서버 선언을 설정에서 찾지 못했습니다.", declaration=declaration)
    if _has_ref(entry):
        return _refuse("config", "unresolved_reference",
                       "선언에 해석하지 않는 참조(${VAR}, SecretRef, $include)가 있어 실행·접속에 쓸 수 없습니다. 참조를 해석하지 않으므로 거부합니다.",
                       declaration=declaration)
    red = Redactor()
    has_cmd, has_url = isinstance(entry.get("command"), str), isinstance(entry.get("url"), str)
    if has_cmd == has_url:
        return _refuse("config", "ambiguous_or_missing_target", "command와 url 중 정확히 하나가 문자열로 선언돼야 합니다.", declaration=declaration)
    if has_cmd:
        if not allow_launch:
            return _refuse("config_stdio", "launch_not_allowed", "stdio 서버 실행은 --allow-launch를 줘야 합니다. 실행하지 않았습니다.", declaration=declaration)
        args = entry.get("args", [])
        env = entry.get("env", {})
        if not (isinstance(args, list) and all(isinstance(a, str) for a in args)) or not (isinstance(env, dict) and all(isinstance(v, str) for v in env.values())):
            return _refuse("config_stdio", "declaration_type_invalid", "args는 문자열 배열, env는 문자열 값의 객체여야 합니다.", declaration=declaration)
        cwd = entry.get("cwd") or entry.get("workingDirectory")
        params = StdioServerParameters(command=entry["command"], args=list(args), env=dict(env) or None, cwd=cwd if isinstance(cwd, str) else None)
        desc = {"kind": "config_declared_stdio", "command": red.sanitize_string(entry["command"], "command"),
                "args": red.sanitize_args(list(args), "args"), "env_names": list(env), "cwd_declared": isinstance(cwd, str),
                "command_origin": "OpenClaw 설정의 선언 (사용자가 키로 지정하고 --allow-launch로 실행을 허용함)", "team_testbed": False}
        return Target("config_stdio", "stdio", desc, stdio=params, declaration=declaration)
    if not allow_connect:
        return _refuse("config_http", "connect_not_allowed", "HTTP 접속은 --allow-connect를 줘야 합니다. 접속하지 않았습니다.", declaration=declaration)
    if entry.get("transport") not in (None, "streamable-http"):
        return _refuse("config_http", "transport_not_supported", "streamable-http만 지원합니다 (sse 등은 지원하지 않으며 후속 작업입니다).",
                       declaration=declaration, followup="sse_transport")
    if "oauth" in entry or entry.get("auth") == "oauth":
        return _refuse("config_http", "oauth_not_supported", "OAuth 대화형 흐름은 지원하지 않습니다(후속 작업). 접속하지 않았습니다.",
                       declaration=declaration, followup="oauth_login")
    try:
        parts = urlsplit(entry["url"])
        host = parts.hostname
        _ = parts.port
    except ValueError:
        return _refuse("config_http", "url_invalid", "url을 해석하지 못했습니다.", declaration=declaration)
    if parts.scheme not in ("http", "https") or not host:
        return _refuse("config_http", "url_scheme_not_supported", "http 또는 https URL만 지원합니다.", declaration=declaration)
    if parts.username or parts.password:
        return _refuse("config_http", "url_userinfo_not_supported", "URL 안의 사용자정보는 사용하지 않습니다.", declaration=declaration)
    if host.lower() not in LOOPBACK_HOSTS and host.lower() not in [h.lower() for h in allow_hosts]:
        return _refuse("config_http", "host_not_allowed",
                       "루프백이 아닌 호스트입니다. 접속하려면 --allow-host로 정확히 그 호스트를 지정해야 합니다. 접속하지 않았습니다.",
                       description={"host": host}, declaration=declaration)
    loopback = host.lower() in LOOPBACK_HOSTS
    if parts.scheme == "http" and not loopback:
        return _refuse("config_http", "insecure_remote_http",
                       "루프백이 아닌 호스트에는 평문 http로 접속하지 않습니다(인증정보가 평문으로 전달됨). https를 쓰세요. 접속하지 않았습니다.",
                       description={"host": host}, declaration=declaration)
    ctx: ssl.SSLContext | None = None
    if ca_bundle is not None and parts.scheme != "https":
        return _refuse("config_http", "ca_bundle_requires_https", "--ca-bundle은 https 대상에만 쓸 수 있습니다.", declaration=declaration)
    if parts.scheme == "https":
        if ca_bundle is not None and not ca_bundle.is_file():
            return _refuse("config_http", "ca_bundle_not_found", "--ca-bundle이 가리키는 파일이 없습니다. 접속하지 않았습니다.", declaration=declaration)
        try:
            ctx = build_ssl_context(ca_bundle)
        except (ssl.SSLError, OSError, ValueError):
            return _refuse("config_http", "ca_bundle_invalid", "--ca-bundle을 인증서 PEM으로 읽지 못했습니다. 접속하지 않았습니다.", declaration=declaration)
    headers: dict[str, str] = {}
    cfg_headers = entry.get("headers", {})
    if not (isinstance(cfg_headers, dict) and all(isinstance(v, str) for v in cfg_headers.values())):
        return _refuse("config_http", "declaration_type_invalid", "headers는 문자열 값의 객체여야 합니다.", declaration=declaration)
    headers.update(cfg_headers)
    if bearer_env:
        token = os.environ.get(bearer_env)
        if not token:
            return _refuse("config_http", "bearer_env_not_set", "--bearer-env가 가리키는 환경변수가 비어 있어 접속하지 않았습니다.", declaration=declaration)
        _set_header(headers, "Authorization", f"Bearer {token}")
    env_headers: list[dict] = []
    for spec_text in auth_header_env or []:
        hname, sep, ename = spec_text.partition("=")
        if not sep or not _HEADER_NAME_RE.match(hname) or not _ENV_NAME_RE.match(ename):
            return _refuse("config_http", "auth_header_env_invalid", "--auth-header-env는 '헤더이름=환경변수이름' 형식이어야 합니다.", declaration=declaration)
        if hname.lower() in FORBIDDEN_HEADER_NAMES:
            return _refuse("config_http", "auth_header_name_forbidden", "프로토콜·전송 계층이 정하는 헤더 이름은 쓸 수 없습니다.", declaration=declaration)
        if any(h.lower() == hname.lower() for h in headers) or any(e["header"].lower() == hname.lower() for e in env_headers):
            return _refuse("config_http", "duplicate_auth_header", "같은 헤더가 이미 선언되었거나 중복 지정되었습니다.", declaration=declaration)
        value = os.environ.get(ename)
        if not value:
            return _refuse("config_http", "auth_header_env_not_set", "--auth-header-env가 가리키는 환경변수가 비어 있어 접속하지 않았습니다.", declaration=declaration)
        headers[hname] = value
        env_headers.append({"header": hname, "env": ename})      # 이름만 기록한다
    auth_kinds = [k for k, on in (("bearer_from_env_var", bool(bearer_env)), ("header_from_env_var", bool(env_headers)),
                                  ("declared_headers", bool(cfg_headers))) if on]
    desc = {"kind": "config_declared_http", "host": host, "scheme": parts.scheme, "port": parts.port,
            "url": red.sanitize_url(entry["url"], "url"), "header_names": sorted(headers), "auth": "+".join(auth_kinds) or "none",
            "bearer_env_name": bearer_env, "auth_header_env": env_headers, "allowed_by": "loopback" if loopback else "--allow-host",
            "command_origin": "OpenClaw 설정의 선언 (사용자가 키로 지정하고 --allow-connect로 접속을 허용함)", "team_testbed": False}
    if ctx is not None:
        desc["tls"] = {"verify_certificate_chain": True, "verify_hostname": True, "can_be_disabled": False, "minimum_version": "TLSv1.2",
                       "trust": "system_default+custom_ca_bundle" if ca_bundle else "system_default", "ca_bundle_set": ca_bundle is not None}
    return Target("config_http", "streamable-http", desc, url=entry["url"], headers=headers, declaration=declaration, ssl_context=ctx)


# ---- 통신 ---------------------------------------------------------------------------------

def decide_listing(negotiated: str | None) -> dict:
    """협상된 버전으로 목록을 요청·해석할 수 있는지. SDK의 통신 지원 범위와 응답 파서의 지원 범위는 다르다."""
    in_sdk = negotiated in mcp_version.SUPPORTED_PROTOCOL_VERSIONS if negotiated else False
    readable = negotiated in SUPPORTED_PROTOCOL_VERSIONS if negotiated else False
    return {"negotiated": negotiated, "negotiated_supported_by_sdk": in_sdk, "negotiated_readable_by_parser": readable}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_port(port: int, timeout: float, proc: subprocess.Popen) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.15)
    return False


_UNTRUSTED_CODES = frozenset({2, 18, 19, 20, 21})     # X509_V_ERR_*: 발급자를 찾지 못함 / 자체 서명 / 체인 검증 불가
_HOSTNAME_CODES = frozenset({62, 64})                 # HOSTNAME_MISMATCH, IP_ADDRESS_MISMATCH


def _walk_exceptions(exc: BaseException, depth: int = 0, seen: set[int] | None = None):
    seen = seen if seen is not None else set()
    if id(exc) in seen or depth > 20:
        return
    seen.add(id(exc))
    yield exc
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            yield from _walk_exceptions(sub, depth + 1, seen)
    for nxt in (exc.__cause__, exc.__context__):
        if nxt is not None:
            yield from _walk_exceptions(nxt, depth + 1, seen)


def classify_transport_error(exc: BaseException) -> dict | None:
    """전송 계층 예외를 범주로 분류한다. 예외 메시지·인증서 내용·호스트 이름은 저장하지 않고 범주, OpenSSL 검증 코드, 예외 종류 이름만 남긴다."""
    leaves = list(_walk_exceptions(exc))
    names = [type(e).__name__ for e in leaves][:8]
    for e in leaves:
        if isinstance(e, ssl.SSLCertVerificationError):
            code = getattr(e, "verify_code", None)
            cat = ("tls_hostname_mismatch" if code in _HOSTNAME_CODES else "tls_certificate_expired" if code == 10 else
                   "tls_certificate_not_yet_valid" if code == 9 else "tls_certificate_untrusted" if code in _UNTRUSTED_CODES else "tls_certificate_invalid")
            return {"category": cat, "verify_code": code, "error_types": names}
    for e in leaves:
        if isinstance(e, ssl.SSLError):
            return {"category": "tls_error", "verify_code": None, "error_types": names}
    for e in leaves:
        if isinstance(e, ConnectionRefusedError):
            return {"category": "connect_refused", "verify_code": None, "error_types": names}
        if isinstance(e, socket.gaierror):
            return {"category": "dns_failure", "verify_code": None, "error_types": names}
    for e in leaves:
        if type(e).__name__ == "ConnectTimeout" or (isinstance(e, TimeoutError) and not isinstance(e, MCPError)):
            return {"category": "network_connect_timeout", "verify_code": None, "error_types": names}
    for e in leaves:
        if isinstance(e, OSError):
            return {"category": "network_error", "verify_code": None, "error_types": names}
    return None


class _CrossOriginBlocked(Exception):
    """엔드포인트와 출처(스킴·호스트·포트)가 다른 요청: 보내기 전에 막는다."""


def _origin_of(url: str) -> tuple[str, str, int]:
    p = urlsplit(url)
    scheme = (p.scheme or "").lower()
    return scheme, (p.hostname or "").lower(), p.port or (443 if scheme == "https" else 80)


def make_origin_guard(state: "_State", endpoint_url: str) -> Any:
    """요청 이벤트 훅: 엔드포인트와 출처(스킴·호스트·포트)가 다른 요청은 헤더(인증 포함)를 보내기 전에 막는다."""
    endpoint_origin = _origin_of(endpoint_url)

    async def guard_origin(request: Any) -> None:
        if _origin_of(str(request.url)) != endpoint_origin:
            state.cross_origin_blocked += 1
            raise _CrossOriginBlocked()

    return guard_origin


class _RecordingTransport(httpx2.AsyncHTTPTransport):
    """연결·TLS 오류를 분류해 `_State`에 남기고 그대로 다시 던진다. SDK가 예외를 일반 오류로 감싸 원인을 잃기 때문이다."""

    def __init__(self, state: "_State", **kw: Any) -> None:
        super().__init__(**kw)
        self._state = state

    async def handle_async_request(self, request: Any) -> Any:
        try:
            return await super().handle_async_request(request)
        except BaseException as exc:      # noqa: BLE001
            if self._state.transport_error is None:
                self._state.transport_error = classify_transport_error(exc)
            raise


def _wait_closed(port: int, timeout: float) -> bool:
    """포트가 닫힐 때까지 기다린다. 닫혔으면 True."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                pass
        except OSError:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.15)


async def _send(client: Client, state: _State, request: Any, timeout: float) -> dict:
    """허용 목록에 있는 목록 요청만 보낸다. 다른 요청은 보내기 전에 예외로 막는다."""
    method = getattr(request, "method", None)
    if method not in ALLOWED_LIST_METHODS:
        raise PermissionError(f"허용하지 않은 요청: {method}")
    state.requests_by_method[method] = state.requests_by_method.get(method, 0) + 1
    return await client.session.send_request(request, _RAW_DICT, request_read_timeout_seconds=timeout)


async def _list_pages(client: Client, state: _State, ls: _ListState, key: str, req_cls: Any, field_name: str, limits: DiscoveryLimits) -> None:
    cursor: str | None = None
    seen: set[str] = set()
    while True:
        if len(ls.pages) >= limits.max_pages:
            ls.fail("max_pages_reached", f"최대 페이지 수({limits.max_pages})에 도달해 나머지를 요청하지 않았습니다.")
            return
        params = types.PaginatedRequestParams(cursor=cursor) if cursor is not None else None
        ls.sent += 1
        try:
            raw = await _send(client, state, req_cls(params=params), limits.request_timeout_s)
        except MCPError as exc:
            if exc.code == types.REQUEST_TIMEOUT:
                ls.fail("request_timeout", f"{key} 목록 응답을 시간 안에 받지 못했습니다.", page_index=len(ls.pages))
            elif exc.code == types.CONNECTION_CLOSED:
                ls.fail("connection_closed", f"{key} 목록을 기다리는 중 서버 연결이 끊어졌습니다.", page_index=len(ls.pages))
                state.session_dead = True
            else:   # 서버가 보낸 JSON-RPC 오류: 저장된 응답 읽기와 같은 오류 응답 경로로 처리한다 (코드와 가린 메시지만 남음)
                ls.pages.append({"error": {"code": exc.code, "message": exc.message}})
            return
        except ValidationError as exc:
            ls.fail("sdk_validation_rejected", "SDK가 협상한 버전의 스키마로 검증하다 서버 응답을 거부했습니다. 항목 0개가 아닙니다.",
                    page_index=len(ls.pages), validation_errors=_validation_summary(exc))
            return
        page = _mark_nonfinite(raw)
        page_index = len(ls.pages)
        items = page.get(field_name)
        if isinstance(items, list):
            remaining = limits.max_items - ls.kept
            if len(items) > remaining:
                excluded = len(items) - remaining
                ls.exclusions.append({"page_index": page_index, "items_in_response": len(items), "items_kept": remaining, "items_excluded": excluded})
                page[field_name] = items[:remaining]
                ls.kept += remaining
                ls.pages.append(page)
                ls.fail("item_limit_reached", f"항목 수 한도({limits.max_items})를 넘어 이 페이지의 항목 {excluded}개를 보존하지 않았습니다.",
                        page_index=page_index, excluded_items=excluded)
                return
            ls.kept += len(items)
        ls.pages.append(page)
        nxt = raw.get("nextCursor")
        if not isinstance(nxt, str):
            return
        if nxt in seen:
            ls.fail("cursor_repeated", "서버가 이미 사용한 nextCursor를 다시 돌려줘 반복을 멈췄습니다.", page_index=page_index)
            return
        if ls.kept >= limits.max_items:
            ls.fail("item_limit_reached", f"항목 수 한도({limits.max_items})에 도달해 다음 페이지를 요청하지 않았습니다.", page_index=page_index)
            return
        seen.add(nxt)
        cursor = nxt


def _declared(caps: Any, name: str) -> str:
    if caps is None:
        return "unknown"
    return "declared" if getattr(caps, name, None) is not None else "not_declared"


async def _run_session(target: Target, limits: DiscoveryLimits, client_mode: str, request_undeclared: bool, state: _State, port: int | None) -> None:
    errlog = open(os.devnull, "w")
    try:
        try:
            with anyio.fail_after(limits.total_timeout_s):
                async with contextlib.AsyncExitStack() as stack:
                    if target.transport == "stdio":
                        transport = stdio_client(target.stdio, errlog=errlog)
                    else:
                        url = target.url or f"http://127.0.0.1:{port}/mcp"

                        async def record_status(response: Any) -> None:     # SDK는 401을 일반 서버 오류로 감싸므로 상태 코드 숫자만 따로 기록한다
                            if len(state.http_statuses) < 200:
                                state.http_statuses.append(int(response.status_code))

                        guard_origin = make_origin_guard(state, url)

                        # trust_env=False: 프록시·인증서 관련 환경변수(HTTPS_PROXY, SSL_CERT_FILE 등)를 읽지 않는다.
                        # follow_redirects=False: 리다이렉트를 따라가지 않는다 (SDK도 같은 출처의 안전한 리다이렉트만 따른다).
                        rec_transport = _RecordingTransport(state, verify=target.ssl_context if target.ssl_context is not None else True, trust_env=False)
                        hc = await stack.enter_async_context(httpx2.AsyncClient(
                            headers=target.headers, timeout=limits.request_timeout_s, transport=rec_transport, follow_redirects=False, trust_env=False,
                            event_hooks={"request": [guard_origin], "response": [record_status]}))
                        transport = streamable_http_client(url, http_client=hc)
                    client = await stack.enter_async_context(
                        Client(transport, cache=None, mode=client_mode, read_timeout_seconds=limits.request_timeout_s))  # type: ignore[arg-type]
                    state.negotiated = client.protocol_version
                    state.server_info = client.server_info
                    state.capabilities = client.server_capabilities
                    plan = decide_listing(state.negotiated)
                    for key, req_cls, field_name, cap in LIST_ORDER:
                        ls = state.lists[key]
                        if not plan["negotiated_readable_by_parser"]:
                            ls.not_performed = "protocol_version_not_readable_by_parser"
                        elif state.session_dead:
                            ls.not_performed = "session_ended"
                        elif _declared(state.capabilities, cap) == "not_declared" and not request_undeclared:
                            ls.not_performed = "capability_not_declared"
                        else:
                            await _list_pages(client, state, ls, key, req_cls, field_name, limits)
                            ls.finished = True
                    state.finished_listing = True
        except TimeoutError:
            for key, *_ in LIST_ORDER:
                ls = state.lists[key]
                if not ls.finished and ls.not_performed is None:
                    if ls.sent:
                        ls.fail("total_timeout", f"전체 제한 시간({limits.total_timeout_s:g}초)이 지나 조회를 중단했습니다.")
                    else:
                        ls.not_performed = "total_timeout"
            state.connect_failure = state.connect_failure or ({"code": "total_timeout", "message": "전체 제한 시간이 지나 조회를 중단했습니다."}
                                                              if state.negotiated is None else None)
        except Exception as exc:  # noqa: BLE001 - 연결·종료 실패를 traceback 없이 상태로 남긴다
            seen = _leaf_error_types(exc)
            if state.finished_listing:
                state.teardown_error_types = seen
            elif state.negotiated is None:
                mcp_err = _mcp_error_in(exc)
                code = ("connection_closed_before_ready" if mcp_err and mcp_err.code == types.CONNECTION_CLOSED else
                        "connect_timeout" if mcp_err and mcp_err.code == types.REQUEST_TIMEOUT else "connect_failed")
                if state.transport_error is not None:
                    code = state.transport_error["category"]      # TLS 오류(미신뢰 인증서·호스트 불일치·만료)·연결 거부·DNS 실패 등
                elif any(s in (401, 403) for s in state.http_statuses):
                    code = "connect_rejected"      # 인증 거부(HTTP 401·403). 상태 코드는 응답 훅이 기록한 숫자이며 본문은 보지 않는다
                elif any(s in (301, 302, 303, 307, 308) for s in state.http_statuses):
                    code = "redirect_not_followed"      # 리다이렉트를 따라가지 않았다(인증 헤더가 다른 곳으로 가지 않음)
                if state.cross_origin_blocked:
                    code = "cross_origin_request_blocked"
                state.connect_failure = {"code": code, "message": "서버에 연결하지 못했습니다 (연결·초기화 실패).", "error_types": seen,
                                         "http_status_codes": sorted(set(state.http_statuses))}
                if state.transport_error is not None:
                    state.connect_failure["transport"] = {k: v for k, v in state.transport_error.items() if k != "category"}
            else:
                for key, *_ in LIST_ORDER:
                    ls = state.lists[key]
                    if not ls.finished and ls.not_performed is None:
                        ls.fail("session_error", "조회 중 예기치 않은 오류가 발생했습니다.", error_types=seen) if ls.sent else setattr(ls, "not_performed", "session_error")
    finally:
        errlog.close()


# ---- 결과 조립 ----------------------------------------------------------------------------------

def _wire_dump(model: Any, path: str, red: Redactor) -> Any:
    if model is None:
        return None
    return _sanitize(model.model_dump(by_alias=True, mode="json", exclude_unset=True), path, red)


def _tools_list(state: _State, ls: _ListState, ref: str, link: dict, declared: str) -> tuple[dict, dict | None]:
    """Tool 목록: 저장된 응답 읽기와 같은 `tools_catalog` 경로. (정규화한 목록 상태, 카탈로그 서버 항목)"""
    if ls.not_performed is not None:
        return {"kind": "tool", "method": "tools/list", "collection_status": "not_performed", "outcome": ls.not_performed, "item_count": None,
                "declared_capability": declared, "issues": [], "pages": []}, None
    if not ls.pages:
        code = ls.failure["code"] if ls.failure else "no_response"
        issue = _tools_issue("error", code, (ls.failure or {}).get("message", "응답을 받지 못했습니다."),
                             **{k: v for k, v in (ls.failure or {}).items() if k not in ("code", "message")})
        return {"kind": "tool", "method": "tools/list", "collection_status": "failed", "outcome": code, "item_count": None,
                "declared_capability": declared, "issues": [issue], "pages": []}, None
    entry = {"server_ref": ref, "protocol_version": state.negotiated, "pages": ls.pages, **link}
    srv = _collect_tools_server(0, entry, set())
    srv["server_ref_kind"] = "live_session_label"
    srv["negotiated_protocol_version"] = state.negotiated
    srv.pop("declared_protocol_version", None)
    if ls.failure is not None and srv["collection_status"] != "failed":
        srv["issues"].append(_tools_issue("error", ls.failure["code"], ls.failure["message"],
                                          **{k: v for k, v in ls.failure.items() if k not in ("code", "message")}))
        if srv["collection_status"] == "complete":
            srv["collection_status"], srv["outcome"] = "partial", ls.failure["code"]
    for t in srv.get("tools", []):
        t["internal_ref"] = t["internal_ref"].replace("capture-server", "live-session", 1)
    norm = {"kind": "tool", "method": "tools/list", "collection_status": srv["collection_status"], "outcome": srv["outcome"],
            "item_count": srv["tool_count"], "declared_capability": declared, "issues": srv["issues"], "pages": srv["pages"],
            "detail": "tools_catalog_server"}
    return norm, srv


def _resources_list(state: _State, ls: _ListState, kd: Any, declared: str) -> dict:
    if ls.not_performed is not None:
        return rp._not_performed(kd, declared) | {"outcome": ls.not_performed}
    if not ls.pages:
        code = ls.failure["code"] if ls.failure else "no_response"
        out = rp._failed_list(kd, declared, code, (ls.failure or {}).get("message", "응답을 받지 못했습니다."))
        return out
    extra: list[dict] = []
    out = rp._collect_list(kd, {"pages": ls.pages}, state.negotiated, declared, 0, DEMO_REF, extra)
    for it in out["items"]:
        it["internal_ref"] = it["internal_ref"].replace("capture-server", "live-session", 1)
    if ls.failure is not None and out["collection_status"] not in ("failed", "unsupported"):
        out["issues"].append(rp._issue("error", ls.failure["code"], ls.failure["message"],
                                       **{k: v for k, v in ls.failure.items() if k not in ("code", "message")}))
        if out["collection_status"] == "complete":
            out["collection_status"], out["outcome"] = "partial", ls.failure["code"]
    return out


def assemble(target: Target, limits: DiscoveryLimits, state: _State, client_mode: str, request_undeclared: bool, elapsed_ms: int,
             config_scan_ref: str | None, child_info: dict | None) -> dict:
    ref = DEMO_REF if target.kind.startswith("demo") else "selected-server"
    plan = decide_listing(state.negotiated)
    if state.negotiated is None:
        # 연결·협상 전에 끝났다: 요청을 한 번도 보내지 않은 목록은 "응답 없음(failed)"이 아니라 "요청하지 않음"이다.
        why = "target_refused" if target.refused else (state.connect_failure or {}).get("code", "not_connected")
        for ls in state.lists.values():
            if ls.not_performed is None and not ls.sent and not ls.pages:
                ls.not_performed = why
    link: dict[str, Any] = {}
    if target.declaration and config_scan_ref:
        link = {"registration_key": target.declaration["registration_key"], "registry_path": target.declaration["registry_path"],
                "config_scan_ref": config_scan_ref}
    lists: dict[str, dict] = {}
    catalog_server: dict | None = None
    kinds = {kd.key: kd for kd in rp.KINDS}
    for key, _req, _field, cap in LIST_ORDER:
        ls = state.lists[key]
        declared = _declared(state.capabilities, cap)
        if key == "tools":
            lists[key], catalog_server = _tools_list(state, ls, ref, link, declared)
        else:
            lists[key] = _resources_list(state, ls, kinds[key], declared)
        if ls.exclusions:
            lists[key]["limit_exclusions"] = ls.exclusions
    statuses = [v["collection_status"] for v in lists.values()]
    if target.refused:
        status, outcome = "failed", "target_refused"
    elif state.connect_failure and state.negotiated is None:
        status, outcome = "failed", state.connect_failure["code"]
    elif not plan["negotiated_readable_by_parser"]:
        status, outcome = "failed", "protocol_version_not_readable_by_parser"
    else:
        status, outcome = rp._aggregate(lists)[0], rp._aggregate(lists)[1]
    reasons = [{"code": "list_incomplete", "list": k, "list_status": v["collection_status"], "list_outcome": v["outcome"]}
               for k, v in lists.items() if v["collection_status"] in ("partial", "failed", "not_performed")]
    red = Redactor()
    caps_wire = _wire_dump(state.capabilities, "live.capabilities", red)
    report = {
        "source": {"source_kind": "live_mcp_list_query", "evidence_type": "live_protocol_response", "live_server_query": not bool(target.refused) and state.negotiated is not None,
                   "transport": target.transport, "target": target.description,
                   "declaration_link": target.declaration, "dev_target_only": target.kind.startswith("demo"),
                   "child_process": child_info},
        "protocol": {
            "negotiated_protocol_version": state.negotiated, "requested_mode": client_mode,
            "negotiated_supported_by_sdk": plan["negotiated_supported_by_sdk"],
            "negotiated_readable_by_parser": plan["negotiated_readable_by_parser"],
            "sdk": {"package": "mcp", "version": sdk_version(), "communication_versions": list(mcp_version.SUPPORTED_PROTOCOL_VERSIONS),
                    "handshake_versions": list(mcp_version.HANDSHAKE_PROTOCOL_VERSIONS), "modern_versions": list(mcp_version.MODERN_PROTOCOL_VERSIONS)},
            "stored_response_parser_versions": list(SUPPORTED_PROTOCOL_VERSIONS),
            "note": "SDK가 통신(협상)할 수 있는 버전과, 이 스캐너가 목록 응답을 읽을 수 있는 버전은 다릅니다. 파서가 읽지 못하는 버전으로 협상되면 목록을 요청하지 않습니다.",
        },
        "server_info_from_wire": _wire_dump(state.server_info, "live.server_info", red),
        "capabilities_from_wire": caps_wire,
        "lists": lists,
        "collection": {"status": status, "outcome": outcome, "reasons": reasons,
                       "item_counts": {k: v["item_count"] for k, v in lists.items()}},
        "requests": {"by_method": dict(state.requests_by_method), "allowed_list_methods": sorted(ALLOWED_LIST_METHODS),
                     "forbidden_requests_sent": 0, "forbidden_examples_never_sent": list(FORBIDDEN_EXAMPLES),
                     "request_undeclared": request_undeclared},
        "limits": {"total_timeout_s": limits.total_timeout_s, "request_timeout_s": limits.request_timeout_s, "connect_timeout_s": limits.connect_timeout_s,
                   "max_pages_per_list": limits.max_pages, "max_items_per_list": limits.max_items},
        "elapsed_ms": elapsed_ms,
        "redactions": red.redactions,
    }
    tls_desc = target.description.get("tls") if isinstance(target.description, dict) else None
    if tls_desc is not None:
        report["tls"] = {**tls_desc, "error": state.transport_error, "cross_origin_requests_blocked": state.cross_origin_blocked,
                         "redirect_responses_seen": sum(1 for s in state.http_statuses if 300 <= s < 400),
                         "redirects_followed": 0, "env_proxy_and_cert_variables_read": False}
    if target.transport != "stdio":
        counts: dict[str, int] = {}
        for sc in state.http_statuses:
            counts[str(sc)] = counts.get(str(sc), 0) + 1
        report["http"] = {"status_code_counts": counts, "note": "HTTP 응답 상태 코드 횟수만 기록합니다(본문·헤더·토큰은 기록하지 않음)."}
    if state.connect_failure:
        report["connect_failure"] = state.connect_failure
    if target.refused:
        report["target_refused"] = target.refused
    if state.teardown_error_types:
        report["teardown_error_types"] = state.teardown_error_types
    report["_catalog_server"] = catalog_server
    return report


def discover(target: Target, limits: DiscoveryLimits | None = None, *, client_mode: str = "auto", request_undeclared: bool = False,
             config_scan_ref: str | None = None) -> dict:
    limits = limits or DiscoveryLimits()
    problems = validate_limits(limits)
    if problems:
        raise ValueError("잘못된 제한값: " + "; ".join(problems))
    state = _State()
    started = time.monotonic()
    if target.refused:
        return assemble(target, limits, state, client_mode, request_undeclared, 0, config_scan_ref, None)
    child: subprocess.Popen | None = None
    port: int | None = None
    child_info: dict | None = None
    try:
        if target.child_cmd is not None:     # 내장 HTTP 시험 서버를 자식 프로세스로 띄운다 (127.0.0.1)
            port = _free_port()
            env = {**os.environ, **target.child_env}
            child = subprocess.Popen(target.child_cmd + ["--port", str(port)], env=env, cwd=str(Path(__file__).resolve().parent.parent),
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            child_info = {"spawned": True, "pid": child.pid, "bind": "127.0.0.1", "port": port}
            if not _wait_port(port, limits.connect_timeout_s, child):
                state.connect_failure = {"code": "server_not_ready", "message": "시험 HTTP 서버가 제한 시간 안에 포트를 열지 못했습니다."}
        if state.connect_failure is None:
            anyio.run(_run_session, target, limits, client_mode, request_undeclared, state, port)
    finally:
        if child is not None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
            # Windows의 가상환경 python.exe는 실제 서버를 자식으로 띄우는 런처일 수 있다. 포트가 아직 열려 있으면 프로세스 트리를 종료한다.
            closed = _wait_closed(port, 3.0) if port else None
            tree_killed = False
            if port and not closed and sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, check=False)
                tree_killed = True
                closed = _wait_closed(port, 3.0)
            child_info = {**(child_info or {}), "terminated": child.poll() is not None, "exit_code": child.poll(),
                          "port_closed_after_cleanup": closed, "process_tree_killed": tree_killed}
    return assemble(target, limits, state, client_mode, request_undeclared, int((time.monotonic() - started) * 1000), config_scan_ref, child_info)


def build_report(result: dict) -> dict:
    res = {k: v for k, v in result.items() if k != "_catalog_server"}
    return {
        "format": FORMAT_NAME, "format_version": FORMAT_VERSION,
        "format_status": ("스캐너 내부 개발용 초안입니다. 팀 공통 스키마가 아니며 공통 server_id·asset_id는 정하지 않았습니다. "
                          "internal_ref·server_ref는 이 파일 안에서만 쓰는 이름입니다."),
        "producer": {"name": "agent-scope-asset-scanner", "version": __version__},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "scope": {
            "method": "명시적으로 선택한 MCP 서버 하나에 SDK 클라이언트로 연결해 목록 요청만 보냄 (tools/call·resources/read·prompts/get 없음)",
            "not_verified": NOT_VERIFIED,
            "support_status": SUPPORT_STATUS,
            "list_status_meaning": {"complete": "끝까지 읽음(빈 목록 포함)", "partial": "일부만 읽음", "failed": "읽지 못함. 0개가 아님",
                                    "unsupported": "첫 응답이 -32601", "not_performed": "요청하지 않았거나 응답이 없음. 0개도 미지원도 아님"},
            "note": ("lists.*는 실제로 받은 목록 응답의 정의입니다. 조회 성공은 Agent 노출·호출 가능·읽기 가능을 뜻하지 않습니다. "
                     "개발용 시험 서버(dev_target_only: true) 결과를 팀 테스트베드 검증으로 표현하지 않습니다."),
        },
        **res,
    }


def catalog_report(result: dict) -> dict | None:
    """Tool 카탈로그 형식(기존 `linking`이 읽는 형식)의 결과. Tool을 조회한 경우에만 만든다."""
    srv = result.get("_catalog_server")
    if srv is None:
        return None
    collected = {"capture_path": None, "origin": "live_mcp_list_query", "servers": [srv],
                 "collection": _summarize_catalog([srv], None, []),
                 "source": {"source_kind": "live_mcp_list_query", "evidence_type": "live_protocol_response", "live_server_query": True,
                            "transport": result["source"]["transport"], "target": result["source"]["target"]}}
    return build_catalog_report(collected)


# ---- CLI ------------------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m asset_scanner.live_discovery",
                                description="명시적으로 선택한 MCP 서버 하나에 연결해 Tool·Resource·ResourceTemplate·Prompt 목록을 조회합니다 "
                                            "(내부 개발용 초안). 이 명령은 서버 프로세스를 실행하거나 네트워크에 접속합니다.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--demo-stdio", action="store_true", help="내장 시험 서버를 stdio로 실행해 조회")
    g.add_argument("--demo-http", action="store_true", help="내장 시험 서버를 127.0.0.1 HTTP로 실행해 조회")
    g.add_argument("--config", type=Path, help="서버 선언을 읽을 OpenClaw 설정 파일 (--server와 함께)")
    p.add_argument("--server", help="--config에서 조회할 서버의 등록키 (하나만)")
    p.add_argument("--registry-path", choices=sorted(SUPPORTED_REGISTRY_PATHS), default="mcp.servers")
    p.add_argument("--allow-launch", action="store_true", help="선택한 설정 서버의 stdio 명령 실행을 허용")
    p.add_argument("--allow-connect", action="store_true", help="선택한 설정 서버의 HTTP 접속을 허용 (기본은 루프백만)")
    p.add_argument("--allow-host", action="append", default=[], help="루프백이 아닌 접속 허용 호스트 (정확히 일치, 여러 번 가능)")
    p.add_argument("--bearer-env", help="Authorization: Bearer 토큰을 읽을 환경변수 이름 (값은 기록하지 않음)")
    p.add_argument("--auth-header-env", action="append", default=[], metavar="헤더이름=환경변수이름",
                   help="인증 헤더(예: X-Api-Key=MY_KEY_VAR)의 값을 읽을 환경변수 이름 (여러 번 가능, 값은 기록하지 않음)")
    p.add_argument("--ca-bundle", type=Path, help="https 대상이 쓰는 사설 CA 인증서 PEM을 신뢰 저장소에 **추가**로 신뢰 (인증서·호스트 이름 검증은 그대로 켜짐)")
    p.add_argument("--config-scan-ref", help="결과의 config_link.config_scan_ref (linking에서 설정 수집 결과 라벨과 맞출 때)")
    p.add_argument("--scenario", choices=SCENARIOS, default="full", help="내장 시험 서버의 동작")
    p.add_argument("--demo-auth", choices=("fake", "none"), default="fake", help="--demo-http의 인증: fake=실행 때 만든 가짜 Bearer 토큰 필요")
    p.add_argument("--client-mode", choices=("auto", "legacy"), default="auto", help="SDK 연결 방식 (auto: server/discover 우선, legacy: initialize)")
    p.add_argument("--request-undeclared", action="store_true", help="능력을 선언하지 않은 목록도 요청해 본다")
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--request-timeout", type=float, default=15.0)
    p.add_argument("--connect-timeout", type=float, default=20.0)
    p.add_argument("--max-pages", type=int, default=50, help="목록당 최대 페이지 수")
    p.add_argument("--max-items", type=int, default=MAX_TOOLS_PER_SERVER, help=f"목록당 보존할 최대 항목 수 (1~{MAX_TOOLS_PER_SERVER})")
    p.add_argument("--demo-request-log", type=Path, default=None, help="내장 시험 서버가 받은 요청의 메서드 이름만 남길 파일 (검증용)")
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--catalog-output", type=Path, help="Tool 카탈로그 형식의 결과도 저장 (linking 입력용)")
    return p


def main(argv: list[str] | None = None) -> int:
    _make_console_output_safe()
    parser = _parser()
    args = parser.parse_args(argv)
    if args.config and not args.server:
        parser.error("--config에는 --server(등록키 하나)가 필요합니다. 설정의 서버를 모두 조회하지 않습니다.")
    if not args.config and (args.server or args.allow_launch or args.allow_connect or args.allow_host or args.bearer_env or args.ca_bundle or args.auth_header_env):
        parser.error("--server, --allow-*, --bearer-env, --auth-header-env, --ca-bundle은 --config와 함께만 쓸 수 있습니다.")
    limits = DiscoveryLimits(args.timeout, args.request_timeout, args.connect_timeout, args.max_pages, args.max_items)
    problems = validate_limits(limits)
    if problems:
        parser.error("; ".join(problems))
    if args.demo_stdio or args.demo_http:
        target = build_demo_target(bool(args.demo_http), args.scenario, args.demo_auth, args.demo_request_log)
    else:
        target = build_config_target(args.config, args.server, args.registry_path, args.allow_launch, args.allow_connect, args.allow_host, args.bearer_env,
                                     args.ca_bundle, args.auth_header_env)
    if target.refused is None:
        print(f"서버에 연결합니다: {target.description.get('kind')} ({target.transport}) — 목록 요청만 보냅니다 (tools/call·resources/read·prompts/get 없음)")
    result = discover(target, limits, client_mode=args.client_mode, request_undeclared=args.request_undeclared, config_scan_ref=args.config_scan_ref)
    cat = catalog_report(result)
    report, normalized = normalize_for_output(build_report(result))
    if normalized:
        report["collection"]["output_text_normalizations"] = normalized
    try:
        write_json_atomic(args.output, report)
        if args.catalog_output is not None and cat is not None:
            cat, _ = normalize_for_output(cat)
            write_json_atomic(args.catalog_output, cat)
    except OutputError as exc:
        print(f"오류: 결과 파일을 저장하지 못했습니다 ({exc.kind}). 기존 결과 파일은 바꾸지 않았습니다.", file=sys.stderr)
        return EXIT_OUTPUT_ERROR
    col = report["collection"]
    print("실제 MCP 목록 조회 결과" + (" (개발용 시험 서버, 팀 테스트베드 아님)" if report["source"]["dev_target_only"] else ""))
    print(f"협상된 protocol_version: {report['protocol']['negotiated_protocol_version']}  "
          f"(SDK 통신 지원: {report['protocol']['negotiated_supported_by_sdk']}, 파서 지원: {report['protocol']['negotiated_readable_by_parser']})")
    print(f"수집 상태: {col['status']} ({col['outcome']})")
    if report.get("tls"):
        tls = report["tls"]
        print(f"TLS: 인증서 체인·호스트 이름 검증 켜짐(끌 수 없음), 신뢰 저장소 {tls['trust']}" + (f", 오류 {tls['error']['category']}" if tls.get("error") else ""))
    for k, v in report["lists"].items():
        n = "미확인" if v["item_count"] is None else f"{v['item_count']}개"
        print(f"  - {k}: {v['collection_status']}/{v['outcome']} ({n})")
    if report.get("target_refused"):
        print(f"  대상 거부: {report['target_refused']['code']} (실행·접속하지 않음)")
    print(f"보낸 요청: {json.dumps(report['requests']['by_method'])}")
    print(f"결과 저장: {args.output}")
    return EXIT_BY_STATUS[col["status"]]


if __name__ == "__main__":
    sys.exit(main())
