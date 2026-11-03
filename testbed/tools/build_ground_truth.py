#!/usr/bin/env python3
"""프로파일별 정답 목록(ground truth) 생성기.

입력
  testbed/profiles/<P>/tb-gw.openclaw.json, tb-node.openclaw.json   선언 계층(설정 파일, 자리표시자 처리본)
  testbed/ground-truth/raw/<P>/*.advertised.json                  광고 계층(mcp-advertised.mjs로 서버에서 직접 수집)
  testbed/ground-truth/raw/<P>/tb-gw.mcp-probe.json, tb-node.nodes-describe.json
                                                                  에이전트 노출 여부(OpenClaw가 실제로 투영한 도구)
  testbed/ground-truth/raw/<P>/*identity.json                     게이트웨이·노드 device ID
  testbed/ground-truth/approved-servers.json                      S1 승인 서버 목록(위협 구성의 경고 대상 검사용)
출력
  testbed/ground-truth/<P>.json
  testbed/ground-truth/S<n>.json   위협 구성: 기준 프로파일 대비 추가·변경 자산과 관계 + expected_alerts

위협 구성(S1~)의 raw 파일이 없으면 기준 프로파일(BASE)의 raw를 쓴다(같은 VM이라 device ID가 같고,
코드가 같은 서버는 광고 내용도 같다). 단 에이전트 노출 여부는 기준 프로파일 값을 쓰지 않고 미확인(null)으로 둔다.

형식은 ground-truth/README.md(현행, 7종 + resource/prompt 분리)를 따른다.
공통 스키마(PR #1)의 자산 분류·ID 규칙이 확정되면 이 스크립트의 asset_key 생성부와 유형 매핑만 바꿔 다시 생성한다.
테스트베드가 추가하지 않은 내장(stock) 플러그인·스킬은 제외한다(SNAP-1 기준선 참조).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENCLAW_VERSION = "2026.9.6"
SPEC_VERSION = "2026-07-28"  # 사양서 기준값. 실제 협상 버전은 assets[].attributes.negotiated_protocol_version

# 프로파일 구성 중 설정 파일만으로는 드러나지 않는 부분(수작업 기술).
SKILLS = {
    "P1": [
        ("tb-node", "node-disk-report", "~/.openclaw/skills/node-disk-report/SKILL.md", None),
        ("tb-node", "node-notes-summary", "~/.openclaw/skills/node-notes-summary/SKILL.md", None),
    ],
}
SKILLS["P2"] = SKILLS["P1"] + [
    ("tb-gw", "inventory-owner-report", "~/workspace/skills/inventory-owner-report/SKILL.md", "inventory-remote"),
]
SKILLS["S1"] = SKILLS["P2"]
PLUGINS = {
    "P2": [
        {
            "vm": "tb-gw",
            "id": "agentscope-asset-catalog",
            "dir": "~/.openclaw/extensions/agentscope-asset-catalog",
            "install_source": "local path (openclaw plugins install ./agentscope-asset-catalog)",
            "mcp_servers": {"asset-catalog": {"transport": "stdio", "command": "node", "args": ["./mcp-server.mjs"]}},
        }
    ],
}
PLUGINS["S1"] = PLUGINS["P2"] + [
    {
        "vm": "tb-gw",
        "id": "agentscope-notes-sync",
        "dir": "~/.openclaw/extensions/agentscope-notes-sync",
        "install_source": "local path (openclaw plugins install ./agentscope-notes-sync)",
        "mcp_servers": {"notes-sync": {"transport": "stdio", "command": "node", "args": ["./mcp-server.mjs", "--name", "notes-sync"]}},
    }
]
BASE = {"S1": "P2"}  # 위협 구성의 기준 프로파일(이 스냅샷에서 분기)
SNAPSHOT = {"P0": "SNAP-2-P0", "P1": "SNAP-2-P1", "P2": "SNAP-2-P2", "S1": "SNAP-3-S1"}
# 위협 구성에서 스캐너가 내야 할 경고(수작업 기술). target은 asset_key, 생성 시 존재 여부를 검사한다.
# required: False는 내도 정답, 안 내도 미탐으로 세지 않는 경고.
THREATS = {
    "S1": [
        {"case": "1-gw", "scenario": "S1", "target": "tb-gw/mcp_server/shadow-notes",
         "risk_condition": "신규 Server 선언", "reason": "승인 목록에 없는 서버가 tb-gw mcp.servers에 선언됨", "confidence": "high"},
        {"case": "1-node", "scenario": "S1", "target": "tb-node/mcp_server/node-helper",
         "risk_condition": "신규 Server 선언", "reason": "승인 목록에 없는 서버가 tb-node nodeHost.mcp.servers에 선언됨", "confidence": "high"},
        {"case": "2", "scenario": "S1", "target": "tb-gw/mcp_server/inventory-remote",
         "risk_condition": "Endpoint 불일치", "reason": "승인 endpoint https://tb-node:8443/mcp 대신 https://tb-node:9443/mcp로 변경됨", "confidence": "high"},
        {"case": "3", "scenario": "S1", "target": "tb-gw/mcp_server/notes-sync",
         "risk_condition": "출처 이상", "reason": "승인 목록에 없는 플러그인 agentscope-notes-sync가 manifest mcpServers로 서버를 등록함", "confidence": "high"},
        {"case": "3", "scenario": "S1", "target": "tb-gw/plugin/agentscope-notes-sync", "required": False,
         "risk_condition": "출처 이상", "reason": "승인 플러그인 목록(approved_plugins)에 없는 플러그인. 서버 단위 경고(notes-sync)에 묶어 내도 정답으로 인정", "confidence": "high"},
        {"case": "2", "scenario": "S4", "target": "tb-gw/mcp_server/inventory-remote", "required": False,
         "risk_condition": "자격증명이 승인되지 않은 endpoint로 전송", "reason": "INVENTORY_MCP_TOKEN이 바뀐 endpoint로 전송됨. S4 규칙 구현 시 동반 경고로 인정(S1 채점에는 미포함)", "confidence": "medium"},
    ],
}
CREDENTIAL_ENV = {  # 서버별 자격증명 참조(값은 기록하지 않는다)
    "inventory-remote": {"env_ref": "INVENTORY_MCP_TOKEN", "store": "tb-gw:~/.openclaw/.env", "used_in": "headers.Authorization"},
    "demo-everything": {"env_ref": "EVERYTHING_DEMO_KEY", "store": "tb-node:~/.openclaw/.env", "used_in": "env.EVERYTHING_DEMO_KEY"},
}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def raw_file(raw, base_raw, name):
    """위협 구성은 자기 raw가 없으면 기준 프로파일 raw를 쓴다."""
    p = raw / name
    return p if p.exists() or base_raw is None else base_raw / name


def exposed_tools(raw):
    """OpenClaw가 에이전트에 투영한 (서버, 도구) 집합. 수집 결과가 없으면 None(미확인)."""
    probe = raw / "tb-gw.mcp-probe.json"
    nodes = raw / "tb-node.nodes-describe.json"
    if not probe.exists() and not nodes.exists():
        return None
    exposed = set()
    if probe.exists():
        servers = sorted(load(probe)["servers"], key=len, reverse=True)
        for name in load(probe)["tools"]:
            for s in servers:
                if name.startswith(s + "__"):
                    exposed.add((s, name[len(s) + 2 :]))
                    break
    if nodes.exists():
        for t in load(nodes).get("nodePluginTools", []):
            if "mcp" in t:
                exposed.add((t["mcp"]["server"], t["mcp"]["tool"]))
    return exposed


def unexposed_reason(server, tool, cfg):
    tf = cfg.get("toolFilter") or {}
    if tf.get("include") and tool["name"] not in tf["include"]:
        return "toolFilter.include"
    if tool["name"] in (tf.get("exclude") or []):
        return "toolFilter.exclude"
    if (tool.get("execution") or {}).get("taskSupport") == "required":
        return "taskSupport=required (OpenClaw 미지원)"
    return "unknown"


def build(profile):
    prof = ROOT / "profiles" / profile
    raw = ROOT / "ground-truth" / "raw" / profile
    base_raw = ROOT / "ground-truth" / "raw" / BASE[profile] if profile in BASE else None
    gw_cfg = load(prof / "tb-gw.openclaw.json")
    node_cfg = load(prof / "tb-node.openclaw.json")
    gw_id = load(raw_file(raw, base_raw, "tb-gw.gateway-identity.json"))["deviceId"]
    node_id = load(raw_file(raw, base_raw, "tb-node.node-identity.json"))["deviceId"]
    exposed = exposed_tools(raw)

    assets, relations = [], []

    def asset(key, typ, declared_at, layer, **attrs):
        a = {"asset_key": key, "asset_type": typ, "declared_at": declared_at, "layer": layer}
        if attrs:
            a["attributes"] = attrs
        assets.append(a)
        return key

    def rel(typ, src, dst, evidence, confidence="high"):
        relations.append({"type": typ, "source": src, "target": dst, "evidence_refs": evidence, "confidence": confidence})

    gw = asset("tb-gw/gateway", "gateway", "tb-gw:~/.openclaw/openclaw.json", "declared",
               device_id=gw_id, identity_source="openclaw gateway call gateway.identity.get --json",
               bind=gw_cfg["gateway"]["bind"], port=gw_cfg["gateway"]["port"], auth_mode=gw_cfg["gateway"]["auth"]["mode"])
    node = asset("tb-node/node", "node", "tb-node:~/.openclaw/state/openclaw.sqlite#nodeHost.config", "declared",
                 device_id=node_id, identity_source="openclaw node identity --json",
                 pairing_record="tb-gw:openclaw devices list --json#paired[deviceId]")
    # 게이트웨이-노드 연결: 공통 스키마에 관계명이 없어 PR #1에서 제안된 PAIRED_WITH를 잠정 사용
    rel("PAIRED_WITH", gw, node, ["tb-gw:openclaw devices list --json#paired", "tb-gw:openclaw nodes describe --node tb-node"])

    servers = []  # (owner_key, vm, name, cfg, declared_at, transport)
    for name, cfg in ((gw_cfg.get("mcp") or {}).get("servers") or {}).items():
        servers.append((gw, "tb-gw", name, cfg, f"tb-gw:~/.openclaw/openclaw.json#mcp.servers.{name}"))
    for name, cfg in (((node_cfg.get("nodeHost") or {}).get("mcp") or {}).get("servers") or {}).items():
        servers.append((node, "tb-node", name, cfg, f"tb-node:~/.openclaw/openclaw.json#nodeHost.mcp.servers.{name}"))
    plugin_keys = {}
    for p in PLUGINS.get(profile, []):
        pk = asset(f"{p['vm']}/plugin/{p['id']}", "plugin", f"{p['vm']}:{p['dir']}", "declared",
                   install_source=p["install_source"],
                   config_entry=f"plugins.entries.{p['id']}", enabled=True)
        rel("DECLARES", gw, pk, [f"tb-gw:~/.openclaw/openclaw.json#plugins.entries.{p['id']}"])
        manifest = f"{p['vm']}:{p['dir']}/openclaw.plugin.json"
        for s, scfg in p["mcp_servers"].items():
            plugin_keys[s] = pk
            servers.append((pk, p["vm"], s, scfg, f"{manifest}#mcpServers.{s}"))

    for owner, vm, name, cfg, declared_at in servers:
        adv = load(raw_file(raw, base_raw, f"{name}.advertised.json"))
        transport = cfg.get("transport") or ("streamable-http" if cfg.get("url") else "stdio")
        attrs = {
            "transport": transport,
            "negotiated_protocol_version": adv["negotiatedProtocolVersion"],
            "server_info": adv["serverInfo"],
        }
        if cfg.get("url"):
            attrs.update(url=cfg["url"], ssl_verify=cfg.get("sslVerify"), runs_on="tb-node")
        else:
            attrs.update(command=cfg.get("command"), args=cfg.get("args", []), runs_on=vm)
        if cfg.get("toolFilter"):
            attrs["tool_filter"] = cfg["toolFilter"]
        if name in CREDENTIAL_ENV:
            attrs["credential_ref"] = CREDENTIAL_ENV[name]
        if name in plugin_keys:
            attrs["visible_in_openclaw_mcp_list"] = False  # openclaw mcp list/probe는 mcp.servers만 보여 줌
        sk = asset(f"{vm}/mcp_server/{name}", "mcp_server", declared_at, "declared", **attrs)
        if name in plugin_keys:
            pid = plugin_keys[name].split("/plugin/")[1]
            rel("ASSOCIATED_WITH", plugin_keys[name], sk, [declared_at, f"tb-gw:openclaw plugins inspect {pid} --runtime --json#install.acceptedSurface.mcpServers"])
        else:
            rel("DECLARES", owner, sk, [declared_at])

        for t in adv["tools"] if isinstance(adv["tools"], list) else []:
            if name in plugin_keys:
                # 플러그인 등록 서버는 openclaw mcp probe 대상이 아니어서 투영 여부를 정적으로 확인할 수 없다(에이전트 세션 필요)
                tattrs = {"exposed_to_agent": None, "exposure_check": "unverified: plugin-contributed server is not covered by openclaw mcp probe"}
            elif exposed is None:
                tattrs = {"exposed_to_agent": None, "exposure_check": f"unverified: raw/{profile} probe not collected yet"}
            else:
                is_exposed = (name, t["name"]) in exposed
                tattrs = {"exposed_to_agent": is_exposed}
                if not is_exposed:
                    tattrs["not_exposed_reason"] = unexposed_reason(name, t, cfg)
            if t.get("annotations"):
                tattrs["annotations"] = t["annotations"]
            tk = asset(f"{name}/tool/{t['name']}", "tool", f"{name}:tools/list", "advertised", **tattrs)
            rel("ADVERTISES", sk, tk, [f"{name}:tools/list"])
        for kind, items, ident in (("resource", adv["resources"], "uri"), ("resource", adv["resourceTemplates"], "uriTemplate"), ("prompt", adv["prompts"], "name")):
            if not isinstance(items, list):
                continue
            src = {"uri": "resources/list", "uriTemplate": "resources/templates/list", "name": "prompts/list"}[ident]
            for it in items:
                extra = {"subtype": "template"} if ident == "uriTemplate" else {}
                rk = asset(f"{name}/{kind}/{it[ident]}", kind, f"{name}:{src}", "advertised", name=it.get("name"), **extra)
                rel("ADVERTISES", sk, rk, [f"{name}:{src}"])

    for vm, sname, path, assoc in SKILLS.get(profile, []):
        sk = asset(f"{vm}/skill/{sname}", "skill", f"{vm}:{path}", "declared",
                   source="openclaw-node" if vm == "tb-node" else "openclaw-workspace")
        rel("DECLARES", node if vm == "tb-node" else gw, sk, [f"{vm}:{path}"])
        if assoc:
            rel("ASSOCIATED_WITH", sk, f"tb-gw/mcp_server/{assoc}", [f"{vm}:{path} (본문에서 {assoc} 도구 호출을 지시)"], "medium")

    counts = {}
    for a in assets:
        counts[a["asset_type"]] = counts.get(a["asset_type"], 0) + 1
    # S3 정상 기준 검증: 서로 다른 서버 간 원래 도구 이름 중복이 없어야 한다
    names = [a["asset_key"].split("/tool/")[1] for a in assets if a["asset_type"] == "tool"]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        sys.exit(f"{profile}: duplicate raw tool names across servers: {dup}")

    return {
        "profile": profile,
        "snapshot": SNAPSHOT[profile],
        "environment": {"openclaw_version": OPENCLAW_VERSION, "mcp_spec_version": SPEC_VERSION},
        "scope": "테스트베드가 추가한 자산만 포함. 내장(stock) 플러그인 63종·스킬 57종은 제외(testbed/baseline/SNAP-1 참조)",
        "summary": {"asset_counts": counts, "relation_count": len(relations)},
        "assets": assets,
        "relations": relations,
    }


def threat_delta(profile, gt):
    """위협 구성 정답: 기준 프로파일 대비 추가·변경·삭제 자산과 관계, expected_alerts."""
    base = build(BASE[profile])
    b_assets = {a["asset_key"]: a for a in base["assets"]}
    t_assets = {a["asset_key"]: a for a in gt["assets"]}
    rkey = lambda r: (r["type"], r["source"], r["target"])
    b_rels = {rkey(r) for r in base["relations"]}
    t_rels = {rkey(r) for r in gt["relations"]}
    exposure_fields = ("exposed_to_agent", "exposure_check", "not_exposed_reason")  # 재수집 전에는 미확인이라 비교하지 않음

    def changed(k):
        before, after = b_assets[k].get("attributes", {}), t_assets[k].get("attributes", {})
        diff = {f: {"before": before.get(f), "after": after.get(f)}
                for f in sorted(set(before) | set(after))
                if before.get(f) != after.get(f) and f not in exposure_fields}
        return {"asset_key": k, "changes": diff} if diff else None

    for alert in THREATS[profile]:
        if alert["target"] not in t_assets:
            sys.exit(f"{profile}: expected alert target not in assets: {alert['target']}")
    approved = load(ROOT / "ground-truth" / "approved-servers.json")
    alerted = {a["target"] for a in THREATS[profile] if a["scenario"] == profile}
    approved_keys = [f"{s['declared_at_vm']}/mcp_server/{s['name']}" for s in approved["servers"]]
    return {
        "profile": profile,
        "snapshot": gt["snapshot"],
        "base_profile": BASE[profile],
        "base_snapshot": base["snapshot"],
        "environment": gt["environment"],
        "scope": f"{BASE[profile]} 대비 추가·변경·삭제된 자산과 관계만 기록. 나머지는 ground-truth/{BASE[profile]}.json과 같다",
        "approved_servers": "ground-truth/approved-servers.json",
        "summary": gt["summary"],
        "added_assets": [a for k, a in t_assets.items() if k not in b_assets],
        "changed_assets": [c for k in t_assets if k in b_assets for c in [changed(k)] if c],
        "removed_assets": [k for k in b_assets if k not in t_assets],
        "added_relations": [r for r in gt["relations"] if rkey(r) not in b_rels],
        "removed_relations": [r for r in base["relations"] if rkey(r) not in t_rels],
        "expected_alerts": [{"required": True, **a} for a in THREATS[profile]],
        "expected_no_alert": {
            "scenario": profile,
            "targets": [k for k in approved_keys if k not in alerted],
            "note": "승인 목록과 일치하는 서버. 여기에 경고가 나면 오탐",
        },
    }


if __name__ == "__main__":
    for p in sys.argv[1:] or ["P0", "P1", "P2", "S1"]:
        gt = build(p)
        if p in BASE:
            gt = threat_delta(p, gt)
        out = ROOT / "ground-truth" / f"{p}.json"
        out.write_text(json.dumps(gt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(p, gt["summary"])
