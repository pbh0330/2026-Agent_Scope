"""기대 결과(위협 시나리오 v2.1) ↔ 탐지 결과 대조 → QAResult 형식(공통 스키마 16.2절 checks).

기대 결과 원본
  - docs/threat-scenarios/expected-results.md 의 ```json 블록 (profile 키별)
  - S1: testbed/ground-truth/S1.json (테스트베드 담당 형식). condition_id·severity는
    expected-results.md 3절 대응표(CASE_MAP)로 붙인다.

판정
  required 경고   같은 condition_id + 대상 자산을 포함한 경고가 있으면 PASS, 심각도가 다르면 PARTIAL, 없으면 FAIL
  선택(동반) 경고  있으면 PASS, 없으면 SKIP (탐지율 분모 제외)
  비경고 대상     해당 시나리오 경고가 대상에 나오면 FAIL(오탐), 아니면 PASS
  판단 불가 대상   그 조건의 평가가 모두 unknown이면 PASS, 아니면 FAIL
  기대에 없는 경고  EXTRA(정보). 비경고 범위에 걸린 경우는 위에서 FAIL로 셈
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import SCHEMA_VERSION

CASE_MAP = {  # expected-results.md 3절: 병하님 case → 조건 ID, severity
    ("S1", "1-gw"): ("S1-C1", "high"), ("S1", "1-node"): ("S1-C1", "high"), ("S1", "2"): ("S1-C2", "high"),
    ("S1", "3"): ("S1-C3", "high"), ("S4", "2"): ("S4-C3", "high"),
}


def load_expected(md_path: Path, s1_json: Path | None) -> dict[str, dict]:
    exp: dict[str, dict] = {}
    for block in re.findall(r"```json\n(.*?)```", md_path.read_text(encoding="utf-8"), re.S):
        data = json.loads(block)
        for p in data if isinstance(data, list) else [data]:
            exp[p["profile"]] = {**p, "_source": f"docs/threat-scenarios/{md_path.name}"}
    if s1_json and s1_json.exists():
        s1 = json.loads(s1_json.read_text(encoding="utf-8"))
        for a in s1["expected_alerts"]:
            cid, sev = CASE_MAP[(a["scenario"], a["case"])]
            a.setdefault("condition_id", cid)
            a.setdefault("severity", sev)
        s1.setdefault("expected_unknown", [])
        s1["_source"] = "testbed/ground-truth/S1.json (조건 ID는 expected-results.md 3절 대응표)"
        exp["S1"] = s1
    return exp


def compare(snap: dict, det: dict, exp: dict, catalog_version: str) -> dict:
    by_key = {a["project"]["canonical_key"]: a["asset_id"] for a in snap["assets"]}
    checks, used = [], set()
    n = 0

    def add(kind, cid, scenario, target, result, expected, actual, reason, evidence=()):
        nonlocal n
        n += 1
        checks.append({"check_id": f"exp-{n:02d}", "kind": kind, "condition_id": cid, "scenario_id": scenario,
                       "target": target, "asset_id": by_key.get(target) if target else None,
                       "result": result, "expected": expected, "actual": actual,
                       "evidence_refs": list(evidence), "reason": reason})

    for x in exp.get("expected_alerts", []):
        aid = by_key.get(x["target"])
        hits = [al for al in det["alerts"] if al["rule_id"] == x["condition_id"] and aid and aid in al["asset_ids"]]
        used |= {h["alert_id"] for h in hits}
        kind = "required" if x.get("required", True) else "optional"
        sev = x.get("severity")
        actual = {"alerts": [{"alert_id": h["alert_id"], "severity": h["severity"], "confidence": h["confidence"]} for h in hits]}
        exp_d = {"alert": True, "severity": sev, "confidence": x.get("confidence")}
        if aid is None:
            add(kind, x["condition_id"], x["scenario"], x["target"], "FAIL" if kind == "required" else "SKIP", exp_d, actual,
                "대상 자산이 스냅샷에 없음")
        elif not hits:
            add(kind, x["condition_id"], x["scenario"], x["target"], "FAIL" if kind == "required" else "SKIP", exp_d, actual,
                "기대한 경고가 나오지 않음" if kind == "required" else "선택 경고 — 나오지 않아도 누락 아님")
        elif sev and all(h["severity"] != sev for h in hits):
            add(kind, x["condition_id"], x["scenario"], x["target"], "PARTIAL", exp_d, actual,
                f"경고는 나왔지만 심각도 다름(기대 {sev}, 실제 {hits[0]['severity']})", hits[0]["evidence_refs"])
        else:
            add(kind, x["condition_id"], x["scenario"], x["target"], "PASS", exp_d, actual, x.get("reason", ""), hits[0]["evidence_refs"])

    for x in exp.get("expected_unknown", []):
        aid = by_key.get(x["target"])
        evs = [e for e in det["evaluations"] if e["rule_id"] == x["condition_id"] and aid in e["asset_ids"]]
        ok = bool(evs) and all(e["result"] == "unknown" for e in evs)
        add("unknown", x["condition_id"], x["scenario"], x["target"], "PASS" if ok else "FAIL",
            {"result": "unknown", "alert": False}, {"results": sorted({e["result"] for e in evs})},
            x["reason"] if ok else ("평가가 없음" if not evs else "판단 불가가 아닌 결과로 판정됨"))

    nae = exp.get("expected_no_alert") or {}
    scs = nae.get("scenario", [])
    scs = [scs] if isinstance(scs, str) else scs
    for t in nae.get("targets", []):
        aid = by_key.get(t)
        bad = [al for al in det["alerts"] if al["scenario_id"] in scs and aid in al["asset_ids"] and al["alert_id"] not in used]
        add("no_alert", None, "/".join(scs), t, "FAIL" if bad else "PASS", {"alert": False, "scenarios": scs},
            {"alerts": [{"alert_id": b["alert_id"], "rule_id": b["rule_id"]} for b in bad]},
            f"오탐: {', '.join(b['rule_id'] for b in bad)}" if bad else nae.get("note", ""))
        used |= {b["alert_id"] for b in bad}

    for al in det["alerts"]:
        if al["alert_id"] in used:
            continue
        keys = [k for k, v in by_key.items() if v in al["asset_ids"]]
        add("extra", al["rule_id"], al["scenario_id"], keys[0] if keys else None, "INFO",
            {"alert": None}, {"alerts": [{"alert_id": al["alert_id"], "severity": al["severity"]}]},
            "기대 결과에 없는 경고 — 규칙·기대 결과 중 어느 쪽을 고칠지 확인 필요")

    req = [c for c in checks if c["kind"] == "required"]
    metrics = [
        {"name": "required_alert_recall", "scope": "required", "numerator": sum(c["result"] in ("PASS", "PARTIAL") for c in req),
         "denominator": len(req)},
        {"name": "severity_match", "scope": "required", "numerator": sum(c["result"] == "PASS" for c in req), "denominator": len(req)},
        {"name": "no_alert_kept", "scope": "no_alert", "numerator": sum(c["result"] == "PASS" for c in checks if c["kind"] == "no_alert"),
         "denominator": sum(c["kind"] == "no_alert" for c in checks)},
        {"name": "unknown_kept", "scope": "unknown", "numerator": sum(c["result"] == "PASS" for c in checks if c["kind"] == "unknown"),
         "denominator": sum(c["kind"] == "unknown" for c in checks)},
    ]
    for m in metrics:
        m["value"] = round(m["numerator"] / m["denominator"], 4) if m["denominator"] else None
    verdict = "FAIL" if any(c["result"] == "FAIL" for c in checks) else "PARTIAL" if any(c["result"] == "PARTIAL" for c in checks) else "PASS"
    return {
        "schema_version": SCHEMA_VERSION,
        "qa_run_id": f"exp-{snap['snapshot_id']}",
        "environment_id": snap["environment_id"], "profile_id": snap["profile_id"], "snapshot_id": snap["snapshot_id"],
        "expected_profile": exp["profile"], "expected_source": exp["_source"], "expected_version": catalog_version,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "detection_report_id": det["report_id"], "verdict": verdict,
        "checks": checks, "metrics": metrics,
        "limitations": ["선택(required: false) 경고는 탐지율 분모에서 제외",
                        "severity 차이는 PARTIAL", "기대 결과에 없는 경고는 INFO로만 표시(비경고 범위에 걸린 경우는 FAIL)"],
    }
