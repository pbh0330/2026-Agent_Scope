"""SnapshotDiff(스키마 12.5·12.9)와 GroundTruth 비교 QAResult(16.2).

Diff
  - added / modified / removed_from_scope / not_observed 구분
  - 같은 범위를 끝까지 성공적으로 조회했을 때만 removed_from_scope, 그 외는 not_observed
  - alert_changes: opened / persisting / resolved / not_evaluated (resolved는 같은 규칙의 not_detected 재평가가 있을 때만)
QA
  - canonical_key ↔ 정답 asset_key로 매핑. 이름만으로 연결하지 않음
  - declared_asset_recall / advertised_asset_recall / relation_recall
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import SCHEMA_VERSION

COMPARE_FIELDS = ("name", "asset_subtype", "owner_ref")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fingerprint(a: dict) -> dict:
    return {
        "name": a.get("name"),
        "/product/config": json.dumps(a.get("product", {}).get("config"), sort_keys=True, ensure_ascii=False),
        "/mcp/definition": json.dumps(a.get("mcp", {}).get("definition"), sort_keys=True, ensure_ascii=False),
        "/project/state_assessments": json.dumps(
            sorted((s["state"], s["value"]) for s in a["project"]["state_assessments"]), ensure_ascii=False),
    }


def _scope_complete(snap: dict, asset: dict, prev_snap: dict) -> bool:
    """이전 자산이 현재 결과에서 같은 범위로 끝까지 조회됐는지."""
    cur_by_key = {a["project"]["canonical_key"]: a for a in snap["assets"]}
    if asset["asset_type"] in ("tool", "resource_prompt"):
        prev_owner = next((a for a in prev_snap["assets"] if a["asset_id"] == asset.get("owner_ref")), None)
        owner = cur_by_key.get(prev_owner["project"]["canonical_key"]) if prev_owner else None
        if not owner:
            return False
        scope = "tools_list" if asset["asset_type"] == "tool" else None
        cols = [c for c in snap["collection_results"] if c["target_ref"] == owner["asset_id"] and (scope is None or c["scope"] == scope)]
        return bool(cols) and all(c["status"] == "success" for c in cols)
    return any(c["scope"] in ("gateway_config", "node_config", "plugin_manifest", "skill_files")
               and c["status"] in ("success", "partial") for c in snap["collection_results"])


def snapshot_diff(prev: dict, cur: dict, prev_det: dict, cur_det: dict) -> dict:
    p = {a["asset_id"]: a for a in prev["assets"]}
    c = {a["asset_id"]: a for a in cur["assets"]}
    changes = []
    for aid, a in c.items():
        if aid not in p:
            changes.append({"asset_id": aid, "change_type": "added", "changed_fields": [], "detected_at": cur["generated_at"],
                            "evidence_refs": a["evidence_refs"], "reason": "이전 스냅샷의 같은 범위에 없던 자산"})
        else:
            fp, fc = _fingerprint(p[aid]), _fingerprint(a)
            diff = [k for k in fc if fp[k] != fc[k]]
            if diff:
                changes.append({"asset_id": aid, "change_type": "modified", "changed_fields": diff,
                                "detected_at": cur["generated_at"], "evidence_refs": a["evidence_refs"], "reason": "비교 필드 변경"})
    for aid, a in p.items():
        if aid in c:
            continue
        if _scope_complete(cur, a, prev):
            changes.append({"asset_id": aid, "change_type": "removed_from_scope", "changed_fields": [], "detected_at": cur["generated_at"],
                            "evidence_refs": [], "reason": "같은 범위를 끝까지 조회했지만 이번 결과에 없음(설치 삭제를 뜻하지 않음)",
                            "previous": {"name": a["name"], "asset_type": a["asset_type"]}})
        else:
            changes.append({"asset_id": aid, "change_type": "not_observed", "changed_fields": [], "detected_at": cur["generated_at"],
                            "evidence_refs": [], "reason": "이번 수집에서 해당 범위를 확인하지 못함 — 삭제로 판정하지 않음",
                            "previous": {"name": a["name"], "asset_type": a["asset_type"]}})
    pr = {r["relation_id"]: r for r in prev["relations"]}
    cr = {r["relation_id"]: r for r in cur["relations"]}
    relation_changes = [{"relation_id": rid, "change_type": "added", "changed_fields": [], "reason": "새 관계"}
                        for rid in cr if rid not in pr]
    relation_changes += [{"relation_id": rid, "change_type": "removed_from_scope" if pr[rid]["target"]["asset_ref"] in p and
                          any(ch["asset_id"] == pr[rid]["target"]["asset_ref"] and ch["change_type"] == "removed_from_scope" for ch in changes)
                          else "not_observed", "changed_fields": [], "reason": "이번 결과에 없음",
                          "previous": {"relation_type": pr[rid]["relation_type"]}}
                         for rid in pr if rid not in cr]
    pa = {a["finding_key"]: a for a in prev_det["alerts"]}
    ca = {a["finding_key"]: a for a in cur_det["alerts"]}
    alert_changes = []
    for fk, a in ca.items():
        alert_changes.append({"finding_key": fk, "change_type": "persisting" if fk in pa else "opened",
                              "previous_alert_id": pa[fk]["alert_id"] if fk in pa else None, "current_alert_id": a["alert_id"],
                              "reason": "이전 평가에도 탐지" if fk in pa else "이번 평가에서 새로 탐지"})
    for fk, a in pa.items():
        if fk in ca:
            continue
        reevaluated = any(e["rule_id"] == a["rule_id"] and e["result"] == "not_detected" and set(a["asset_ids"]) & set(e["asset_ids"])
                          for e in cur_det["evaluations"])
        alert_changes.append({"finding_key": fk, "change_type": "resolved" if reevaluated else "not_evaluated",
                              "previous_alert_id": a["alert_id"], "current_alert_id": None,
                              "reason": "같은 규칙 재평가 결과 not_detected" if reevaluated else "같은 범위의 재평가가 없어 해결로 판정하지 않음"})
    comparable = prev["environment_id"] == cur["environment_id"]
    return {
        "schema_version": SCHEMA_VERSION,
        "diff_id": f"diff-{prev['snapshot_id']}--{cur['snapshot_id']}",
        "environment_id": cur["environment_id"],
        "profile_id": cur["profile_id"],
        "previous_snapshot_id": prev["snapshot_id"],
        "current_snapshot_id": cur["snapshot_id"],
        "previous_report_id": prev_det["report_id"],
        "current_report_id": cur_det["report_id"],
        "generated_at": _now(),
        "comparison_status": "complete" if comparable and not any(ch["change_type"] == "not_observed" for ch in changes) else
                             ("partial" if comparable else "not_comparable"),
        "changes": changes,
        "relation_changes": relation_changes,
        "alert_changes": alert_changes,
        "limitations": [] if comparable else ["environment_id가 달라 비교할 수 없음"],
    }


GT_TYPE = {"resource": "resource_prompt", "prompt": "resource_prompt"}


def qa_result(snap: dict, gt: dict, det: dict | None) -> dict:
    by_key = {a["project"]["canonical_key"]: a for a in snap["assets"]}
    id_mappings, checks = [], []
    layers = {"declared": [0, 0], "advertised": [0, 0]}
    for g in gt["assets"]:
        a = by_key.get(g["asset_key"])
        ok = a is not None and a["asset_type"] == GT_TYPE.get(g["asset_type"], g["asset_type"])
        layers[g["layer"]][1] += 1
        layers[g["layer"]][0] += int(ok)
        id_mappings.append({"gt_asset_id": g["asset_key"], "asset_id": a["asset_id"] if ok else None,
                            "asset_type": g["asset_type"], "layer": g["layer"],
                            "status": "matched" if ok else "unmatched",
                            "reason": "canonical_key 일치" if ok else "스냅샷에 같은 키의 자산 없음"})
        exp = (g.get("attributes") or {}).get("exposed_to_agent")
        if ok and g["asset_type"] == "tool" and exp is not None:
            s = next((x for x in a["project"]["state_assessments"] if x["state"] == "EXPOSED"), None)
            actual = s["value"] if s else None
            checks.append({"check_id": f"chk-expo-{g['asset_key']}", "condition_id": "EXPOSED", "scenario_id": None,
                           "result": "PASS" if actual == exp else ("PARTIAL" if actual is None else "FAIL"),
                           "expected": {"exposed_to_agent": exp}, "actual": {"EXPOSED": actual},
                           "evidence_refs": s["evidence_refs"] if s else [], "reason": (s or {}).get("reason", "")})
    gt_keys = {g["asset_key"] for g in gt["assets"]}
    extra = [a for k, a in by_key.items() if k not in gt_keys]
    key_by_id = {a["asset_id"]: a["project"]["canonical_key"] for a in snap["assets"]}
    ours = {(r["relation_type"], key_by_id[r["source_asset_ref"]], key_by_id[r["target"]["asset_ref"]]) for r in snap["relations"]}
    gt_rels = [(r["type"], r["source"], r["target"]) for r in gt["relations"]]
    rel_hit = sum(1 for r in gt_rels if r in ours)
    missing_rels = [{"type": t, "source": s, "target": tg} for t, s, tg in gt_rels if (t, s, tg) not in ours]
    metrics = [
        {"name": "declared_asset_recall", "scope": "declared", "numerator": layers["declared"][0], "denominator": layers["declared"][1]},
        {"name": "advertised_asset_recall", "scope": "advertised", "numerator": layers["advertised"][0], "denominator": layers["advertised"][1]},
        {"name": "relation_recall", "scope": "relations", "numerator": rel_hit, "denominator": len(gt_rels)},
    ]
    for m in metrics:
        m["value"] = round(m["numerator"] / m["denominator"], 4) if m["denominator"] else None
    if det is not None:
        alerts = len(det["alerts"])
        checks.append({"check_id": "chk-normal-no-alerts", "condition_id": "NORMAL-STATE", "scenario_id": None,
                       "result": "PASS" if alerts == 0 else "FAIL", "expected": {"alerts": 0}, "actual": {"alerts": alerts},
                       "evidence_refs": [], "reason": "정상군 프로파일에서는 S1~S5 경고가 없어야 함"})
    return {
        "schema_version": SCHEMA_VERSION,
        "qa_run_id": f"qa-{snap['snapshot_id']}",
        "environment_id": snap["environment_id"],
        "profile_id": snap["profile_id"],
        "snapshot_id": snap["snapshot_id"],
        "ground_truth_id": f"testbed-gt-{gt['profile']}",
        "ground_truth_version": gt["snapshot"],
        "generated_at": _now(),
        "detection_report_id": det["report_id"] if det else None,
        "id_mappings": id_mappings,
        "checks": checks,
        "metrics": metrics,
        "extra_assets": [{"asset_id": a["asset_id"], "canonical_key": a["project"]["canonical_key"], "asset_type": a["asset_type"]}
                         for a in extra],
        "missing_relations": missing_rels,
        "limitations": ["정답 목록에는 permission_auth 자산이 없어 해당 유형은 추가 자산으로만 표시",
                        "관계 비교는 (유형, 출발 키, 대상 키) 완전 일치 기준"],
    }
