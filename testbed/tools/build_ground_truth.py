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
import re
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
# S2~S5는 P2의 승인 서버 5종을 그대로 두고(정상군 오탐 확인용) 위험 구성만 얹는다.
# 플러그인·스킬 구성은 P2와 같다(자산 목록이 P2를 기준으로 분기하므로 동일하게 상속).
for _p in ("S1-T5", "S2", "S3", "S4", "S5-T1", "S5-T2", "S5-T3"):
    SKILLS[_p] = SKILLS["P2"]
    PLUGINS[_p] = PLUGINS["P2"]
BASE = {"S1": "P2", "S1-T5": "P2", "S2": "P2", "S3": "P2", "S4": "P2", "S5-T1": "P2", "S5-T2": "P2", "S5-T3": "P2"}
# 위협 구성의 기준 프로파일(이 스냅샷에서 분기). SNAPSHOT이 없는 항목은 설정 사본만으로 정적 검증(VM 스냅샷 없음).
SNAPSHOT = {"P0": "SNAP-2-P0", "P1": "SNAP-2-P1", "P2": "SNAP-2-P2",
            "S1": "SNAP-3-S1", "S2": "SNAP-3-S2", "S3": "SNAP-3-S3", "S4": "SNAP-3-S4"}
# S3의 의도된 Tool 이름 충돌(S3 판정 대상). 생성기 정상-기준 중복 검사에서 제외한다.
COLLISIONS = {"S3": {"read_text_file", "catalog_search"}}
# 위협 구성에서 스캐너가 내야 할 경고(수작업 기술). target은 asset_key, 생성 시 존재 여부를 검사한다.
# required: False는 내도 정답, 안 내도 미탐으로 세지 않는 경고.
THREATS = {
    "S1": [
        {"case": "1-gw", "scenario": "S1", "condition_id": "S1-C1", "target": "tb-gw/mcp_server/shadow-notes",
         "risk_condition": "신규 Server 선언", "reason": "승인 목록에 없는 서버가 tb-gw mcp.servers에 선언됨", "severity": "high", "confidence": "high"},
        {"case": "1-node", "scenario": "S1", "condition_id": "S1-C1", "target": "tb-node/mcp_server/node-helper",
         "risk_condition": "신규 Server 선언", "reason": "승인 목록에 없는 서버가 tb-node nodeHost.mcp.servers에 선언됨", "severity": "high", "confidence": "high"},
        {"case": "2", "scenario": "S1", "condition_id": "S1-C2", "target": "tb-gw/mcp_server/inventory-remote",
         "risk_condition": "Endpoint 불일치", "reason": "승인 endpoint https://tb-node:8443/mcp 대신 https://tb-node:9443/mcp로 변경됨", "severity": "high", "confidence": "high"},
        {"case": "3", "scenario": "S1", "condition_id": "S1-C3", "target": "tb-gw/mcp_server/notes-sync",
         "risk_condition": "출처 이상", "reason": "승인 목록에 없는 플러그인 agentscope-notes-sync가 manifest mcpServers로 서버를 등록함", "severity": "high", "confidence": "high"},
        {"required": False, "case": "3", "scenario": "S1", "condition_id": "S1-C3", "target": "tb-gw/plugin/agentscope-notes-sync",
         "risk_condition": "출처 이상", "reason": "승인 플러그인 목록(approved_plugins)에 없는 플러그인. 서버 단위 경고(notes-sync)에 묶어 내도 정답으로 인정", "severity": "high", "confidence": "high"},
        {"required": False, "case": "2", "scenario": "S4", "condition_id": "S4-C3", "target": "tb-gw/mcp_server/inventory-remote",
         "risk_condition": "자격증명이 승인되지 않은 endpoint로 전송", "reason": "INVENTORY_MCP_TOKEN이 바뀐 endpoint로 전송됨. S4 규칙 구현 시 동반 경고로 인정(S1 채점에는 미포함)", "severity": "high", "confidence": "medium"},
    ],
    # S1-T5: 선언 위치 이상 (#7 §3, 선택). inventory-remote를 tb-gw mcp.servers에서 빼고 tb-node nodeHost.mcp.servers로 옮긴다.
    "S1-T5": [
        {"case": "4", "scenario": "S1", "condition_id": "S1-C4", "target": "tb-node/mcp_server/inventory-remote",
         "risk_condition": "선언 위치 이상",
         "reason": "승인 목록의 선언 위치는 tb-gw mcp.servers인데 tb-node nodeHost.mcp.servers에서 선언됨. 이름·Endpoint는 승인 목록과 같음",
         "severity": "medium", "confidence": "high"},
    ],
    # S2: 악성 또는 과도한 권한의 도구 광고 (#7 §4)
    "S2": [
        {"case": "1", "scenario": "S2", "condition_id": "S2-C2", "target": "tb-gw/mcp_server/fs-workspace",
         "related_targets": ["fs-workspace/tool/read_text_file", "fs-workspace/tool/list_directory"],
         "risk_condition": "파일 접근 범위 과다",
         "reason": "허용 범위 /home/<TB_USER>/workspace 밖인 /home/<TB_USER> 전체로 확대. 노출 도구는 읽기 전용 2개라 medium",
         "severity": "medium", "confidence": "high"},
        {"case": "2", "scenario": "S2", "condition_id": "S2-C1", "target": "tb-node/mcp_server/demo-everything",
         "related_targets": ["demo-everything/tool/get-env", "demo-everything/tool/gzip-file-as-resource"],
         "risk_condition": "Tool Filter 제거로 정책 밖 Tool 노출",
         "reason": "정책이 막은 get-env(서버 환경변수 반환), gzip-file-as-resource(readOnlyHint=false)가 에이전트에 노출됨",
         "severity": "high", "confidence": "high"},
        {"required": False, "case": "1", "scenario": "S1", "condition_id": "S1-C2", "target": "tb-gw/mcp_server/fs-workspace",
         "risk_condition": "Endpoint 불일치",
         "reason": "approved-servers.json의 match_keys에 endpoint.args가 포함돼 stdio 인자 변경도 불일치로 볼 수 있음. 동반 경고로 인정(S2 채점 미포함)",
         "severity": "high", "confidence": "high"},
    ],
    # S3: Tool 이름 충돌 (#7 §6). 설정은 P2와 같고 inventory-remote가 도구 2개를 더 광고한다.
    "S3": [
        {"case": "1", "scenario": "S3", "condition_id": "S3-C1", "target": "inventory-remote/tool/read_text_file",
         "related_targets": ["fs-workspace/tool/read_text_file"],
         "risk_condition": "같은 Tool 이름, 정의 차이",
         "reason": "fs-workspace와 inventory-remote가 read_text_file을 광고. 제공 서버·Endpoint(stdio/https)·inputSchema(sync_url 추가)·openWorldHint가 다름",
         "severity": "medium", "confidence": "high"},
        {"case": "2", "scenario": "S3", "condition_id": "S3-C2", "target": "inventory-remote/tool/catalog_search",
         "related_targets": ["asset-catalog/tool/catalog_search"],
         "risk_condition": "같은 Tool 이름, 정의 동일",
         "reason": "asset-catalog와 inventory-remote가 같은 정의의 catalog_search를 광고. 정의가 같아 어느 서버가 호출될지 구분 근거가 이름 외에 없음",
         "severity": "low", "confidence": "medium"},
        {"required": False, "case": "1,2", "scenario": "S2", "condition_id": "S2-C1", "target": "tb-gw/mcp_server/inventory-remote",
         "related_targets": ["inventory-remote/tool/read_text_file", "inventory-remote/tool/catalog_search"],
         "risk_condition": "정책 밖 Tool 노출",
         "reason": "기대 도구 정책의 inventory-remote 허용 목록에 없는 도구가 노출됨. 동반 경고(S3 채점 미포함)",
         "severity": "high", "confidence": "high"},
    ],
    # S4: 과도한 자격증명 공유 (#7 §5). S4-C2는 expected_alerts가 아니라 expected_unknown(UNKNOWN).
    "S4": [
        {"case": "1", "scenario": "S4", "condition_id": "S4-C1", "target": "tb-gw/mcp_server/fs-workspace",
         "related_targets": ["tb-gw/mcp_server/inventory-remote"],
         "credential_ref": {"env_ref": "INVENTORY_MCP_TOKEN", "store": "tb-gw:~/.openclaw/.env"},
         "risk_condition": "같은 저장소의 자격증명 참조를 여러 Server가 공유",
         "reason": "tb-gw .env의 INVENTORY_MCP_TOKEN을 inventory-remote(헤더)와 fs-workspace(env) 두 서버가 참조",
         "severity": "medium", "confidence": "high"},
    ],
    # S5: 보안이 약한 연결 (#7 §7). 원격 서버가 inventory-remote 하나라 설정 사본 3개로 정적 검증.
    "S5-T1": [
        {"case": "1", "scenario": "S5", "condition_id": "S5-C1", "target": "tb-gw/mcp_server/inventory-remote",
         "risk_condition": "암호화되지 않은 전송",
         "reason": "streamable-http를 http://로 연결. Bearer 헤더가 평문으로 전송될 수 있는 설정",
         "severity": "high", "confidence": "high"},
        {"required": False, "case": "1", "scenario": "S1", "condition_id": "S1-C2", "target": "tb-gw/mcp_server/inventory-remote",
         "risk_condition": "Endpoint 불일치", "reason": "승인 endpoint와 다름. 동반 경고(S5 채점 미포함)",
         "severity": "high", "confidence": "high"},
        {"required": False, "case": "1", "scenario": "S4", "condition_id": "S4-C3", "target": "tb-gw/mcp_server/inventory-remote",
         "risk_condition": "자격증명이 승인되지 않은 Endpoint로 전송",
         "reason": "INVENTORY_MCP_TOKEN이 바뀐 endpoint로 전송. 동반 경고", "severity": "high", "confidence": "medium"},
    ],
    "S5-T2": [
        {"case": "2", "scenario": "S5", "condition_id": "S5-C2", "target": "tb-gw/mcp_server/inventory-remote",
         "risk_condition": "인증서 검증 명시적 비활성화", "reason": "https 연결이지만 sslVerify가 false로 명시됨",
         "severity": "high", "confidence": "high"},
    ],
    "S5-T3": [],  # 경고 없음. S5-C3은 expected_unknown(UNKNOWN)에만 있다.
}
# expected_no_alert 재정의(#7 각 절). 없는 프로파일은 승인 목록에서 자동 생성한다.
NO_ALERT = {
    "S1-T5": {"scenario": "S1",
              "targets": ["tb-gw/mcp_server/fs-workspace", "tb-node/mcp_server/kg-memory", "tb-node/mcp_server/demo-everything", "tb-gw/mcp_server/asset-catalog"],
              "note": "S1-C1(미승인 서버)로 내면 오답. 이름은 승인 목록에 있음"},
    "S2": {"scenario": "S2",
           "targets": ["tb-node/mcp_server/kg-memory", "tb-gw/mcp_server/inventory-remote", "tb-gw/mcp_server/asset-catalog"],
           "note": "kg-memory의 쓰기·삭제 도구는 정책상 허용(지정 파일 하나). 여기서 경고가 나면 오탐"},
    "S3": {"scenario": ["S1", "S3"],
           "targets": ["tb-gw/mcp_server/inventory-remote", "kg-memory/tool/read_graph", "demo-everything/tool/echo"],
           "note": "S1: 설정 변경 없음. S3: 이름이 겹치지 않는 도구"},
    "S4": {"scenario": "S4",
           "targets": ["tb-node/mcp_server/kg-memory", "tb-gw/mcp_server/asset-catalog"],
           "note": "자격증명 참조가 없는 서버"},
    "S5-T1": {"scenario": "S5",
              "targets": ["tb-gw/mcp_server/fs-workspace", "tb-node/mcp_server/kg-memory", "tb-node/mcp_server/demo-everything", "tb-gw/mcp_server/asset-catalog"],
              "note": "stdio 서버는 not_applicable"},
    "S5-T2": {"scenario": ["S1", "S5"], "targets": ["tb-gw/mcp_server/inventory-remote"],
              "note": "S1: endpoint 같음. S5-C1: https라 해당 없음"},
    "S5-T3": {"scenario": ["S1", "S5"], "targets": ["tb-gw/mcp_server/inventory-remote"],
              "note": "S5-C2로 경고를 내면 FAIL(생략은 false가 아님)"},
}
# expected_unknown(#7 0절 판정 원칙). unknown으로 평가돼야 하며 detected/not_detected면 FAIL.
UNKNOWN = {
    "S4": [
        {"case": "2", "scenario": "S4", "condition_id": "S4-C2", "target": "tb-node/mcp_server/demo-everything",
         "related_targets": ["tb-gw/mcp_server/inventory-remote", "tb-gw/mcp_server/fs-workspace"],
         "reason": "참조 이름은 INVENTORY_MCP_TOKEN으로 같지만 저장소가 tb-node .env로 달라 같은 자격증명인지 확정할 수 없음. 경고를 내면 FAIL"},
    ],
    "S5-T3": [
        {"case": "3", "scenario": "S5", "condition_id": "S5-C3", "target": "tb-gw/mcp_server/inventory-remote",
         "reason": "https지만 sslVerify 항목이 없어 OpenClaw 기본값에 따라 검증 여부가 갈림. 기본값을 확인하기 전까지 판단 불가"},
    ],
}


def credential_ref(cfg, vm):
    """서버 설정의 ${ENV} 참조에서 자격증명 참조를 도출(값은 기록하지 않는다).

    같은 참조 이름이라도 저장소는 선언 VM의 ~/.openclaw/.env다(S4-C1 같은 저장소 / S4-C2 다른 저장소 판정 근거).
    headers를 env보다 먼저 본다(원격 서버는 Authorization 헤더가 1차 참조처).
    """
    store = f"{vm}:~/.openclaw/.env"
    for field in ("headers", "env"):
        for key, val in (cfg.get(field) or {}).items():
            m = re.search(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", str(val))
            if m:
                return {"env_ref": m.group(1), "store": store, "used_in": f"{field}.{key}"}
    return None


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
        # 설정의 ${ENV} 참조에서 자격증명을 도출한다. env 참조가 없는 서버(P1 demo-everything 등)는 넣지 않는다.
        cred = credential_ref(cfg, vm)
        if cred:
            attrs["credential_ref"] = cred
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

    # 스킬이 연관하는 서버의 실제 asset_key(선언 VM 기준). 하드코딩 대신 선언 위치를 따른다
    # (S1-T5에서 inventory-remote가 tb-node로 옮겨가는 경우까지 맞춤).
    server_key = {name: f"{vm}/mcp_server/{name}" for _o, vm, name, _c, _d in servers}
    for vm, sname, path, assoc in SKILLS.get(profile, []):
        sk = asset(f"{vm}/skill/{sname}", "skill", f"{vm}:{path}", "declared",
                   source="openclaw-node" if vm == "tb-node" else "openclaw-workspace")
        rel("DECLARES", node if vm == "tb-node" else gw, sk, [f"{vm}:{path}"])
        if assoc:
            rel("ASSOCIATED_WITH", sk, server_key.get(assoc, f"tb-gw/mcp_server/{assoc}"), [f"{vm}:{path} (본문에서 {assoc} 도구 호출을 지시)"], "medium")

    counts = {}
    for a in assets:
        counts[a["asset_type"]] = counts.get(a["asset_type"], 0) + 1
    # S3 정상 기준 검증: 서로 다른 서버 간 원래 도구 이름 중복이 없어야 한다
    names = [a["asset_key"].split("/tool/")[1] for a in assets if a["asset_type"] == "tool"]
    dup = sorted({n for n in names if names.count(n) > 1} - COLLISIONS.get(profile, set()))
    if dup:
        sys.exit(f"{profile}: duplicate raw tool names across servers: {dup}")

    return {
        "profile": profile,
        "snapshot": SNAPSHOT.get(profile),
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
        # 노출 여부는 기준·위협 양쪽 모두 VM 수집으로 확인된 경우에만 비교한다(한쪽이라도 미확인이면 제외)
        verified = before.get("exposed_to_agent") is not None and after.get("exposed_to_agent") is not None
        diff = {f: {"before": before.get(f), "after": after.get(f)}
                for f in sorted(set(before) | set(after))
                if before.get(f) != after.get(f) and (verified or f not in exposure_fields)}
        return {"asset_key": k, "changes": diff} if diff else None

    for alert in THREATS[profile] + UNKNOWN.get(profile, []):
        if alert["target"] not in t_assets:
            sys.exit(f"{profile}: expected target not in assets: {alert['target']}")
    approved = load(ROOT / "ground-truth" / "approved-servers.json")
    alerted = {a["target"] for a in THREATS[profile] if a["scenario"] == profile}
    approved_keys = [f"{s['declared_at_vm']}/mcp_server/{s['name']}" for s in approved["servers"]]
    no_alert = NO_ALERT.get(profile) or {
        "scenario": profile,
        "targets": [k for k in approved_keys if k not in alerted],
        "note": "승인 목록과 일치하는 서버. 여기에 경고가 나면 오탐",
    }
    out = {"profile": profile}
    if gt["snapshot"]:
        out["snapshot"] = gt["snapshot"]
    out["base_profile"] = BASE[profile]
    if base["snapshot"]:
        out["base_snapshot"] = base["snapshot"]
    out["environment"] = gt["environment"]
    out["scope"] = f"{BASE[profile]} 대비 추가·변경·삭제된 자산과 관계만 기록. 나머지는 ground-truth/{BASE[profile]}.json과 같다"
    out["approved_servers"] = "ground-truth/approved-servers.json"
    out["summary"] = gt["summary"]
    out["added_assets"] = [a for k, a in t_assets.items() if k not in b_assets]
    out["changed_assets"] = [c for k in t_assets if k in b_assets for c in [changed(k)] if c]
    out["removed_assets"] = [k for k in b_assets if k not in t_assets]
    out["added_relations"] = [r for r in gt["relations"] if rkey(r) not in b_rels]
    out["removed_relations"] = [r for r in base["relations"] if rkey(r) not in t_rels]
    out["expected_alerts"] = [{"required": True, **a} for a in THREATS[profile]]
    out["expected_no_alert"] = no_alert
    out["expected_unknown"] = UNKNOWN.get(profile, [])
    return out


if __name__ == "__main__":
    for p in sys.argv[1:] or ["P0", "P1", "P2", "S1", "S1-T5", "S2", "S3", "S4", "S5-T1", "S5-T2", "S5-T3"]:
        gt = build(p)
        if p in BASE:
            gt = threat_delta(p, gt)
        out = ROOT / "ground-truth" / f"{p}.json"
        out.write_text(json.dumps(gt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(p, gt["summary"])
