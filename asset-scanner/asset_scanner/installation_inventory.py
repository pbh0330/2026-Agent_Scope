"""명시한 OpenClaw 설치·상태·workspace 경계에서 Plugin/Skill을 자동 탐색한다.

원천: eb377ac의 plugins/{roots,install-paths,installed-plugin-index-store}.ts와 skills.load.extraDirs.
홈 전체 탐색·코드 실행·설치/갱신·인덱스 재생성 없음. 발견 후보와 런타임 로딩은 별개다.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import re
from pathlib import Path
import sys

from .cli import _make_console_output_safe, _same_file
from .collector import CollectionFailure, parse_config, read_config
from .output import OutputError, normalize_for_output, write_json_atomic
from .plugin_skill_assets import _safe_path, collect_assets, build_report as asset_report
from .redaction import Redactor, looks_like_secret_value
from .process_identity import inspect_entry_file
from .source_io import SourceError, duplicate_count, parse_source_json, read_source_json, read_state_rows

MAX_ENTRIES = 5000
MAX_ASSETS = 500
MAX_DEPTH = 8
INSTALL_STRINGS = ("source", "spec", "sourcePath", "installPath", "version", "resolvedName", "resolvedVersion", "resolvedSpec",
                   "resolvedAt", "installedAt", "clawhubUrl", "clawhubPackage", "clawhubFamily", "clawhubChannel", "clawhubTrustDisposition",
                   "gitUrl", "gitRef", "gitCommit", "acceptedSurfaceAt", "marketplaceName", "marketplaceSource", "marketplacePlugin")
DIGEST_FIELDS = ("integrity", "shasum", "npmIntegrity", "npmShasum", "clawpackSha256", "clawpackManifestSha256", "acceptedSurfaceHash", "acceptedSurfaceIntegrity")


def _path_text(value, red, field):
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value):
        return red.sanitize_string(value, field)
    return "".join(red.sanitize_string(part, field) if looks_like_secret_value(part) else part
                   for part in re.split(r"([/\\])", value))


def _in_roots(path, roots):
    try:
        absolute, actual = path.absolute(), path.resolve()
        for root in roots:
            try:
                relative = absolute.relative_to(root)
                actual.relative_to(root)
            except ValueError:
                continue
            walk = root
            if root.is_symlink():
                continue
            for part in relative.parts:
                walk /= part
                if walk.is_symlink():
                    break
            else:
                return True
    except (OSError, RuntimeError):
        pass
    return False


def collect_installations(state_dirs=(), workspace_dirs=(), installation_roots=(), allowed_roots=(),
                          config=None, resolve_includes=False, index_json=(), state_databases=()):
    roots = [Path(p).absolute() for p in [*state_dirs, *workspace_dirs, *installation_roots, *allowed_roots]]
    if config is not None:
        roots.append(Path(config).absolute().parent)
    result = {"format": "agent-scope.scanner.installation-inventory", "format_version": "0.1.0-draft",
              "generated_at": datetime.now(timezone.utc).isoformat(), "discovery": [], "index_sources": [], "installation_records": [], "issues": [],
              "scope": {"method": "bounded_discovery_within_operator_selected_roots", "allowed_roots": [_safe_path(p)[0] for p in roots],
                        "limits": {"directory_entries": MAX_ENTRIES, "assets_per_kind": MAX_ASSETS, "depth": MAX_DEPTH},
                        "not_verified": ["runtime_loading", "installed_index_freshness", "signatures_and_integrity", "effective_activation", "live_openclaw"],
                        "not_performed": ["home_wide_scan", "install_or_refresh", "plugin_execution", "common_asset_id"]}}
    red = Redactor()
    plugin_paths, skill_paths = {}, {}
    candidates = []
    count = 0

    def issue(code, severity="error"):
        result["issues"].append({"severity": severity, "code": code})

    def candidate(path, kind, origin, required=False):
        path = Path(path)
        if not path.is_absolute():
            issue("relative_or_unexpanded_discovery_path")
            return
        if not _in_roots(path, roots):
            issue("discovery_path_outside_selected_roots_or_linked")
            return
        if path.exists():
            candidates.append((path, kind, origin))
        elif required:
            issue("declared_discovery_path_missing")

    for values, specs in ((state_dirs, (("extensions", "plugin"), ("git", "plugin"), ("npm", "plugin"), ("skills", "skill"))),
                          (workspace_dirs, ((".openclaw/extensions", "plugin"), ("skills", "skill"))),
                          # 소스 배치와 npm 배포물의 빌드 배치를 명시된 동일 경계 안에서 탐색한다.
                          (installation_roots, (("extensions", "plugin"), ("dist/extensions", "plugin"), ("skills", "skill")))):
        for value in values:
            root = Path(value).absolute()
            if not root.is_dir():
                issue("selected_root_missing")
                continue
            for subdir, kind in specs:
                candidate(root / subdir, kind, "selected_root_layout")
    if config is not None:
        try:
            tree = parse_config(read_config(Path(config)))
            if resolve_includes:
                from .config_includes import resolve_includes as resolve
                context = resolve(Path(config), tree)
                tree = context.root
                if context.issues:
                    issue("discovery_config_includes_incomplete")
            for section, field, kind in (("plugins", "paths", "plugin"), ("skills", "extraDirs", "skill")):
                load = tree.get(section, {}).get("load", {}) if isinstance(tree, dict) and isinstance(tree.get(section, {}), dict) else {}
                if not isinstance(load, dict) or field not in load:
                    continue
                if not isinstance(load[field], list):
                    issue("configured_discovery_paths_invalid")
                    continue
                if len(load[field]) > MAX_ASSETS:
                    issue("configured_discovery_path_limit")
                for path in load[field][:MAX_ASSETS]:
                    if isinstance(path, str) and path and "${" not in path and not path.startswith("~"):
                        candidate(Path(path), kind, "config_declared_load_path", required=True)
                    else:
                        issue("configured_discovery_path_unresolved")
        except (CollectionFailure, SourceError, OSError, TypeError):
            issue("discovery_config_unreadable")

    for kind, files in (("stored_index_json", index_json), ("state_database_snapshot", state_databases)):
        for path in files:
            source = {"ref": f"install-source[{len(result['index_sources'])}]", "file": _safe_path(Path(path))[0], "kind": kind, "status": "complete", "issues": []}
            result["index_sources"].append(source)
            try:
                values = [read_source_json(path)] if kind == "stored_index_json" else [parse_source_json(r[0]) for r in read_state_rows(Path(path), "plugin_index")]
                for value in values:
                    if duplicate_count(value):
                        source["issues"].append({"code": "duplicate_key"})
                        source["status"] = "partial"
                    if isinstance(value, dict) and "index" in value:
                        value = value["index"]
                    if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1 or not isinstance(value.get("plugins"), list):
                        raise SourceError("plugin_index_structure_unsupported")
                    entries = list(value["plugins"])
                    ledger = value.get("installRecords", {})
                    if isinstance(ledger, dict):
                        for pid, install in ledger.items():
                            if not isinstance(install, dict):
                                source["status"] = "partial"
                                source["issues"].append({"code": "install_ledger_record_invalid"})
                                continue
                            entries.append({"pluginId": pid, "rootDir": install.get("installPath"), "installRecord": install, "_ledger": True})
                    elif "installRecords" in value:
                        source["status"] = "partial"
                        source["issues"].append({"code": "install_ledger_structure_invalid"})
                    if len(entries) > MAX_ASSETS:
                        issue("plugin_index_record_limit")
                    for n, item in enumerate(entries[:MAX_ASSETS]):
                        if not isinstance(item, dict) or not isinstance(item.get("pluginId"), str) or not item["pluginId"] or (not item.get("_ledger") and not isinstance(item.get("rootDir"), str)) or (item.get("rootDir") is not None and not isinstance(item["rootDir"], str)):
                            source["issues"].append({"code": "plugin_index_record_invalid"})
                            source["status"] = "partial"
                            continue
                        shown_id = red.sanitize_string(item["pluginId"], "pluginId")
                        shown_root = _path_text(item["rootDir"], red, "rootDir") if isinstance(item.get("rootDir"), str) else None
                        rec = {"ref": f"install-record[{len(result['installation_records'])}]", "source_ref": source["ref"], "index": n,
                               "plugin_id": shown_id, "root_dir": shown_root, "source_container": "installRecords" if item.get("_ledger") else "plugins", "identity_altered": shown_id != item["pluginId"] or shown_root != item["rootDir"],
                               "verified_by_scanner": False, "install": {}, "digest_metadata": {}}
                        result["installation_records"].append(rec)
                        inst = item.get("installRecord")
                        if inst is None:
                            ledger = value.get("installRecords", {})
                            possible = ledger.get(item["pluginId"]) if isinstance(ledger, dict) else None
                            # ID만 같은 다른 설치본에 인덱스의 설치 정보를 옮기지 않는다.
                            if isinstance(possible, dict) and possible.get("installPath") == item["rootDir"]:
                                inst = possible
                        if inst is not None and not isinstance(inst, dict):
                            source["status"] = "partial"
                            source["issues"].append({"code": "install_record_invalid"})
                        elif isinstance(inst, dict):
                            for key in INSTALL_STRINGS:
                                if key in inst:
                                    if isinstance(inst[key], str):
                                        rec["install"][key] = _path_text(inst[key], red, "install." + key) if key in ("sourcePath", "installPath") else red.sanitize_string(inst[key], "install." + key)
                                    else:
                                        source["status"] = "partial"
                                        source["issues"].append({"code": "install_field_type_invalid", "field": key})
                            for key in DIGEST_FIELDS:
                                if key in inst:
                                    rec["digest_metadata"][key] = {"declared": True, "verified": False}
                        for key in ("origin", "packageName", "packageVersion", "source"):
                            if isinstance(item.get(key), str):
                                rec[key] = red.sanitize_string(item[key], key)
                        if isinstance(item.get("enabled"), bool):
                            rec["index_reported_enabled"] = item["enabled"]
                        if isinstance(item.get("rootDir"), str) and item["rootDir"]:
                            candidate(Path(item["rootDir"]), "plugin", "stored_index_root", required=True)
                        else:
                            rec["discovery_status"] = "installation_path_not_reported"
            except SourceError as exc:
                source["status"] = "failed"
                source["issues"].append({"code": exc.code})

    seen = set()
    for path, kind, origin in candidates:
        queue = [(path, 0)]
        while queue and count < MAX_ENTRIES:
            current, depth = queue.pop(0)
            key = (str(current), kind)
            if key in seen:
                continue
            seen.add(key)
            count += 1
            if not _in_roots(current, roots):
                issue("discovery_path_outside_selected_roots_or_linked")
                continue
            if current.is_file():
                current = current.parent
            if not current.is_dir():
                issue("discovery_directory_invalid")
                continue
            marker = current / ("openclaw.plugin.json" if kind == "plugin" else "SKILL.md")
            if marker.exists() or marker.is_symlink():
                if not _in_roots(marker, roots) or marker.stat().st_nlink > 1:
                    issue("metadata_file_link_refused")
                    continue
                target = plugin_paths if kind == "plugin" else skill_paths
                if len(target) >= MAX_ASSETS:
                    issue("discovered_asset_limit")
                    break
                if kind == "plugin" and (current / "package.json").exists() and not _in_roots(current / "package.json", roots):
                    issue("metadata_file_link_refused")
                    continue
                target[str(current)] = current
                result["discovery"].append({"kind": kind, "root": _safe_path(current)[0], "source": origin})
                continue
            if depth >= MAX_DEPTH:
                issue("discovery_depth_limit")
                continue
            try:
                children = []
                with os.scandir(current) as iterator:
                    for child in iterator:
                        count += 1
                        if count >= MAX_ENTRIES:
                            issue("discovery_entry_limit")
                            break
                        if child.is_symlink():
                            issue("discovery_link_not_followed", "warning")
                        elif child.is_dir(follow_symlinks=False) and child.name not in {".git", "__pycache__", ".cache"}:
                            children.append(Path(child.path))
                queue.extend((p, depth + 1) for p in sorted(children))
            except OSError:
                issue("discovery_directory_unreadable")
    if count >= MAX_ENTRIES:
        issue("discovery_entry_limit")
    result["assets"] = asset_report(collect_assets(list(plugin_paths.values()), list(skill_paths.values()), config, None, None, resolve_includes), True)
    for plugin, raw_root in zip(result["assets"]["plugins"], plugin_paths.values()):
        plugin["entry_file_observations"] = []
        package = raw_root / "package.json"
        if package.exists():
            try:
                raw_package = read_source_json(package)
                openclaw = raw_package.get("openclaw", {}) if isinstance(raw_package, dict) else {}
                if isinstance(openclaw, dict):
                    paths = []
                    for key in ("extensions", "runtimeExtensions", "setupEntry", "runtimeSetupEntry"):
                        val = openclaw.get(key, [])
                        if isinstance(val, str):
                            val = [val]
                        if isinstance(val, list):
                            paths.extend(x for x in val if isinstance(x, str))
                    if len(paths) > 50:
                        issue("entry_file_count_limit")
                    for value in paths[:50]:
                        target = raw_root / value
                        if ".." in value.replace("\\", "/").split("/") or not _in_roots(target, [raw_root]):
                            issue("entry_file_outside_package_or_linked")
                            continue
                        facts = inspect_entry_file(target)
                        plugin["entry_file_observations"].append(facts)
                        if facts["status"] != "complete":
                            issue("entry_file_observation_incomplete")
            except SourceError:
                issue("entry_package_json_unreadable")
        pid = plugin.get("identity", {}).get("id", {}).get("original_value")
        root = plugin.get("root_dir", {}).get("value")
        plugin["index_record_refs"] = [r["ref"] for r in result["installation_records"] if not r["identity_altered"] and r["plugin_id"] == pid
                                      and isinstance(r["root_dir"], str) and str(Path(r["root_dir"]).absolute()) == root]
    errors = any(i["severity"] == "error" for i in result["issues"]) or any(s["status"] != "complete" for s in result["index_sources"])
    if not result["assets"]["plugins"] and not result["assets"]["skills"] and not errors and result["assets"]["collection"].get("outcome") == "nothing_read":
        result["assets"]["collection"].update(status="complete", outcome="no_assets_in_selected_roots")
    status = "partial" if errors or result["assets"]["collection"]["status"] != "complete" else "complete"
    if errors and not result["assets"]["plugins"] and not result["assets"]["skills"] and not result["installation_records"]:
        status = "failed"
    result["collection"] = {"status": status, "plugin_count": len(result["assets"]["plugins"]), "skill_count": len(result["assets"]["skills"]),
                            "index_record_count": len(result["installation_records"]), "directory_entries_examined": count}
    result["redactions"] = red.redactions
    return result


def main(argv=None):
    _make_console_output_safe()
    parser = argparse.ArgumentParser(description="지정한 경계에서 Plugin·Skill 설치 정보를 읽기 전용으로 자동 탐색합니다.")
    for key in ("state-dir", "workspace-dir", "installation-root", "allow-root", "plugin-index-json", "state-db"):
        parser.add_argument("--" + key, action="append", default=[], type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--resolve-includes", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if not any((args.state_dir, args.workspace_dir, args.installation_root, args.plugin_index_json, args.state_db, args.config)):
        parser.error("탐색할 설치·상태·workspace 경계 또는 원천을 지정하세요.")
    if args.resolve_includes and not args.config:
        parser.error("--resolve-includes에는 --config가 필요합니다.")
    output_boundaries = args.state_dir + args.workspace_dir + args.installation_root + args.allow_root + ([args.config.parent] if args.config else [])
    if args.resolve_includes:
        output_boundaries += [Path(x.strip()).expanduser() for x in os.environ.get("OPENCLAW_INCLUDE_ROOTS", "").split(os.pathsep) if x.strip()]
    for p in output_boundaries:
        for output, boundary in ((args.output.absolute(), p.absolute()), (args.output.resolve(), p.resolve())):
            try:
                output.relative_to(boundary)
            except ValueError:
                continue
            parser.error("출력은 탐색·허용 경계 밖에 지정하세요. 발견된 원천을 덮어쓰지 않습니다.")
    for p in args.plugin_index_json + args.state_db + ([args.config] if args.config else []):
        if any(_same_file(Path(str(p) + suffix), args.output) for suffix in ("", "-wal", "-shm")):
            parser.error("출력은 입력 JSON·DB·WAL·SHM과 달라야 합니다.")
    result, _ = normalize_for_output(collect_installations(args.state_dir, args.workspace_dir, args.installation_root, args.allow_root,
        args.config, args.resolve_includes, args.plugin_index_json, args.state_db))
    try:
        write_json_atomic(args.output, result)
    except OutputError:
        return 4
    print(f"설치 원천 수집: {result['collection']['status']}, Plugin {result['collection']['plugin_count']}, Skill {result['collection']['skill_count']}")
    return {"complete": 0, "partial": 1, "failed": 3}[result["collection"]["status"]]


if __name__ == "__main__":
    sys.exit(main())
