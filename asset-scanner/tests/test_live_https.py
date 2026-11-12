"""원격 HTTPS MCP 목록 조회(live_discovery의 TLS·인증 확장) 테스트.

**테스트가 만든 임시 CA와 로컬 HTTPS 시험 서버(127.0.0.1)만 쓴다.** 외부 서버·팀 테스트베드에는 접속하지 않으며 DNS 조회도 하지 않는다.
토큰은 테스트 중 만든 임의 값이고 `FAKE` 표식 값은 가짜 비밀값이다. TLS 검증을 끄는 경로는 없으며 테스트도 끄지 않는다
(신뢰하는 CA는 `--ca-bundle`로 **추가**한다). 서버가 받은 요청 기록(메서드 이름·인증 결과·Host 값)으로 목록 요청만 갔는지 확인한다.
"""

import contextlib
import datetime
import inspect
import json
import os
import secrets
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from asset_scanner import live_discovery as ld
from asset_scanner.live_discovery import (ALLOWED_LIST_METHODS, DiscoveryLimits, build_config_target, build_report, build_ssl_context, catalog_report, discover,
                                          classify_transport_error, make_origin_guard)
from conftest import SCANNER_ROOT

_REAL_POPEN = subprocess.Popen
FAST = DiscoveryLimits(total_timeout_s=40, request_timeout_s=10, connect_timeout_s=20)
OK_SERVER_METHODS = {"server/discover", "initialize", "notifications/initialized", "ping", "tools/list", "resources/list", "resources/templates/list", "prompts/list"}


# ---- 테스트용 PKI ------------------------------------------------------------------------------------

def _name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _ski(key) -> x509.SubjectKeyIdentifier:
    return x509.SubjectKeyIdentifier.from_public_key(key.public_key())


def make_ca(cn: str):
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(_name(cn)).issuer_name(_name(cn)).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=False,
                                         key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(_ski(key), critical=False)
            .sign(key, hashes.SHA256()))
    return key, cert


def make_leaf(ca_key, ca_cert, dns=(), ips=(), valid_from_days=-1, valid_to_days=30):
    import ipaddress
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.datetime.now(datetime.timezone.utc)
    san = [x509.DNSName(d) for d in dns] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    cert = (x509.CertificateBuilder().subject_name(_name("test-server")).issuer_name(ca_cert.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now + datetime.timedelta(days=valid_from_days))
            .not_valid_after(now + datetime.timedelta(days=valid_to_days))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=True,
                                         key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(_ski(key), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    return key, cert


def write_pem(path: Path, cert=None, key=None) -> Path:
    if cert is not None:
        path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    else:
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return path


@pytest.fixture(scope="session")
def pki(tmp_path_factory):
    d = tmp_path_factory.mktemp("pki")
    ca1_key, ca1 = make_ca("scanner-test-ca-1")
    ca2_key, ca2 = make_ca("scanner-test-ca-2")
    out = SimpleNamespace(dir=d, ca1=write_pem(d / "ca1.pem", ca1), ca2=write_pem(d / "ca2.pem", ca2))

    def leaf(name, ca_key, ca, **kw):
        k, c = make_leaf(ca_key, ca, **kw)
        return SimpleNamespace(cert=write_pem(d / f"{name}.crt", c), key=write_pem(d / f"{name}.key", key=k))

    out.good = leaf("good", ca1_key, ca1, dns=["localhost"], ips=["127.0.0.1"])
    out.good_b = leaf("good_b", ca1_key, ca1, dns=["localhost"], ips=["127.0.0.1"])
    out.dns_only = leaf("dns_only", ca1_key, ca1, dns=["localhost"])                                  # IP SAN 없음: 127.0.0.1로 접속하면 불일치
    out.other_host = leaf("other_host", ca1_key, ca1, dns=["other.test"])                            # localhost와 다른 이름
    out.expired = leaf("expired", ca1_key, ca1, dns=["localhost"], ips=["127.0.0.1"], valid_from_days=-10, valid_to_days=-1)
    out.by_ca2 = leaf("by_ca2", ca2_key, ca2, dns=["localhost"], ips=["127.0.0.1"])                  # 신뢰하지 않는 CA가 서명
    return out


# ---- 서버 도우미 ---------------------------------------------------------------------------------------

def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def read_log(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()] if Path(path).exists() else []


def methods(events):
    return [e["method"] for e in events if e["event"] == "request"]


def http_events(events):
    return [e for e in events if e["event"] == "http"]


@contextlib.contextmanager
def https_server(tmp, name, cert=None, *, scenario="full", bearer=True, api_key_header=None, redirect_to=None):
    port, log = free_port(), tmp / f"{name}.log.jsonl"
    token, key = "fake-" + secrets.token_hex(12), "fakekey-" + secrets.token_hex(8)
    env = {**os.environ, "DEV_MCP_SERVER_LOG": str(log), "PYTHONUTF8": "1"}
    cmd = [sys.executable, "-m", "asset_scanner.dev_lists_server", "--scenario", scenario, "--transport", "http", "--port", str(port)]
    if cert is not None:
        cmd += ["--tls-cert", str(cert.cert), "--tls-key", str(cert.key)]
    if bearer:
        cmd += ["--require-bearer"]
        env["DEV_MCP_SERVER_TOKEN"] = token
    if api_key_header:
        cmd += ["--require-api-key-header", api_key_header]
        env["DEV_MCP_SERVER_API_KEY"] = key
    if redirect_to:
        cmd += ["--redirect-to", redirect_to]
    proc = _REAL_POPEN(cmd, env=env, cwd=SCANNER_ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(150):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
                break
            except OSError:
                time.sleep(0.2)
        else:
            pytest.fail("시험 HTTPS 서버가 포트를 열지 못했습니다")
        yield SimpleNamespace(port=port, token=token, api_key=key, log=log, proc=proc)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_discovery(tmp, url, *, ca=None, bearer_env=None, header_envs=None, allow_hosts=None, name="cfg", scan_ref=None):
    cfg = tmp / f"{name}.json5"
    cfg.write_text(json.dumps({"mcp": {"servers": {"s": {"url": url}}}}), encoding="utf-8")
    target = build_config_target(cfg, "s", "mcp.servers", False, True, allow_hosts or [], bearer_env, ca, header_envs)
    result = discover(target, FAST, config_scan_ref=scan_ref)
    return build_report(result), target, result


def lst(rep, key):
    return rep["lists"][key]


def dump(x):
    return json.dumps(x, ensure_ascii=False, default=str)


# ---- 정상: 신뢰하는 CA + 호스트 이름 일치 + 인증 ----------------------------------------------------------

def test_https_with_trusted_private_ca_and_bearer_collects_all_lists(tmp_path, pki, monkeypatch):
    with https_server(tmp_path, "srv", pki.good) as srv:
        monkeypatch.setenv("SCANNER_TEST_TOKEN", srv.token)
        rep, target, result = run_discovery(tmp_path, f"https://localhost:{srv.port}/mcp", ca=pki.ca1, bearer_env="SCANNER_TEST_TOKEN", scan_ref="gw")
        events = read_log(srv.log)
    assert rep["collection"]["status"] == "complete" and rep["collection"]["item_counts"] == {"tools": 2, "resources": 2, "resource_templates": 2, "prompts": 2}
    assert rep["source"]["transport"] == "streamable-http" and rep["source"]["target"]["scheme"] == "https" and rep["source"]["target"]["host"] == "localhost"
    p = rep["protocol"]
    assert p["negotiated_protocol_version"] == "2026-07-28" and p["negotiated_readable_by_parser"] is True          # 실제 협상된 버전
    tls = rep["tls"]
    assert tls["verify_certificate_chain"] is True and tls["verify_hostname"] is True and tls["can_be_disabled"] is False
    assert tls["trust"] == "system_default+custom_ca_bundle" and tls["error"] is None and tls["redirects_followed"] == 0
    assert tls["env_proxy_and_cert_variables_read"] is False
    # 서버가 받은 요청: 목록 요청뿐, 모든 HTTP 요청에 인증이 있었음, Host는 접속한 이름
    seen = methods(events)
    assert set(seen) <= OK_SERVER_METHODS and not {"tools/call", "resources/read", "prompts/get"} & set(seen)
    assert len([m for m in seen if m.endswith("/list")]) == sum(rep["requests"]["by_method"].values())
    assert {e["auth"] for e in http_events(events)} == {"ok"} and {e["host"] for e in http_events(events)} == {f"localhost:{srv.port}"}
    assert [e["tls"] for e in events if e["event"] == "start"] == [True]
    # 토큰 비노출: 결과·카탈로그·서버 기록·대상 설명 어디에도 없다
    blob = dump(rep) + dump(events) + dump(catalog_report(result))
    assert srv.token not in blob and "Bearer" not in dump(rep)
    assert rep["source"]["target"]["auth"] == "bearer_from_env_var" and rep["source"]["target"]["bearer_env_name"] == "SCANNER_TEST_TOKEN"
    assert rep["source"]["target"]["header_names"] == ["Authorization"]
    assert rep["source"]["declaration_link"]["declaration_path"] == "mcp.servers.s" and result["_catalog_server"]["config_link"]["config_scan_ref"] == "gw"
    assert rep["source"]["child_process"] is None                           # 이 모듈이 띄운 프로세스가 없다 (테스트가 띄운 서버)


def test_custom_auth_header_from_an_environment_variable(tmp_path, pki, monkeypatch):
    with https_server(tmp_path, "srv", pki.good, bearer=False, api_key_header="X-Api-Key") as srv:
        monkeypatch.setenv("SCANNER_TEST_KEY", srv.api_key)
        rep, target, result = run_discovery(tmp_path, f"https://localhost:{srv.port}/mcp", ca=pki.ca1, header_envs=["X-Api-Key=SCANNER_TEST_KEY"])
        events = read_log(srv.log)
        assert rep["collection"]["status"] == "complete" and {e["auth"] for e in http_events(events)} == {"ok"}
        assert rep["source"]["target"]["auth"] == "header_from_env_var" and rep["source"]["target"]["auth_header_env"] == [{"header": "X-Api-Key", "env": "SCANNER_TEST_KEY"}]
        assert rep["source"]["target"]["header_names"] == ["X-Api-Key"]
        assert srv.api_key not in dump(rep) + dump(events) + dump(catalog_report(result))
        # 헤더 없이 접속하면 서버가 거부한다 (인증이 실제로 적용되고 있다는 증거)
        rep2, *_ = run_discovery(tmp_path, f"https://localhost:{srv.port}/mcp", ca=pki.ca1, name="cfg2")
        assert rep2["collection"]["outcome"] == "connect_rejected" and rep2["connect_failure"]["http_status_codes"] == [401]
        assert {e["auth"] for e in http_events(read_log(srv.log))} >= {"ok", "missing"}


@pytest.mark.parametrize("variant", ["missing", "wrong"])
def test_https_auth_rejection_is_distinguished_from_tls_and_connection_errors(tmp_path, pki, monkeypatch, variant):
    with https_server(tmp_path, "srv", pki.good) as srv:
        env = None
        if variant == "wrong":
            monkeypatch.setenv("SCANNER_TEST_TOKEN", "FAKE-WRONG-TOKEN")
            env = "SCANNER_TEST_TOKEN"
        rep, *_ = run_discovery(tmp_path, f"https://localhost:{srv.port}/mcp", ca=pki.ca1, bearer_env=env)
        events = read_log(srv.log)
    assert rep["collection"]["status"] == "failed" and rep["collection"]["outcome"] == "connect_rejected"
    assert rep["connect_failure"]["http_status_codes"] == [401] and rep["tls"]["error"] is None                    # TLS는 성공했고 인증만 거부
    assert {e["auth"] for e in http_events(events)} == {"missing" if variant == "missing" else "bad"} and methods(events) == []
    assert all(v["collection_status"] == "not_performed" for v in rep["lists"].values()) and rep["requests"]["by_method"] == {}
    assert "FAKE-WRONG-TOKEN" not in dump(rep) + dump(events)


# ---- TLS 검증: 실제 핸드셰이크 --------------------------------------------------------------------------------

def assert_tls_failure_before_any_http(rep, events, category, code=None):
    assert rep["collection"]["status"] == "failed" and rep["collection"]["outcome"] == category
    assert rep["tls"]["error"]["category"] == category and rep["tls"]["verify_certificate_chain"] is True
    if code is not None:
        assert rep["tls"]["error"]["verify_code"] == code
    assert rep["connect_failure"]["transport"]["error_types"]
    assert http_events(events) == [] and methods(events) == []                         # 핸드셰이크에서 끝나 HTTP 요청도 인증 헤더도 서버에 가지 않았다
    assert rep["requests"]["by_method"] == {} and all(v["collection_status"] == "not_performed" for v in rep["lists"].values())
    assert all(v["outcome"] == category for v in rep["lists"].values())


def test_certificate_from_an_untrusted_ca_is_rejected_by_default(tmp_path, pki, monkeypatch):
    with https_server(tmp_path, "srv", pki.good) as srv:
        monkeypatch.setenv("SCANNER_TEST_TOKEN", srv.token)
        rep, *_ = run_discovery(tmp_path, f"https://localhost:{srv.port}/mcp", ca=None, bearer_env="SCANNER_TEST_TOKEN")      # CA를 신뢰 목록에 더하지 않음
        events = read_log(srv.log)
    assert_tls_failure_before_any_http(rep, events, "tls_certificate_untrusted")
    assert rep["tls"]["trust"] == "system_default" and rep["tls"]["error"]["verify_code"] in (19, 20, 21, 18, 2)
    assert srv.token not in dump(rep) + dump(events)


def test_certificate_signed_by_a_different_ca_than_the_trusted_one_is_rejected(tmp_path, pki, monkeypatch):
    with https_server(tmp_path, "srv", pki.by_ca2) as srv:
        monkeypatch.setenv("SCANNER_TEST_TOKEN", srv.token)
        rep, *_ = run_discovery(tmp_path, f"https://localhost:{srv.port}/mcp", ca=pki.ca1, bearer_env="SCANNER_TEST_TOKEN")
        events = read_log(srv.log)
    assert_tls_failure_before_any_http(rep, events, "tls_certificate_untrusted")


@pytest.mark.parametrize("cert_name, host, code", [("other_host", "localhost", 62), ("dns_only", "127.0.0.1", 64)])
def test_hostname_and_ip_mismatch_are_rejected_even_with_a_trusted_ca(tmp_path, pki, monkeypatch, cert_name, host, code):
    with https_server(tmp_path, "srv", getattr(pki, cert_name)) as srv:
        monkeypatch.setenv("SCANNER_TEST_TOKEN", srv.token)
        rep, *_ = run_discovery(tmp_path, f"https://{host}:{srv.port}/mcp", ca=pki.ca1, bearer_env="SCANNER_TEST_TOKEN")      # CA는 신뢰하지만 이름이 맞지 않음
        events = read_log(srv.log)
    assert_tls_failure_before_any_http(rep, events, "tls_hostname_mismatch", code)
    assert srv.token not in dump(rep) + dump(events)


def test_expired_certificate_is_rejected(tmp_path, pki, monkeypatch):
    with https_server(tmp_path, "srv", pki.expired) as srv:
        monkeypatch.setenv("SCANNER_TEST_TOKEN", srv.token)
        rep, *_ = run_discovery(tmp_path, f"https://localhost:{srv.port}/mcp", ca=pki.ca1, bearer_env="SCANNER_TEST_TOKEN")
        events = read_log(srv.log)
    assert_tls_failure_before_any_http(rep, events, "tls_certificate_expired", 10)


def test_plaintext_server_behind_an_https_url_is_a_tls_error_not_a_success(tmp_path, pki, monkeypatch):
    with https_server(tmp_path, "plain", None, bearer=False) as srv:                           # TLS 없이 듣는 서버에 https로 접속
        rep, *_ = run_discovery(tmp_path, f"https://localhost:{srv.port}/mcp", ca=pki.ca1)
    assert rep["collection"]["status"] == "failed" and rep["collection"]["outcome"] in ("tls_error", "network_error", "connect_failed")
    assert all(v["collection_status"] == "not_performed" for v in rep["lists"].values())


def test_connection_refused_is_its_own_category(tmp_path, pki):
    rep, *_ = run_discovery(tmp_path, f"https://127.0.0.1:{free_port()}/mcp", ca=pki.ca1)
    assert rep["collection"]["status"] == "failed" and rep["collection"]["outcome"] == "connect_refused"
    assert rep["tls"]["error"]["category"] == "connect_refused" and rep["requests"]["by_method"] == {}


def test_transport_error_classification_covers_dns_and_timeouts_without_any_network():
    import httpx2
    assert classify_transport_error(socket.gaierror(11001, "x"))["category"] == "dns_failure"
    assert classify_transport_error(ConnectionRefusedError())["category"] == "connect_refused"
    wrapped = httpx2.ConnectError("boom")
    wrapped.__cause__ = ssl.SSLCertVerificationError(1, "x")
    assert classify_transport_error(wrapped)["category"] == "tls_certificate_invalid"                    # 알 수 없는 검증 코드
    assert classify_transport_error(RuntimeError("other")) is None
    e = ssl.SSLCertVerificationError(1, "hostname")
    e.verify_code = 62
    assert classify_transport_error(ExceptionGroup("g", [e]))["verify_code"] == 62                      # 예외 그룹 안쪽까지 본다
    for text in ("FAKEHOST.secret.example", "x509 secret"):
        assert text not in dump(classify_transport_error(ExceptionGroup("g", [ssl.SSLCertVerificationError(1, text)])))     # 메시지 원문 비저장


# ---- TLS 검증을 끌 수 없음, 환경변수 무시 -------------------------------------------------------------------------

def test_there_is_no_way_to_disable_tls_verification(tmp_path, pki):
    ctx = build_ssl_context(pki.ca1)
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True and ctx.minimum_version >= ssl.TLSVersion.TLSv1_2
    for fn in (build_config_target, build_ssl_context, discover, ld.DiscoveryLimits):
        names = " ".join(inspect.signature(fn).parameters).lower()
        assert not any(w in names for w in ("verify", "insecure", "cert_reqs", "check_hostname", "skip_tls"))
    out = subprocess.run([sys.executable, "-m", "asset_scanner.live_discovery", "--insecure", "--demo-stdio", "--output", str(tmp_path / "x.json")], cwd=SCANNER_ROOT,
                         capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 2
    cfg = tmp_path / "c.json5"
    cfg.write_text(json.dumps({"mcp": {"servers": {"s": {"url": "https://localhost:1/mcp"}}}}), encoding="utf-8")
    t = build_config_target(cfg, "s", "mcp.servers", False, True, [], None, pki.ca1)
    assert t.ssl_context.verify_mode == ssl.CERT_REQUIRED and t.description["tls"]["can_be_disabled"] is False


def test_proxy_and_certificate_environment_variables_are_ignored(tmp_path, pki, monkeypatch):
    with https_server(tmp_path, "srv", pki.good) as srv:
        monkeypatch.setenv("SCANNER_TEST_TOKEN", srv.token)
        for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "HTTP_PROXY"):
            monkeypatch.setenv(name, "http://127.0.0.1:9")                                    # 닫힌 포트: 읽었다면 연결이 실패한다
        monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "nonexistent.pem"))
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(tmp_path / "nonexistent.pem"))
        monkeypatch.setenv("CURL_CA_BUNDLE", str(tmp_path / "nonexistent.pem"))
        rep, *_ = run_discovery(tmp_path, f"https://localhost:{srv.port}/mcp", ca=pki.ca1, bearer_env="SCANNER_TEST_TOKEN")
    assert rep["collection"]["status"] == "complete" and rep["tls"]["env_proxy_and_cert_variables_read"] is False


# ---- 리다이렉트·교차 출처 -----------------------------------------------------------------------------------------

def test_redirect_to_another_host_is_not_followed_and_the_token_never_reaches_it(tmp_path, pki, monkeypatch):
    with https_server(tmp_path, "b", pki.good_b) as b:
        with https_server(tmp_path, "a", pki.good, redirect_to=f"https://127.0.0.1:{b.port}/mcp") as a:
            monkeypatch.setenv("SCANNER_TEST_TOKEN", a.token)
            rep, *_ = run_discovery(tmp_path, f"https://localhost:{a.port}/mcp", ca=pki.ca1, bearer_env="SCANNER_TEST_TOKEN")
            a_events, b_events = read_log(a.log), read_log(b.log)
    assert rep["collection"]["status"] == "failed" and rep["collection"]["outcome"] == "redirect_not_followed"
    assert rep["tls"]["redirect_responses_seen"] >= 1 and rep["tls"]["redirects_followed"] == 0
    assert any(e["event"] == "http" for e in a_events)                                           # 처음 요청은 의도한 서버에 갔다
    assert [e for e in b_events if e["event"] in ("http", "request")] == []                       # 리다이렉트 대상 서버는 어떤 요청도 받지 않았다
    assert a.token not in dump(rep) + dump(a_events) + dump(b_events) and rep["requests"]["by_method"] == {}


def test_a_request_to_another_origin_is_blocked_before_it_is_sent():
    import anyio
    import httpx2
    state = ld._State()
    guard = make_origin_guard(state, "https://api.example.test:8443/mcp")
    same = httpx2.Request("POST", "https://api.example.test:8443/other/path", headers={"Authorization": "Bearer FAKE"})
    anyio.run(guard, same)                                                                       # 같은 출처는 통과
    assert state.cross_origin_blocked == 0
    # 호스트·기본 포트·스킴·IP 표기·끝에 점이 붙은 호스트는 모두 다른 출처다 (잘못된 포트 문자열은 클라이언트가 요청을 만들기 전에 거부한다)
    for url in ("https://evil.test:8443/mcp", "https://api.example.test/mcp", "http://api.example.test:8443/mcp",
                "https://127.0.0.1:8443/mcp", "https://api.example.test.:8443/mcp"):
        with pytest.raises(ld._CrossOriginBlocked):
            anyio.run(guard, httpx2.Request("POST", url, headers={"Authorization": "Bearer FAKE"}))
    assert state.cross_origin_blocked == 5
    anyio.run(guard, httpx2.Request("POST", "https://API.EXAMPLE.test:8443/x"))             # 호스트의 대소문자 차이는 같은 출처
    assert state.cross_origin_blocked == 5


# ---- 대상 선택·거부 (접속하지 않는다) ------------------------------------------------------------------------------

def write_cfg(tmp, decl):
    p = tmp / "c.json5"
    p.write_text(json.dumps({"mcp": {"servers": {"s": decl}}}), encoding="utf-8")
    return p


def target_for(tmp, decl, *, allow_hosts=(), bearer_env=None, ca=None, header_envs=None):
    return build_config_target(write_cfg(tmp, decl), "s", "mcp.servers", False, True, list(allow_hosts), bearer_env, ca, header_envs)


def test_remote_hosts_need_https_and_an_exact_allow_host(tmp_path, pki, monkeypatch):
    assert target_for(tmp_path, {"url": "https://mcp.example.test/mcp"}).refused["code"] == "host_not_allowed"
    assert target_for(tmp_path, {"url": "http://mcp.example.test/mcp"}, allow_hosts=["mcp.example.test"]).refused["code"] == "insecure_remote_http"
    ok = target_for(tmp_path, {"url": "https://mcp.example.test:8443/mcp"}, allow_hosts=["mcp.example.test"])       # 접속하지 않고 대상만 만든다
    assert ok.refused is None and ok.description["allowed_by"] == "--allow-host" and ok.description["tls"]["verify_hostname"] is True
    assert ok.description["tls"]["trust"] == "system_default" and ok.ssl_context is not None
    assert target_for(tmp_path, {"url": "https://other.example.test/mcp"}, allow_hosts=["mcp.example.test"]).refused["code"] == "host_not_allowed"
    loop = target_for(tmp_path, {"url": "http://127.0.0.1:1/mcp"})                                                    # 루프백은 평문도 허용(기존 동작)
    assert loop.refused is None and loop.ssl_context is None and "tls" not in loop.description


def test_ca_bundle_must_be_a_readable_certificate_and_only_for_https(tmp_path, pki):
    https = {"url": "https://localhost:1/mcp"}
    assert target_for(tmp_path, https, ca=tmp_path / "missing.pem").refused["code"] == "ca_bundle_not_found"
    junk = tmp_path / "junk.pem"
    junk.write_text("not a certificate", encoding="utf-8")
    assert target_for(tmp_path, https, ca=junk).refused["code"] == "ca_bundle_invalid"
    assert target_for(tmp_path, {"url": "http://127.0.0.1:1/mcp"}, ca=pki.ca1).refused["code"] == "ca_bundle_requires_https"
    ok = target_for(tmp_path, https, ca=pki.ca1)
    assert ok.refused is None and ok.description["tls"]["trust"] == "system_default+custom_ca_bundle" and ok.description["tls"]["ca_bundle_set"] is True
    assert str(pki.ca1) not in dump(ok.description)                                                                    # CA 파일 경로는 기록하지 않음


@pytest.mark.parametrize("spec, env_set, code", [
    ("X-Api-Key", True, "auth_header_env_invalid"), ("=ENVV", True, "auth_header_env_invalid"), ("X Api=ENVV", True, "auth_header_env_invalid"),
    ("X-Api-Key=bad name", True, "auth_header_env_invalid"), ("Host=ENVV", True, "auth_header_name_forbidden"),
    ("content-length=ENVV", True, "auth_header_name_forbidden"), ("Transfer-Encoding=ENVV", True, "auth_header_name_forbidden"),
    ("Mcp-Session-Id=ENVV", True, "auth_header_name_forbidden"), ("X-Api-Key=ENVV", False, "auth_header_env_not_set"),
])
def test_auth_header_options_are_validated_before_anything_is_sent(tmp_path, monkeypatch, spec, env_set, code):
    monkeypatch.delenv("ENVV", raising=False)
    if env_set:
        monkeypatch.setenv("ENVV", "FAKE-HEADER-VALUE")
    t = target_for(tmp_path, {"url": "https://localhost:1/mcp"}, header_envs=[spec])
    assert t.refused["code"] == code and "FAKE-HEADER-VALUE" not in dump(t.refused)


def test_duplicate_authentication_headers_are_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVV", "FAKE-VALUE")
    monkeypatch.setenv("TOKV", "FAKE-TOKEN")
    two = target_for(tmp_path, {"url": "https://localhost:1/mcp"}, header_envs=["X-A=ENVV", "x-a=ENVV"])
    assert two.refused["code"] == "duplicate_auth_header"
    declared = target_for(tmp_path, {"url": "https://localhost:1/mcp", "headers": {"X-A": "literal"}}, header_envs=["x-a=ENVV"])
    assert declared.refused["code"] == "duplicate_auth_header"
    both = target_for(tmp_path, {"url": "https://localhost:1/mcp"}, bearer_env="TOKV", header_envs=["X-A=ENVV"])
    assert both.refused is None and both.description["auth"] == "bearer_from_env_var+header_from_env_var" and both.description["header_names"] == ["Authorization", "X-A"]
    assert "FAKE-VALUE" not in dump(both.description) and "FAKE-TOKEN" not in dump(both.description)
    over = target_for(tmp_path, {"url": "https://localhost:1/mcp", "headers": {"authorization": "Bearer FAKE-LITERAL"}}, bearer_env="TOKV")
    assert over.headers == {"Authorization": "Bearer FAKE-TOKEN"}                                                          # 환경의 토큰이 이긴다(헤더가 둘로 나가지 않음)


@pytest.mark.parametrize("decl, code, followup", [
    ({"url": "https://localhost:1/mcp", "auth": "oauth"}, "oauth_not_supported", "oauth_login"),
    ({"url": "https://localhost:1/mcp", "oauth": {"scope": "x"}}, "oauth_not_supported", "oauth_login"),
    ({"url": "https://localhost:1/sse", "transport": "sse"}, "transport_not_supported", "sse_transport"),
])
def test_oauth_and_sse_remain_explicitly_unsupported_follow_up_work(tmp_path, decl, code, followup):
    t = target_for(tmp_path, decl)
    assert t.refused["code"] == code and t.refused["followup"] == followup
    rep = build_report(discover(t, FAST))
    assert rep["collection"]["outcome"] == "target_refused" and rep["target_refused"]["followup"] == followup and rep["source"]["live_server_query"] is False
    ss = rep["scope"]["support_status"]
    assert ss["oauth_login"].startswith("not_supported") and ss["sse_transport"].startswith("not_supported") and ss["streamable_http"] == "supported"
    assert ss["https_tls_verification"].startswith("supported")


# ---- CLI ---------------------------------------------------------------------------------------------------

def cli(*args, env_extra=None):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", **(env_extra or {}))
    return subprocess.run([sys.executable, "-m", "asset_scanner.live_discovery", *map(str, args)], cwd=SCANNER_ROOT, env=env, capture_output=True, text=True, encoding="utf-8")


def test_cli_https_end_to_end_and_argument_rules(tmp_path, pki):
    with https_server(tmp_path, "srv", pki.good) as srv:
        cfg = write_cfg(tmp_path, {"url": f"https://localhost:{srv.port}/mcp"})
        out, cat = tmp_path / "o.json", tmp_path / "c.json"
        ok = cli("--config", cfg, "--server", "s", "--allow-connect", "--ca-bundle", pki.ca1, "--bearer-env", "SCANNER_CLI_TOKEN", "--config-scan-ref", "gw",
                 "--output", out, "--catalog-output", cat, env_extra={"SCANNER_CLI_TOKEN": srv.token})
        events = read_log(srv.log)
        assert ok.returncode == 0, ok.stderr
        assert "TLS: 인증서 체인·호스트 이름 검증 켜짐(끌 수 없음)" in ok.stdout and "complete" in ok.stdout
        saved = out.read_text(encoding="utf-8")
        assert srv.token not in ok.stdout + ok.stderr + saved + cat.read_text(encoding="utf-8") + dump(events)
        assert json.loads(cat.read_text(encoding="utf-8"))["servers"][0]["config_link"]["config_scan_ref"] == "gw"
        bad = cli("--config", cfg, "--server", "s", "--allow-connect", "--bearer-env", "SCANNER_CLI_TOKEN", "--output", tmp_path / "b.json",
                  env_extra={"SCANNER_CLI_TOKEN": srv.token})                                                    # CA를 더하지 않음: 검증 실패
        assert bad.returncode == 3 and "tls_certificate_untrusted" in bad.stdout and srv.token not in bad.stdout + bad.stderr
    assert cli("--demo-stdio", "--ca-bundle", pki.ca1, "--output", tmp_path / "x.json").returncode == 2             # --config 없이 쓸 수 없음
    assert cli("--demo-stdio", "--auth-header-env", "X=Y", "--output", tmp_path / "x.json").returncode == 2
    refused = cli("--config", cfg, "--server", "s", "--allow-connect", "--auth-header-env", "Host=ENVV", "--output", tmp_path / "r.json", env_extra={"ENVV": "x"})
    assert refused.returncode == 3 and "auth_header_name_forbidden" in refused.stdout
