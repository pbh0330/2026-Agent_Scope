"""Plugin·Skill 자체 정보 수집(plugin_skill_assets) 테스트.

모든 플러그인·스킬·설정·명령 출력은 테스트가 임시 폴더에 만든 **가상 자료**다. 실제 OpenClaw를 설치·실행하지 않으며
`FAKE` 표식이 붙은 값은 전부 가짜 비밀값이다.
"""

import json
import os
import subprocess
import sys

import pytest

from asset_scanner import plugin_skill_assets as psa
from asset_scanner.plugin_skill_assets import build_report, collect_assets, parse_frontmatter
from conftest import SCANNER_ROOT

TOKEN = "ghp_FAKEPLUGINTOKEN1234567890abcdefgh"


def make_plugin(root, manifest=None, package=None, files=None, name="plug"):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    if manifest is not None:
        (d / "openclaw.plugin.json").write_text(manifest if isinstance(manifest, str) else json.dumps(manifest), encoding="utf-8")
    if package is not None:
        (d / "package.json").write_text(json.dumps(package), encoding="utf-8")
    for rel, text in (files or {}).items():
        f = d / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    return d


def make_skill(root, folder, text):
    d = root / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(text, encoding="utf-8")
    return d


SKILL_OK = "---\nname: image-lab\ndescription: Generate images via a workflow\nhomepage: https://example.test/lab\nuser-invocable: true\n---\nBody text with FAKEBODYSECRET.\n"


def run(plugin_dirs=(), skills_dirs=(), config=None, plugins_list=None, skills_list=None):
    return build_report(collect_assets(list(plugin_dirs), list(skills_dirs), config, plugins_list, skills_list))


def dump(x):
    return json.dumps(x, ensure_ascii=False)


# ---- Plugin ---------------------------------------------------------------------------

BASE_MANIFEST = {"id": "voice-call", "name": "Voice Call", "version": "1.2.3", "description": "Calls", "kind": "memory",
                 "channels": ["voice"], "providers": ["acme"], "enabledByDefault": True, "configSchema": {"type": "object"}}


def test_plugin_identity_manifest_and_supply_source_are_read_from_files(tmp_path):
    pkg = {"name": "@acme/voice-call", "version": "1.2.3",
           "openclaw": {"install": {"npmSpec": "@acme/voice-call@1.2.3", "minHostVersion": ">=2026.3.22", "expectedIntegrity": "sha512-FAKEINTEGRITY"},
                        "compat": {"pluginApi": ">=2026.5.27"}, "extensions": ["./dist/index.js"]}}
    d = make_plugin(tmp_path, BASE_MANIFEST, pkg)
    rep = run([d])
    p = rep["plugins"][0]
    assert rep["collection"]["status"] == "complete" and p["collection_status"] == "complete"
    assert p["identity"]["id"] == {"original_value": "voice-call", "status": "as_reported"}
    assert p["manifest"]["declared"]["version"] == "1.2.3" and p["manifest"]["declared"]["channels"] == ["voice"]
    assert p["manifest"]["declared"]["enabledByDefault"] is True and "configSchema" in p["manifest"]["declared_keys"]
    assert p["supply_source"]["package_name"] == "@acme/voice-call"
    assert p["supply_source"]["install_hints"]["npmSpec"] == "@acme/voice-call@1.2.3"
    assert p["package"]["expected_integrity_declared"] is True and "FAKEINTEGRITY" not in dump(rep)   # 무결성 값은 저장하지 않음
    assert p["observed_from"]["manifest"]["evidence_type"] == "static_file"
    assert "설치 기록" in p["supply_source"]["basis"]
    assert p["runtime_observation"] is None if "runtime_observation" in p else True
    assert "실제 활성 상태가 아닙니다" in p["manifest"]["activation_note"]


def test_missing_fields_are_not_invented(tmp_path):
    p = run([make_plugin(tmp_path, {"configSchema": {}})])["plugins"][0]
    assert p["identity"]["id"]["status"] == "missing" and p["identity"]["name"]["status"] == "missing"
    assert "version" not in p["manifest"]["declared"] and p["package"] is None
    assert p["supply_source"]["package_name"] is None and p["mcp_servers"] is None
    assert any(i["code"] == "required_field_missing" for i in p["issues"]) and p["collection_status"] == "partial"


def test_plugin_directory_and_manifest_problems_fail_without_traceback(tmp_path):
    rep = run([tmp_path / "nope", make_plugin(tmp_path, None, name="empty"), make_plugin(tmp_path, "{ not json", name="bad"),
               make_plugin(tmp_path, "[1]", name="arr")])
    assert [p["collection_status"] for p in rep["plugins"]] == ["failed"] * 4
    assert [p["outcome"] for p in rep["plugins"]][0] == "plugin_dir_not_found" and rep["collection"]["status"] == "failed"
    assert "Traceback" not in dump(rep)


def test_wrong_types_are_reported_and_other_fields_survive(tmp_path):
    m = {"id": "x", "name": 5, "version": ["1"], "channels": "voice", "providers": ["ok", 3], "enabledByDefault": "yes", "kind": 7}
    p = run([make_plugin(tmp_path, m)])["plugins"][0]
    d = p["manifest"]["declared"]
    assert d == {"id": "x"} and p["identity"]["name"]["status"] == "invalid_type"
    assert {i["field_path"] for i in p["issues"] if i["code"] == "field_type_invalid"} >= {"name", "version", "channels", "providers", "enabledByDefault", "kind"}
    assert p["identity"]["id"]["original_value"] == "x"


def test_duplicate_manifest_keys_make_the_plugin_partial(tmp_path):
    p = run([make_plugin(tmp_path, '{"id":"a","id":"b","configSchema":{}}')])["plugins"][0]
    assert p["collection_status"] == "partial" and any(i["code"] == "duplicate_key" for i in p["issues"])
    assert p["identity"]["id"]["original_value"] == "b"       # 마지막 값만 읽음


def test_secret_looking_identity_is_withheld_not_treated_as_original(tmp_path):
    m = {"id": TOKEN, "name": "https://u:FAKEPW@h.test/x", "description": f"use {TOKEN}"}
    rep = run([make_plugin(tmp_path, m)])
    p = rep["plugins"][0]
    assert p["identity"]["id"] == {"original_value": None, "status": "withheld_by_redaction"}
    assert p["identity"]["name"]["status"] == "withheld_by_redaction"
    assert "FAKEPLUGINTOKEN" not in dump(rep) and "FAKEPW" not in dump(rep)
    assert p["redactions"]


def test_manifest_mcp_servers_are_linked_to_the_plugin_without_claiming_activation(tmp_path):
    m = {**BASE_MANIFEST, "mcpServers": {"voice-srv": {"command": "node", "args": ["server.js"], "env": {"API_KEY": "FAKEENVVALUE"}},
                                          "remote": {"url": "https://u:FAKEURLPW@mcp.test/mcp", "transport": "streamable-http"}}}
    rep = run([make_plugin(tmp_path, m)])
    p = rep["plugins"][0]
    mcp = p["mcp_servers"]
    assert mcp["link_basis"] == "declared_in_same_manifest" and mcp["registry_path"] == "mcpServers"
    assert [r["registration_key"] for r in mcp["records"]] == ["voice-srv", "remote"]
    assert mcp["records"][0]["declaration_path"] == "mcpServers.voice-srv" and mcp["records"][0]["declared"]["command"] == "node"
    assert "실행·로딩·등록 성공을 뜻하지 않습니다" in mcp["note"]
    assert "FAKEENVVALUE" not in dump(rep) and "FAKEURLPW" not in dump(rep)
    assert "runtime_observation" not in p or p["runtime_observation"] is None


def test_manifest_skills_inside_the_plugin_root_are_read_and_linked(tmp_path):
    d = make_plugin(tmp_path, {**BASE_MANIFEST, "skills": ["skills"]}, files={"skills/lab/SKILL.md": SKILL_OK})
    rep = run([d])
    p, s = rep["plugins"][0], rep["skills"][0]
    assert p["skills_declared"][0]["status"] == "read" and p["skills_declared"][0]["skills"] == [s["internal_ref"]]
    assert s["declared_by_plugin"]["plugin_ref"] == p["internal_ref"] and s["identity"]["name"]["original_value"] == "image-lab"
    assert s["observed_from"]["provided_by"] == "declared_by_plugin_manifest"


@pytest.mark.parametrize("rel", ["../outside", "..\\outside", "sub/../../outside"])
def test_manifest_skills_paths_cannot_leave_the_plugin_root(tmp_path, rel):
    make_skill(tmp_path, "outside", SKILL_OK)
    d = make_plugin(tmp_path, {**BASE_MANIFEST, "skills": [rel]})
    rep = run([d])
    assert rep["skills"] == [] and rep["plugins"][0]["skills_declared"][0]["status"] == "outside_plugin_root_not_read"
    assert any(i["code"] == "skills_path_outside_plugin_root" for i in rep["plugins"][0]["issues"])
    assert "FAKEBODYSECRET" not in dump(rep)


def test_absolute_skills_path_is_not_read(tmp_path):
    out = make_skill(tmp_path, "abs", SKILL_OK)
    rep = run([make_plugin(tmp_path, {**BASE_MANIFEST, "skills": [str(out)]})])
    assert rep["skills"] == [] and rep["plugins"][0]["skills_declared"][0]["status"] == "outside_plugin_root_not_read"


def test_plugin_code_is_never_executed(tmp_path):
    marker = tmp_path / "EXECUTED.txt"
    code = f"require('fs').writeFileSync({json.dumps(str(marker))}, 'ran')"
    py = f"open({json.dumps(str(marker))}, 'w').write('ran')"
    d = make_plugin(tmp_path, {**BASE_MANIFEST, "skills": ["skills"]},
                    {"name": "x", "version": "1", "scripts": {"postinstall": py}, "openclaw": {"extensions": ["./index.js"]}},
                    {"index.js": code, "setup.py": py, "__init__.py": py, "skills/s/SKILL.md": SKILL_OK})
    run([d], [tmp_path / "plug" / "skills"])
    assert not marker.exists()


# ---- Skill ---------------------------------------------------------------------------

def test_skill_frontmatter_is_read_and_the_body_is_not_stored(tmp_path):
    rep = run(skills_dirs=[make_skill(tmp_path, "image-lab", SKILL_OK)])
    s = rep["skills"][0]
    assert s["frontmatter"] == {"name": "image-lab", "description": "Generate images via a workflow", "homepage": "https://example.test/lab", "user-invocable": True}
    assert s["identity"]["name"] == {"original_value": "image-lab", "status": "as_reported"} and s["name_matches_folder"] is True
    assert s["config_key"] == {"value": "image-lab", "basis": "name"} and s["body_size_bytes"] > 0
    assert "FAKEBODYSECRET" not in dump(rep) and "Body text" not in dump(rep)
    assert s["observed_from"]["provided_by"] == "operator_selected_directory" and s["collection_status"] == "complete"


def test_skill_metadata_openclaw_and_skill_key(tmp_path):
    text = ('---\nname: peek\ndescription: d\nmetadata: { "openclaw": { "skillKey": "peekaboo", "primaryEnv": "PEEK_KEY", "emoji": "x", '
            '"requires": { "bins": ["peek"], "env": ["PEEK_KEY"] }, "install": [{"kind": "brew"}], "future": 1 } }\n---\nbody')
    s = run(skills_dirs=[make_skill(tmp_path, "peek", text)])["skills"][0]
    m = s["metadata_openclaw"]
    assert m["skillKey"] == "peekaboo" and m["primaryEnv"] == "PEEK_KEY" and m["requires"] == {"bins": ["peek"], "env": ["PEEK_KEY"]}
    assert m["install_spec_count"] == 1 and m["other_keys"] == ["future"]
    assert s["config_key"] == {"value": "peekaboo", "basis": "metadata.openclaw.skillKey"}


def test_multiline_metadata_block_is_reinterpreted_and_block_scalars_are_not_guessed(tmp_path):
    text = "---\nname: n\ndescription: >\n  long folded\n  text\nmetadata:\n  openclaw:\n    emoji: \"e\"\n    always: true\n---\nb"
    fm, unparsed, problem = parse_frontmatter(text)
    assert problem is None and fm["metadata"] == {"openclaw": {"emoji": "e", "always": True}} and "description" in unparsed
    s = run(skills_dirs=[make_skill(tmp_path, "n", text)])["skills"][0]
    assert "description" not in s["frontmatter"] and s["frontmatter_unparsed_keys"] == ["description"]
    assert s["metadata_openclaw"]["always"] is True
    assert any(i["code"] == "required_field_missing" for i in s["issues"])        # description을 읽지 못해 필수 필드 누락으로 표시


@pytest.mark.parametrize("text, code", [("no frontmatter", "frontmatter_missing"), ("---\nname: x\n", "frontmatter_unterminated")])
def test_bad_frontmatter_fails_that_skill_only(tmp_path, text, code):
    rep = run(skills_dirs=[make_skill(tmp_path, "bad", text), make_skill(tmp_path, "good", SKILL_OK.replace("image-lab", "good"))])
    by = {s["folder_name"]: s for s in rep["skills"]}
    assert by["bad"]["collection_status"] == "failed" and by["bad"]["outcome"] == code
    assert by["good"]["collection_status"] == "complete" and rep["collection"]["status"] == "partial"


def test_skill_secrets_and_wrong_types_are_masked_or_reported(tmp_path):
    text = f"---\nname: s\ndescription: key {TOKEN} at https://u:FAKESKILLPW@h.test/x?t=FAKEQ\nuser-invocable: maybe\nhomepage: 5\n---\nbody"
    rep = run(skills_dirs=[make_skill(tmp_path, "s", text)])
    s = rep["skills"][0]
    assert "FAKEPLUGINTOKEN" not in dump(rep) and "FAKESKILLPW" not in dump(rep) and "FAKEQ" not in dump(rep)
    assert {i["field_path"] for i in s["issues"] if i["code"] == "field_type_invalid"} == {"user-invocable", "homepage"}
    assert s["redactions"]


def test_skill_directory_discovery_is_shallow_bounded_and_does_not_follow_links(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    for n in ("a", "b", "c"):
        make_skill(root, n, SKILL_OK.replace("image-lab", n))
    make_skill(root / "group", "deep", SKILL_OK.replace("image-lab", "deep"))          # 깊이 2는 읽지 않음
    assert sorted(s["folder_name"] for s in run(skills_dirs=[root])["skills"]) == ["a", "b", "c"]
    monkeypatch.setattr(psa, "MAX_SKILLS_PER_DIR", 2)
    rep = run(skills_dirs=[root])
    assert len(rep["skills"]) == 2 and any(i["code"] == "skill_limit_exceeded" for i in rep["issues"]) and rep["collection"]["status"] == "partial"
    # 이 PC의 계정은 심볼릭 링크를 만들 권한이 없을 수 있으므로, 이름이 lnk인 폴더를 링크로 판정하게 만들어 분기를 검증한다.
    make_skill(tmp_path / "linkroot", "lnk", SKILL_OK.replace("image-lab", "linked"))
    real = type(tmp_path).is_symlink
    monkeypatch.setattr(type(tmp_path), "is_symlink", lambda self: self.name == "lnk" or real(self))
    rep = run(skills_dirs=[tmp_path / "linkroot"])
    assert rep["skills"] == [] and any(i["code"] == "symlink_not_followed" for i in rep["issues"])


def test_empty_or_missing_skills_dirs_are_reported_not_called_empty_success(tmp_path):
    (tmp_path / "empty").mkdir()
    rep = run(skills_dirs=[tmp_path / "empty", tmp_path / "missing"])
    assert rep["skills"] == [] and {i["code"] for i in rep["issues"]} == {"no_skill_files", "dir_not_found"}
    assert rep["collection"]["status"] != "complete"


# ---- 설정에 선언된 활성화 값 -------------------------------------------------------------------

CONFIG = """{
  plugins: { enabled: true, allow: ["voice-call"], deny: ["bad"], entries: { "voice-call": { enabled: false, config: { x: 1 } }, other: { enabled: true } } },
  skills: { allowBundled: ["image-lab"], load: { extraDirs: ["~/more"] },
    entries: { "image-lab": { enabled: true, apiKey: "FAKEAPIKEYLITERAL", env: { GEMINI_KEY: "FAKEENVSECRET" }, config: { endpoint: "https://x" } },
               peekaboo: { apiKey: { source: "env", provider: "default", id: "PEEK" } } } }
}"""


def test_config_activation_is_declared_and_linked_by_documented_keys_only(tmp_path):
    cfg = tmp_path / "openclaw.json5"
    cfg.write_text(CONFIG, encoding="utf-8")
    d = make_plugin(tmp_path, BASE_MANIFEST)
    rep = run([d], [make_skill(tmp_path, "image-lab", SKILL_OK)], config=cfg)
    da = rep["plugins"][0]["declared_activation"]
    assert da["entry_declared"] is True and da["entry_enabled"] is False and da["listed_in_allow"] is True and da["listed_in_deny"] is False
    assert da["source"] == "config_declared" and "판단하지 않습니다" in da["note"]
    assert "effective_enabled" not in da and "loaded" not in dump(da)
    sa = rep["skills"][0]["declared_activation"]
    assert sa["entry_enabled"] is True and sa["apiKey"] == {"value_kind": "literal_withheld"} and sa["env_names"] == ["GEMINI_KEY"]
    assert sa["listed_in_allowBundled"] is True
    out = dump(rep)
    assert "FAKEAPIKEYLITERAL" not in out and "FAKEENVSECRET" not in out
    peek = rep["activation_settings"]["skills"]["entries"]["peekaboo"]["apiKey"]
    assert peek["value_kind"] == "secret_ref" and peek["ref"]["id"] == "PEEK"


def test_config_without_matching_entries_is_not_called_enabled_or_disabled(tmp_path):
    cfg = tmp_path / "c.json5"
    cfg.write_text("{ plugins: { entries: { zzz: { enabled: true } } } }", encoding="utf-8")
    rep = run([make_plugin(tmp_path, BASE_MANIFEST)], config=cfg)
    da = rep["plugins"][0]["declared_activation"]
    assert da["entry_declared"] is False and da["entry_enabled"] is None and da["listed_in_allow"] is None


def test_config_errors_are_reported(tmp_path):
    bad = tmp_path / "bad.json5"
    bad.write_text("{ nope", encoding="utf-8")
    rep = run([make_plugin(tmp_path, BASE_MANIFEST)], config=bad)
    assert rep["activation_settings"]["status"] == "failed" and rep["collection"]["status"] == "partial"
    typed = tmp_path / "typed.json5"
    typed.write_text('{ plugins: { enabled: "yes", allow: "x", entries: { a: 5 } }, skills: { entries: { b: { enabled: 1 } } } }', encoding="utf-8")
    rep = run(config=typed)
    codes = {i["field_path"] for i in rep["activation_settings"]["issues"]}
    assert {"plugins.enabled", "plugins.allow", "skills.entries.b.enabled"} <= codes


# ---- 저장된 명령 출력 --------------------------------------------------------------------------

def test_plugins_list_json_links_only_with_id_and_root_and_keeps_other_records_separate(tmp_path):
    d = make_plugin(tmp_path, BASE_MANIFEST)
    listing = {"workspaceDir": "/w", "registry": {"source": "persisted", "diagnostics": []}, "diagnostics": [], "plugins": [
        {"id": "voice-call", "name": "Voice Call", "version": "1.2.3", "origin": "workspace", "source": "x", "rootDir": str(d), "enabled": True,
         "explicitlyEnabled": True, "activated": True, "status": "loaded", "toolNames": ["call"], "hookNames": [], "error": f"boom {TOKEN}"},
        {"id": "voice-call", "name": "Same id elsewhere", "origin": "global", "rootDir": str(tmp_path / "elsewhere"), "enabled": False, "status": "disabled"},
        {"id": "only-runtime", "name": "R", "origin": "bundled", "enabled": True, "status": "loaded"}]}
    f = tmp_path / "plugins.json"
    f.write_text(json.dumps(listing), encoding="utf-8")
    rep = run([d], plugins_list=f)
    p = rep["plugins"][0]
    ro = p["runtime_observation"]
    assert ro["link_basis"] == "id_and_root_dir_match" and ro["observed"]["status"] == "loaded" and ro["observed"]["origin"] == "workspace"
    assert ro["observed"]["error_present"] is True and ro["registered_names"]["toolNames"] == ["call"]
    assert ro["observation"]["source_kind"] == "stored_command_output" and ro["observation"]["observed_at"] is None
    assert ro["observation"]["verified_by_scanner"] is False and "관측 시각이 아닙니다" in ro["observation"]["observed_at_note"]
    assert "FAKEPLUGINTOKEN" not in dump(rep)                                              # 오류 메시지 원문은 저장하지 않음
    names = sorted(r["observed"]["name"] for r in rep["runtime_only"]["plugins"])
    assert names == ["R", "Same id elsewhere"]                                              # 같은 id의 다른 경로 항목은 합치지 않음
    assert "runtime_candidates_not_linked" not in p                                         # 루트가 맞는 항목이 정확히 하나라 후보 목록 불필요


def test_same_id_with_different_root_is_a_candidate_not_a_link(tmp_path):
    d = make_plugin(tmp_path, BASE_MANIFEST)
    f = tmp_path / "plugins.json"
    f.write_text(json.dumps({"plugins": [{"id": "voice-call", "rootDir": str(tmp_path / "other"), "enabled": True, "status": "loaded"}]}), encoding="utf-8")
    p = run([d], plugins_list=f)["plugins"][0]
    assert p["runtime_observation"] is None and p["runtime_candidates_not_linked"][0]["record_index"] == 0


def test_skills_list_json_links_by_file_path_only(tmp_path):
    sd = make_skill(tmp_path, "image-lab", SKILL_OK)
    other = make_skill(tmp_path, "other", SKILL_OK.replace("image-lab", "image-lab"))
    listing = {"skills": [{"name": "image-lab", "source": "openclaw-workspace", "filePath": str(sd / "SKILL.md"), "baseDir": str(sd), "bundled": False,
                           "disabled": False, "eligible": True, "modelVisible": True},
                          {"name": "ghost", "source": "openclaw-bundled", "filePath": "/nowhere/SKILL.md", "bundled": True}]}
    f = tmp_path / "skills.json"
    f.write_text(json.dumps(listing), encoding="utf-8")
    rep = run(skills_dirs=[sd, other], skills_list=f)
    linked = [s for s in rep["skills"] if s["runtime_observation"]]
    assert len(linked) == 1 and linked[0]["folder_name"] == "image-lab"           # 이름이 같은 다른 폴더는 연결하지 않음
    assert linked[0]["runtime_observation"]["observed"]["eligible"] is True and linked[0]["runtime_observation"]["observed"]["source"] == "openclaw-workspace"
    assert [r["observed"]["name"] for r in rep["runtime_only"]["skills"]] == ["ghost"]


def test_stored_output_with_wrong_shape_fails_without_pretending(tmp_path):
    f = tmp_path / "x.json"
    f.write_text('{"nope": 1}', encoding="utf-8")
    rep = run(plugins_list=f, skills_list=tmp_path / "missing.json")
    assert rep["stored_outputs"]["plugins_list"]["status"] == "failed" and rep["stored_outputs"]["skills_list"]["status"] == "failed"
    assert rep["collection"]["status"] == "failed" and rep["runtime_only"] == {"plugins": [], "skills": []}


def test_runtime_only_inventory_works_without_any_directory(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"plugins": [{"id": "a", "name": "A", "enabled": True, "status": "loaded", "origin": "bundled"}]}), encoding="utf-8")
    rep = run(plugins_list=f)
    assert rep["collection"]["status"] == "complete" and rep["collection"]["runtime_only_plugin_count"] == 1
    assert rep["runtime_only"]["plugins"][0]["source"] == "stored_plugins_list_json_only"


# ---- CLI ---------------------------------------------------------------------------------

def run_cli(*args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-m", "asset_scanner.plugin_skill_assets", *map(str, args)], cwd=SCANNER_ROOT, env=env,
                          capture_output=True, text=True, encoding="utf-8")


def test_cli_exit_codes_and_no_leaks(tmp_path):
    d = make_plugin(tmp_path, {**BASE_MANIFEST, "description": f"x {TOKEN}"}, files={"skills/lab/SKILL.md": SKILL_OK})
    sd = make_skill(tmp_path, "image-lab", SKILL_OK)
    out = tmp_path / "o.json"
    proc = run_cli("--plugin-dir", d, "--skills-dir", sd, "--output", out)
    assert proc.returncode == 0 and "읽기 전용" in proc.stdout
    saved = out.read_text(encoding="utf-8")
    assert "FAKEPLUGINTOKEN" not in proc.stdout + proc.stderr + saved and "FAKEBODYSECRET" not in saved
    assert json.loads(saved)["format"] == "agent-scope.scanner.openclaw-plugin-skill-assets"
    assert run_cli("--output", tmp_path / "x.json").returncode == 2                                     # 입력 없음
    assert run_cli("--plugin-dir", tmp_path / "missing", "--output", tmp_path / "f.json").returncode == 3
    part = run_cli("--plugin-dir", d, "--skills-dir", tmp_path / "missing", "--output", tmp_path / "p.json")
    assert part.returncode == 1
    cfg = tmp_path / "c.json5"
    cfg.write_text("{}", encoding="utf-8")
    assert run_cli("--config", cfg, "--output", cfg).returncode == 4 and cfg.read_text(encoding="utf-8") == "{}"
