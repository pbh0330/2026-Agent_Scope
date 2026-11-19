"""Gateway·Node identity 수집(node_gateway_identity)과 linking의 관측 identity 연결 테스트.

입력은 테스트가 만든 **가상 출력 파일**이다. 이 테스트는 어떤 명령도 실행하지 않으며(실행하면 실패하도록 감시한다)
`FAKE` 표식이 붙은 값은 전부 가짜 비밀값이다.
"""

import json
import os
import subprocess
import sys

import pytest

from asset_scanner import node_gateway_identity as ngi
from asset_scanner.linking import build_link_report, link_scans
from asset_scanner.node_gateway_identity import build_report, collect_identities, parse_observed_at
from conftest import SCANNER_ROOT
from test_linking import GATEWAY, cat_server, gw, make, reasons  # noqa: F401  (make는 픽스처)

DEVICE = "9f2c" * 16                        # 64자 hex: 엔트로피 규칙으로 가려지면 안 되는 형태의 식별값
DEVICE2 = "1b7d" * 16
PUBKEY = "Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MEFCQ0Q"   # base64url 모양의 가상 공개키 (43자 내외)
TOKEN = "ghp_FAKEIDENTITYTOKEN1234567890abcdefgh"


def out_file(tmp_path, name, payload):
    p = tmp_path / name
    p.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def no_process_is_ever_started(monkeypatch):
    """이 모듈은 명령을 실행하지 않는다: 프로세스를 만들려는 시도가 있으면 즉시 실패시킨다."""
    def boom(*a, **k):
        raise AssertionError("프로세스를 실행하려 했습니다")
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(os, "system", boom)


def run(gateways=(), nodes=(), observed=None):
    return build_report(collect_identities(list(gateways), list(nodes), observed or {}))


def dump(x):
    return json.dumps(x, ensure_ascii=False)


# ---- 정상 ----------------------------------------------------------------------------------

def test_gateway_and_node_outputs_are_read_with_their_sources(tmp_path):
    g = out_file(tmp_path, "g.json", {"deviceId": DEVICE, "publicKey": PUBKEY})
    n = out_file(tmp_path, "n.json", {"deviceId": DEVICE2, "publicKey": PUBKEY})
    rep = run([("gw", g)], [("node1", n)])
    assert rep["collection"] == {"status": "complete", "outcome": "identities_read", "identity_count": 2}
    gi, ni = rep["identities"]
    assert (gi["kind"], gi["label"], ni["kind"], ni["label"]) == ("gateway", "gw", "node", "node1")
    assert gi["device_id"] == {"original_value": DEVICE, "status": "as_reported"}           # 64자 hex가 가려지지 않음
    assert gi["public_key"]["status"] == "as_reported" and gi["origin"] == "observed_from_stored_command_output"
    obs = gi["observation"]
    assert obs["command"] == "openclaw gateway call gateway.identity.get --json" and obs["read_only_command"] is True
    assert obs["required_scope"] == "operator.read" and "callGatewayReadOnlyCli" in obs["basis"]
    assert ni["observation"]["command"] == "openclaw node identity --json" and ni["observation"]["required_scope"] is None
    for o in (gi["observation"], ni["observation"]):
        assert o["executed_by_scanner"] is False and o["verified_by_scanner"] is False and o["source_kind"] == "stored_command_output"
    assert "공통 자산 ID로 확정하지 않았습니다" in rep["format_status"]
    assert "command_executed_by_scanner" in rep["scope"]["not_verified"]


def test_observation_time_is_only_what_the_operator_declared(tmp_path):
    g = out_file(tmp_path, "g.json", {"deviceId": DEVICE, "publicKey": PUBKEY})
    none = run([(None, g)])["identities"][0]["observation"]
    assert none["observed_at"] is None and none["observed_at_origin"] is None and none["file_modified_at"] is not None
    assert "관측 시각이 아닙니다" in none["observed_at_note"]
    declared = run([("gw", g)], observed={"gw": "2026-11-12T00:00:00Z"})["identities"][0]["observation"]
    assert declared["observed_at"] == "2026-11-12T00:00:00Z" and declared["observed_at_origin"] == "operator_declared"
    assert declared["observed_at"] != declared["file_modified_at"]


@pytest.mark.parametrize("text, expected", [("2026-11-12T09:00:00+09:00", "2026-11-12T00:00:00Z"), ("2026-11-12T00:00:00Z", "2026-11-12T00:00:00Z"),
                                            ("2026-11-12T09:00:00", None), ("yesterday", None), ("", None)])
def test_observed_at_requires_a_timezone(text, expected):
    assert parse_observed_at(text) == expected          # 시간대 없는 값은 UTC로 가정하지 않는다


# ---- 오류와 경계 ------------------------------------------------------------------------------

@pytest.mark.parametrize("payload, device_status, outcome", [
    ({"publicKey": PUBKEY}, "missing", "device_id_missing"),
    ({"deviceId": "", "publicKey": PUBKEY}, "invalid", "device_id_invalid"),
    ({"deviceId": 5}, "invalid", "device_id_invalid"),
    ({"deviceId": "has space"}, "invalid", "device_id_invalid"),
    ({"deviceId": "x" * 201}, "invalid", "device_id_invalid"),
    ({"deviceId": TOKEN}, "withheld_by_redaction", "device_id_withheld_by_redaction"),
])
def test_device_id_problems_fail_that_observation_without_inventing_a_value(tmp_path, payload, device_status, outcome):
    rep = run([("gw", out_file(tmp_path, "g.json", payload))])
    it = rep["identities"][0]
    assert it["device_id"]["status"] == device_status and it["device_id"]["original_value"] is None
    assert (it["collection_status"], it["outcome"]) == ("failed", outcome) and rep["collection"]["status"] == "failed"
    assert "FAKEIDENTITYTOKEN" not in dump(rep)


@pytest.mark.parametrize("pk", ["-----BEGIN PRIVATE KEY-----\nFAKEPRIVATEKEYMATERIAL\n-----END PRIVATE KEY-----", "short", "has space in it ......", 7, TOKEN + "!"])
def test_a_public_key_that_is_not_base64url_is_not_stored(tmp_path, pk):
    rep = run([("gw", out_file(tmp_path, "g.json", {"deviceId": DEVICE, "publicKey": pk}))])
    it = rep["identities"][0]
    assert it["public_key"] == {"original_value": None, "status": "invalid_format"}
    assert it["device_id"]["status"] == "as_reported" and it["collection_status"] == "partial"   # deviceId는 보존
    assert "FAKEPRIVATEKEYMATERIAL" not in dump(rep)


def test_unknown_fields_are_listed_by_name_only_and_secrets_in_them_never_appear(tmp_path):
    p = {"deviceId": DEVICE, "publicKey": PUBKEY, "privateKey": "FAKEPRIVATEVALUE", "token": "FAKE-TOKEN-VALUE", TOKEN: "x"}
    rep = run([("gw", out_file(tmp_path, "g.json", p))])
    it = rep["identities"][0]
    assert "privateKey" in it["unknown_fields"] and "token" in it["unknown_fields"]
    assert any(i["code"] == "unknown_fields_ignored" for i in it["issues"]) and it["collection_status"] == "complete"
    assert "FAKEPRIVATEVALUE" not in dump(rep) and "FAKE-TOKEN-VALUE" not in dump(rep) and "FAKEIDENTITYTOKEN" not in dump(rep)


def test_wrapped_or_malformed_outputs_are_not_guessed(tmp_path):
    wrapped = out_file(tmp_path, "w.json", {"ok": True, "payload": {"deviceId": DEVICE, "publicKey": PUBKEY}})
    for name, content in (("arr.json", "[1]"), ("bad.json", "{ nope"), ("empty.json", "")):
        out_file(tmp_path, name, content)
    rep = run([("w", wrapped), ("a", tmp_path / "arr.json"), ("b", tmp_path / "bad.json"), ("e", tmp_path / "empty.json"), ("m", tmp_path / "missing.json")])
    assert [i["collection_status"] for i in rep["identities"]] == ["failed"] * 5
    assert rep["identities"][0]["device_id"]["status"] == "missing"              # 감싼 형태에서 값을 꺼내지 않는다
    assert "Traceback" not in dump(rep) and rep["collection"]["status"] == "failed"


def test_duplicate_keys_mark_the_observation_partial(tmp_path):
    p = out_file(tmp_path, "d.json", '{"deviceId":"' + DEVICE2 + '","deviceId":"' + DEVICE + '","publicKey":"' + PUBKEY + '"}')
    it = run([("gw", p)])["identities"][0]
    assert it["device_id"]["original_value"] == DEVICE and it["collection_status"] == "partial"
    assert any(i["code"] == "duplicate_key" for i in it["issues"])


def test_same_device_id_in_two_inputs_is_not_merged(tmp_path):
    g = out_file(tmp_path, "g.json", {"deviceId": DEVICE, "publicKey": PUBKEY})
    n = out_file(tmp_path, "n.json", {"deviceId": DEVICE, "publicKey": PUBKEY})
    rep = run([("gw", g)], [("nd", n)])
    assert len(rep["identities"]) == 2
    assert all(any(i["code"] == "same_device_id_in_multiple_inputs" for i in it["issues"]) for it in rep["identities"])


def test_duplicate_labels_drop_the_label_and_the_time(tmp_path):
    g1 = out_file(tmp_path, "g1.json", {"deviceId": DEVICE, "publicKey": PUBKEY})
    g2 = out_file(tmp_path, "g2.json", {"deviceId": DEVICE2, "publicKey": PUBKEY})
    rep = run([("gw", g1), ("gw", g2)], observed={"gw": "2026-11-12T00:00:00Z", "zzz": "2026-11-12T00:00:00Z"})
    assert [i["label"] for i in rep["identities"]] == [None, None] and all(i["observation"]["observed_at"] is None for i in rep["identities"])
    assert any(i["code"] == "observed_at_label_unused" for i in rep["issues"])


# ---- CLI ---------------------------------------------------------------------------------------

_REAL_RUN = subprocess.run      # 모듈을 불러오는 시점의 실제 함수 (감시용 패치 이전)


def run_cli(*args, module="asset_scanner.node_gateway_identity"):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return _REAL_RUN([sys.executable, "-m", module, *map(str, args)], cwd=SCANNER_ROOT, env=env, capture_output=True, text=True, encoding="utf-8")


def test_cli_exit_codes_and_outputs(tmp_path, monkeypatch):
    monkeypatch.undo()     # CLI를 별도 프로세스로 띄우는 것은 테스트 자체의 일이다. 감시용 패치를 해제한다
    g = out_file(tmp_path, "g.json", {"deviceId": DEVICE, "publicKey": PUBKEY, "privateKey": "FAKECLIPRIV"})
    out = tmp_path / "o.json"
    ok = run_cli("--gateway-identity", f"gw={g}", "--observed-at", "gw=2026-11-12T09:00:00+09:00", "--output", out)
    assert ok.returncode == 0 and "명령 실행 없음" in ok.stdout
    saved = out.read_text(encoding="utf-8")
    assert json.loads(saved)["identities"][0]["observation"]["observed_at"] == "2026-11-12T00:00:00Z"
    assert "FAKECLIPRIV" not in ok.stdout + ok.stderr + saved
    assert run_cli("--output", tmp_path / "x.json").returncode == 2                                           # 입력 없음
    assert run_cli("--gateway-identity", g, "--observed-at", "gw=not-a-time", "--output", tmp_path / "y.json").returncode == 2
    assert run_cli("--gateway-identity", g, "--observed-at", "gw=2026-11-12T09:00:00", "--output", tmp_path / "y.json").returncode == 2   # 시간대 없음
    assert run_cli("--gateway-identity", tmp_path / "missing.json", "--output", tmp_path / "z.json").returncode == 3
    part = out_file(tmp_path, "p.json", {"deviceId": DEVICE, "publicKey": "short"})
    assert run_cli("--node-identity", part, "--output", tmp_path / "w.json").returncode == 1
    assert run_cli("--gateway-identity", g, "--output", g).returncode == 4 and json.loads(g.read_text(encoding="utf-8"))["deviceId"] == DEVICE


# ---- linking 연결: 사용자 입력(--subject)과 관측 identity는 별도 필드 -------------------------------------

def identity_report(tmp_path, name, kind="gateway", device=DEVICE, count=1):
    src = out_file(tmp_path, f"{name}-raw.json", {"deviceId": device, "publicKey": PUBKEY})
    items = [(None, src)] * count
    rep = run(items if kind == "gateway" else [], items if kind == "node" else [], {})
    return out_file(tmp_path, f"{name}.json", rep)


def link(scans, cats, subjects=None, observed=None):
    return build_link_report(link_scans(list(scans), cats, subjects, observed))


def test_default_linking_output_has_no_observed_identity_fields(make, tmp_path):
    scan, catalog = make
    rep = link([gw(scan)], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")))
    assert "observed_identity" not in rep["declarations"][0]["declaring_subject"]
    assert "observed_identity_inputs" not in rep["inputs"]


def test_observed_identity_is_attached_separately_from_the_user_provided_subject(make, tmp_path):
    scan, catalog = make
    ident = identity_report(tmp_path, "gwid")
    rep = link([gw(scan)], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")),
               [{"scan_label": "gw", "kind": "gateway", "id": DEVICE}], [{"scan_label": "gw", "path": ident}])
    subj = rep["declarations"][0]["declaring_subject"]
    assert subj["id"] == DEVICE and subj["id_origin"] == "user_provided"                              # 사용자 입력은 그대로
    oi = subj["observed_identity"]
    assert oi["origin"] == "observed_from_stored_command_output" and oi["kind"] == "gateway"
    assert oi["device_id"] == {"original_value": DEVICE, "status": "as_reported"} and oi["verified_by_scanner"] is False
    assert oi["id_conflicts_with_user_provided"] is False and oi["kind_conflicts_with_subject_kind"] is False
    assert oi["command"] == "openclaw gateway call gateway.identity.get --json" and oi["observed_at"] is None
    assert rep["inputs"]["observed_identity_inputs"][0]["status"] == "applied" and "observed_identity_conflict" not in reasons(rep)


def test_observed_identity_without_a_user_subject_does_not_fill_the_user_field(make, tmp_path):
    scan, catalog = make
    rep = link([gw(scan)], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")), None,
               [{"scan_label": "gw", "path": identity_report(tmp_path, "gwid")}])
    subj = rep["declarations"][0]["declaring_subject"]
    assert subj["id"] is None and subj["id_origin"] == "not_collected"                                   # 관측값을 사용자 필드로 옮기지 않음
    assert subj["observed_identity"]["device_id"]["original_value"] == DEVICE
    assert subj["observed_identity"]["id_conflicts_with_user_provided"] is None


def test_conflict_between_user_input_and_observation_is_reported_not_resolved(make, tmp_path):
    scan, catalog = make
    ident = identity_report(tmp_path, "nodeid", kind="node", device=DEVICE2)
    rep = link([gw(scan)], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")),
               [{"scan_label": "gw", "kind": "gateway", "id": DEVICE}], [{"scan_label": "gw", "path": ident}])
    oi = rep["declarations"][0]["declaring_subject"]["observed_identity"]
    assert oi["id_conflicts_with_user_provided"] is True and oi["kind_conflicts_with_subject_kind"] is True
    assert rep["declarations"][0]["declaring_subject"]["id"] == DEVICE                                     # 어느 쪽도 덮어쓰지 않음
    assert "observed_identity_conflict" in reasons(rep) and rep["collection"]["status"] == "partial"


@pytest.mark.parametrize("label, count, problem", [("nope", 1, "unknown_scan_label"), ("bad label!", 1, "scan_label_invalid"), ("gw", 2, "identity_report_not_single")])
def test_unusable_observed_identity_inputs_are_ignored_with_a_reason(make, tmp_path, label, count, problem):
    scan, catalog = make
    ident = identity_report(tmp_path, "gwid", count=count)
    rep = link([gw(scan)], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")), None, [{"scan_label": label, "path": ident}])
    rec = rep["inputs"]["observed_identity_inputs"][0]
    assert rec["status"] == "ignored" and problem in rec["problems"] and "observed_identity_ignored" in reasons(rep)
    assert "observed_identity" not in rep["declarations"][0]["declaring_subject"]


def test_failed_or_foreign_identity_files_are_ignored(make, tmp_path):
    scan, catalog = make
    bad = identity_report(tmp_path, "bad", device="")           # deviceId를 읽지 못한 관측
    foreign = out_file(tmp_path, "foreign.json", {"format": "something-else", "identities": []})
    rep = link([gw(scan)], catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw")), None,
               [{"scan_label": "gw", "path": bad}, {"scan_label": "gw", "path": foreign}])
    recs = rep["inputs"]["observed_identity_inputs"]
    assert all(r["status"] == "ignored" for r in recs) and all("duplicate_observed_identity_input" in r["problems"] for r in recs)
    assert "observed_identity" not in rep["declarations"][0]["declaring_subject"]


def test_linking_cli_accepts_observed_identity(make, tmp_path, monkeypatch):
    scan, catalog = make
    scan_path = gw(scan)[1]
    cat_path = catalog(cat_server("a", key="files", reg="mcp.servers", scan="gw"))
    ident = identity_report(tmp_path, "gwid")
    monkeypatch.undo()
    out = tmp_path / "link.json"
    base = ["--config-scan", f"gw={scan_path}", "--catalog", cat_path]
    ok = run_cli(*base, "--observed-identity", f"gw={ident}", "--output", out, module="asset_scanner.linking")
    assert ok.returncode == 0, ok.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["declarations"][0]["declaring_subject"]["observed_identity"]["kind"] == "gateway"
    bad = run_cli(*base, "--observed-identity", str(ident), "--output", tmp_path / "x.json", module="asset_scanner.linking")
    assert bad.returncode == 2                                                                              # 라벨 없는 형식
    same = run_cli(*base, "--observed-identity", f"gw={ident}", "--output", ident, module="asset_scanner.linking")
    assert same.returncode == 4
