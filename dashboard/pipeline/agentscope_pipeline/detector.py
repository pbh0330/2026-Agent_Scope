"""S1~S5 정적 탐지 → DetectionReport(스키마 13절).

규칙은 docs/threat-scenarios의 scenario-s1~s5.md "Static Detection" 절을 옮긴 1차 구현이다.
팀의 탐지 모듈이 생기면 이 파일을 대체하고, 대시보드는 같은 detections.json 형식만 읽는다.

- 평가(evaluations)를 항상 함께 출력해 "정상(not_detected)"과 "미평가(unknown/not_evaluated)"를 구분한다.
- detected 평가만 alert가 된다. confidence는 근거의 명확성이며 공격 성공 확률이 아니다.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from . import PRODUCER, SCHEMA_VERSION
from .ids import digest

RULESET = {"id": "agentscope-static", "version": "draft-1"}

HIGH_RISK_INPUTS = {
    "path": "경로", "paths": "경로", "file_path": "경로", "directory": "경로", "source": "경로", "destination": "경로",
    "command": "명령", "exec": "명령", "shell": "명령", "script": "명령",
    "url": "네트워크 주소", "uri": "네트워크 주소", "host": "네트워크 주소", "address": "네트워크 주소", "endpoint": "네트워크 주소",
    "token": "인증정보", "credential": "인증정보", "api_key": "인증정보", "apikey": "인증정보", "password": "인증정보",
}

SEVERITY = {"S1": "high", "S2": "high", "S3": "medium", "S4": "high", "S5": "high"}


def _state(asset: dict, name: str) -> dict | None:
    return next((s for s in asset["project"]["state_assessments"] if s["state"] == name), None)


class Detector:
    def __init__(self, snap: dict, policies: dict[str, Any]):
        self.snap = snap
        self.pol = policies
        self.assets = {a["asset_id"]: a for a in snap["assets"]}
        self.by_type: dict[str, list[dict]] = defaultdict(list)
        for a in snap["assets"]:
            self.by_type[a["asset_type"]].append(a)
        self.rel_by_target: dict[str, list[dict]] = defaultdict(list)
        for r in snap["relations"]:
            self.rel_by_target[r["target"]["asset_ref"]].append(r)
        self.now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.evaluations: list[dict] = []
        self.alerts: list[dict] = []

    # ---- 공통 -----------------------------------------------------------
    def _rels(self, asset_id: str, types: tuple[str, ...]) -> list[str]:
        return [r["relation_id"] for r in self.rel_by_target[asset_id] if r["relation_type"] in types]

    def evaluate(self, scenario: str, rule: str, asset_ids: list[str], result: str, reason: str,
                 evidence_refs: list[str] | None = None, relation_ids: list[str] | None = None,
                 policy_refs: list[dict] | None = None, alert: dict | None = None, details: dict | None = None) -> None:
        ev_id = f"eval-{rule}-{digest(*sorted(asset_ids), rule, length=10)}"
        rec = {
            "evaluation_id": ev_id, "scenario_id": scenario, "rule_id": rule, "rule_version": RULESET["version"],
            "asset_ids": asset_ids, "relation_ids": relation_ids or [], "evidence_refs": evidence_refs or [],
            "policy_refs": policy_refs or [], "result": result, "reason": reason, "evaluated_at": self.now,
        }
        if details:
            rec["details"] = details
        if result in ("detected", "not_detected"):
            assert rec["evidence_refs"], f"{rule}: 판정에는 근거가 필요"
        self.evaluations.append(rec)
        if result == "detected" and alert:
            fk = digest(self.snap["environment_id"], self.snap["profile_id"], scenario, rule, *sorted(asset_ids), length=24)
            self.alerts.append({
                "alert_id": f"alert-{fk[:12]}", "evaluation_id": ev_id, "finding_key": fk,
                "scenario_id": scenario, "rule_id": rule, "rule_version": RULESET["version"],
                "severity": alert.get("severity", SEVERITY[scenario]), "confidence": alert["confidence"],
                "title": alert["title"], "message": alert["message"],
                "asset_ids": asset_ids, "relation_ids": rec["relation_ids"], "evidence_refs": rec["evidence_refs"],
                "detected_at": self.now, "recommendation": alert.get("recommendation"),
            })

    # ---- S1 비인가 MCP Server 등록 ---------------------------------------
    def s1(self) -> None:
        pol = self.pol["approved_servers"]
        pref = [{"id": pol["policy_id"], "version": pol["version"], "source_ref": pol["source_ref"]}]
        approved = {s["name"]: s for s in pol["servers"]}
        for srv in self.by_type["mcp_server"]:
            cfg = srv.get("product", {}).get("config", {})
            declared_by = srv["project"].get("declared_by")
            endpoint = f"url:{cfg['url']}" if cfg.get("url") else f"command:{cfg.get('command')}"
            rel = self._rels(srv["asset_id"], ("DECLARES", "ASSOCIATED_WITH"))
            ap = approved.get(srv["name"])
            facts = {"name": srv["name"], "declared_by": declared_by, "host": srv["project"].get("host"), "endpoint": endpoint}
            if ap is None:
                self.evaluate("S1", "S1-C1", [srv["asset_id"]], "detected",
                              f"승인 목록({pol['version']})에 없는 서버가 {declared_by} 설정에 선언됨",
                              srv["evidence_refs"], rel, pref, details=facts,
                              alert={"confidence": "high", "title": "승인되지 않은 MCP 서버 등록",
                                     "message": f"`{srv['name']}` 서버가 승인 목록에 없지만 {facts['host']} {declared_by} 설정에 등록되어 있습니다.",
                                     "recommendation": "등록 출처를 확인하고, 필요하면 승인 목록에 추가하거나 설정에서 제거하세요."})
                continue
            mismatch = [k for k in ("declared_by", "host", "endpoint") if ap.get(k) and ap[k] != facts[k]]
            if mismatch:
                self.evaluate("S1", "S1-C2", [srv["asset_id"]], "detected",
                              f"승인 정보와 다른 항목: {', '.join(mismatch)}", srv["evidence_refs"], rel, pref,
                              details={**facts, "approved": {k: ap.get(k) for k in mismatch}},
                              alert={"confidence": "high" if "endpoint" in mismatch else "medium",
                                     "title": "승인된 서버의 연결 대상 변경",
                                     "message": f"`{srv['name']}`의 {', '.join(mismatch)} 값이 승인 정보와 다릅니다 "
                                                f"(현재 {facts['endpoint']}, 승인 {ap.get('endpoint')}).",
                                     "recommendation": "변경 이력을 확인하고 승인된 Endpoint로 되돌리거나 승인 정보를 갱신하세요."})
            else:
                self.evaluate("S1", "S1-C1", [srv["asset_id"]], "not_detected", "승인 목록의 이름·등록 주체·Endpoint와 일치",
                              srv["evidence_refs"], rel, pref, details=facts)

    # ---- S2 과도한 권한의 도구 광고 ---------------------------------------
    def s2(self) -> None:
        pol = self.pol["tool_risk"]
        pref = [{"id": pol["policy_id"], "version": pol["version"], "source_ref": pol["source_ref"]}]
        filters = {}
        for pa in self.by_type["permission_auth"]:
            d = pa["project"].get("permission_auth", {})
            if d.get("source_field", "").endswith("toolFilter"):
                for t in d.get("target_refs", []):
                    filters[t] = pa
        tools_by_server: dict[str, list[dict]] = defaultdict(list)
        for t in self.by_type["tool"]:
            tools_by_server[t["owner_ref"]].append(t)
        for srv in self.by_type["mcp_server"]:
            tools = tools_by_server.get(srv["asset_id"], [])
            disc = _state(srv, "DISCOVERED")
            if not tools and (disc is None or disc["value"] is None):
                self.evaluate("S2", "S2-C1", [srv["asset_id"]], "unknown", "Tool 광고 목록을 수집하지 못해 평가할 수 없음")
                continue
            flagged, notes = [], []
            cfg = srv.get("product", {}).get("config", {})
            scope_exp = pol["expected_filesystem_scope"].get(srv["name"])
            scope_now = [a for a in cfg.get("args", []) if isinstance(a, str) and a.startswith("/")]
            scope_wide = bool(scope_exp) and any(not s.startswith(scope_exp) for s in scope_now)
            for t in tools:
                props = list((t["mcp"]["definition"].get("inputSchema") or {}).get("properties", {}).keys())
                risky = sorted({HIGH_RISK_INPUTS[p.lower()] for p in props if p.lower() in HIGH_RISK_INPUTS})
                if not risky:
                    continue
                ro = (t["mcp"]["definition"].get("annotations") or {}).get("readOnlyHint") is True
                expo = _state(t, "EXPOSED")
                if expo and expo["value"] is False:
                    continue
                fpa = filters.get(srv["asset_id"])
                if fpa and not scope_wide:
                    d = fpa["project"]["permission_auth"]
                    pats = d.get("patterns") or []
                    if (d.get("effect") == "allow" and t["name"] not in pats) or (d.get("effect") == "deny" and t["name"] in pats):
                        continue  # 선언된 toolFilter가 제외하는 도구
                if ro and not scope_wide:
                    continue
                if srv["asset_id"] in filters and not scope_wide and expo and expo["value"] is True:
                    continue
                flagged.append(t)
                notes.append({"tool": t["name"], "risky_inputs": risky, "read_only": ro,
                              "exposed": expo["value"] if expo else None})
            if not flagged:
                self.evaluate("S2", "S2-C1", [srv["asset_id"]], "not_detected",
                              "고위험 입력을 가진 쓰기 도구가 필터로 제외되었거나 없음" if tools else "도구 0개",
                              srv["evidence_refs"], [], pref)
                continue
            exposed_known = all(n["exposed"] is True for n in notes)
            reasons = []
            if scope_wide:
                reasons.append(f"파일 접근 범위가 기준({scope_exp})보다 넓음: {', '.join(scope_now)}")
            if srv["asset_id"] not in filters:
                reasons.append("toolFilter가 없어 모든 도구가 노출 대상")
            ids = [srv["asset_id"]] + [t["asset_id"] for t in flagged]
            rels = [r for t in flagged for r in self._rels(t["asset_id"], ("ADVERTISES",))]
            self.evaluate("S2", "S2-C1" if not scope_wide else "S2-C2", ids, "detected", " · ".join(reasons) or "고위험 도구 노출",
                          srv["evidence_refs"] + flagged[0]["evidence_refs"], rels, pref, details={"tools": notes},
                          alert={"confidence": "high" if exposed_known else "medium",
                                 "title": "고위험 도구가 제한 없이 노출됨",
                                 "message": f"`{srv['name']}`가 제공하는 고위험 입력 도구 {len(flagged)}개"
                                            f"({', '.join(n['tool'] for n in notes[:4])}{' 외' if len(notes) > 4 else ''})가 "
                                            f"제한 없이 노출될 수 있습니다. {' '.join(reasons)}",
                                 "recommendation": "필요한 도구만 toolFilter.include로 노출하고, 파일 범위를 작업 디렉터리로 제한하세요."})

    # ---- S3 Tool 이름 충돌 -----------------------------------------------
    def s3(self) -> None:
        groups: dict[str, list[dict]] = defaultdict(list)
        for t in self.by_type["tool"]:
            groups[t["mcp"]["definition"]["name"]].append(t)
        missing = [s["name"] for s in self.by_type["mcp_server"]
                   if (_state(s, "DISCOVERED") or {}).get("value") is None]
        collisions = {n: ts for n, ts in groups.items() if len({t["owner_ref"] for t in ts}) > 1}
        for name, ts in collisions.items():
            diffs = []
            schemas = {tuple(sorted((t["mcp"]["definition"].get("inputSchema") or {}).get("properties", {}))) for t in ts}
            if len(schemas) > 1:
                diffs.append("입력 스키마")
            if len({t["mcp"]["definition"].get("description") for t in ts}) > 1:
                diffs.append("설명")
            owners = [self.assets[t["owner_ref"]] for t in ts]
            endpoints = {o["product"]["config"].get("url") or o["product"]["config"].get("command") for o in owners}
            if len(endpoints) > 1:
                diffs.append("제공 서버 Endpoint")
            ids = [t["asset_id"] for t in ts] + [o["asset_id"] for o in owners]
            rels = [r for t in ts for r in self._rels(t["asset_id"], ("ADVERTISES",))]
            evs = sorted({e for t in ts for e in t["evidence_refs"]})
            self.evaluate("S3", "S3-C1", ids, "detected", f"서로 다른 서버 {len(owners)}곳이 `{name}`을 광고 · 차이: {', '.join(diffs) or '없음'}",
                          evs, rels, details={"tool_name": name, "servers": [o["name"] for o in owners], "differences": diffs},
                          alert={"confidence": "high" if diffs else "medium", "title": "서버 간 도구 이름 충돌",
                                 "message": f"`{name}` 도구를 {', '.join(o['name'] for o in owners)}가 동시에 제공합니다."
                                            + (f" {', '.join(diffs)}이(가) 서로 다릅니다." if diffs else ""),
                                 "recommendation": "에이전트가 호출할 서버를 확인하고, 의도하지 않은 서버의 도구는 toolFilter로 제외하세요."})
        if not collisions:
            tools = self.by_type["tool"]
            reason = f"서버 간 원래 도구 이름 {len(groups)}개 모두 고유"
            if missing:
                reason += f" · 광고 미수집 서버 제외: {', '.join(missing)}"
            self.evaluate("S3", "S3-C1", [t["asset_id"] for t in tools][:1] or [s["asset_id"] for s in self.by_type["mcp_server"]][:1],
                          "not_detected" if tools else "unknown", reason,
                          sorted({e for t in tools for e in t["evidence_refs"]})[:3], details={"tool_names_checked": len(groups)})

    # ---- S4 자격증명 공유 -------------------------------------------------
    def s4(self) -> None:
        refs: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
        auths = [a for a in self.by_type["permission_auth"] if a.get("asset_subtype") == "authentication"]
        for a in auths:
            for c in a["project"]["permission_auth"].get("credential_refs", []):
                if c.get("reference_id"):
                    refs[c["reference_id"]].append((a, c))
        if not refs:
            self.evaluate("S4", "S4-C1", [a["asset_id"] for a in auths][:1] or [self.by_type["gateway"][0]["asset_id"]], "unknown",
                          "식별 가능한 자격증명 참조가 없음")
            return
        def pack(uses):
            targets = sorted({t for a, _ in uses for t in a["project"]["permission_auth"]["target_refs"]})
            ids = sorted({a["asset_id"] for a, _ in uses} | set(targets))
            evs = sorted({e for _, c in uses for e in c["evidence_refs"]})
            rels = sorted({r["relation_id"] for a, _ in uses for r in self.snap["relations"] if r["source_asset_ref"] == a["asset_id"]})
            return targets, ids, evs, rels, [self.assets[t]["name"] for t in targets]

        for ref, uses in refs.items():
            by_ns: dict[str, list] = defaultdict(list)
            for u in uses:
                by_ns[u[1]["namespace"]].append(u)
            for ns, group in by_ns.items():
                targets, ids, evs, rels, names = pack(group)
                if len(targets) < 2:
                    self.evaluate("S4", "S4-C1", ids, "not_detected", f"`{ref}`는 {ns}에서 서버 1곳({', '.join(names)})만 참조", evs, rels)
                    continue
                self.evaluate("S4", "S4-C1", ids, "detected", f"같은 저장소({ns})의 `{ref}`를 서버 {len(targets)}곳이 공유",
                              evs, rels, details={"reference": ref, "servers": names, "namespace": ns},
                              alert={"confidence": "high", "title": "하나의 자격증명을 여러 서버가 공유",
                                     "message": f"`{ref}` 참조를 {', '.join(names)}가 함께 사용합니다. 한 서버가 침해되면 다른 서버 접근 권한까지 노출될 수 있습니다.",
                                     "recommendation": "서버별로 별도 자격증명을 발급하고 최소 권한 scope를 지정하세요."})
            if len(by_ns) > 1:
                targets, ids, evs, rels, names = pack(uses)
                self.evaluate("S4", "S4-C2", ids, "unknown",
                              f"같은 이름 `{ref}`이 서로 다른 저장소({', '.join(sorted(by_ns))})에서 참조됨 — 이름만으로 동일 자격증명이라 단정하지 않음",
                              evs, rels, details={"reference": ref, "servers": names, "namespaces": sorted(by_ns)})

    # ---- S5 연결 보안 -----------------------------------------------------
    def s5(self) -> None:
        for srv in self.by_type["mcp_server"]:
            cfg = srv.get("product", {}).get("config", {})
            transport = srv["project"].get("transport")
            url = cfg.get("url")
            rel = self._rels(srv["asset_id"], ("DECLARES", "ASSOCIATED_WITH"))
            if not url:
                self.evaluate("S5", "S5-00", [srv["asset_id"]], "not_applicable", f"{transport or 'stdio'} 로컬 실행 — 네트워크 전송 검증 대상 아님",
                              srv["evidence_refs"])
                continue
            if url.startswith("http://"):
                self.evaluate("S5", "S5-01", [srv["asset_id"]], "detected", f"암호화되지 않은 전송: {url}", srv["evidence_refs"], rel,
                              details={"url": url, "transport": transport},
                              alert={"confidence": "high", "title": "암호화되지 않은 MCP 연결",
                                     "message": f"`{srv['name']}`이(가) 평문 HTTP({url})로 연결됩니다. 통신 내용과 인증 헤더가 노출될 수 있습니다.",
                                     "recommendation": "HTTPS로 전환하고 서버 인증서를 검증하세요."})
            ssl = cfg.get("sslVerify")
            if ssl is False:
                self.evaluate("S5", "S5-02", [srv["asset_id"]], "detected", "sslVerify가 명시적으로 false", srv["evidence_refs"], rel,
                              details={"sslVerify": False},
                              alert={"confidence": "high", "title": "서버 인증서 검증 비활성화",
                                     "message": f"`{srv['name']}`의 sslVerify가 false로 설정되어 서버 신원을 확인하지 않습니다.",
                                     "recommendation": "sslVerify를 true로 두고 신뢰할 CA를 지정하세요."})
            elif ssl is None and url.startswith("https://"):
                self.evaluate("S5", "S5-03", [srv["asset_id"]], "unknown",
                              "sslVerify가 설정에 없음 — 기본값 미확인이므로 비활성으로 판단하지 않음")
            elif ssl is True and url.startswith("https://"):
                self.evaluate("S5", "S5-02", [srv["asset_id"]], "not_detected", "HTTPS + sslVerify true", srv["evidence_refs"], rel)

    def run(self) -> dict:
        for fn in (self.s1, self.s2, self.s3, self.s4, self.s5):
            fn()
        return {
            "schema_version": SCHEMA_VERSION,
            "report_id": f"det-{self.snap['snapshot_id']}",
            "environment_id": self.snap["environment_id"],
            "profile_id": self.snap["profile_id"],
            "snapshot_id": self.snap["snapshot_id"],
            "generated_at": self.now,
            "producer": {**PRODUCER, "component": "static-detector"},
            "ruleset": RULESET,
            "evaluations": self.evaluations,
            "alerts": self.alerts,
        }
