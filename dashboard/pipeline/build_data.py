#!/usr/bin/env python3
"""팀 산출물 → 대시보드 데이터(public/data) 생성.

사용 예 (팀 저장소의 각 브랜치를 한 폴더에 받아 둔 경우)

  python pipeline/build_data.py \
      --scanner   ../2026-Agent_Scope/asset-scanner          # feature/scanner-config
      --testbed   ../2026-Agent_Scope/testbed                # develop + PR #24 feature/testbed-threat-vm-capture (P0~P2, S1~S5)
      --scenarios ../2026-Agent_Scope/docs/threat-scenarios  # 생략하면 pipeline/policies 사본
      --out       public/data

단계
  1) 자산 스캐너를 실제로 실행: 프로파일별 Gateway(mcp.servers)·Node(nodeHost.mcp.servers) 설정
  2) 어댑터: 스캐너 출력 + 테스트베드 원본 → InventorySnapshot (snapshot.json)
  3) S1~S5 정적 탐지 → DetectionReport (detections.json)
  4) 스냅샷 비교 → SnapshotDiff (diffs/*.json)
  5) 정상군은 정답 목록과 비교 → QAResult (qa.json)
  6) 토큰 수집기 usage.json 복사, manifest.json 작성

위험 구성은 테스트베드 profiles/<키>(설정) + ground-truth/raw/<키>(VM 수집본)를 그대로 쓴다.
  S1~S4         VM 수집 (measured=true, SNAP-3-*)
  S1-T5, S5-*   설정 사본 (measured=false) — 수집본은 P2 기준, 바뀐 서버의 노출은 미확인
기대 결과는 testbed/ground-truth/<키>.json의 expected_*(없으면 docs/threat-scenarios/expected-results.md).
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from agentscope_pipeline.adapter import ProfileInput, SkillInput, SnapshotBuilder, load  # noqa: E402
from agentscope_pipeline.compare import qa_result, snapshot_diff  # noqa: E402
from agentscope_pipeline.detector import Detector  # noqa: E402
from agentscope_pipeline.expected import compare as expected_compare, load_expected  # noqa: E402

ENV_ID = "agentscope-testbed"
NORMAL = ["P0", "P1", "P2"]
SKILL_DIRS = {  # 프로파일은 누적 구성(P2 = P1 + β)
    "P1": [("tb-node", "P1/tb-node-skills", "~/.openclaw/skills")],
    "P2": [("tb-gw", "P2/tb-gw-workspace-skills", "~/workspace/skills")],
}


def dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_scanner(scanner: Path, config: Path, out: Path, registry: str) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "asset_scanner", "--config", str(config), "--output", str(out), "--registry-path", registry]
    proc = subprocess.run(cmd, cwd=scanner, capture_output=True, text=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if proc.returncode not in (0, 1):  # 0 complete, 1 partial
        raise SystemExit(f"스캐너 실패({proc.returncode}): {config}\n{proc.stderr or proc.stdout}")
    return load(out)


USAGE_API_FILES = {  # 정적 사본 파일 이름 → API 경로 (token-collector/backend/usageapi README)
    "health.json": "health",
    "summary.json": "summary",
    "by-asset.asset.json": "by-asset?group=asset",
    "by-asset.server.json": "by-asset?group=server",
    "by-asset.pattern.json": "by-asset?group=pattern",
    "records.json": "records?limit=500",
    "timeseries.json": "timeseries",
    "brake-events.json": "brake-events?limit=500",
}


def snapshot_usage_api(base: str, out: Path) -> dict:
    """실행 중인 사용 현황 API의 응답을 그대로 저장한다(대시보드가 API 없이 열릴 때 쓰는 정적 사본)."""
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for name, path in USAGE_API_FILES.items():
        with opener.open(f"{base.rstrip('/')}/api/v1/usage/{path}", timeout=10) as r:
            dump(out / name, json.loads(r.read().decode("utf-8")))
    return load(out / "health.json")


def skills_for(testbed: Path, profile: str) -> list[SkillInput]:
    order = NORMAL[: NORMAL.index(profile) + 1]
    out = []
    for p in order:
        for host, rel, loc in SKILL_DIRS.get(p, []):
            for md in sorted((testbed / "profiles" / rel).glob("*/SKILL.md")):
                out.append(SkillInput(host, md, f"{loc}/{md.parent.name}/SKILL.md"))
    return out


# ---- 위험 구성 ------------------------------------------------------------
# 테스트베드 profiles/<키>(설정)와 ground-truth/raw/<키>(VM 수집본)를 그대로 쓴다.
# raw/<키>가 없는 구성(VM 미구축)은 P2 수집본을 기준으로 두고, P2와 선언이 달라진 서버의 노출은 "미확인"으로 둔다.
# 순서 = 구현 우선순위(S1 → S2 → S4 → S3 → S5)
SCENARIOS = [
    ("S1", "S1", "비인가 서버 등록", ["S1-T1", "S1-T2", "S1-T3", "S1-T4"]),
    ("S1-T5", "S1", "선언 위치 이상", ["S1-T5"]),
    ("S2", "S2", "과도한 도구 권한", ["S2-T1", "S2-T2"]),
    ("S4", "S4", "자격증명 공유", ["S4-T1", "S4-T2"]),
    ("S3", "S3", "도구 이름 충돌", ["S3-T1", "S3-T2"]),
    ("S5-T1", "S5", "평문 전송", ["S5-T1"]),
    ("S5-T2", "S5", "인증서 검증 끔", ["S5-T2"]),
    ("S5-T3", "S5", "sslVerify 항목 없음", ["S5-T3"]),
]


def _decls(gw: dict, node: dict | None) -> dict[str, tuple[str, str]]:
    out = {k: ("tb-gw", json.dumps(v, sort_keys=True)) for k, v in (gw.get("mcp", {}).get("servers") or {}).items()}
    for k, v in ((node or {}).get("nodeHost", {}).get("mcp", {}).get("servers") or {}).items():
        out[k] = ("tb-node", json.dumps(v, sort_keys=True))
    return out


def scenario_raw(testbed: Path, key: str, work: Path) -> tuple[Path, set[str], bool]:
    """(원본 폴더, 노출 미확인 서버, VM 수집 여부). raw/P2 위에 raw/<키>를 덮고, 플러그인 점검 원본이 없으면 저장소 manifest로 대신한다."""
    raw = work / key / "raw"
    if raw.exists():
        shutil.rmtree(raw)
    raw.mkdir(parents=True)
    for f in (testbed / "ground-truth" / "raw" / "P2").glob("*.json"):
        shutil.copy(f, raw / f.name)
    own = testbed / "ground-truth" / "raw" / key
    for f in own.glob("*.json"):
        shutil.copy(f, raw / f.name)
    gw = load(testbed / "profiles" / key / "tb-gw.openclaw.json")
    for pid, ent in (gw.get("plugins", {}).get("entries") or {}).items():
        man = testbed / "plugins" / pid / "openclaw.plugin.json"
        if (raw / f"tb-gw.plugin-inspect.{pid}.json").exists() or not man.exists() or not (ent or {}).get("enabled", True):
            continue
        m, pkg = load(man), (load(man.parent / "package.json") if (man.parent / "package.json").exists() else {})
        dump(raw / f"tb-gw.plugin-inspect.{pid}.json", {"plugin": {
            "_from_manifest": True, "id": m["id"], "name": m.get("name"), "description": m.get("description"),
            "version": pkg.get("version"), "packageName": pkg.get("name"),
            "rootDir": f"/home/<TB_USER>/.openclaw/extensions/{pid}", "mcpServers": m.get("mcpServers", {}),
            "trust": {"reason": "unverified: manifest only"}}})
    measured = (own / "tb-gw.mcp-probe.json").exists()
    if measured:
        return raw, set(), True
    p2 = _decls(load(testbed / "profiles" / "P2" / "tb-gw.openclaw.json"), load(testbed / "profiles" / "P2" / "tb-node.openclaw.json"))
    node_path = testbed / "profiles" / key / "tb-node.openclaw.json"
    cur = _decls(gw, load(node_path) if node_path.exists() else None)
    return raw, {k for k, v in cur.items() if p2.get(k) != v}, False


def run_catalog(scanner: Path, raw_dir: Path, overrides: dict[str, Path], out: Path) -> dict | None:
    """저장된 tools/list 응답(*.advertised.json)을 스캐너 tools_catalog로 읽는다. 스캐너가 지원하지 않으면 None."""
    caps = {f.name.split(".")[0]: f for f in raw_dir.glob("*.advertised.json")}
    caps.update(overrides)
    servers = []
    for name, f in sorted(caps.items()):
        d = load(f)
        servers.append({"server_ref": name, "protocol_version": d.get("negotiatedProtocolVersion"),
                        "pages": [{"result": {"tools": d.get("tools", [])}}]})
    if not servers:
        return None
    cap = out.with_name(out.stem + ".capture.json")
    dump(cap, {"format": "tools-list-capture", "origin": "testbed_capture", "servers": servers})
    proc = subprocess.run([sys.executable, "-m", "asset_scanner.tools_catalog", "--capture", str(cap), "--output", str(out)],
                          cwd=scanner, capture_output=True, text=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return load(out) if proc.returncode in (0, 1) and out.exists() else None


def scrub_paths(out: Path, prefixes: dict[str, str]) -> int:
    """출력 JSON의 실행 PC 절대 경로를 저장소 기준 상대 표기로 바꾼다(스캐너가 입력 파일 경로를 기록함)."""
    pairs = sorted(prefixes.items(), key=lambda kv: -len(kv[0]))

    def walk(v):
        if isinstance(v, str):
            for a, b in pairs:
                for form in (a, a.replace("\\", "/")):
                    if form in v:
                        v = v.replace(form, b)
            return v.replace("\\", "/") if any(b and v.startswith(b) for _, b in pairs) else v
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v
    n = 0
    for f in out.rglob("*.json"):
        d = load(f)
        w = walk(d)
        if w != d:
            dump(f, w)
            n += 1
    return n


def run_plugin_manifest(scanner: Path, manifest: Path, out: Path) -> dict | None:
    proc = subprocess.run([sys.executable, "-m", "asset_scanner", "--plugin-manifest", str(manifest), "--output", str(out)],
                          cwd=scanner, capture_output=True, text=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return load(out) if proc.returncode in (0, 1) and out.exists() else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scanner", type=Path, required=True, help="asset-scanner 폴더 (feature/scanner-config)")
    ap.add_argument("--testbed", type=Path, required=True, help="testbed 폴더 (develop, VM 수집본은 PR #24 feature/testbed-threat-vm-capture)")
    ap.add_argument("--usage", type=Path, help="토큰 수집기 usage.json (feature/token-collector)")
    ap.add_argument("--usage-api", help="실행 중인 사용 현황 API 주소(예: http://127.0.0.1:8088). 응답을 public/data/usage-api에 저장")
    ap.add_argument("--scenarios", type=Path, help="docs/threat-scenarios 폴더 (생략 시 pipeline/policies 사본)")
    ap.add_argument("--out", type=Path, default=HERE.parent / "public" / "data")
    ap.add_argument("--work", type=Path, default=HERE / ".work")
    args = ap.parse_args()

    testbed, out, work = args.testbed.resolve(), args.out.resolve(), args.work.resolve()
    if out.exists():
        shutil.rmtree(out)
    docs = args.scenarios.resolve() if args.scenarios else HERE / "policies"
    approved_tb = testbed / "ground-truth" / "approved-servers.json"
    approved_src = approved_tb if approved_tb.exists() else HERE / "policies" / "approved-servers.json"
    policies = {"catalog": load(docs / "scenario-catalog.json"),
                "tool_policy": load(docs / "policies" / "expected-tool-policy.json") if (docs / "policies").exists()
                else load(docs / "expected-tool-policy.json"),
                "approved_servers": load(approved_src)}
    manifest = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "environment_id": ENV_ID,
                "sources": {}, "snapshots": [], "diffs": [], "usage": None,
                "ruleset": {"id": policies["catalog"]["catalog_id"], "version": policies["catalog"]["catalog_version"]},
                "policies": {"approved_servers": str(approved_src.relative_to(testbed.parent)) if approved_src == approved_tb
                             else "pipeline/policies/approved-servers.json (testbed에 없어 사본 사용)",
                             "tool_policy": policies["tool_policy"]["policy_id"] + " " + policies["tool_policy"]["version"]}}
    dump(out / "scenario-catalog.json", policies["catalog"])
    expected = load_expected(docs / "expected-results.md", testbed / "ground-truth")
    manifest["expected"] = {"source": "testbed/ground-truth/<키>.json의 expected_* (없으면 docs/threat-scenarios/expected-results.md)",
                            "version": policies["catalog"]["catalog_version"], "profiles": sorted(expected)}
    snaps, dets = {}, {}

    def build(key, label, kind, gw_cfg_path, node_cfg_path, raw_dir, skills, scenario=None, captures=None, stale=None, notes=None,
              synthetic=False, test_cases=None, vm_label=None):
        gw_scan = run_scanner(args.scanner, gw_cfg_path, work / key / "scan.gw.json", "mcp.servers")
        node_scan = run_scanner(args.scanner, node_cfg_path, work / key / "scan.node.json", "nodeHost.mcp.servers") if node_cfg_path else None
        catalog = run_catalog(args.scanner, raw_dir, captures or {}, work / key / "scan.tools-catalog.json")
        plugin_scans = {}
        for f in raw_dir.glob("tb-gw.plugin-inspect.*.json"):
            pid = f.name[len("tb-gw.plugin-inspect."):-len(".json")]
            man = testbed / "plugins" / pid / "openclaw.plugin.json"
            if man.exists():
                ps = run_plugin_manifest(args.scanner, man, work / key / f"scan.plugin.{pid}.json")
                if ps:
                    plugin_scans[pid] = ps
        inp = ProfileInput(
            key=key, label=label, kind=kind, environment_id=ENV_ID, profile_id="tb-openclaw",
            configuration_id=key, vm_snapshot_label=vm_label if scenario else f"SNAP-2-{key}",
            scenario_id=scenario, gw_config=gw_cfg_path, gw_scan=gw_scan, node_config=node_cfg_path, node_scan=node_scan,
            raw_dir=raw_dir, skills=skills, capture_overrides=captures or {}, stale_exposure_servers=stale or set(),
            notes=notes or [], tools_catalog=catalog, plugin_scans=plugin_scans)
        snap = SnapshotBuilder(inp).build()
        det = Detector(snap, policies).run()
        d = out / "snapshots" / key
        dump(d / "snapshot.json", snap)
        dump(d / "detections.json", det)
        dump(d / "scanner" / "gateway.mcp-config.json", gw_scan)
        if node_scan:
            dump(d / "scanner" / "node.mcp-config.json", node_scan)
        if catalog:
            dump(d / "scanner" / "tools-catalog.json", catalog)
        for pid, ps in plugin_scans.items():
            dump(d / "scanner" / f"plugin.{pid}.mcp-config.json", ps)
        audit = raw_dir / "tb-gw.security-audit.json"
        entry = {"key": key, "label": label, "kind": kind, "scenario_id": scenario, "synthetic": synthetic,
                 "vm_label": inp.vm_snapshot_label,
                 "test_case_ids": test_cases or [],
                 "snapshot_id": snap["snapshot_id"], "files": {"snapshot": f"snapshots/{key}/snapshot.json",
                                                              "detections": f"snapshots/{key}/detections.json"},
                 "counts": {"assets": len(snap["assets"]), "relations": len(snap["relations"]), "alerts": len(det["alerts"])}}
        if key in expected:
            ex = expected_compare(snap, det, expected[key], policies["catalog"]["catalog_version"])
            dump(d / "expected.json", ex)
            entry["files"]["expected"] = f"snapshots/{key}/expected.json"
            entry["expected"] = {"verdict": ex["verdict"],
                                 "counts": {r: sum(c["result"] == r for c in ex["checks"]) for r in ("PASS", "PARTIAL", "FAIL", "SKIP", "INFO")}}
        if audit.exists():
            shutil.copy(audit, d / "openclaw-security-audit.json")
            entry["files"]["audit"] = f"snapshots/{key}/openclaw-security-audit.json"
        gt = testbed / "ground-truth" / f"{key}.json"
        if kind == "normal" and gt.exists():
            dump(d / "qa.json", qa_result(snap, load(gt), det))
            entry["files"]["qa"] = f"snapshots/{key}/qa.json"
        manifest["snapshots"].append(entry)
        snaps[key], dets[key] = snap, det
        print(f"  {key:5} {label:24} 자산 {len(snap['assets']):3} · 관계 {len(snap['relations']):3} · 경고 {len(det['alerts'])}"
              f" · scan {snap['scan']['status']}" + (f" · 기대 결과 {entry['expected']['verdict']}" if "expected" in entry else ""))

    print("정상군 프로파일")
    for p in NORMAL:
        prof = testbed / "profiles" / p
        build(p, {"P0": "P0 · 기본 구성", "P1": "P1 · 노드 서버·스킬", "P2": "P2 · 원격 서버·플러그인"}[p], "normal",
              prof / "tb-gw.openclaw.json", prof / "tb-node.openclaw.json", testbed / "ground-truth" / "raw" / p, skills_for(testbed, p))

    print("위험 구성 (테스트베드 profiles/<키> + raw/<키>)")
    scen_keys = []
    for key, scenario, title, tests in SCENARIOS:
        prof = testbed / "profiles" / key
        if not (prof / "tb-gw.openclaw.json").exists():
            print(f"  {key}: 테스트베드 구성(profiles/{key})이 없어 건너뜀")
            continue
        raw_dir, stale, measured = scenario_raw(testbed, key, work)
        gt = load(testbed / "ground-truth" / f"{key}.json") if (testbed / "ground-truth" / f"{key}.json").exists() else {}
        notes = [f"테스트베드 profiles/{key} 설정" + (f" + VM 수집본 raw/{key} ({gt.get('snapshot') or 'SNAP-3-' + key})" if measured
                 else " (VM 미구축 — 수집본은 P2 기준)")]
        notes += [f"변경: {c['asset_key']} ({', '.join(c.get('changes', {}))})" for c in gt.get("changed_assets", [])][:6]
        notes += [f"추가: {a['asset_key']}" for a in gt.get("added_assets", []) if a.get("asset_type") in ("mcp_server", "plugin")][:6]
        if stale:
            notes.append("노출 목록을 이 구성에서 다시 수집하지 않아 바뀐 서버(" + ", ".join(sorted(stale)) + ")의 노출은 미확인")
        build(key, f"{key} · {title}", "scenario", prof / "tb-gw.openclaw.json",
              prof / "tb-node.openclaw.json" if (prof / "tb-node.openclaw.json").exists() else None, raw_dir,
              skills_for(testbed, "P2"), scenario=scenario, stale=stale, notes=notes, synthetic=False, test_cases=tests,
              vm_label=(gt.get("snapshot") or f"SNAP-3-{key}") if measured else None)
        manifest["snapshots"][-1]["measured"] = measured
        scen_keys.append(key)

    pairs = [("P0", "P1"), ("P1", "P2")] + [("P2", s) for s in scen_keys]
    for a, b in pairs:
        diff = snapshot_diff(snaps[a], snaps[b], dets[a], dets[b])
        path = f"diffs/{a}__{b}.json"
        dump(out / path, diff)
        manifest["diffs"].append({"from": a, "to": b, "file": path,
                                  "counts": {t: sum(1 for c in diff["changes"] if c["change_type"] == t)
                                             for t in ("added", "modified", "removed_from_scope", "not_observed")}})

    if args.usage_api:
        health = snapshot_usage_api(args.usage_api, out / "usage-api")
        manifest["usage_api"] = {
            "dir": "usage-api", "api_base": "/api/v1/usage", "captured_at": manifest["generated_at"],
            "mode": health.get("mode"), "sources": health.get("sources"), "records": health.get("records"),
            "inventory_snapshot_id": health.get("inventory_snapshot_id"),
            "source": "feature/token-collector · backend/usageapi (agentscope-usage-api)"}
        print(f"사용 현황 API 응답 저장: {args.usage_api} → usage-api/ (기록 {health.get('records')}건)")
    if args.usage:
        usage = load(args.usage)
        dump(out / "usage.json", usage)
        manifest["usage"] = {"file": "usage.json", "source": "token-collector/collector/usagereport",
                             "linked_snapshot": usage.get("inventory_snapshot_id"),
                             "note": "토큰 수집기 3주차 검증 로그로 만든 usage.json. 테스트베드 스냅샷과 다른 환경(environment_id)"}
    manifest["sources"] = {
        "scanner": "feature/scanner-config(11/13) · asset_scanner 설정 수집·tools_catalog·--plugin-manifest",
        "testbed": "develop + PR #24 feature/testbed-threat-vm-capture · profiles P0~P2·S1~S5, ground-truth/raw(VM 수집), approved-servers.json",
        "threat_rules": f"docs/threat-scenarios v{policies['catalog']['catalog_version']} · scenario-catalog.json, 부록 A",
        "schema": "docs/mcp-attack-surface-definition · schema-design-draft v0.6",
        "usage": "feature/token-collector · backend/usageapi" if args.usage_api else ("feature/token-collector · usagereport" if args.usage else None),
    }
    dump(out / "manifest.json", manifest)
    scrub_paths(out, {str(testbed.parent) + os.sep: "", str(work): "pipeline/.work", str(args.scanner.resolve()): "asset-scanner"})
    print(f"완료 → {out}")


if __name__ == "__main__":
    main()
