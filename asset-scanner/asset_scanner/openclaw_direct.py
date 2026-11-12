"""지정한 OpenClaw 실행 파일에 **허용 목록에 있는 조회 명령만** 실행해 결과를 얻는다 (직접 조회 경로, 내부 개발용 초안).

    python -m asset_scanner.openclaw_direct --openclaw-bin <경로> --query version|plugins|node-identity|gateway-identity|skills ...

저장된 CLI 출력 파일을 미리 준비하지 않아도 `plugin_skill_assets`·`node_gateway_identity`가 이 모듈로 같은 파서에 결과를 넘길 수 있다.

허용 명령 (OpenClaw 2026.9.6 패키지 문서·번들 코드에서 확인, docs/openclaw-direct.md 1장)
- `--version`                                        설치 버전 기록용
- `plugins list --json`                              로컬 명령. Gateway에 접속하지 않고 설정·지속 레지스트리·매니페스트를 읽는다
- `node identity --json`                             로컬 상태의 장치 신원을 읽기만 한다. 신원이 없으면 만들지 않고 오류로 끝난다
- `gateway call gateway.identity.get --json`         **이 메서드 하나만.** `gateway call`은 임의 메서드를 부르는 범용 RPC라 읽기 전용으로 취급하지 않는다.
                                                     읽기 전용 호출 모드(장치 신원을 만들지 않음)로 `{deviceId, publicKey}`만 돌려받는다
- `skills list --json`                               **기본 거부.** 이 명령은 먼저 Gateway의 `skills.status` RPC를 호출하고, 비읽기 모드라 loopback+공유 비밀
                                                     인증이 아니면 로컬 장치 신원을 새로 만들 수 있다(이후 연결은 페어링 요청으로 이어질 수 있음).
                                                     `accept_skills_gateway_rpc`(CLI `--accept-skills-list-gateway-rpc`)로 사용자가 명시적으로 동의해야만 실행한다

하지 않는 것: 셸 문자열 실행(인자 배열만 사용, `shell=False`), 초기화·설치·업데이트·페어링·설정 변경 명령, `--url/--token/--password`
(명령행에 인증정보가 드러남), `--container`(컨테이너 안 실행), 허용 목록 밖의 하위 명령·메서드.

안전 장치: 전체 시간 제한, stdout/stderr 크기 제한(넘으면 프로세스 트리를 종료), 시간 초과 시 프로세스 트리 종료, 자식 환경은 최소 기본 변수 +
명시한 범위(프로필·설정 경로·상태 폴더) + 사용자가 이름을 지정한 환경변수뿐(값은 기록하지 않음), 새로 만들면 안 되는 폴더는 존재해야 함.
출력 원문은 파일·로그에 쓰지 않는다. JSON 파싱은 메모리에서 하고 기존 파서의 가림을 거친 값만 결과에 남는다.
OpenClaw 자체가 남기는 로그 파일 기록까지 막지는 못한다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .cli import _make_console_output_safe
from .output import OutputError, normalize_for_output, write_json_atomic
from .redaction import REDACTED, Redactor, looks_like_secret_value
from .tools_catalog import _NonFinite, _pairs_hook, _parse_constant, _parse_float, _safe_short, _seg

RESEARCHED_VERSION = "2026.9.6"
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MAX_STDOUT = 8 * 1024 * 1024
DEFAULT_MAX_STDERR = 64 * 1024
MAX_TIMEOUT_S = 600.0
_PROFILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
_AGENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_ENVNAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_URL_RE = re.compile(r"^wss?://[A-Za-z0-9.\-]+(:\d{1,5})?(/[A-Za-z0-9._~\-/]*)?$|^wss?://\[[0-9A-Fa-f:]+\](:\d{1,5})?(/[A-Za-z0-9._~\-/]*)?$")
_VERSION_RE = re.compile(r"(\d{4}\.\d{1,2}\.\d{1,2}(?:[-.][0-9A-Za-z.]+)?)")
_COMMIT_RE = re.compile(r"\(([0-9a-f]{7,40})\)")
# 범위를 옵션으로 정해야 하므로 자식 프로세스에 넘기지 않는 이름
_SCOPE_ENV = frozenset({"OPENCLAW_CONFIG_PATH", "OPENCLAW_STATE_DIR", "OPENCLAW_HOME", "OPENCLAW_PROFILE", "OPENCLAW_CONTAINER"})
_BASE_ENV = ("PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "HOMEDRIVE",
             "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "USERNAME", "LANG", "LC_ALL")


@dataclass(frozen=True)
class Query:
    key: str
    argv: tuple[str, ...]
    kind: str            # text | json
    read_only_basis: str
    needs_ack: str | None = None
    uses_gateway: bool = False


QUERIES: dict[str, Query] = {
    "version": Query("version", ("--version",), "text", "버전 출력만 한다 (commander의 version 옵션)"),
    "plugins": Query("plugins", ("plugins", "list", "--json"), "json",
                     "runPluginsListCommand → buildPluginRegistrySnapshotReport: 설정·지속 레지스트리·매니페스트를 읽고 Gateway에 접속하지 않는다 "
                     "(docs/cli/plugins/list.md, 번들 코드)"),
    "node-identity": Query("node-identity", ("node", "identity", "--json"), "json",
                           "runNodeIdentityShow → loadDeviceIdentityIfPresentAsync: 신원이 없으면 만들지 않고 오류로 끝난다 (docs/cli/node.md)"),
    "gateway-identity": Query("gateway-identity", ("gateway", "call", "gateway.identity.get", "--json"), "json",
                              "gateway call → callGatewayReadOnlyCli(sharedStateMode: read-only): 장치 신원을 만들지 않는다. 호출 메서드는 "
                              "gateway.identity.get(범위 operator.read, 신원만 반환) 하나로 고정", uses_gateway=True),
    "skills": Query("skills", ("skills", "list", "--json"), "json",
                    "loadSkillsStatusReport → callGateway(skills.status): 비읽기 모드라 loopback+공유 비밀 인증이 아니면 로컬 장치 신원을 새로 만들 수 있다. "
                    "사용자가 명시적으로 동의한 경우에만 실행", needs_ack="skills_gateway_rpc", uses_gateway=True),
}


@dataclass
class DirectConfig:
    openclaw_bin: Path
    profile: str | None = None
    dev: bool = False
    config_path: Path | None = None
    state_dir: Path | None = None
    home: Path | None = None
    pass_env: tuple[str, ...] = ()
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_stdout_bytes: int = DEFAULT_MAX_STDOUT
    max_stderr_bytes: int = DEFAULT_MAX_STDERR
    expect_gateway_url: str | None = None
    accept_configured_gateway: bool = False
    accept_skills_gateway_rpc: bool = False
    agent: str | None = None
    require_version: str | None = None


@dataclass
class DirectResult:
    query: str
    data: Any = None                 # 파싱한 JSON (메모리에만 있다)
    failure: dict | None = None      # {"code", "message", ...}
    observation: dict = field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def validate_config(cfg: DirectConfig, queries: list[str]) -> list[str]:
    """실행 전에 설정을 검사한다. 문제가 있으면 한국어 문장 목록을 돌려준다(프로세스를 만들지 않음)."""
    problems: list[str] = []
    b = cfg.openclaw_bin
    if not b.is_file():
        problems.append("--openclaw-bin: 실행 파일이 없거나 파일이 아닙니다 (PATH에서 찾지 않으며 지정한 경로만 씁니다)")
    if cfg.profile is not None and not _PROFILE_RE.match(cfg.profile):
        problems.append("--profile: 영문자·숫자로 시작하고 영문자·숫자·_-만 쓰는 32자 이하여야 합니다")
    if cfg.profile and cfg.dev:
        problems.append("--profile과 --dev는 함께 쓸 수 없습니다")
    if cfg.config_path is not None and not cfg.config_path.is_file():
        problems.append("--config-path: 존재하는 파일이어야 합니다 (OpenClaw가 새로 만들지 않도록 확인)")
    for name, p in (("--state-dir", cfg.state_dir), ("--openclaw-home", cfg.home)):
        if p is not None and not p.is_dir():
            problems.append(f"{name}: 존재하는 폴더여야 합니다 (스캐너가 폴더를 새로 만들지 않으며 OpenClaw가 초기화하지 않도록 확인)")
    for n in cfg.pass_env:
        if not _ENVNAME_RE.match(n) or n.upper() in _SCOPE_ENV:
            problems.append(f"--pass-env {n}: 환경변수 이름 형식이 아니거나 범위 옵션으로 정해야 하는 이름입니다")
    if not (isinstance(cfg.timeout_s, (int, float)) and 0 < cfg.timeout_s <= MAX_TIMEOUT_S and cfg.timeout_s == cfg.timeout_s):
        problems.append(f"--openclaw-timeout: 0보다 크고 {MAX_TIMEOUT_S:g} 이하인 수여야 합니다")
    if not (isinstance(cfg.max_stdout_bytes, int) and 1024 <= cfg.max_stdout_bytes <= 64 * 1024 * 1024):
        problems.append("--max-output-bytes: 1024 이상 67108864 이하여야 합니다")
    if cfg.expect_gateway_url is not None and not _URL_RE.match(cfg.expect_gateway_url):
        problems.append("--expect-gateway-url: ws:// 또는 wss:// 주소여야 하며 쿼리·사용자정보·특수문자는 쓸 수 없습니다")
    if cfg.agent is not None and not _AGENT_RE.match(cfg.agent):
        problems.append("--openclaw-agent: 영문자·숫자로 시작하는 64자 이하 이름이어야 합니다")
    for q in queries:
        spec = QUERIES.get(q)
        if spec is None:
            problems.append(f"허용하지 않는 조회: {q}")
            continue
        if q == "gateway-identity" and not (cfg.expect_gateway_url or cfg.accept_configured_gateway):
            problems.append("gateway-identity: 접속 대상은 OpenClaw 설정이 정합니다. --expect-gateway-url로 대상을 고정하거나, "
                            "--accept-configured-gateway로 설정이 가리키는 Gateway에 접속함을 확인하세요")
        if spec.needs_ack == "skills_gateway_rpc" and not cfg.accept_skills_gateway_rpc:
            problems.append("skills: `skills list`는 설정이 가리키는 Gateway에 RPC를 보내고 장치 신원을 새로 만들 수 있어 기본 거부입니다. "
                            "위험을 이해하고 진행하려면 --accept-skills-list-gateway-rpc를 주세요 (저장된 `skills list --json` 출력을 쓰는 방법도 있습니다)")
    return problems


def _child_env(cfg: DirectConfig) -> tuple[dict[str, str], dict]:
    env: dict[str, str] = {k: os.environ[k] for k in _BASE_ENV if k in os.environ}
    env["NO_COLOR"] = "1"                # 표준 관례. 문서로 확인하지 못한 OPENCLAW_* 변수는 만들지 않는다 (stdin은 닫혀 있다)
    scope: dict[str, Any] = {"profile": cfg.profile, "dev_profile": cfg.dev, "default_state_location": True}
    if cfg.config_path is not None:
        env["OPENCLAW_CONFIG_PATH"] = str(cfg.config_path)
        scope["config_path_set"] = True
        scope["default_state_location"] = False
    if cfg.state_dir is not None:
        env["OPENCLAW_STATE_DIR"] = str(cfg.state_dir)
        scope["state_dir_set"] = True
        scope["default_state_location"] = False
    if cfg.home is not None:
        env["OPENCLAW_HOME"] = str(cfg.home)
        scope["home_set"] = True
        scope["default_state_location"] = False
    if cfg.profile or cfg.dev:
        scope["default_state_location"] = False
    passed, not_set = [], []
    for n in cfg.pass_env:
        if n in os.environ:
            env[n] = os.environ[n]
            passed.append(n)
        else:
            not_set.append(n)
    scope["pass_env_names"] = passed          # 이름만 기록한다. 값은 기록하지 않는다
    scope["pass_env_names_not_set"] = not_set
    return env, scope


def build_argv(cfg: DirectConfig, key: str) -> list[str]:
    spec = QUERIES[key]
    argv = [str(cfg.openclaw_bin)]
    if key != "version":
        if cfg.profile:
            argv += ["--profile", cfg.profile]
        if cfg.dev:
            argv += ["--dev"]
    argv += list(spec.argv)
    if key == "gateway-identity":
        argv += ["--timeout", str(max(1000, int(cfg.timeout_s * 1000 * 0.8)))]     # OpenClaw 쪽 제한이 우리 제한보다 먼저 끝나도록
        if cfg.expect_gateway_url:
            argv += ["--expect-url", cfg.expect_gateway_url]
    if key == "skills" and cfg.agent:
        argv += ["--agent", cfg.agent]
    return argv


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False, timeout=10)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, subprocess.SubprocessError, ProcessLookupError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


@dataclass
class _Raw:
    exit_code: int | None = None
    stdout: bytes = b""
    stderr: bytes = b""
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    duration_ms: int = 0
    spawn_error: str | None = None
    tree_killed: bool = False
    pid: int | None = None


def run_process(argv: list[str], env: dict[str, str], cwd: str, timeout_s: float, max_out: int, max_err: int) -> _Raw:
    """셸 없이 인자 배열로 실행한다. 시간·출력 크기 제한을 넘으면 프로세스 트리를 종료한다."""
    raw = _Raw()
    started = time.monotonic()
    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(argv, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=cwd, **kwargs)
    except OSError as exc:
        raw.spawn_error = type(exc).__name__
        raw.duration_ms = int((time.monotonic() - started) * 1000)
        return raw
    raw.pid = proc.pid
    bufs = {"out": bytearray(), "err": bytearray()}
    limits = {"out": max_out, "err": max_err}
    over = threading.Event()
    flags = {"out": False, "err": False}

    def pump(stream: Any, name: str) -> None:
        try:
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    return
                room = limits[name] - len(bufs[name])
                if len(chunk) > room:
                    bufs[name] += chunk[:max(room, 0)]
                    flags[name] = True
                    over.set()
                    return
                bufs[name] += chunk
        except (OSError, ValueError):
            return

    threads = [threading.Thread(target=pump, args=(proc.stdout, "out"), daemon=True), threading.Thread(target=pump, args=(proc.stderr, "err"), daemon=True)]
    for t in threads:
        t.start()
    deadline = started + timeout_s
    while proc.poll() is None:
        if over.is_set():
            break
        if time.monotonic() >= deadline:
            raw.timed_out = True
            break
        time.sleep(0.02)
    if raw.timed_out or over.is_set():
        _kill_tree(proc)
        raw.tree_killed = True
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
    for t in threads:
        t.join(timeout=3)
    if any(t.is_alive() for t in threads):     # 손자 프로세스가 파이프를 붙잡고 있는 경우
        _kill_tree(proc)
        raw.tree_killed = True
        for s in (proc.stdout, proc.stderr):
            try:
                s.close()
            except (OSError, ValueError):
                pass
    raw.exit_code = proc.returncode
    raw.stdout, raw.stderr = bytes(bufs["out"]), bytes(bufs["err"])
    raw.stdout_truncated, raw.stderr_truncated = flags["out"], flags["err"]
    raw.duration_ms = int((time.monotonic() - started) * 1000)
    return raw


def _parse_version(text: str) -> dict:
    red = Redactor()
    first = (text.strip().splitlines() or [""])[0]
    shown = _safe_short(red, first, "version_line") if first else None
    m, c = _VERSION_RE.search(first), _COMMIT_RE.search(first)
    return {"text": shown, "version": m.group(1) if m else None, "commit": c.group(1) if c else None,
            "version_matches_researched_basis": (m.group(1) == RESEARCHED_VERSION) if m else None, "researched_basis": RESEARCHED_VERSION}


def _parse_json(data: bytes) -> tuple[Any, dict | None]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, {"code": "output_not_utf8", "message": "출력이 UTF-8이 아닙니다."}
    if text.strip() == "":
        return None, {"code": "empty_output", "message": "출력이 비어 있습니다."}
    try:
        return json.loads(text, object_pairs_hook=_pairs_hook, parse_constant=_parse_constant, parse_float=_parse_float), None
    except (ValueError, RecursionError):
        return None, {"code": "output_not_json", "message": "출력이 JSON이 아닙니다."}


def _exe_label(p: Path) -> str:
    parts = p.resolve().parts if p.exists() else p.parts
    return str(Path(*[REDACTED if looks_like_secret_value(x) else x for x in parts]))


def run_query(cfg: DirectConfig, key: str, version_info: dict | None = None) -> DirectResult:
    """허용 목록의 조회 하나를 실행한다. 검증 문제가 있으면 ValueError(프로세스를 만들지 않음)."""
    problems = validate_config(cfg, [key])
    if problems:
        raise ValueError("; ".join(problems))
    spec = QUERIES[key]
    env, scope = _child_env(cfg)
    argv = build_argv(cfg, key)
    raw = run_process(argv, env, tempfile.gettempdir(), cfg.timeout_s, cfg.max_stdout_bytes, cfg.max_stderr_bytes)
    red = Redactor()
    obs: dict[str, Any] = {
        "source_kind": "direct_query", "executed_by_scanner": True, "verified_by_scanner": False,
        "query": key, "command": "openclaw " + " ".join(argv[1:]), "argv_count": len(argv) - 1,
        "executable": _exe_label(cfg.openclaw_bin), "shell": False,
        "read_only_basis": spec.read_only_basis, "uses_gateway": spec.uses_gateway,
        "scope": scope, "installed_version": version_info,
        "observed_at": _now(), "observed_at_origin": "scanner_clock_at_query",
        "duration_ms": raw.duration_ms, "exit_code": raw.exit_code, "timed_out": raw.timed_out,
        "stdout_bytes": len(raw.stdout), "stderr_bytes": len(raw.stderr), "output_truncated": raw.stdout_truncated or raw.stderr_truncated,
        "process_tree_killed": raw.tree_killed,
        "limits": {"timeout_s": cfg.timeout_s, "max_stdout_bytes": cfg.max_stdout_bytes, "max_stderr_bytes": cfg.max_stderr_bytes},
        "raw_output_stored": False,
    }
    if key == "gateway-identity":
        obs["gateway_target"] = {"basis": "expect_url" if cfg.expect_gateway_url else "configured_by_openclaw_unverified",
                                 "expect_url": red.sanitize_url(cfg.expect_gateway_url, "expect_url") if cfg.expect_gateway_url else None,
                                 "gateway_method": "gateway.identity.get", "params": "none"}
    if key == "skills":
        obs["acknowledged_risk"] = "skills_list_gateway_rpc"
        obs["agent"] = cfg.agent
    result = DirectResult(query=key, observation=obs)
    if raw.spawn_error:
        result.failure = {"code": "spawn_failed", "message": "OpenClaw 실행 파일을 실행하지 못했습니다.", "error_type": raw.spawn_error}
        return result
    if raw.timed_out:
        result.failure = {"code": "timeout", "message": f"제한 시간({cfg.timeout_s:g}초)을 넘겨 프로세스를 종료했습니다."}
        return result
    if raw.stdout_truncated or raw.stderr_truncated:
        result.failure = {"code": "output_too_large", "message": "출력이 크기 제한을 넘어 프로세스를 종료했습니다. 일부 출력은 폐기했습니다."}
        return result
    if raw.exit_code != 0:
        # 오류 출력에는 인증정보가 섞일 수 있다. 원문은 저장하지 않고 가린 짧은 일부와 크기·JSON 키 이름만 남긴다.
        err_text = raw.stderr.decode("utf-8", errors="replace").strip()
        fail: dict[str, Any] = {"code": "command_failed", "message": "명령이 0이 아닌 종료 코드로 끝났습니다.", "exit_code": raw.exit_code}
        if err_text:
            fail["stderr_excerpt_sanitized"] = _safe_short(red, err_text.splitlines()[0], "stderr")
        obj, _ = _parse_json(raw.stdout) if raw.stdout.strip() else (None, None)
        if isinstance(obj, dict):
            fail["stdout_error_json_keys"] = sorted(_seg(k) for k in obj)[:20]      # --json 모드 오류 객체의 키 이름만
        result.failure = fail
        return result
    if spec.kind == "text":
        result.data = raw.stdout.decode("utf-8", errors="replace")
        return result
    data, failure = _parse_json(raw.stdout)
    if failure is not None:
        result.failure = failure
        return result
    result.data = data
    return result


def probe_version(cfg: DirectConfig) -> DirectResult:
    res = run_query(cfg, "version")
    if res.failure is None:
        res.observation["installed_version"] = _parse_version(str(res.data))
        res.data = None      # 버전 줄은 observation에 가려서 남겼다
    return res


def check_required_version(cfg: DirectConfig, version_res: DirectResult) -> str | None:
    if not cfg.require_version:
        return None
    v = (version_res.observation.get("installed_version") or {}).get("version")
    if v is None or not v.startswith(cfg.require_version):
        return f"설치 버전({v or '확인 불가'})이 --require-openclaw-version({cfg.require_version})과 맞지 않아 조회하지 않았습니다"
    return None


def run_queries(cfg: DirectConfig, keys: list[str]) -> tuple[dict[str, DirectResult], DirectResult]:
    """버전을 먼저 확인한 뒤 요청한 조회를 순서대로(순차) 실행한다. 요구 버전이 맞지 않으면 조회를 실행하지 않는다."""
    problems = validate_config(cfg, keys)
    if problems:
        raise ValueError("; ".join(problems))
    ver = probe_version(cfg)
    vinfo = ver.observation.get("installed_version")
    out: dict[str, DirectResult] = {}
    mismatch = check_required_version(cfg, ver)
    for k in keys:
        if mismatch:
            r = DirectResult(query=k, failure={"code": "version_requirement_not_met", "message": mismatch},
                             observation={"source_kind": "direct_query", "executed_by_scanner": False, "query": k, "installed_version": vinfo,
                                          "observed_at": _now(), "observed_at_origin": "scanner_clock_at_query", "raw_output_stored": False})
        else:
            r = run_query(cfg, k, vinfo)
        out[k] = r
    return out, ver


# ---- 공통 CLI 인자 (plugin_skill_assets · node_gateway_identity가 함께 쓴다) ------------------------------------

def add_direct_arguments(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("OpenClaw 직접 조회 (허용 목록의 읽기 조회만 실행, docs/openclaw-direct.md)")
    g.add_argument("--openclaw-bin", type=Path, help="OpenClaw 실행 파일 경로. PATH에서 찾지 않으며 지정한 파일만 실행합니다")
    g.add_argument("--profile", help="OpenClaw 프로필 이름 (--profile). --dev와 함께 쓸 수 없습니다")
    g.add_argument("--dev", action="store_true", help="OpenClaw dev 프로필 (--dev)")
    g.add_argument("--config-path", type=Path, help="OPENCLAW_CONFIG_PATH로 넘길 기존 설정 파일")
    g.add_argument("--state-dir", type=Path, help="OPENCLAW_STATE_DIR로 넘길 기존 폴더")
    g.add_argument("--openclaw-home", type=Path, help="OPENCLAW_HOME으로 넘길 기존 폴더")
    g.add_argument("--pass-env", action="append", default=[], metavar="NAME", help="자식 프로세스에 전달할 환경변수 이름 (예: OPENCLAW_GATEWAY_TOKEN). 값은 기록하지 않습니다")
    g.add_argument("--openclaw-timeout", type=float, default=DEFAULT_TIMEOUT_S, help="조회 하나의 제한 시간(초, 기본 30)")
    g.add_argument("--max-output-bytes", type=int, default=DEFAULT_MAX_STDOUT, help="stdout 최대 바이트(기본 8MiB). 넘으면 프로세스 트리를 종료합니다")
    g.add_argument("--expect-gateway-url", help="gateway-identity 조회가 접속해야 하는 ws(s):// 주소 (OpenClaw의 --expect-url로 대상을 고정)")
    g.add_argument("--accept-configured-gateway", action="store_true", help="gateway-identity가 OpenClaw 설정이 가리키는 Gateway에 접속함을 확인")
    g.add_argument("--accept-skills-list-gateway-rpc", action="store_true",
                   help="`skills list`가 Gateway RPC를 보내고 장치 신원을 새로 만들 수 있음을 이해하고 실행을 허용 (기본 거부)")
    g.add_argument("--openclaw-agent", help="skills 조회의 --agent")
    g.add_argument("--require-openclaw-version", help="설치 버전이 이 접두어(예: 2026.9.6)로 시작하지 않으면 조회하지 않음")


def config_from_args(args: argparse.Namespace) -> DirectConfig:
    return DirectConfig(openclaw_bin=args.openclaw_bin, profile=args.profile, dev=args.dev, config_path=args.config_path, state_dir=args.state_dir,
                        home=args.openclaw_home, pass_env=tuple(args.pass_env), timeout_s=args.openclaw_timeout, max_stdout_bytes=args.max_output_bytes,
                        expect_gateway_url=args.expect_gateway_url, accept_configured_gateway=args.accept_configured_gateway,
                        accept_skills_gateway_rpc=args.accept_skills_list_gateway_rpc, agent=args.openclaw_agent,
                        require_version=args.require_openclaw_version)


# ---- 단독 CLI: 설치 버전 확인과 조회 요약 (원문 출력은 저장·표시하지 않는다) ---------------------------------------

def _summary(res: DirectResult) -> dict:
    d = res.data
    s: dict[str, Any] = {"query": res.query, "ok": res.failure is None, "failure": res.failure, "observation": res.observation}
    if res.failure is None and isinstance(d, dict):
        for k in ("plugins", "skills"):
            if isinstance(d.get(k), list):
                s[f"{k}_record_count"] = len(d[k])
        if "deviceId" in d:
            s["has_device_id"] = isinstance(d.get("deviceId"), str)
    return s


def main(argv: list[str] | None = None) -> int:
    _make_console_output_safe()
    p = argparse.ArgumentParser(prog="python -m asset_scanner.openclaw_direct",
                                description="지정한 OpenClaw 실행 파일에 허용 목록의 읽기 조회를 실행하고 관측 요약을 저장합니다 (출력 원문은 저장하지 않음).")
    add_direct_arguments(p)
    p.add_argument("--query", action="append", default=[], choices=sorted(QUERIES), help="실행할 조회 (여러 번 가능, 생략하면 version만)")
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args(argv)
    if args.openclaw_bin is None:
        p.error("--openclaw-bin이 필요합니다.")
    keys = [q for q in (args.query or ["version"]) if q != "version"]
    cfg = config_from_args(args)
    problems = validate_config(cfg, keys)
    if problems:
        p.error("; ".join(problems))
    results, ver = run_queries(cfg, keys)
    report = {"format": "agent-scope.scanner.openclaw-direct-query", "format_version": "0.1.0-draft", "generated_at": _now(),
              "note": "OpenClaw 직접 조회의 관측 요약입니다. 출력 원문은 저장하지 않았고 값은 각 수집 모듈이 가려서 담습니다.",
              "version": _summary(ver), "queries": [_summary(r) for r in results.values()]}
    report, _ = normalize_for_output(report)
    try:
        write_json_atomic(args.output, report)
    except OutputError as exc:
        print(f"오류: 결과 파일을 저장하지 못했습니다 ({exc.kind}).", file=sys.stderr)
        return 4
    bad = [r for r in results.values() if r.failure] + ([ver] if ver.failure else [])
    print("OpenClaw 직접 조회 (허용 목록의 읽기 조회만, 출력 원문 저장 없음)")
    iv = ver.observation.get("installed_version") or {}
    print(f"설치 버전: {iv.get('version') or '확인 불가'} (근거 문서 버전 {RESEARCHED_VERSION}과 일치: {iv.get('version_matches_researched_basis')})")
    for k, r in results.items():
        print(f"  - {k}: {'성공' if not r.failure else '실패 ' + r.failure['code']}")
    print(f"결과 저장: {args.output}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
