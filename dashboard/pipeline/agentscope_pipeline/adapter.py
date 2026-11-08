"""스캐너 출력 + 테스트베드 원본 → InventorySnapshot(스키마 v0.6.0-draft, 8종 자산).

입력
  - 자산 스캐너(feature/scanner-config) `agent-scope.scanner.openclaw-mcp-config` 결과
      Gateway 설정의 mcp.servers, Node 설정의 nodeHost.mcp.servers 각각 1개
  - 테스트베드(feature/testbed-profiles) raw/<P>/ 원본
      *.advertised.json            서버 광고(tools/resources/templates/prompts)
      tb-gw.mcp-probe.json         Gateway 측 에이전트 투영 도구
      tb-node.nodes-describe.json  Node 측 에이전트 투영 도구
      *-identity.json, devices-list.json, plugin-inspect.*.json
  - 프로파일 설정 사본과 스킬 파일

원칙(스키마 문서 기준)
  - 스캐너가 수집한 값을 우선 사용한다. 스캐너 0.1.0이 키 이름만 남기는 비밀이 아닌 값
    (sslVerify, toolFilter)은 어댑터가 설정 파일에서 보강 수집하고 별도 수집 작업으로 기록한다.
  - 비밀값은 읽지 않는다. 자격증명은 참조 이름·위치·존재만 남긴다.
  - 확인하지 못한 상태는 null + reason. CALLABLE·USED는 정적 단계에서 판정하지 않는다.
  - Gateway는 8종 협의안(asset-classification-proposal)에 따라 자산으로 두고 context.gateway_ref도 함께 채운다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import PRODUCER, SCHEMA_VERSION
from .ids import asset_id, relation_id

CREDENTIAL_NAME = re.compile(r"(TOKEN|KEY|SECRET|PASSWORD|PASSWD|AUTH|CREDENTIAL)", re.I)


def utc(ts: str | float | int | None) -> str | None:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dig(obj: dict, dotted: str) -> Any:
    cur: Any = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


@dataclass
class SkillInput:
    host: str            # tb-gw / tb-node
    path: Path           # SKILL.md
    location: str        # 안전한 설치 위치 표기


@dataclass
class ProfileInput:
    key: str                         # P0 / P1 / P2 / S1 ...
    label: str
    kind: str                        # normal / scenario
    environment_id: str
    profile_id: str
    configuration_id: str
    vm_snapshot_label: str | None
    scenario_id: str | None
    gw_config: Path
    gw_scan: dict
    raw_dir: Path
    node_config: Path | None = None
    node_scan: dict | None = None
    skills: list[SkillInput] = field(default_factory=list)
    capture_overrides: dict[str, Path] = field(default_factory=dict)
    stale_exposure_servers: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)


class SnapshotBuilder:
    def __init__(self, inp: ProfileInput):
        self.inp = inp
        self.env = inp.environment_id
        self.assets: list[dict] = []
        self.relations: list[dict] = []
        self.evidence: list[dict] = []
        self.collections: list[dict] = []
        self._ids: set[str] = set()
        self.by_key: dict[str, dict] = {}
        self.gw_cfg = load(inp.gw_config)
        self.node_cfg = load(inp.node_config) if inp.node_config else None
        probe = self.raw("tb-gw.mcp-probe.json")
        self.captured_at = utc(probe["generatedAt"]) if probe else utc(inp.gw_scan["generated_at"])
        self.gateway_ref: str | None = None

    # ---- 원본 읽기 -------------------------------------------------------
    def raw(self, name: str) -> Any:
        p = self.inp.raw_dir / name
        return load(p) if p.exists() else None

    # ---- 레코드 추가 -----------------------------------------------------
    def ev(self, evidence_id: str, evidence_type: str, source_ref: str, observed_at: str, collection_ref: str,
           field_path: str | None = None, redacted_fields: list[str] | None = None, note: str | None = None) -> str:
        if evidence_id in self._ids:
            return evidence_id
        self._ids.add(evidence_id)
        rec = {
            "evidence_id": evidence_id,
            "evidence_type": evidence_type,
            "source_ref": source_ref,
            "observed_at": observed_at,
            "collection_ref": collection_ref,
            "redaction_status": "redacted" if redacted_fields else "not_needed",
        }
        if field_path:
            rec["field_path"] = field_path
        if redacted_fields:
            rec["redacted_fields"] = redacted_fields
        if note:
            rec["note"] = note
        self.evidence.append(rec)
        return evidence_id

    def collect(self, collection_id: str, scope: str, source_ref: str, mode: str, status: str,
                target_ref: str | None, reason: str | None = None, **extra) -> str:
        rec = {
            "collection_id": collection_id,
            "source_ref": source_ref,
            "scope": scope,
            "target_ref": target_ref,
            "mode": mode,
            "status": status,
            "collected_at": extra.pop("collected_at", self.captured_at),
        }
        if reason:
            rec["reason"] = reason
        rec.update({k: v for k, v in extra.items() if v is not None})
        self.collections.append(rec)
        return collection_id

    def asset(self, asset_type: str, canonical_key: str, name: str, evidence_refs: list[str], states: list[dict],
              owner_ref: str | None = None, subtype: str | None = None, mcp: dict | None = None,
              product: dict | None = None, extra_project: dict | None = None, host: str | None = None) -> dict:
        aid = asset_id(self.env, asset_type, canonical_key)
        context = {"profile_id": self.inp.profile_id}
        if self.gateway_ref:
            context["gateway_ref"] = self.gateway_ref
        if host:
            context["host"] = host
        rec: dict[str, Any] = {
            "asset_id": aid,
            "asset_type": asset_type,
            "name": name,
            "context": context,
            "evidence_refs": evidence_refs,
            "project": {"canonical_key": canonical_key, "state_assessments": states, **(extra_project or {})},
        }
        if subtype:
            rec["asset_subtype"] = subtype
        if owner_ref:
            rec["owner_ref"] = owner_ref
        if mcp:
            rec["mcp"] = mcp
        if product:
            rec["product"] = product
        self.assets.append(rec)
        self.by_key[canonical_key] = rec
        return rec

    def rel(self, relation_type: str, source: dict, target: dict, evidence_refs: list[str], confidence: str,
            basis_kind: str = "declared", inference_rule: str | None = None) -> None:
        rec = {
            "relation_id": relation_id(self.env, relation_type, source["asset_id"], target["asset_id"]),
            "relation_type": relation_type,
            "source_asset_ref": source["asset_id"],
            "target": {"kind": "asset", "asset_ref": target["asset_id"]},
            "evidence_refs": evidence_refs,
            "confidence": confidence,
            "basis_kind": basis_kind,
        }
        if inference_rule:
            rec["inference_rule"] = inference_rule
        self.relations.append(rec)

    # ---- 상태 판정 헬퍼 --------------------------------------------------
    @staticmethod
    def st(state: str, value: bool | None, evidence_refs: list[str] | None = None, reason: str | None = None,
           subject: dict | None = None, **extra) -> dict:
        rec: dict[str, Any] = {"state": state, "value": value, "evidence_refs": evidence_refs or []}
        if reason:
            rec["reason"] = reason
        if subject:
            rec["subject_ref"] = subject
        rec.update(extra)
        return rec

    def agent_subject(self) -> dict:
        return {"kind": "agent", "profile_id": self.inp.profile_id, "agent_key": "main"}

    def static_tail(self) -> list[dict]:
        return [
            self.st("CALLABLE", None, reason="런타임 호출 검증은 정적 수집 범위 밖"),
            self.st("USED", None, reason="실행 로그 기반 사용 관찰은 정적 수집 범위 밖"),
        ]

    # ---- 빌드 ------------------------------------------------------------
    def build(self) -> dict:
        self._gateway_and_node()
        servers = self._servers()
        self._plugins(servers)
        self._catalogs(servers)
        self._skills(servers)
        return self._finish()

    def _gateway_and_node(self) -> None:
        ident = self.raw("tb-gw.gateway-identity.json")
        col = self.collect("col-gateway-identity", "gateway_identity", "tb-gw:openclaw gateway call gateway.identity.get --json",
                           "imported_catalog", "success" if ident else "not_attempted", None,
                           reason=None if ident else "Gateway identity 원본 없음")
        ev_cfg = self.ev("ev-gw-config", "config", "tb-gw:~/.openclaw/openclaw.json", utc(self.inp.gw_scan["generated_at"]),
                         "col-gw-config", field_path="gateway", redacted_fields=["gateway.auth.token"])
        evs = [ev_cfg]
        if ident:
            evs.append(self.ev("ev-gw-identity", "protocol", "tb-gw:gateway.identity.get", self.captured_at, col))
        gw_conf = self.gw_cfg.get("gateway", {})
        device_id = ident["deviceId"] if ident else None
        self.gateway_ref = f"gwctx_{device_id[:12]}" if device_id else "gwctx_unknown"
        gw = self.asset(
            "gateway", "tb-gw/gateway", "tb-gw", evs,
            [self.st("DECLARED", True, [ev_cfg]),
             self.st("DISCOVERED", True if ident else None, evs[1:] if ident else [],
                     reason=None if ident else "identity 미수집")],
            product={"name": "openclaw", "source_ref": "tb-gw:~/.openclaw/openclaw.json", "config_path": "gateway",
                     "config": {k: gw_conf.get(k) for k in ("mode", "bind", "port") if k in gw_conf}},
            extra_project={
                "device_id": device_id,
                "openclaw_version": dig(self.gw_cfg, "meta.lastTouchedVersion"),
                "tools_profile": dig(self.gw_cfg, "tools.profile"),
                "auth_mode": dig(self.gw_cfg, "gateway.auth.mode"),
            },
            host="tb-gw",
        )
        self.gw = gw
        # Gateway 인증 — 값은 설정에 평문으로 있으므로 저장하지 않고 존재만 기록
        if dig(self.gw_cfg, "gateway.auth.mode"):
            ev_auth = self.ev("ev-gw-auth", "config", "tb-gw:~/.openclaw/openclaw.json", utc(self.inp.gw_scan["generated_at"]),
                              "col-gw-config", field_path="gateway.auth", redacted_fields=["gateway.auth.token"])
            token_raw = dig(self.gw_cfg, "gateway.auth.token")
            is_ref = isinstance(token_raw, str) and "${" in token_raw
            auth = self.asset(
                "permission_auth", "tb-gw/authentication/gateway.auth", "Gateway 접속 인증", [ev_auth],
                [self.st("DECLARED", True, [ev_auth])], subtype="authentication",
                product={"name": "openclaw", "source_ref": "tb-gw:~/.openclaw/openclaw.json", "config_path": "gateway.auth",
                         "config": {"mode": dig(self.gw_cfg, "gateway.auth.mode")}},
                extra_project={"permission_auth": {
                    "source_ref": "tb-gw:~/.openclaw/openclaw.json", "source_field": "gateway.auth",
                    "target_refs": [gw["asset_id"]], "assessment_status": "declared",
                    "credential_refs": [{
                        "reference_id": None, "namespace": "tb-gw", "source_field": "gateway.auth.token",
                        "kind": "gateway_token", "presence": token_raw is not None, "evidence_refs": [ev_auth],
                        "reason": "환경변수 참조가 아닌 설정 내 값 — 값은 수집하지 않음" if not is_ref else "참조 이름 미해석",
                    }]}},
                host="tb-gw",
            )
            self.rel("APPLIES_TO", auth, gw, [ev_auth], "confirmed")
        # 에이전트 도구 정책(tools.profile)
        profile = dig(self.gw_cfg, "tools.profile")
        if profile:
            ev_tp = self.ev("ev-gw-tools-profile", "config", "tb-gw:~/.openclaw/openclaw.json", utc(self.inp.gw_scan["generated_at"]),
                            "col-gw-config", field_path="tools.profile")
            pol = self.asset(
                "permission_auth", "tb-gw/permission/tools.profile", f"에이전트 도구 정책 · {profile}", [ev_tp],
                [self.st("DECLARED", True, [ev_tp])], subtype="permission",
                product={"name": "openclaw", "source_ref": "tb-gw:~/.openclaw/openclaw.json", "config_path": "tools.profile",
                         "config": {"profile": profile}},
                extra_project={"permission_auth": {
                    "source_ref": "tb-gw:~/.openclaw/openclaw.json", "source_field": "tools.profile",
                    "target_refs": [gw["asset_id"]], "assessment_status": "declared",
                    "effect": "allow", "patterns": ["*"] if profile == "full" else [profile],
                    "reason": "OpenClaw 프로필 이름만 확인. 프로필이 허용하는 실제 도구 범위는 미해석"}},
                host="tb-gw",
            )
            self.rel("APPLIES_TO", pol, gw, [ev_tp], "confirmed")

        # Node
        nid = self.raw("tb-node.node-identity.json")
        self.node = None
        if nid:
            self.collect("col-node-identity", "node_identity", "tb-node:openclaw node identity --json", "imported_catalog", "success", None)
            ev_n = self.ev("ev-node-identity", "protocol", "tb-node:openclaw node identity", self.captured_at, "col-node-identity")
            describe = self.raw("tb-node.nodes-describe.json") or {}
            node = self.asset(
                "node", "tb-node/node", "tb-node", [ev_n],
                [self.st("DECLARED", True, [ev_n]), self.st("DISCOVERED", True if describe.get("connected") else None,
                                                            [ev_n] if describe else [], reason=None if describe else "describe 미수집")],
                extra_project={"device_id": nid["deviceId"], "platform": describe.get("platform"),
                               "openclaw_version": describe.get("version"), "caps": describe.get("caps"),
                               "connected": describe.get("connected")},
                host="tb-node",
            )
            self.node = node
            devices = self.raw("tb-gw.devices-list.json")
            if devices and any(d.get("deviceId") == nid["deviceId"] for d in devices.get("paired", [])):
                self.collect("col-gw-devices", "gateway_pairing", "tb-gw:openclaw devices list --json", "imported_catalog", "success", None)
                ev_p = self.ev("ev-gw-paired", "protocol", "tb-gw:openclaw devices list --json", self.captured_at, "col-gw-devices",
                               field_path="paired[deviceId]")
                self.rel("PAIRED_WITH", self.gw, node, [ev_p], "confirmed", basis_kind="observed")

    # -- 서버 -------------------------------------------------------------
    def _scan_collection(self, scan: dict, scope: str, col_id: str, target: str) -> tuple[str, str]:
        status = {"complete": "success", "partial": "partial", "failed": "failed"}[scan["collection"]["status"]]
        c = scan["collection"]
        self.collect(col_id, scope, f"{target}:~/.openclaw/openclaw.json#{scan['source']['registry_path']}", "local_file", status, None,
                     reason="profile-scoped configuration collection" + (f" · {c['reasons'][0]['code']}" if c.get("reasons") else ""),
                     collected_at=utc(scan["generated_at"]),
                     details={"outcome": c["outcome"], "reported_count": c["server_count"],
                              "values_resolved": scan["scope"]["values_resolved"],
                              "not_verified": scan["scope"]["not_verified"],
                              "producer": scan["producer"], "format": f"{scan['format']}@{scan['format_version']}",
                              "unresolved": [u for s in scan["servers"] for u in s.get("unresolved", [])]})
        return col_id, status

    def _servers(self) -> dict[str, dict]:
        servers: dict[str, dict] = {}
        plans = [(self.inp.gw_scan, self.gw_cfg, "tb-gw", self.gw, "col-gw-config", "gateway_config")]
        if self.inp.node_scan is not None and self.node:
            plans.append((self.inp.node_scan, self.node_cfg, "tb-node", self.node, "col-node-config", "node_config"))
        supplement_fields: list[str] = []
        for scan, cfg, host, declarer, col_id, scope in plans:
            self._scan_collection(scan, scope, col_id, host)
            for s in scan["servers"]:
                key = s["registration_key"]
                raw_entry = dig(cfg, s["declaration_path"]) or {}
                ev_decl = self.ev(f"ev-decl-{host}-{key}", "config", f"{host}:~/.openclaw/openclaw.json", utc(scan["generated_at"]),
                                  col_id, field_path=s["declaration_path"],
                                  redacted_fields=[f"{s['declaration_path']}.{k}" for k in s.get("credentials", {})] or None)
                config = dict(s["declared"])
                normalizations = []
                # 스캐너가 키 이름만 남긴 비밀 아닌 값 보강
                for fld in ("sslVerify", "toolFilter"):
                    if fld in s.get("other_declared_keys", []) and fld in raw_entry:
                        config[fld] = raw_entry[fld]
                        supplement_fields.append(f"{s['declaration_path']}.{fld}")
                        normalizations.append({"source_field": f"{s['declaration_path']}.{fld}", "target_field": f"product.config.{fld}",
                                               "rule_id": "adapter-supplement-non-secret", "evidence_refs": [ev_decl]})
                transport = config.get("transport") or ("stdio" if config.get("command") else None)
                cred_refs = []
                for kind, block in s.get("credentials", {}).items():
                    for e in block.get("entries", []):
                        for ref in e.get("ref_names", []):
                            cred_refs.append({
                                "reference_id": f"env:{ref}", "namespace": f"{host}:~/.openclaw/.env",
                                "source_field": f"{s['declaration_path']}.{kind}.{e['name']}", "kind": kind,
                                "presence": True, "evidence_refs": [ev_decl]})
                srv = self.asset(
                    "mcp_server", f"{host}/mcp_server/{key}", key, [ev_decl],
                    [self.st("DECLARED", True, [ev_decl])],
                    product={"name": "openclaw", "source_ref": f"{host}:~/.openclaw/openclaw.json",
                             "config_path": s["declaration_path"], "config": config},
                    extra_project={"declared_by": "gateway" if declarer is self.gw else "node", "host": host,
                                   "transport": transport, "credential_refs": cred_refs,
                                   "normalizations": normalizations,
                                   "scanner_metadata": {"declared_keys": s.get("declared_keys", []),
                                                        "other_declared_keys": s.get("other_declared_keys", []),
                                                        "collection_status": s["collection_status"]}},
                    host=host,
                )
                self.rel("DECLARES", declarer, srv, [ev_decl], "confirmed")
                servers[key] = srv
                self._server_policies(srv, host, s, raw_entry, ev_decl, cred_refs)
        if supplement_fields:
            self.collect("col-adapter-supplement", "adapter_supplement", "pipeline:adapter", "local_file", "success", None,
                         reason="스캐너 0.1.0은 sslVerify·toolFilter의 키 이름만 수집 — 비밀이 아닌 값을 어댑터가 설정에서 보강",
                         collected_at=utc(self.inp.gw_scan["generated_at"]), details={"fields": supplement_fields})
        return servers

    def _server_policies(self, srv: dict, host: str, s: dict, raw_entry: dict, ev_decl: str, cred_refs: list[dict]) -> None:
        key = s["registration_key"]
        tf = raw_entry.get("toolFilter")
        if isinstance(tf, dict) and (tf.get("include") or tf.get("exclude")):
            effect = "allow" if tf.get("include") else "deny"
            perm = self.asset(
                "permission_auth", f"{host}/permission/{s['declaration_path']}.toolFilter", f"{key} · toolFilter", [ev_decl],
                [self.st("DECLARED", True, [ev_decl])], subtype="permission",
                product={"name": "openclaw", "source_ref": f"{host}:~/.openclaw/openclaw.json",
                         "config_path": f"{s['declaration_path']}.toolFilter", "config": tf},
                extra_project={"permission_auth": {
                    "source_ref": f"{host}:~/.openclaw/openclaw.json", "source_field": f"{s['declaration_path']}.toolFilter",
                    "target_refs": [srv["asset_id"]], "assessment_status": "declared", "effect": effect,
                    "patterns": tf.get("include") or tf.get("exclude"),
                    "access_scope": {"exclude_patterns": tf["exclude"]} if tf.get("include") and tf.get("exclude") else {}}},
                host=host,
            )
            self.rel("APPLIES_TO", perm, srv, [ev_decl], "confirmed")
        creds = [c for c in cred_refs if CREDENTIAL_NAME.search(c["reference_id"]) or c["kind"] == "headers"]
        if creds:
            auth = self.asset(
                "permission_auth", f"{host}/authentication/{s['declaration_path']}", f"{key} · 자격증명 참조", [ev_decl],
                [self.st("DECLARED", True, [ev_decl])], subtype="authentication",
                product={"name": "openclaw", "source_ref": f"{host}:~/.openclaw/openclaw.json",
                         "config_path": s["declaration_path"],
                         "config": {"fields": sorted({c['source_field'].split('.')[-2] for c in creds})}},
                extra_project={"permission_auth": {
                    "source_ref": f"{host}:~/.openclaw/openclaw.json", "source_field": s["declaration_path"],
                    "target_refs": [srv["asset_id"]], "assessment_status": "declared", "credential_refs": creds}},
                host=host,
            )
            self.rel("AUTHENTICATES", auth, srv, [ev_decl], "confirmed")

    # -- 플러그인 ----------------------------------------------------------
    def _plugins(self, servers: dict[str, dict]) -> None:
        for p in sorted(self.inp.raw_dir.glob("tb-gw.plugin-inspect.*.json")):
            data = load(p)["plugin"]
            pid = data["id"]
            from_manifest = bool(data.get("_from_manifest"))
            col = self.collect(f"col-plugin-{pid}", "plugin_manifest",
                               f"testbed:plugins/{pid}/openclaw.plugin.json" if from_manifest
                               else f"tb-gw:openclaw plugins inspect {pid} --runtime --json",
                               "local_file" if from_manifest else "imported_catalog", "partial" if from_manifest else "success", None,
                               reason="런타임 점검 원본(plugins inspect) 미수집 — 저장소의 manifest로 대신 읽음" if from_manifest else None)
            ev_m = self.ev(f"ev-plugin-{pid}", "manifest", f"tb-gw:~/.openclaw/extensions/{pid}/openclaw.plugin.json", self.captured_at, col)
            ev_c = self.ev(f"ev-plugin-cfg-{pid}", "config", "tb-gw:~/.openclaw/openclaw.json", utc(self.inp.gw_scan["generated_at"]),
                           "col-gw-config", field_path=f"plugins.entries.{pid}")
            enabled = dig(self.gw_cfg, f"plugins.entries.{pid}.enabled")
            plg = self.asset(
                "plugin", f"tb-gw/plugin/{pid}", pid, [ev_m, ev_c],
                [self.st("DECLARED", True, [ev_c]),
                 self.st("DISCOVERED", None, reason="런타임 점검 원본 미수집") if from_manifest
                 else self.st("DISCOVERED", data.get("status") == "loaded", [ev_m])],
                product={"name": "openclaw", "source_ref": "tb-gw:~/.openclaw/openclaw.json", "config_path": f"plugins.entries.{pid}",
                         "config": {"enabled": enabled}},
                extra_project={
                    "description": data.get("description"),
                    "supply_chain": {"provider": "local", "package_id": data.get("packageName"), "version": data.get("version"),
                                     "source_uri": f"path:{data.get('rootDir')}", "integrity_status": "unknown",
                                     "install_path": data.get("rootDir"), "active": data.get("activated"),
                                     "evidence_refs": [ev_m]},
                    "trust": data.get("trust", {}).get("reason"),
                    "status": data.get("status"),
                },
                host="tb-gw",
            )
            self.rel("DECLARES", self.gw, plg, [ev_c], "confirmed")
            for name, spec in (data.get("mcpServers") or {}).items():
                ev_s = self.ev(f"ev-plugin-srv-{pid}-{name}", "manifest", f"tb-gw:~/.openclaw/extensions/{pid}/openclaw.plugin.json",
                               self.captured_at, col, field_path=f"mcpServers.{name}")
                srv = self.asset(
                    "mcp_server", f"tb-gw/mcp_server/{name}", name, [ev_s],
                    [self.st("DECLARED", True, [ev_s])],
                    product={"name": "openclaw", "source_ref": f"tb-gw:~/.openclaw/extensions/{pid}/openclaw.plugin.json",
                             "config_path": f"mcpServers.{name}", "config": spec},
                    extra_project={"declared_by": "plugin", "host": "tb-gw", "transport": spec.get("transport", "stdio"),
                                   "credential_refs": [], "declared_via_plugin": pid},
                    host="tb-gw",
                )
                self.rel("ASSOCIATED_WITH", plg, srv, [ev_s], "confirmed")
                servers[name] = srv

    # -- 광고 목록 ---------------------------------------------------------
    def _exposure(self) -> tuple[set[tuple[str, str]], set[str], set[str]]:
        exposed: set[tuple[str, str]] = set()
        probed_servers: set[str] = set()
        node_servers: set[str] = set()
        probe = self.raw("tb-gw.mcp-probe.json")
        if probe:
            names = sorted(probe["servers"], key=len, reverse=True)
            probed_servers |= set(probe["servers"])
            for t in probe["tools"]:
                for s in names:
                    if t.startswith(s + "__"):
                        exposed.add((s, t[len(s) + 2:]))
                        break
        describe = self.raw("tb-node.nodes-describe.json")
        if describe:
            for t in describe.get("nodePluginTools", []):
                if "mcp" in t:
                    exposed.add((t["mcp"]["server"], t["mcp"]["tool"]))
                    node_servers.add(t["mcp"]["server"])
        return exposed, probed_servers, node_servers

    def _catalogs(self, servers: dict[str, dict]) -> None:
        exposed, probed, node_published = self._exposure()
        for key, srv in servers.items():
            cap_path = self.inp.capture_overrides.get(key) or self.inp.raw_dir / f"{key}.advertised.json"
            host = srv["project"]["host"]
            if not Path(cap_path).exists():
                for scope in ("tools_list", "resources_list", "prompts_list"):
                    self.collect(f"col-{scope}-{key}", scope, f"{key}:{scope.replace('_list', '/list')}", "imported_catalog",
                                 "not_attempted", srv["asset_id"], reason="서버 광고 원본(advertised capture)이 없음 — 목록 미수집",
                                 protocol_version=None, auth_context_ref="anonymous-testbed")
                srv["project"]["state_assessments"].append(self.st("DISCOVERED", None, reason="광고 목록 미수집"))
                srv["project"]["state_assessments"].append(self.st("EXPOSED", None, reason="노출 목록 미수집", subject=self.agent_subject()))
                srv["project"]["state_assessments"] += self.static_tail()
                continue
            cap = load(cap_path)
            synthetic = bool(self.inp.capture_overrides.get(key))
            proto = cap.get("negotiatedProtocolVersion")
            src = f"{key}:advertised" + ("(synthetic)" if synthetic else "")
            lists = {f: cap.get(f) for f in ("resources", "resourceTemplates", "prompts")}
            not_adv = [f for f, v in lists.items() if isinstance(v, dict) and v.get("notAdvertised")]
            for f in not_adv:
                cap[f] = []
            col = self.collect(f"col-tools_list-{key}", "tools_list", src, "imported_catalog", "success", srv["asset_id"],
                               protocol_version=proto, auth_context_ref="anonymous-testbed",
                               details={"reported_count": len(cap.get("tools", [])),
                                        "requested_protocol_version": cap.get("requestedProtocolVersion"),
                                        "capabilities_not_advertised": not_adv, "synthetic": synthetic})
            for scope, field_ in (("resources_list", "resources"), ("resource_templates_list", "resourceTemplates"), ("prompts_list", "prompts")):
                if field_ in not_adv:
                    continue
                self.collect(f"col-{scope}-{key}", scope, src, "imported_catalog", "success", srv["asset_id"],
                             protocol_version=proto, auth_context_ref="anonymous-testbed",
                             details={"reported_count": len(cap.get(field_, []))})
            ev_cap = self.ev(f"ev-cap-{key}", "protocol", src, self.captured_at, col,
                             note="실제 협상 버전이 설계 기준(2026-07-28)과 다름" if proto and proto != "2026-07-28" else None)
            srv["mcp"] = {"protocol_version": proto,
                          "version_note": f"requested {cap.get('requestedProtocolVersion')}, negotiated {proto}",
                          "discovery": {"serverInfo": cap.get("serverInfo"), "capabilities": cap.get("capabilities")}}
            srv["project"]["state_assessments"].append(self.st("DISCOVERED", True, [ev_cap]))
            stale = key in self.inp.stale_exposure_servers
            projected = key in probed or key in node_published
            ev_expo = None
            if projected and not stale:
                ev_expo = self.ev(f"ev-expo-{key}", "protocol",
                                  "tb-gw:openclaw mcp probe --json" if key in probed else "tb-node:openclaw nodes describe --json",
                                  self.captured_at, "col-exposure")
                srv["project"]["state_assessments"].append(self.st("EXPOSED", True, [ev_expo], subject=self.agent_subject()))
            else:
                why = ("위험 구성은 설정 변경으로 생성 — 에이전트 노출 목록을 다시 수집하지 않음" if stale
                       else "openclaw mcp probe 대상 아님(플러그인 등록 서버)")
                srv["project"]["state_assessments"].append(self.st("EXPOSED", None, reason=why, subject=self.agent_subject()))
            srv["project"]["state_assessments"] += self.static_tail()
            tf = (srv.get("product", {}).get("config") or {}).get("toolFilter") or {}
            for tool in cap.get("tools", []):
                name = tool["name"]
                states = [self.st("DISCOVERED", True, [ev_cap])]
                if ev_expo:
                    if (key, name) in exposed:
                        states.append(self.st("EXPOSED", True, [ev_expo], subject=self.agent_subject()))
                    else:
                        if tf.get("include") and name not in tf["include"]:
                            reason = "toolFilter.include에 없음"
                        elif name in (tf.get("exclude") or []):
                            reason = "toolFilter.exclude"
                        elif (tool.get("execution") or {}).get("taskSupport") == "required":
                            reason = "taskSupport: required — OpenClaw가 게시하지 않음"
                        else:
                            reason = "에이전트 투영 목록에 없음"
                        states.append(self.st("EXPOSED", False, [ev_expo], reason=reason, subject=self.agent_subject()))
                else:
                    srv_expo = next(x for x in srv["project"]["state_assessments"] if x["state"] == "EXPOSED")
                    states.append(self.st("EXPOSED", None, reason=srv_expo.get("reason", "미확인"), subject=self.agent_subject()))
                states.append(self.st("POTENTIALLY_CALLABLE", None, reason="정적 호출 조건 미평가"))
                states += self.static_tail()
                t = self.asset("tool", f"{key}/tool/{name}", name, [ev_cap], states, owner_ref=srv["asset_id"],
                               mcp={"protocol_version": proto, "definition": tool}, host=host,
                               extra_project={"trust": "untrusted_server_provided", "synthetic": synthetic or None})
                self.rel("ADVERTISES", srv, t, [ev_cap], "confirmed", basis_kind="observed")
            for field_, sub, ident in (("resources", "resource", "uri"), ("resourceTemplates", "resource_template", "uriTemplate"),
                                       ("prompts", "prompt", "name")):
                for obj in cap.get(field_, []):
                    gt_type = "prompt" if sub == "prompt" else "resource"
                    r = self.asset("resource_prompt", f"{key}/{gt_type}/{obj[ident]}", obj.get("name") or obj[ident], [ev_cap],
                                   [self.st("DISCOVERED", True, [ev_cap]),
                                    self.st("EXPOSED", None, reason="리소스·프롬프트의 에이전트 노출 경로는 미해석", subject=self.agent_subject())]
                                   + self.static_tail(),
                                   owner_ref=srv["asset_id"], subtype=sub, mcp={"protocol_version": proto, "definition": obj}, host=host)
                    self.rel("ADVERTISES", srv, r, [ev_cap], "confirmed", basis_kind="observed")
        if probed or node_published:
            self.collect("col-exposure", "agent_exposure", "tb-gw:openclaw mcp probe / tb-node:nodes describe", "imported_catalog",
                         "success", None, reason="에이전트에 투영된 도구 목록(OpenClaw CLI 출력)")

    # -- 스킬 -------------------------------------------------------------
    def _skills(self, servers: dict[str, dict]) -> None:
        if not self.inp.skills:
            return
        self.collect("col-skills", "skill_files", "profiles:SKILL.md", "local_file", "success", None,
                     reason="테스트베드 프로파일 사본의 SKILL.md")
        for sk in self.inp.skills:
            text = sk.path.read_text(encoding="utf-8")
            fm = dict(re.findall(r"^(\w+):\s*(.+)$", text.split("---")[1], re.M)) if text.startswith("---") else {}
            name = fm.get("name", sk.path.parent.name)
            ev = self.ev(f"ev-skill-{sk.host}-{name}", "manifest", f"{sk.host}:{sk.location}", self.captured_at, "col-skills")
            host_asset = self.gw if sk.host == "tb-gw" else self.node
            skill = self.asset("skill", f"{sk.host}/skill/{name}", name, [ev],
                               [self.st("DECLARED", True, [ev]), self.st("DISCOVERED", True, [ev])],
                               extra_project={"description": fm.get("description"),
                                              "supply_chain": {"provider": "local", "install_path": sk.location,
                                                               "integrity_status": "unknown", "evidence_refs": [ev]}},
                               host=sk.host)
            if host_asset:
                self.rel("DECLARES", host_asset, skill, [ev], "confirmed")
            body = text.split("---", 2)[-1]
            for skey, srv in servers.items():
                if re.search(rf"`?{re.escape(skey)}`?", body):
                    self.rel("ASSOCIATED_WITH", skill, srv, [ev], "medium", basis_kind="inferred",
                             inference_rule="skill-body-mentions-server-name")

    # -- 마무리 ------------------------------------------------------------
    def _finish(self) -> dict:
        statuses = [c["status"] for c in self.collections]
        if all(s == "success" for s in statuses):
            scan_status = "success"
        elif any(s in ("success", "partial") for s in statuses):
            scan_status = "partial"
        else:
            scan_status = "failed"
        scan_times = [utc(self.inp.gw_scan["generated_at"])] + ([utc(self.inp.node_scan["generated_at"])] if self.inp.node_scan else [])
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        snap = {
            "schema_version": SCHEMA_VERSION,
            "snapshot_id": f"snap-{self.inp.key.lower()}-{now.replace(':', '').replace('-', '')}",
            "environment_id": self.env,
            "profile_id": self.inp.profile_id,
            "context": {"gateway_ref": self.gateway_ref},
            "basis": {"mcp_spec_version": "2026-07-28"},
            "environment": {"openclaw_version": dig(self.gw_cfg, "meta.lastTouchedVersion"), "openclaw_commit": None,
                            "version_note": "설정 meta.lastTouchedVersion 기준. commit 미확인"},
            "producer": {**PRODUCER, "upstream": [self.inp.gw_scan["producer"]]},
            "generated_at": now,
            "scan": {"started_at": min(scan_times), "finished_at": max(scan_times), "status": scan_status},
            "testbed_context": {"configuration_id": self.inp.configuration_id, "scenario_id": self.inp.scenario_id,
                                "vm_snapshot_label": self.inp.vm_snapshot_label, "label": self.inp.label,
                                "kind": self.inp.kind, "captured_at": self.captured_at, "notes": self.inp.notes},
            "assets": self.assets,
            "relations": self.relations,
            "evidence": self.evidence,
            "collection_results": self.collections,
        }
        validate(snap)
        return snap


def validate(snap: dict) -> None:
    """스키마 10절의 최소 수용 규칙 — ID 중복, 없는 참조, 근거 없는 판정."""
    ids = [a["asset_id"] for a in snap["assets"]]
    assert len(ids) == len(set(ids)), "asset_id 중복"
    rel_ids = [r["relation_id"] for r in snap["relations"]]
    assert len(rel_ids) == len(set(rel_ids)), "relation_id 중복"
    ev_ids = {e["evidence_id"] for e in snap["evidence"]}
    col_ids = {c["collection_id"] for c in snap["collection_results"]}
    aset = set(ids)
    for a in snap["assets"]:
        assert a["evidence_refs"] and set(a["evidence_refs"]) <= ev_ids, f"근거 참조 오류 {a['asset_id']}"
        if "owner_ref" in a:
            assert a["owner_ref"] in aset
        for s in a["project"]["state_assessments"]:
            if s["value"] is not None:
                assert s["evidence_refs"] and set(s["evidence_refs"]) <= ev_ids, f"판정 근거 없음 {a['name']} {s}"
            else:
                assert s.get("reason"), f"미확인 사유 없음 {a['name']} {s['state']}"
            assert not (s["state"] in ("CALLABLE", "USED") and s["value"] is not None)
    for r in snap["relations"]:
        assert r["source_asset_ref"] in aset and r["target"]["asset_ref"] in aset
        assert set(r["evidence_refs"]) <= ev_ids
    for e in snap["evidence"]:
        assert e["collection_ref"] in col_ids, f"수집 작업 참조 오류 {e['evidence_id']} → {e['collection_ref']}"
