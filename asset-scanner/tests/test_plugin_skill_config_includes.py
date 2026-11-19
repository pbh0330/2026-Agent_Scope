"""`plugin_skill_assets --config`의 `$include` 연동 테스트 (가상 설정·플러그인).

기대값의 근거: 공식 구현(`includes.ts`·`deep-merge.ts`, 고정 커밋 eb377ac)의 병합 규칙 — 배열은 연결, 객체는 재귀 병합, 형제 키가 마지막.
옵션을 생략한 기존 동작은 바뀌지 않는다.
"""

import json
import os
import subprocess
import sys

from asset_scanner.plugin_skill_assets import build_report, collect_assets
from conftest import SCANNER_ROOT
from test_plugin_skill_assets import make_plugin, make_skill

PLUGIN = {"id": "my-plugin", "name": "My", "configSchema": {"type": "object"}}


def w(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
    return path


def run(tmp_path, cfg, resolve, with_skill=False):
    d = make_plugin(tmp_path, PLUGIN, None, name="plug")
    skills = [make_skill(tmp_path / "skills", "my-skill", "---\nname: my-skill\ndescription: d\n---\nbody\n")] if with_skill else []
    return build_report(collect_assets([d], skills, cfg, None, None, resolve))


def layout(tmp_path):
    main = w(tmp_path / "cfg" / "openclaw.json", {
        "plugins": {"$include": ["./plugins-a.json5", "./plugins-b.json5"], "deny": ["blocked"]},
        "skills": {"$include": "./skills.json5", "allowBundled": ["from-main"]},
    })
    w(tmp_path / "cfg" / "plugins-a.json5", {"enabled": True, "allow": ["my-plugin", "other"], "entries": {"my-plugin": {"enabled": True, "extra": 1}}})
    w(tmp_path / "cfg" / "plugins-b.json5", {"allow": ["my-plugin"], "deny": ["from-b"]})
    w(tmp_path / "cfg" / "skills.json5", {"allowBundled": ["my-skill", "bundled-2"], "entries": {"my-skill": {"enabled": False, "apiKey": "FAKESKILLSECRET789"}}})
    return main


def test_plugin_declarations_from_included_files_carry_file_and_key_path(tmp_path):
    rep = run(tmp_path, layout(tmp_path), True)
    d = rep["plugins"][0]["declared_activation"]
    assert d["plugins_enabled_globally"] is True and d["entry_declared"] is True and d["entry_enabled"] is True
    assert d["listed_in_allow"] is True and d["listed_in_deny"] is False
    o = d["origins"]
    assert o["plugins_enabled"] == {"file": "plugins-a.json5", "include_chain": ["plugins-a.json5"], "config_path": "plugins.enabled"}
    assert o["entry"]["config_path"] == "plugins.entries.my-plugin" and o["entry"]["file"] == "plugins-a.json5"
    assert o["entry_enabled"]["config_path"] == "plugins.entries.my-plugin.enabled"
    # 공식 병합: allow 배열은 a→b 순서로 연결되어 my-plugin이 두 번 나온다. 원소별 출처가 각각 기록된다.
    assert [(x["file"], x["config_path"]) for x in o["allow"]] == [("plugins-a.json5", "plugins.allow[0]"), ("plugins-b.json5", "plugins.allow[2]")]
    assert rep["activation_settings"]["plugins"]["allow"] == ["my-plugin", "other", "my-plugin"]


def test_deny_array_concatenates_included_values_then_sibling_values_with_each_origin(tmp_path):
    rep = run(tmp_path, layout(tmp_path), True)
    p = rep["activation_settings"]["plugins"]
    assert p["deny"] == ["from-b", "blocked"]                                                  # include(b) 뒤에 형제 키
    assert [(o["file"], o["config_path"]) for o in p["deny_origins"]] == [("plugins-b.json5", "plugins.deny[0]"), ("(top-level config)", "plugins.deny[1]")]


def test_skill_declarations_from_included_files(tmp_path):
    rep = run(tmp_path, layout(tmp_path), True, with_skill=True)
    sk = [s for s in rep["skills"] if s["identity"]["name"]["original_value"] == "my-skill"][0]["declared_activation"]
    assert sk["entry_declared"] is True and sk["entry_enabled"] is False and sk["listed_in_allowBundled"] is True
    assert sk["origins"]["entry"]["file"] == "skills.json5" and sk["origins"]["entry"]["config_path"] == "skills.entries.my-skill"
    assert sk["origins"]["allowBundled"] == [{"file": "skills.json5", "include_chain": ["skills.json5"], "config_path": "skills.allowBundled[0]"}]
    s = rep["activation_settings"]["skills"]
    assert s["allowBundled"] == ["my-skill", "bundled-2", "from-main"] and s["allowBundled_origins"][2]["file"] == "(top-level config)"


def test_secrets_are_still_withheld_and_physical_paths_are_not_recorded(tmp_path):
    rep = run(tmp_path, layout(tmp_path), True, with_skill=True)
    text = json.dumps(rep, ensure_ascii=False)
    assert "FAKESKILLSECRET789" not in text
    assert rep["activation_settings"]["skills"]["entries"]["my-skill"]["apiKey"] == {"value_kind": "literal_withheld"}
    assert str(tmp_path / "cfg") not in json.dumps(rep["activation_settings"]["includes"])
    assert rep["activation_settings"]["includes"]["files_read"] == 3 and rep["activation_settings"]["status"] == "complete"


def test_without_the_option_nothing_changes_and_no_origin_fields_appear(tmp_path):
    rep = run(tmp_path, layout(tmp_path), False)
    d = rep["plugins"][0]["declared_activation"]
    assert d["entry_declared"] is False and "origins" not in d                               # include를 읽지 않으므로 선언을 찾지 못함
    assert "includes" not in rep["activation_settings"]


def test_include_failures_make_the_settings_partial_with_the_reason(tmp_path):
    main = w(tmp_path / "cfg" / "openclaw.json", {"plugins": {"$include": ["./ok.json5", "./missing.json5", "../outside.json5"]}})
    w(tmp_path / "cfg" / "ok.json5", {"allow": ["my-plugin"]})
    w(tmp_path / "outside.json5", {"deny": ["my-plugin"]})
    rep = run(tmp_path, main, True)
    st = rep["activation_settings"]
    assert st["status"] == "partial"
    assert {"include_file_not_found", "include_path_outside_root"} <= {i["code"] for i in st["issues"]}
    assert "outside" not in json.dumps(st["plugins"])                                          # 경계 밖 파일은 읽지 않았다
    assert rep["plugins"][0]["declared_activation"]["listed_in_allow"] is True               # 읽은 부분은 보존


def test_duplicate_keys_inside_an_included_file_are_still_reported(tmp_path):
    main = w(tmp_path / "cfg" / "openclaw.json", {"plugins": {"$include": "./p.json5"}})
    (tmp_path / "cfg" / "p.json5").write_text('{"enabled": true, "enabled": false}', encoding="utf-8")
    st = run(tmp_path, main, True)["activation_settings"]
    assert any(i["code"] == "duplicate_key" for i in st["issues"]) and st["status"] == "partial"


def test_cli_requires_config_and_records_the_option(tmp_path):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    d = make_plugin(tmp_path, PLUGIN, None, name="plug")
    bad = subprocess.run([sys.executable, "-m", "asset_scanner.plugin_skill_assets", "--plugin-dir", str(d), "--resolve-includes", "--output", str(tmp_path / "o.json")],
                         cwd=SCANNER_ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    assert bad.returncode == 2
    cfg = layout(tmp_path)
    ok = subprocess.run([sys.executable, "-m", "asset_scanner.plugin_skill_assets", "--plugin-dir", str(d), "--config", str(cfg), "--resolve-includes", "--output", str(tmp_path / "o2.json")],
                        cwd=SCANNER_ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    assert ok.returncode == 0, ok.stderr
    rep = json.loads((tmp_path / "o2.json").read_text(encoding="utf-8"))
    assert rep["plugins"][0]["declared_activation"]["origins"]["entry"]["file"] == "plugins-a.json5"
