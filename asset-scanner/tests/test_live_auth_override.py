"""설정의 인증 헤더 `${VAR}` 참조와 --bearer-env / --auth-header-env 적용 순서 회귀 테스트.

배경(P2 설정 사본): `headers.Authorization: "Bearer ${INVENTORY_MCP_TOKEN}"`가 선언된 서버에 사용자가 같은 헤더의 값을
환경변수 옵션으로 명시적으로 제공해도, 선언 전체를 먼저 검사하는 `unresolved_reference` 때문에 조회가 거부됐다.
실제 원격 서버를 쓰지 않고 로컬 루프백 시험 서버(가짜 토큰)만 사용한다. 값은 모두 가짜다.
"""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from asset_scanner.live_discovery import DiscoveryLimits, build_config_target, build_report, discover
from conftest import SCANNER_ROOT

_REAL_POPEN = subprocess.Popen
FAST = DiscoveryLimits(total_timeout_s=40, request_timeout_s=10, connect_timeout_s=20)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(tmp_path):
    port, log = _free_port(), tmp_path / "server.log.jsonl"
    token = "fake-" + secrets.token_hex(12)
    env = {**os.environ, "DEV_MCP_SERVER_LOG": str(log), "PYTHONUTF8": "1", "DEV_MCP_SERVER_TOKEN": token}
    cmd = [sys.executable, "-m", "asset_scanner.dev_lists_server", "--scenario", "full", "--transport", "http", "--port", str(port), "--require-bearer"]
    proc = _REAL_POPEN(cmd, env=env, cwd=SCANNER_ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(150):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
                break
            except OSError:
                time.sleep(0.2)
        else:
            pytest.fail("시험 서버가 포트를 열지 못했습니다")
        yield SimpleNamespace(port=port, token=token, url=f"http://127.0.0.1:{port}/mcp", log=log)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cfg_with(tmp_path, decl):
    p = tmp_path / "cfg.json5"
    p.write_text(json.dumps({"mcp": {"servers": {"s": decl}}}), encoding="utf-8")
    return p


def target(tmp_path, decl, bearer_env=None, header_envs=None):
    return build_config_target(cfg_with(tmp_path, decl), "s", "mcp.servers", False, True, [], bearer_env, None, header_envs)


def dump(x):
    return json.dumps(x, ensure_ascii=False, default=str)


# ---- 재현: P2 형태의 선언 + 명시적 옵션 ------------------------------------------------------------------

def test_declared_authorization_reference_is_replaced_by_bearer_env_and_collection_works(tmp_path, server, monkeypatch):
    monkeypatch.setenv("TEST_PROVIDED_TOKEN", server.token)
    t = target(tmp_path, {"url": server.url, "transport": "streamable-http",
                          "headers": {"Authorization": "Bearer ${INVENTORY_MCP_TOKEN}"}}, bearer_env="TEST_PROVIDED_TOKEN")
    assert t.refused is None, t.refused
    assert t.headers["Authorization"] == f"Bearer {server.token}"
    result = discover(t, FAST)
    rep = build_report(result)
    assert rep["lists"]["tools"]["collection_status"] == "complete"
    # 인증값은 어디에도 남지 않는다
    assert server.token not in dump(rep) and server.token not in dump(t.description) and server.token not in dump(t.declaration)
    assert "TEST_PROVIDED_TOKEN" in dump(t.description)            # 환경변수 '이름'만


def test_the_two_sources_are_kept_apart_in_the_record(tmp_path, server, monkeypatch):
    monkeypatch.setenv("TEST_PROVIDED_TOKEN", server.token)
    t = target(tmp_path, {"url": server.url, "headers": {"Authorization": "Bearer ${INVENTORY_MCP_TOKEN}"}}, bearer_env="TEST_PROVIDED_TOKEN")
    rec = t.declaration["declared_header_replacements"]
    assert rec == [{"header": "Authorization", "declared_value_kind": "env_ref", "ref_names": ["INVENTORY_MCP_TOKEN"],
                    "provided_by": "--bearer-env", "provided_env_name": "TEST_PROVIDED_TOKEN", "ref_name_matches_provided_env": False,
                    "declared_value_used": False}]


def test_the_same_env_name_is_reported_as_matching(tmp_path, server, monkeypatch):
    monkeypatch.setenv("INVENTORY_MCP_TOKEN", server.token)
    t = target(tmp_path, {"url": server.url, "headers": {"Authorization": "Bearer ${INVENTORY_MCP_TOKEN}"}}, bearer_env="INVENTORY_MCP_TOKEN")
    assert t.declaration["declared_header_replacements"][0]["ref_name_matches_provided_env"] is True


def test_auth_header_env_can_provide_the_same_declared_header(tmp_path, server, monkeypatch):
    monkeypatch.setenv("TEST_PROVIDED_TOKEN", f"Bearer {server.token}")
    t = target(tmp_path, {"url": server.url, "headers": {"Authorization": "Bearer ${INVENTORY_MCP_TOKEN}"}},
               header_envs=["Authorization=TEST_PROVIDED_TOKEN"])
    assert t.refused is None, t.refused
    assert t.declaration["declared_header_replacements"][0]["provided_by"] == "--auth-header-env"
    rep = build_report(discover(t, FAST))
    assert rep["lists"]["tools"]["collection_status"] == "complete"
    assert server.token not in dump(rep)


def test_header_name_matching_is_case_insensitive(tmp_path, server, monkeypatch):
    monkeypatch.setenv("TEST_PROVIDED_TOKEN", server.token)
    t = target(tmp_path, {"url": server.url, "headers": {"authorization": "Bearer ${X}"}}, bearer_env="TEST_PROVIDED_TOKEN")
    assert t.refused is None and list(t.headers) == ["Authorization"]       # 선언 헤더가 남지 않고 하나만 전달


# ---- 기존대로 거부해야 하는 것 --------------------------------------------------------------------------

@pytest.mark.parametrize("decl", [
    {"headers": {"Authorization": "Bearer ${X}"}},                                       # 옵션 없음
    {"headers": {"Authorization": "Bearer ${X}", "X-Other": "${Y}"}},                    # 다른 헤더의 참조
    {"headers": {"Authorization": "Bearer ${X}"}, "env": {"K": "${Z}"}},                 # 다른 필드의 참조
    {"headers": {"Authorization": "Bearer ${X}"}, "args": ["${Z}"]},
    {"headers": {"Authorization": {"source": "env", "provider": "p", "id": "I"}}},       # SecretRef 객체
])
def test_other_unresolved_references_are_still_refused(tmp_path, server, monkeypatch, decl):
    monkeypatch.setenv("TEST_PROVIDED_TOKEN", server.token)
    opt = {} if decl["headers"].get("Authorization") == "Bearer ${X}" and len(decl) == 1 and len(decl["headers"]) == 1 else {"bearer_env": "TEST_PROVIDED_TOKEN"}
    t = target(tmp_path, {"url": server.url, **decl}, **opt)
    assert t.refused is not None and t.refused["code"] in ("unresolved_reference", "declaration_type_invalid")


def test_a_reference_in_the_url_is_still_refused_even_with_the_option(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_PROVIDED_TOKEN", "fake")
    t = target(tmp_path, {"url": "http://127.0.0.1:1/${PATH_VAR}"}, bearer_env="TEST_PROVIDED_TOKEN")
    assert t.refused["code"] == "unresolved_reference"


def test_option_for_a_different_header_does_not_exempt_the_declared_authorization_reference(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_PROVIDED_KEY", "fake")
    t = target(tmp_path, {"url": "http://127.0.0.1:1/mcp", "headers": {"Authorization": "Bearer ${X}"}}, header_envs=["X-Api-Key=TEST_PROVIDED_KEY"])
    assert t.refused["code"] == "unresolved_reference"


def test_missing_or_empty_environment_variable_is_still_refused(tmp_path, monkeypatch):
    monkeypatch.delenv("NO_SUCH_TOKEN_VAR", raising=False)
    decl = {"url": "http://127.0.0.1:1/mcp", "headers": {"Authorization": "Bearer ${X}"}}
    assert target(tmp_path, decl, bearer_env="NO_SUCH_TOKEN_VAR").refused["code"] == "bearer_env_not_set"
    assert target(tmp_path, decl, header_envs=["Authorization=NO_SUCH_TOKEN_VAR"]).refused["code"] == "auth_header_env_not_set"
    monkeypatch.setenv("EMPTY_TOKEN_VAR", "")
    assert target(tmp_path, decl, bearer_env="EMPTY_TOKEN_VAR").refused["code"] == "bearer_env_not_set"


def test_invalid_option_forms_are_still_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_PROVIDED_TOKEN", "fake")
    plain = {"url": "http://127.0.0.1:1/mcp"}
    assert target(tmp_path, plain, header_envs=["Authorization"]).refused["code"] == "auth_header_env_invalid"
    assert target(tmp_path, plain, header_envs=["Bad Name=TEST_PROVIDED_TOKEN"]).refused["code"] == "auth_header_env_invalid"
    assert target(tmp_path, plain, header_envs=["Host=TEST_PROVIDED_TOKEN"]).refused["code"] == "auth_header_name_forbidden"
    # 형식이 틀린 옵션은 값을 제공한 것으로 보지 않으므로 선언된 참조는 대체되지 않고 그대로 거부된다
    ref = {"url": "http://127.0.0.1:1/mcp", "headers": {"Authorization": "Bearer ${X}"}}
    for bad in (["Authorization"], ["Bad Name=TEST_PROVIDED_TOKEN"], ["Authorization=bad name"]):
        assert target(tmp_path, ref, header_envs=bad).refused["code"] == "unresolved_reference"


def test_duplicates_between_the_two_options_and_with_literal_headers_are_still_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_PROVIDED_TOKEN", "fake")
    ref = {"url": "http://127.0.0.1:1/mcp", "headers": {"Authorization": "Bearer ${X}"}}
    both = target(tmp_path, ref, bearer_env="TEST_PROVIDED_TOKEN", header_envs=["Authorization=TEST_PROVIDED_TOKEN"])
    assert both.refused["code"] == "duplicate_auth_header"
    twice = target(tmp_path, ref, header_envs=["Authorization=TEST_PROVIDED_TOKEN", "authorization=TEST_PROVIDED_TOKEN"])
    assert twice.refused["code"] == "duplicate_auth_header"
    literal = {"url": "http://127.0.0.1:1/mcp", "headers": {"X-Api-Key": "fake-literal"}}      # 참조가 아닌 선언 헤더와의 중복은 기존대로
    assert target(tmp_path, literal, header_envs=["X-Api-Key=TEST_PROVIDED_TOKEN"]).refused["code"] == "duplicate_auth_header"


def test_without_any_declared_header_behaviour_is_unchanged(tmp_path, server, monkeypatch):
    monkeypatch.setenv("TEST_PROVIDED_TOKEN", server.token)
    t = target(tmp_path, {"url": server.url}, bearer_env="TEST_PROVIDED_TOKEN")
    assert t.refused is None and "declared_header_replacements" not in t.declaration


# ---- $include 연동 ---------------------------------------------------------------------------------------

def test_server_declared_in_an_included_file_is_found_only_with_the_option(tmp_path, server, monkeypatch):
    monkeypatch.setenv("TEST_PROVIDED_TOKEN", server.token)
    main = tmp_path / "openclaw.json"
    main.write_text(json.dumps({"mcp": {"servers": {"$include": "./servers.json5"}}}), encoding="utf-8")
    (tmp_path / "servers.json5").write_text(json.dumps({"s": {"url": server.url, "headers": {"Authorization": "Bearer ${INVENTORY_MCP_TOKEN}"}}}), encoding="utf-8")
    plain = build_config_target(main, "s", "mcp.servers", False, True, [], "TEST_PROVIDED_TOKEN")
    assert plain.refused is not None                                            # 옵션 없으면 include를 읽지 않아 선언을 찾지 못함
    t = build_config_target(main, "s", "mcp.servers", False, True, [], "TEST_PROVIDED_TOKEN", None, None, True)
    assert t.refused is None and t.declaration["include_origin"]["file"] == "servers.json5"
    rep = build_report(discover(t, FAST))
    assert rep["lists"]["tools"]["collection_status"] == "complete" and server.token not in dump(rep)


def test_unresolvable_include_is_refused_not_guessed(tmp_path):
    main = tmp_path / "openclaw.json"
    main.write_text(json.dumps({"mcp": {"servers": {"s": {"$include": "../outside.json5"}}}}), encoding="utf-8")
    t = build_config_target(main, "s", "mcp.servers", False, True, [], None, None, None, True)
    assert t.refused is not None and t.refused["code"] == "include_unresolved"
