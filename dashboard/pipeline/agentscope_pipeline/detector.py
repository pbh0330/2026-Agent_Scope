"""S1~S5 정적 탐지 → DetectionReport(공통 스키마 13절).

규칙 원본: docs/threat-scenarios v2.1 (각 scenario-s*.md 부록 A, scenario-catalog.json).
팀의 탐지 모듈이 생기면 이 파일을 대체하고, 대시보드는 같은 detections.json 형식만 읽는다.

- 평가(evaluations)를 항상 함께 출력해 "이상 없음(not_detected)"과 "판단 불가(unknown)·미평가"를 구분한다.
- detected 평가만 경고가 된다. confidence는 근거의 명확성이며 공격 성공 확률이 아니다.
- 조건 ID·기본 severity/confidence는 카탈로그(policies/scenario-catalog.json)에서 읽는다.

기준 정책
  S1·S4-C3  testbed/ground-truth/approved-servers.json (테스트베드 담당 형식)
  S2        policies/expected-tool-policy.json (docs/threat-scenarios/policies 사본)
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from . import PRODUCER, SCHEMA_VERSION
from .ids import digest


def _state(asset: dict, name: str) -> dict | None:
    return next((s for s in asset["project"]["state_assessments"] if s["state"] == name), None)


def _defn(t: dict) -> dict:
    return t["mcp"]["definition"]


def _readonly(t: dict) -> bool:
    return (_defn(t).get("annotations") or {}).get("readOnlyHint") is True


def _openworld(t: dict) -> bool:
    return (_defn(t).get("annotations") or {}).get("openWorldHint") is True


def _inputs(t: dict) -> list[str]:
    return list((_defn(t).get("inputSchema") or {}).get("properties", {}).keys())


class Detector:
    def __init__(self, snap: dict, policies: dict[str, Any]):
        self.snap = snap
        self.catalog = policies["catalog"]
        self.approved = policies.get("approved_servers")
        self.tool_pol = policies.get("tool_policy")
        self.ruleset = {"id": self.catalog["catalog_id"], "version": self.catalog["catalog_version"]}
        self.cond = {c["condition_id"]: c for s in self.catalog["scenarios"] for c in s["conditions"]}
        self.assets = {a["asset_id"]: a for a in snap["assets"]}
        self.by_type: dict[str, list[dict]] = defaultdict(list)
        for a in snap["assets"]:
            self.by_type[a["asset_type"]].append(a)
        self.rel_by_target: dict[str, list[dict]] = defaultdict(list)
        for r in snap["relations"]:
            self.rel_by_target[r["target"]["asset_ref"]].append(r)
        self.tools_by_server: dict[str, list[dict]] = defaultdict(list)
        for t in self.by_type["tool"]:
            self.tools_by_server[t["owner_ref"]].append(t)
        self.now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.evaluations: list[dict] = []
        self.alerts: list[dict] = []

    # ---- 공통 -----------------------------------------------------------
    def _rels(self, asset_id: str, types: tuple[str, ...]) -> list[str]:
        return [r["relation_id"] for r in self.rel_by_target[asset_id] if r["relation_type"] in types]

    def _decl_rels(self, srv: dict) -> list[str]:
        return self._rels(srv["asset_id"], ("DECLARES", "ASSOCIATED_WITH"))

    def _pref(self, which: str) -> list[dict]:
        if which == "approved" and self.approved:
            return [{"id": "approved-servers", "version": self.approved["version"],
                     "source_ref": "testbed/ground-truth/approved-servers.json"}]
        if which == "tool" and self.tool_pol:
            return [{"id": self.tool_pol["policy_id"], "version": self.tool_pol["version"],
                     "source_ref": "docs/threat-scenarios/policies/expected-tool-policy.json"}]
        return []

    def evaluate(self, rule: str, asset_ids: list[str], result: str, reason: str,
                 evidence_refs: list[str] | None = None, relation_ids: list[str] | None = None,
                 policy_refs: list[dict] | None = None, alert: dict | None = None, details: dict | None = None) -> None:
        scenario = rule.split("-")[0]
        c = self.cond[rule]
        ev_id = f"eval-{rule}-{digest(*sorted(asset_ids), rule, length=10)}"
        rec = {
            "evaluation_id": ev_id, "scenario_id": scenario, "rule_id": rule, "rule_version": self.ruleset["version"],
            "rule_name": c["name"],
            "asset_ids": asset_ids, "relation_ids": relation_ids or [], "evidence_refs": evidence_refs or [],
            "policy_refs": policy_refs or [], "result": result, "reason": reason, "evaluated_at": self.now,
        }
        if details:
            rec["details"] = details
        if result in ("detected", "not_detected"):
            assert rec["evidence_refs"], f"{rule}: 판정에는 근거가 필요"
        assert ev_id not in {e["evaluation_id"] for e in self.evaluations}, f"중복 평가 {ev_id}"
        self.evaluations.append(rec)
        if result == "detected" and alert:
            fk = digest(self.snap["environment_id"], self.snap["profile_id"], scenario, rule, *sorted(asset_ids), length=24)
            self.alerts.append({
                "alert_id": f"alert-{fk[:12]}", "evaluation_id": ev_id, "finding_key": fk,
                "scenario_id": scenario, "rule_id": rule, "rule_version": self.ruleset["version"],
                "severity": alert.get("severity") or c["severity"], "confidence": alert.get("confidence") or c["confidence"],
                "title": alert["title"], "message": alert["message"],
                "asset_ids": asset_ids, "relation_ids": rec["relation_ids"], "evidence_refs": rec["evidence_refs"],
                "detected_at": self.now, "recommendation": alert.get("recommendation"),
            })

    # ---- 서버 사실과 승인 목록 비교 ---------------------------------------
    @staticmethod
    def facts(srv: dict) -> dict:
        cfg = srv.get("product", {}).get("config", {}) or {}
        p = srv["project"]
        host = p.get("host")
        registered_by = f"plugin:{p['declared_via_plugin']}" if p.get("declared_via_plugin") else f"{host}:config"
        if cfg.get("url"):
            endpoint = {"transport": cfg.get("transport") or "streamable-http", "url": cfg["url"]}
        else:
            endpoint = {"transport": cfg.get("transport") or "stdio", "command": cfg.get("command"), "args": cfg.get("args") or []}
        return {"name": srv["name"], "declared_at_vm": host, "registered_by": registered_by, "endpoint": endpoint}

    @staticmethod
    def ep_text(ep: dict) -> str:
        return ep.get("url") or " ".join([ep.get("command") or ""] + [str(a) for a in ep.get("args") or []]).strip()

    def compare(self, srv: dict) -> tuple[dict | None, dict, list[str], bool]:
        """(승인 항목, 사실, 위치 불일치 필드, endpoint 불일치)"""
        f = self.facts(srv)
        ap = next((s for s in self.approved["servers"] if s["name"] == f["name"]), None) if self.approved else None
        if not ap:
            return None, f, [], False
        loc = [k for k in ("declared_at_vm", "registered_by") if ap.get(k) and ap[k] != f[k]]
        a_ep = ap.get("endpoint") or {}
        ep_bad = any((f["endpoint"].get(k, [] if k == "args" else None) != v) for k, v in a_ep.items())
        return ap, f, loc, ep_bad

    # ---- S1 비인가 MCP Server 등록 ---------------------------------------
    def s1(self) -> None:
        servers = self.by_type["mcp_server"]
        if not self.approved:
            for srv in servers:
                self.evaluate("S1-C0", [srv["asset_id"]], "unknown", "승인 서버 목록이 제공되지 않아 판정 기준이 없음")
            return
        pref = self._pref("approved")
        okp = set(self.approved.get("approved_plugins", []))
        plugin_by_id = {p["name"]: p for p in self.by_type["plugin"]}
        for srv in servers:
            ap, f, loc, ep_bad = self.compare(srv)
            ids, evs, rels = [srv["asset_id"]], srv["evidence_refs"], self._decl_rels(srv)
            pid = srv["project"].get("declared_via_plugin")
            if pid:
                plg = plugin_by_id.get(pid)
                pids = [srv["asset_id"]] + ([plg["asset_id"]] if plg else [])
                if pid not in okp:
                    self.evaluate("S1-C3", pids, "detected",
                                  f"승인 플러그인 목록에 없는 `{pid}`가 manifest mcpServers로 서버를 등록", evs, rels, pref,
                                  details={**f, "approved_plugins": sorted(okp)},
                                  alert={"title": "승인되지 않은 플러그인이 MCP 서버 등록",
                                         "message": f"`{pid}` 플러그인은 승인 목록에 없지만 `{f['name']}` 서버를 등록합니다. "
                                                    "플러그인 등록 서버는 `openclaw mcp list`에 보이지 않습니다.",
                                         "recommendation": "플러그인 설치 출처를 확인하고, 필요 없으면 제거하거나 승인 목록에 올리세요."})
                    continue
                self.evaluate("S1-C3", pids, "not_detected", f"등록 플러그인 `{pid}`가 승인 목록에 있음", evs, rels, pref)
            if ap is None:
                self.evaluate("S1-C1", ids, "detected",
                              f"승인 목록({self.approved['version']})에 없는 서버가 {f['registered_by']}에 선언됨", evs, rels, pref,
                              details=f,
                              alert={"title": "승인되지 않은 MCP 서버 등록",
                                     "message": f"`{f['name']}` 서버가 승인 목록에 없지만 {f['declared_at_vm']} 설정에 등록되어 있습니다 "
                                                f"({self.ep_text(f['endpoint'])}).",
                                     "recommendation": "등록 출처를 확인하고, 필요하면 승인 목록에 추가하거나 설정에서 제거하세요."})
                continue
            self.evaluate("S1-C1", ids, "not_detected", "이름이 승인 목록에 있음", evs, rels, pref)
            if loc:
                self.evaluate("S1-C4", ids, "detected",
                              f"승인 위치와 다름: " + ", ".join(f"{k} {ap[k]} → {f[k]}" for k in loc), evs, rels, pref,
                              details={**f, "approved": {k: ap[k] for k in loc}},
                              alert={"title": "승인된 서버가 다른 위치에서 선언됨",
                                     "message": f"`{f['name']}`는 승인 목록에서 {ap['declared_at_vm']}({ap['registered_by']})에 선언하도록 되어 있지만 "
                                                f"{f['declared_at_vm']}({f['registered_by']})에서 선언되었습니다.",
                                     "recommendation": "선언 위치가 바뀐 이유를 확인하고 승인 위치로 되돌리거나 승인 목록을 갱신하세요."})
            else:
                self.evaluate("S1-C4", ids, "not_detected", "선언 위치·등록 주체가 승인 목록과 같음", evs, rels, pref)
            if ep_bad:
                self.evaluate("S1-C2", ids, "detected",
                              f"Endpoint 승인 {self.ep_text(ap['endpoint'])} → 현재 {self.ep_text(f['endpoint'])}", evs, rels, pref,
                              details={**f, "approved_endpoint": ap["endpoint"]},
                              alert={"title": "승인된 서버의 Endpoint 변경",
                                     "message": f"`{f['name']}`의 연결 대상이 승인 값({self.ep_text(ap['endpoint'])})과 다릅니다 "
                                                f"(현재 {self.ep_text(f['endpoint'])}).",
                                     "recommendation": "변경 이력을 확인하고 승인된 Endpoint로 되돌리거나 승인 목록을 갱신하세요."})
            else:
                self.evaluate("S1-C2", ids, "not_detected", "Endpoint가 승인 목록과 같음", evs, rels, pref)

    # ---- S2 과도한 권한의 도구 광고 ---------------------------------------
    @staticmethod
    def exposed(t: dict, srv: dict) -> tuple[bool, bool]:
        """(노출 여부, 추정 여부). 노출 목록을 다시 수집하지 않은 경우 선언된 toolFilter로 추정."""
        st = _state(t, "EXPOSED")
        if st and st["value"] is not None:
            return st["value"], False
        tf = (srv.get("product", {}).get("config") or {}).get("toolFilter") or {}
        name = _defn(t)["name"]
        if tf.get("include"):
            return name in tf["include"], True
        return name not in (tf.get("exclude") or []), True

    def s2(self) -> None:
        pol = self.tool_pol
        pref = self._pref("tool")
        cats = {k: {x.lower() for x in v} for k, v in (pol or {}).get("high_risk_inputs", {}).items()}
        for srv in self.by_type["mcp_server"]:
            sp = (pol or {}).get("servers", {}).get(srv["name"])
            tools = self.tools_by_server.get(srv["asset_id"], [])
            disc = _state(srv, "DISCOVERED")
            if sp is None:
                self.evaluate("S2-C0", [srv["asset_id"]], "unknown",
                              "기대 도구 정책에 없는 서버 — 허용 범위 기준이 없음 (승인 여부는 S1에서 판정)", policy_refs=pref)
                continue
            if not tools and (disc is None or disc["value"] is None):
                self.evaluate("S2-C0", [srv["asset_id"]], "unknown", "Tool 광고 목록을 수집하지 못함", policy_refs=pref)
                continue
            evs = srv["evidence_refs"] + (tools[0]["evidence_refs"] if tools else [])
            expo = [(t, *self.exposed(t, srv)) for t in tools]
            shown = [t for t, e, _ in expo if e]
            guessed = any(g for _, e, g in expo if e)
            note = " (노출 목록 미재수집 — 선언된 toolFilter로 추정)" if guessed else ""
            allowed, denied = sp.get("allowed_exposed_tools"), set(sp.get("denied_exposed_tools", []))
            bad = [t for t in shown if (allowed != "*" and t["name"] not in allowed) or t["name"] in denied]
            rel_of = lambda ts: [r for t in ts for r in self._rels(t["asset_id"], ("ADVERTISES",))]
            names = lambda ts: ", ".join(f"`{t['name']}`" for t in ts[:5]) + (" 외" if len(ts) > 5 else "")
            base = [srv["asset_id"]]
            # C1
            if bad:
                tf = (srv.get("product", {}).get("config") or {}).get("toolFilter")
                self.evaluate("S2-C1", base + [t["asset_id"] for t in bad], "detected",
                              f"정책 밖 도구 {len(bad)}개 노출: {names(bad)}{note}", evs, rel_of(bad), pref,
                              details={"tools": [{"tool": t["name"], "read_only": _readonly(t)} for t in bad], "toolFilter": tf},
                              alert={"title": "정책이 막은 도구가 에이전트에 노출됨",
                                     "message": f"`{srv['name']}`에서 기대 도구 정책이 허용하지 않은 도구 {len(bad)}개({names(bad)})가 노출됩니다."
                                                + (" toolFilter가 없습니다." if not tf else ""),
                                     "recommendation": "toolFilter로 필요한 도구만 노출하세요."})
            else:
                self.evaluate("S2-C1", base, "not_detected", f"노출 도구 {len(shown)}개 모두 정책 허용 범위{note}", evs, [], pref)
            # C2
            scope = sp.get("filesystem_scope") or []
            args = (srv.get("product", {}).get("config") or {}).get("args") or []
            paths = [a for a in args if isinstance(a, str) and a.startswith("/")]
            if scope and paths:
                wide = [a for a in paths if not any(a == s or a.startswith(s.rstrip("/") + "/") for s in scope)]
                if wide:
                    ro = all(_readonly(t) for t in shown)
                    self.evaluate("S2-C2", base + [t["asset_id"] for t in shown], "detected",
                                  f"파일 범위 기준 {', '.join(scope)} 밖: {', '.join(wide)} · 노출 도구 "
                                  f"{'모두 읽기 전용' if ro else '쓰기 포함'}{note}", evs, rel_of(shown), pref,
                                  details={"expected_scope": scope, "declared": paths, "read_only_only": ro},
                                  alert={"severity": "medium" if ro else "high",
                                         "title": "파일 접근 범위가 기준보다 넓음",
                                         "message": f"`{srv['name']}`의 파일 접근 범위가 {', '.join(scope)}에서 {', '.join(wide)}(으)로 넓어졌습니다. "
                                                    + ("노출 도구는 읽기 전용이지만 읽을 수 있는 파일이 늘어납니다." if ro
                                                       else "쓰기·이동 도구도 넓어진 범위에서 동작합니다."),
                                         "recommendation": "서버 인자를 작업 디렉터리로 되돌리세요."})
                else:
                    self.evaluate("S2-C2", base, "not_detected", f"파일 범위가 기준 {', '.join(scope)} 안", evs, [], pref)
            elif scope:
                self.evaluate("S2-C2", base, "not_detected", "설정 인자에 파일 경로 없음 (기준 범위는 서버 내부 지정)", evs, [], pref)
            else:
                self.evaluate("S2-C2", base, "not_applicable", "파일 접근 범위 기준이 없는 서버", evs)
            # C3, C4 — C1에서 이미 잡은 도구는 제외
            rest = [t for t in shown if t not in bad]
            for rule, keys, label in (("S2-C3", ("command", "network"), "명령·네트워크"), ("S2-C4", ("credential",), "인증정보")):
                hit = []
                for t in rest:
                    ins = [p for p in _inputs(t) if any(p.lower() in cats.get(k, set()) for k in keys)]
                    if ins and (rule == "S2-C4" or not _readonly(t) or _openworld(t)):
                        hit.append((t, ins))
                if hit:
                    ts = [t for t, _ in hit]
                    self.evaluate(rule, base + [t["asset_id"] for t in ts], "detected",
                                  f"{label} 입력 도구: " + ", ".join(f"{t['name']}({', '.join(i)})" for t, i in hit), evs, rel_of(ts), pref,
                                  alert={"title": f"{label} 입력을 받는 도구 노출",
                                         "message": f"`{srv['name']}`의 {names(ts)}가 {label} 입력을 받습니다.",
                                         "recommendation": "입력 대상을 제한하거나 도구를 필터로 제외하세요."})
                else:
                    self.evaluate(rule, base, "not_detected", f"정책 허용 도구 중 {label} 고위험 입력 없음", evs, [], pref)

    # ---- S4 자격증명 공유 -------------------------------------------------
    def s4(self) -> None:
        auths = [a for a in self.by_type["permission_auth"] if a.get("asset_subtype") == "authentication"]
        uses: dict[tuple[str, str], list[tuple[dict, dict]]] = defaultdict(list)
        for a in auths:
            for c in a["project"]["permission_auth"].get("credential_refs", []):
                if c.get("reference_id"):
                    uses[(c["reference_id"], c["namespace"])].append((a, c))
        anchor = [self.by_type["gateway"][0]["asset_id"]] if self.by_type["gateway"] else []
        if not uses:
            self.evaluate("S4-C1", anchor, "unknown", "식별 가능한 자격증명 참조가 없음")
            return

        def pack(group):
            targets = sorted({t for a, _ in group for t in a["project"]["permission_auth"]["target_refs"]})
            ids = sorted({a["asset_id"] for a, _ in group} | set(targets))
            evs = sorted({e for _, c in group for e in c["evidence_refs"]})
            rels = sorted({r["relation_id"] for a, _ in group for r in self.snap["relations"] if r["source_asset_ref"] == a["asset_id"]})
            return targets, ids, evs, rels, [self.assets[t]["name"] for t in targets]

        # C3 먼저: 승인되지 않은 Endpoint로 가는 자격증명
        bad_ep: set[str] = set()
        for a in auths:
            for sid in a["project"]["permission_auth"]["target_refs"]:
                srv = self.assets[sid]
                if srv["asset_type"] != "mcp_server":
                    continue  # Gateway 접속 인증 등은 MCP Endpoint 비교 대상이 아님
                evs = sorted({e for c in a["project"]["permission_auth"]["credential_refs"] for e in c["evidence_refs"]})
                refs = sorted({c["reference_id"].split(":", 1)[-1] for c in a["project"]["permission_auth"]["credential_refs"] if c.get("reference_id")}) or ["참조 이름 미확인"]
                if not self.approved:
                    self.evaluate("S4-C3", [a["asset_id"], sid], "unknown", "승인 서버 목록이 없어 Endpoint를 비교할 수 없음")
                    continue
                ap, f, _, ep_bad = self.compare(srv)
                rels = [r["relation_id"] for r in self.snap["relations"] if r["source_asset_ref"] == a["asset_id"]]
                if ap is None or ep_bad:
                    bad_ep.add(sid)
                    why = "승인 목록에 없는 서버" if ap is None else f"승인 {self.ep_text(ap['endpoint'])} → 현재 {self.ep_text(f['endpoint'])}"
                    self.evaluate("S4-C3", [a["asset_id"], sid], "detected", f"`{', '.join(refs)}`를 붙여 보내는 대상: {why}",
                                  evs, rels, self._pref("approved"), details={"references": refs, "endpoint": f["endpoint"]},
                                  alert={"title": "자격증명이 승인되지 않은 Endpoint로 전송",
                                         "message": f"`{srv['name']}`가 `{', '.join(refs)}` 참조를 {self.ep_text(f['endpoint'])}로 보냅니다 ({why}).",
                                         "recommendation": "Endpoint 변경을 확인하고, 의도하지 않았다면 자격증명을 교체하세요."})
                else:
                    self.evaluate("S4-C3", [a["asset_id"], sid], "not_detected", "자격증명 전송 대상이 승인 Endpoint와 같음",
                                  evs, rels, self._pref("approved"))

        by_ref: dict[str, list[str]] = defaultdict(list)
        for (ref, ns), group in uses.items():
            by_ref[ref].append(ns)
            targets, ids, evs, rels, names = pack(group)
            name = ref.split(":", 1)[-1]
            if len(targets) < 2:
                self.evaluate("S4-C1", ids, "not_detected", f"`{name}`({ns})를 서버 1곳({', '.join(names)})만 참조", evs, rels)
                continue
            boosted = any(t in bad_ep for t in targets)
            self.evaluate("S4-C1", ids, "detected", f"같은 저장소({ns})의 `{name}`를 서버 {len(targets)}곳이 공유",
                          evs, rels, details={"reference": f"{ns}#{name}", "servers": names},
                          alert={"severity": "high" if boosted else None,
                                 "title": "하나의 자격증명을 여러 서버가 공유",
                                 "message": f"`{name}` 참조를 {', '.join(names)}가 함께 사용합니다. 한 서버가 침해되면 다른 서버 접근 권한까지 노출될 수 있습니다."
                                            + (" 공유 대상 중 승인되지 않은 Endpoint가 있습니다." if boosted else ""),
                                 "recommendation": "서버별로 별도 자격증명을 발급하고 최소 권한 scope를 지정하세요."})
        for ref, nss in by_ref.items():
            if len(nss) < 2:
                continue
            group = [u for ns in nss for u in uses[(ref, ns)]]
            targets, ids, evs, rels, names = pack(group)
            self.evaluate("S4-C2", ids, "unknown",
                          f"같은 이름 `{ref.split(':', 1)[-1]}`이 서로 다른 저장소({', '.join(sorted(nss))})에서 참조됨 — 같은 자격증명인지 확정할 수 없음",
                          evs, rels, details={"servers": names, "namespaces": sorted(nss)})
        self.evaluate("S4-C4", anchor, "not_evaluated", "권한 범위(scope)·대상(audience)을 수집하지 않음 — v2.1 범위 밖")

    # ---- S3 Tool 이름 충돌 -----------------------------------------------
    def s3(self) -> None:
        groups: dict[str, list[dict]] = defaultdict(list)
        for t in self.by_type["tool"]:
            groups[_defn(t)["name"]].append(t)
        for s in self.by_type["mcp_server"]:
            if (_state(s, "DISCOVERED") or {}).get("value") is None:
                self.evaluate("S3-C3", [s["asset_id"]], "unknown", "광고 목록을 수집하지 못해 이 서버의 도구 이름을 비교하지 못함")
        collisions = {n: ts for n, ts in groups.items() if len({t["owner_ref"] for t in ts}) > 1}
        for name, ts in sorted(collisions.items()):
            fields = ("title", "description", "inputSchema", "annotations", "outputSchema")
            diffs = [f for f in fields if len({json.dumps(_defn(t).get(f), sort_keys=True) for t in ts}) > 1]
            owners = [self.assets[t["owner_ref"]] for t in ts]
            eps = {self.ep_text(self.facts(o)["endpoint"]) for o in owners}
            ids = [t["asset_id"] for t in ts] + [o["asset_id"] for o in owners]
            rels = [r for t in ts for r in self._rels(t["asset_id"], ("ADVERTISES",))]
            evs = sorted({e for t in ts for e in t["evidence_refs"]})
            srv_names = ", ".join(o["name"] for o in owners)
            if diffs:
                self.evaluate("S3-C1", ids, "detected", f"`{name}`을 {srv_names}가 광고 · 정의 차이: {', '.join(diffs)}", evs, rels,
                              details={"tool_name": name, "servers": [o["name"] for o in owners], "differences": diffs, "endpoints": sorted(eps)},
                              alert={"title": "서버 간 도구 이름 충돌 (정의 다름)",
                                     "message": f"`{name}` 도구를 {srv_names}가 함께 제공하고 {', '.join(diffs)}이(가) 서로 다릅니다. "
                                                "이름만으로는 어느 서버의 도구가 호출될지 구분하기 어렵습니다.",
                                     "recommendation": "에이전트가 호출할 서버를 정하고, 다른 쪽 도구는 toolFilter로 제외하세요."})
            else:
                self.evaluate("S3-C2", ids, "detected", f"`{name}`을 {srv_names}가 같은 정의로 광고", evs, rels,
                              details={"tool_name": name, "servers": [o["name"] for o in owners], "endpoints": sorted(eps)},
                              alert={"title": "서버 간 도구 이름 충돌 (정의 같음)",
                                     "message": f"`{name}` 도구를 {srv_names}가 같은 정의로 함께 제공합니다. 정의가 같아 제공 서버를 구분할 근거가 이름 외에 없습니다.",
                                     "recommendation": "같은 기능이 두 서버에 있어야 하는지 확인하고, 하나만 노출하세요."})
        if not collisions:
            tools = self.by_type["tool"]
            if tools:
                self.evaluate("S3-C1", [tools[0]["owner_ref"]], "not_detected",
                              f"수집한 서버들의 도구 이름 {len(groups)}개가 모두 고유",
                              sorted({e for t in tools for e in t["evidence_refs"]})[:3], details={"tool_names_checked": len(groups)})

    # ---- S5 연결 보안 -----------------------------------------------------
    def s5(self) -> None:
        remote = []
        for srv in self.by_type["mcp_server"]:
            cfg = srv.get("product", {}).get("config", {}) or {}
            url = cfg.get("url")
            ids, evs, rel = [srv["asset_id"]], srv["evidence_refs"], self._decl_rels(srv)
            if not url:
                self.evaluate("S5-NA", ids, "not_applicable", "stdio 로컬 실행 — 네트워크 전송 검증 대상 아님", evs)
                continue
            remote.append(srv["asset_id"])
            plain = url.startswith(("http://", "ws://"))
            if plain:
                self.evaluate("S5-C1", ids, "detected", f"암호화되지 않은 전송: {url}", evs, rel, details={"url": url},
                              alert={"title": "암호화되지 않은 MCP 연결",
                                     "message": f"`{srv['name']}`가 평문({url})으로 연결됩니다. 통신 내용과 인증 헤더가 노출될 수 있습니다.",
                                     "recommendation": "HTTPS로 바꾸고 서버 인증서를 검증하세요."})
                continue
            self.evaluate("S5-C1", ids, "not_detected", "TLS 전송(https/wss)", evs, rel)
            ssl = cfg.get("sslVerify")
            if ssl is False:
                self.evaluate("S5-C2", ids, "detected", "sslVerify가 false로 명시됨", evs, rel, details={"sslVerify": False},
                              alert={"title": "서버 인증서 검증 비활성화",
                                     "message": f"`{srv['name']}`의 sslVerify가 false라 서버 신원을 확인하지 않습니다.",
                                     "recommendation": "sslVerify를 true로 두고 신뢰할 CA를 지정하세요."})
            elif ssl is True:
                self.evaluate("S5-C2", ids, "not_detected", "sslVerify true", evs, rel)
            else:
                self.evaluate("S5-C3", ids, "unknown", "sslVerify 항목이 없음 — 기본값을 확인하지 못해 비활성으로 판단하지 않음")
        if remote:
            self.evaluate("S5-C4", remote, "not_evaluated", "연결 대상 검증 정보(인증서 주체·핀 등) 미수집 — v2.1 범위 밖")
            self.evaluate("S5-C5", remote, "not_evaluated", "보안 설정 적용 범위 분석 — v2.1 범위 밖")

    def run(self) -> dict:
        for fn in (self.s1, self.s2, self.s4, self.s3, self.s5):  # 구현 우선순위 순서
            fn()
        return {
            "schema_version": SCHEMA_VERSION,
            "report_id": f"det-{self.snap['snapshot_id']}",
            "environment_id": self.snap["environment_id"],
            "profile_id": self.snap["profile_id"],
            "snapshot_id": self.snap["snapshot_id"],
            "generated_at": self.now,
            "producer": {**PRODUCER, "component": "static-detector"},
            "ruleset": self.ruleset,
            "evaluations": self.evaluations,
            "alerts": self.alerts,
        }
