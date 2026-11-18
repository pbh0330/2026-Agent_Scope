"""가짜 인증 자료만 사용한다. 원본 DB/WAL 불변·비밀 비노출·고정 스키마 거부를 검증한다."""
import base64
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from asset_scanner.auth_metadata import collect_auth_metadata
from asset_scanner.source_io import SourceError, read_state_rows
from conftest import SCANNER_ROOT


def write(tmp_path, name, value):
    path = tmp_path / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_profile_metadata_whitelist_and_no_secret_or_personal_identity(tmp_path):
    p = write(tmp_path, "auth.json", {"version": 1, "profiles": {"provider:FAKE_PERSON@example.test": {
        "type": "oauth", "provider": "sample", "issuer": "https://issuer.example.test", "expires": 1900000000000,
        "access": "FAKE_ACCESS", "refresh": "FAKE_REFRESH", "email": "FAKE_EMAIL", "accountId": "FAKE_ACCOUNT", "idToken": "FAKE_ID_TOKEN"}}})
    before = p.read_bytes()
    report = collect_auth_metadata([p])
    assert report["collection"]["status"] == "complete" and p.read_bytes() == before
    item = report["items"][0]
    assert item["metadata"]["issuer"] == "https://issuer.example.test"
    assert item["metadata"]["expires"]["value"] == 1900000000000 and item["metadata"]["expires"]["unit"] == "unix_milliseconds"
    assert item["secret_fields_declared"] == ["access", "idToken", "refresh"]
    assert "token_claim_observations" not in item and "FAKE" not in json.dumps(report)


def test_jwt_audience_is_opt_in_and_explicitly_unverified(tmp_path):
    claims = {"iss": "https://issuer.test", "aud": ["mcp-a", "mcp-b"], "exp": 1900000000, "scope": "read docs", "sub": "FAKE_SUBJECT", "email": "FAKE_EMAIL"}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    token = "eyJhbGciOiJub25lIn0." + payload + ".FAKE_SIGNATURE"
    p = write(tmp_path, "auth.json", {"version": 1, "profiles": {"sample": {"type": "token", "provider": "sample", "token": token}}})
    report = collect_auth_metadata([p], inspect_token_claims=True)
    observation = report["items"][0]["token_claim_observations"][0]
    assert observation["status"] == "decoded_unverified" and observation["signature_verified"] is False
    assert observation["claims"]["aud"] == ["mcp-a", "mcp-b"]
    assert "sub" not in observation["claims"] and "email" not in observation["claims"]
    assert token not in json.dumps(report) and "FAKE" not in json.dumps(report)


@pytest.mark.parametrize("token", ["FAKE_OPAQUE", "a.@@@.b", "a." + "x" * 33000 + ".b", None, [], "a.e30.b"])
def test_opaque_or_malformed_token_is_not_used_or_echoed(tmp_path, token):
    p = write(tmp_path, "auth.json", {"version": 1, "profiles": {"p": {"type": "token", "provider": "p", "token": token}}})
    report = collect_auth_metadata([p], inspect_token_claims=True)
    assert len(report["items"]) == 1
    assert "FAKE_OPAQUE" not in json.dumps(report)
    assert not report["items"][0]["token_claim_observations"][0]["signature_verified"]


@pytest.mark.parametrize("expiry", [True, 0, -1, "tomorrow", 10**100])
def test_wrong_expiry_types_and_unrepresentable_timestamp_are_partial(tmp_path, expiry):
    p = write(tmp_path, "auth.json", {"version": 1, "profiles": {"p": {"type": "token", "provider": "p", "expires": expiry}}})
    report = collect_auth_metadata([p])
    assert report["collection"]["status"] == "partial" and "expires" not in report["items"][0]["metadata"]


def mcp_store():
    return {"tokens": {"access_token": "FAKE_ACCESS", "refresh_token": "FAKE_REFRESH", "scope": "files:read", "token_type": "Bearer"},
            "tokenExpiresAt": 1900000000000, "codeVerifier": "FAKE_VERIFIER", "redirectUrl": "http://localhost/callback",
            "discoveryState": {"authorizationServerUrl": "https://auth.example.test", "authorizationServerMetadata": {"issuer": "https://auth.example.test", "token_endpoint": "https://user:FAKE_PASSWORD@auth.example.test/token"},
                               "resourceMetadata": {"resource": "https://mcp.example.test", "authorization_servers": ["https://auth.example.test"], "scopes_supported": ["files:read"]}}}


def test_mcp_discovery_metadata_distinguishes_resource_from_audience(tmp_path):
    p = write(tmp_path, "mcp.json", mcp_store())
    report = collect_auth_metadata(mcp_exports=[p])
    meta = report["items"][0]["metadata"]
    assert meta["resourceMetadata"]["resource"] == "https://mcp.example.test" and "audience" not in meta
    assert meta["scope"] == "files:read" and "FAKE" not in json.dumps(report)


def test_sqlite_with_wal_is_read_from_a_private_snapshot_without_changing_source(tmp_path):
    db = tmp_path / "state.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE mcp_oauth_stores(store_key TEXT,format_version INTEGER,store_json TEXT)")
    conn.execute("INSERT INTO mcp_oauth_stores VALUES(?,?,?)", ("FAKE_PRIVATE_STORE", 1, json.dumps(mcp_store())))
    conn.commit()
    paths = [db, Path(str(db) + "-wal"), Path(str(db) + "-shm")]
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
    try:
        report = collect_auth_metadata(state_databases=[db])
        assert report["collection"]["status"] == "complete" and report["collection"]["item_count"] == 1
        assert "FAKE" not in json.dumps(report)
        assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths} == before
    finally:
        conn.close()


def test_sqlite_unsupported_schema_and_views_are_refused_without_running_them(tmp_path):
    for n, query in enumerate(["CREATE TABLE mcp_oauth_stores(wrong TEXT)", "CREATE VIEW mcp_oauth_stores AS SELECT load_extension('FAKE_EXTENSION')"]):
        db = tmp_path / f"bad{n}.sqlite"
        with sqlite3.connect(db) as conn:
            conn.execute(query)
        report = collect_auth_metadata(state_databases=[db])
        assert report["collection"]["status"] == "failed"
        assert report["sources"][0]["issues"][0]["code"] == "state_schema_unsupported"
        assert "FAKE_EXTENSION" not in json.dumps(report)


def test_missing_database_is_not_created_and_missing_table_is_an_empty_result(tmp_path):
    missing = tmp_path / "missing.sqlite"
    assert collect_auth_metadata(state_databases=[missing])["collection"]["status"] == "failed"
    assert not missing.exists()
    empty = tmp_path / "empty.sqlite"
    with sqlite3.connect(empty) as conn:
        conn.execute("CREATE TABLE unrelated(secret TEXT)")
    assert read_state_rows(empty, "mcp_oauth") == []


def test_duplicate_keys_are_partial_and_no_private_diagnostic_path_is_emitted(tmp_path):
    p = tmp_path / "dup.json"
    p.write_text('{"version":1,"profiles":{"FAKE_PERSON":{"type":"token","provider":"p","expires":1,"expires":2}}}')
    report = collect_auth_metadata([p])
    assert report["collection"]["status"] == "partial" and "FAKE_PERSON" not in json.dumps(report)


def test_cli_exit_code_and_input_overwrite_refusal(tmp_path):
    p = write(tmp_path, "profiles.json", {"version": 1, "profiles": {}})
    out = tmp_path / "out.json"
    cmd = [sys.executable, "-m", "asset_scanner.auth_metadata", "--auth-profiles-json", str(p), "--output"]
    assert subprocess.run(cmd + [str(out)], cwd=SCANNER_ROOT, capture_output=True).returncode == 0
    before = p.read_bytes()
    assert subprocess.run(cmd + [str(p)], cwd=SCANNER_ROOT, capture_output=True).returncode == 2 and p.read_bytes() == before


def test_linked_database_is_not_followed(tmp_path):
    p = tmp_path / "db.sqlite"
    with sqlite3.connect(p) as conn:
        conn.execute("CREATE TABLE unrelated(x)")
    linked = tmp_path / "linked.sqlite"
    os.link(p, linked)
    with pytest.raises(SourceError, match="source_not_regular_or_linked"):
        read_state_rows(linked, "mcp_oauth")


def test_personal_model_account_namespace_preserves_owner_partition_without_identity(tmp_path):
    db = tmp_path / "models.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE secret_store_entries(scope_kind TEXT,scope_id TEXT,name TEXT,kind TEXT,allowed_hosts TEXT,deleted_at_ms INTEGER,value TEXT)")
        for owner, suffix in (("FAKE_OWNER_A", "first"), ("FAKE_OWNER_A", "second"), ("FAKE_OWNER_B", "third")):
            value = json.dumps({"version": 1, "credential": {"type": "oauth", "provider": "sample", "issuer": "https://issuer.test", "access": "FAKE_ACCESS", "refresh": "FAKE_REFRESH", "expires": 1900000000000}})
            conn.execute("INSERT INTO secret_store_entries VALUES(?,?,?,?,?,?,?)", ("identity", owner, "model-account:" + suffix, "secret", None, None, value))
        conn.execute("INSERT INTO secret_store_entries VALUES(?,?,?,?,?,?,?)", ("identity", "FAKE_OWNER", "other-secret", "secret", None, None, "FAKE_NON_JSON_MUST_NOT_BE_QUERIED"))
        conn.execute("INSERT INTO secret_store_entries VALUES(?,?,?,?,?,?,?)", ("identity", "FAKE_OWNER", "model-account:deleted", "secret", None, 1, "FAKE_DELETED_NON_JSON"))
    before = db.read_bytes()
    report = collect_auth_metadata(model_account_databases=[db])
    assert report["collection"]["status"] == "complete" and len(report["items"]) == 3
    refs = [i["stored_owner_partition_ref"] for i in report["items"]]
    assert refs[0] == refs[1] and refs[2] != refs[0]
    assert all(i["owner_identity_resolved"] is False for i in report["items"])
    assert "FAKE" not in json.dumps(report) and db.read_bytes() == before
    assert collect_auth_metadata(state_databases=[db])["items"] == []  # MCP 선택만으로 개인 계정 원천을 읽지 않음


@pytest.mark.parametrize("version,kind,allowed", [(2, "secret", None), (1, "reference", None), (1, "secret", "[\"host\"]")])
def test_model_account_wrong_shape_is_partial_not_assumed_valid(tmp_path, version, kind, allowed):
    db = tmp_path / "models.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE secret_store_entries(scope_kind,scope_id,name,kind,allowed_hosts,deleted_at_ms,value)")
        conn.execute("INSERT INTO secret_store_entries VALUES(?,?,?,?,?,?,?)", ("identity", "FAKE_OWNER", "model-account:p", kind, allowed, None,
                     json.dumps({"version": version, "credential": {"type": "token", "provider": "p", "token": "FAKE_TOKEN"}})))
    report = collect_auth_metadata(model_account_databases=[db])
    assert report["collection"]["status"] == "partial" and report["items"] == [] and "FAKE" not in json.dumps(report)


@pytest.mark.parametrize("expiry,expected", [(999, True), (1000, True), (1001, False)])
def test_expiry_is_compared_with_explicit_scanner_clock_not_credential_validity(tmp_path, expiry, expected):
    p = write(tmp_path, "auth.json", {"version": 1, "profiles": {"p": {"type": "token", "provider": "p", "expires": expiry}}})
    report = collect_auth_metadata([p], now_ms=1000)
    assert report["items"][0]["metadata"]["expires"]["expired_against_scanner_clock"] is expected
    assert "credential_is_currently_usable" in report["scope"]["not_verified"]
