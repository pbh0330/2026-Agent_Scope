"""명시한 인증 저장 자료의 허용된 메타데이터만 수집한다. 로그인·갱신·네트워크·인증값 저장 없음.

원천: OpenClaw eb377ac auth-profiles/{types,credential-schema}.ts,
mcp-oauth-store.{types,kernel}.ts, state/user-model-accounts.ts. JWT 해석은 별도 opt-in이며 서명·issuer·audience를 검증하지 않는다.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import math
from pathlib import Path
import re
import sys

from .cli import _make_console_output_safe, _same_file
from .output import OutputError, normalize_for_output, write_json_atomic
from .plugin_skill_assets import _safe_path
from .redaction import Redactor
from .source_io import MAX_ROWS, SourceError, duplicate_count, parse_source_json, read_source_json, read_state_rows

BASIS = "openclaw/openclaw eb377ac59e6c9fd6c7705028034812becf00271b auth-profiles/types.ts, credential-schema.ts; mcp-oauth-store.types.ts, kernel.ts; state/user-model-accounts.ts"
SECRET_FIELDS = frozenset({"access", "refresh", "token", "key", "idToken", "access_token", "refresh_token", "id_token", "client_secret", "codeVerifier"})


def _finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) <= 2**53 - 1 and (not isinstance(value, float) or math.isfinite(value))


def _claims(token):
    """최대 32KiB JWT의 허용 클레임만 검사한다. 토큰·서명·주체 클레임은 반환하지 않는다."""
    if not isinstance(token, str) or len(token) > 32768:
        return None, "not_inspected"
    parts = token.split(".")
    if len(parts) != 3 or not re.fullmatch(r"[A-Za-z0-9_-]+", parts[1]) or len(parts[1]) > 12000:
        return None, "not_a_supported_jwt"
    try:
        raw = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
        if len(raw) > 8192:
            return None, "claims_limit_exceeded"
        data = parse_source_json(raw)
    except (ValueError, SourceError):
        return None, "claims_invalid"
    if not isinstance(data, dict) or duplicate_count(data):
        return None, "claims_invalid"
    values = {}
    for key in ("iss", "aud", "scope", "exp"):
        if key not in data:
            continue
        value = data[key]
        if key == "exp" and _finite_number(value):
            values[key] = value
        elif key in ("iss", "scope") and isinstance(value, str):
            values[key] = value
        elif key == "aud" and (isinstance(value, str) or (isinstance(value, list) and len(value) <= 100 and all(isinstance(v, str) for v in value))):
            values[key] = value
    return values, "decoded_unverified"


def collect_auth_metadata(auth_profiles=(), mcp_exports=(), state_databases=(), inspect_token_claims=False, now_ms=None, model_account_databases=()):
    clock_ms = datetime.now(timezone.utc).timestamp() * 1000 if now_ms is None else now_ms
    if not _finite_number(clock_ms):
        raise ValueError("observation clock must be finite")
    report = {"format": "agent-scope.scanner.auth-metadata", "observation_clock_unix_ms": clock_ms, "format_version": "0.1.0-draft",
              "generated_at": datetime.now(timezone.utc).isoformat(), "sources": [], "items": [], "issues": [],
              "basis": BASIS,
              "scope": {"method": "operator_selected_stored_auth_metadata", "token_claims_requested": inspect_token_claims,
                        "not_collected": ["credential_values_and_hashes", "email_subject_and_account_identity", "login_or_refresh", "effective_permissions", "common_asset_id"],
                        "not_verified": ["jwt_signature", "issuer_audience_validity", "credential_is_currently_usable", "live_openclaw"]}}

    def problem(source, code):
        source["status"] = "partial" if source["status"] == "complete" else source["status"]
        source["issues"].append({"severity": "error", "code": code})

    def text(item, key, value, source, red):
        if isinstance(value, str):
            item[key] = red.sanitize_string(value, "metadata." + key)
        else:
            problem(source, "metadata_field_type_invalid")

    def record(data, kind, source, index):
        if not isinstance(data, dict):
            problem(source, "credential_record_not_object")
            return
        red = Redactor()
        item = {"ref": f"auth-item[{len(report['items'])}]", "source_ref": source["ref"], "source_record_index": index,
                "source_kind": kind, "source_key": {"status": "withheld", "original_value": None},
                "source_pointer_is_original": False, "metadata": {}, "secret_fields_declared": sorted(k for k in SECRET_FIELDS if k in data)}
        report["items"].append(item)
        meta = item["metadata"]
        if kind == "auth_profile":
            typ = data.get("type")
            if typ not in ("oauth", "token", "api_key"):
                problem(source, "credential_type_unsupported")
                return
            meta["credential_type"] = typ
            if "provider" not in data or not isinstance(data["provider"], str) or not data["provider"]:
                problem(source, "provider_missing_or_invalid")
            else:
                text(meta, "provider", data["provider"], source, red)
            if typ == "oauth":
                for key in ("clientId", "issuer", "tokenEndpoint", "deviceAuthorizationEndpoint", "authFlow"):
                    if key in data:
                        text(meta, key, data[key], source, red)
            if "expires" in data:
                if _finite_number(data["expires"]) and data["expires"] > 0:
                    meta["expires"] = {"value": data["expires"], "unit": "unix_milliseconds", "origin": "stored_declaration", "expired_against_scanner_clock": data["expires"] <= clock_ms}
                else:
                    problem(source, "expiry_invalid")
            for key in ("keyRef", "tokenRef", "oauthRef"):
                if key in data:
                    item.setdefault("reference_fields_declared", []).append(key)
        else:
            for key in ("tokensAuthorizationServerUrl", "redirectUrl"):
                if key in data:
                    text(meta, key, data[key], source, red)
            if "tokenExpiresAt" in data:
                if _finite_number(data["tokenExpiresAt"]) and data["tokenExpiresAt"] > 0:
                    meta["tokenExpiresAt"] = {"value": data["tokenExpiresAt"], "unit": "unix_milliseconds", "origin": "stored_declaration", "expired_against_scanner_clock": data["tokenExpiresAt"] <= clock_ms}
                else:
                    problem(source, "expiry_invalid")
            tokens = data.get("tokens", {})
            if not isinstance(tokens, dict):
                problem(source, "tokens_structure_invalid")
                tokens = {}
            item["secret_fields_declared"] += sorted(k for k in SECRET_FIELDS if k in tokens)
            for key in ("scope", "token_type"):
                if key in tokens:
                    text(meta, key, tokens[key], source, red)
            discovery = data.get("discoveryState", {})
            if not isinstance(discovery, dict):
                problem(source, "discovery_structure_invalid")
                discovery = {}
            for key in ("authorizationServerUrl", "resourceMetadataUrl"):
                if key in discovery:
                    text(meta, key, discovery[key], source, red)
            for field, keys in (("authorizationServerMetadata", ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri", "scopes_supported")),
                                ("resourceMetadata", ("resource", "authorization_servers", "scopes_supported"))):
                if field not in discovery:
                    continue
                obj = discovery[field]
                if not isinstance(obj, dict):
                    problem(source, "discovery_metadata_invalid")
                    continue
                meta[field] = {}
                for key in keys:
                    if key not in obj:
                        continue
                    val = obj[key]
                    if key in ("authorization_servers", "scopes_supported"):
                        if isinstance(val, list) and len(val) <= 100 and all(isinstance(x, str) for x in val):
                            meta[field][key] = [red.sanitize_string(x, key) for x in val]
                        else:
                            problem(source, "discovery_metadata_invalid")
                    else:
                        text(meta[field], key, val, source, red)
            if inspect_token_claims:
                data = {**data, **{k: v for k, v in tokens.items() if k in ("access_token", "id_token")}}
        if inspect_token_claims:
            item["token_claim_observations"] = []
            for key in ("access", "token", "idToken", "access_token", "id_token"):
                if key not in data:
                    continue
                claims, status = _claims(data[key])
                observation = {"credential_field": key, "status": status, "signature_verified": False}
                if claims is not None:
                    observation["claim_time_unit"] = "unix_seconds"
                    observation["claims"] = {k: [red.sanitize_string(x, "claim." + k) for x in v] if isinstance(v, list)
                                              else red.sanitize_string(v, "claim." + k) if isinstance(v, str) else v for k, v in claims.items()}
                item["token_claim_observations"].append(observation)
        item["redactions"] = red.redactions

    for kind, paths in (("auth_profile", auth_profiles), ("mcp_oauth", mcp_exports), ("state_database", state_databases), ("model_account_database", model_account_databases)):
        for path in paths:
            source = {"ref": f"auth-source[{len(report['sources'])}]", "file": _safe_path(Path(path))[0],
                      "kind": kind, "status": "complete", "issues": []}
            report["sources"].append(source)
            try:
                if kind == "model_account_database":
                    owners = {}
                    for n, (owner, _name, record_kind, allowed_hosts, raw) in enumerate(read_state_rows(Path(path), "model_accounts")):
                        if not isinstance(owner, str) or not owner or record_kind != "secret" or allowed_hosts is not None:
                            problem(source, "model_account_record_invalid")
                            continue
                        payload = parse_source_json(raw)
                        if not isinstance(payload, dict) or type(payload.get("version")) is not int or payload["version"] != 1 or not isinstance(payload.get("credential"), dict):
                            problem(source, "model_account_payload_unsupported")
                            continue
                        if duplicate_count(payload):
                            problem(source, "duplicate_key")
                        owners.setdefault(owner, len(owners))
                        record(payload["credential"], "auth_profile", source, n)
                        report["items"][-1]["stored_owner_partition_ref"] = f"{source['ref']}:owner[{owners[owner]}]"
                        report["items"][-1]["owner_identity_resolved"] = False
                    continue
                if kind == "state_database":
                    for n, (_, version, raw) in enumerate(read_state_rows(Path(path), "mcp_oauth")):
                        if type(version) is not int or version != 1:
                            problem(source, "mcp_store_version_unsupported")
                            continue
                        value = parse_source_json(raw)
                        if duplicate_count(value):
                            problem(source, "duplicate_key")
                        record(value, "mcp_oauth", source, n)
                    continue
                value = read_source_json(path)
                if duplicate_count(value):
                    problem(source, "duplicate_key")
                if kind == "auth_profile":
                    if not isinstance(value, dict) or not isinstance(value.get("version"), int) or isinstance(value.get("version"), bool) or value["version"] != 1 or not isinstance(value.get("profiles"), dict):
                        raise SourceError("auth_profile_store_structure_unsupported")
                    if len(value["profiles"]) > MAX_ROWS:
                        problem(source, "profile_limit_exceeded")
                    for n, data in enumerate(list(value["profiles"].values())[:MAX_ROWS]):
                        record(data, kind, source, n)
                else:
                    record(value, kind, source, 0)
            except SourceError as exc:
                source["status"] = "failed"
                problem(source, exc.code)
    statuses = [s["status"] for s in report["sources"]]
    status = "complete" if statuses and all(s == "complete" for s in statuses) else "failed" if not statuses or all(s == "failed" for s in statuses) else "partial"
    report["collection"] = {"status": status, "item_count": len(report["items"]), "source_count": len(statuses)}
    return report


def main(argv=None):
    _make_console_output_safe()
    parser = argparse.ArgumentParser(description="명시한 인증 자료의 비밀이 아닌 메타데이터만 수집합니다. 로그인·갱신·네트워크 요청 없음.")
    parser.add_argument("--auth-profiles-json", action="append", default=[], type=Path)
    parser.add_argument("--mcp-oauth-json", action="append", default=[], type=Path)
    parser.add_argument("--state-db", action="append", default=[], type=Path)
    parser.add_argument("--model-account-db", action="append", default=[], type=Path,
                        help="지정한 DB의 identity/model-account: 원천만 읽습니다. 다른 secret store 항목은 조회하지 않음")
    parser.add_argument("--inspect-token-claims", action="store_true", help="JWT의 iss/aud/scope/exp만 한도 내 해석(서명 검증·인증 아님)")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    inputs = args.auth_profiles_json + args.mcp_oauth_json + args.state_db + args.model_account_db
    if not inputs:
        parser.error("하나 이상의 입력을 지정하세요.")
    if any(_same_file(p, args.output) or _same_file(Path(str(p) + suffix), args.output) for p in inputs for suffix in ("-wal", "-shm")):
        parser.error("출력은 입력 DB·JSON·WAL·SHM과 달라야 합니다.")
    result, _ = normalize_for_output(collect_auth_metadata(args.auth_profiles_json, args.mcp_oauth_json, args.state_db, args.inspect_token_claims,
                                                        model_account_databases=args.model_account_db))
    try:
        write_json_atomic(args.output, result)
    except OutputError:
        return 4
    print(f"인증 메타데이터 수집: {result['collection']['status']}, {result['collection']['item_count']}개")
    return {"complete": 0, "partial": 1, "failed": 3}[result["collection"]["status"]]


if __name__ == "__main__":
    sys.exit(main())
