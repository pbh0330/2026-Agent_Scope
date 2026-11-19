"""Plugin의 출처·진입점·의존성·무결성 선언 필드 보완 테스트 (가상 자료).

근거: OpenClaw 2026.9.6 `docs/plugins/manifest.md`, `docs/plugins/manifest/package-json.md`.
서명·무결성 검증은 신뢰 기준(허용 레지스트리·키)이 합의되지 않아 구현하지 않으며, 선언 여부만 확인한다.
"""

import json

from test_plugin_skill_assets import make_plugin, run

MANIFEST = {"id": "demo-plugin", "name": "Demo", "configSchema": {"type": "object"},
            "activation": {"onStartup": True, "onCommands": ["x"]},
            "contracts": {"tools": ["demo_tool"], "speechProviders": ["sp"], "odd": {"a": 1}}}


def package(**extra):
    base = {"name": "@scope/demo", "version": "1.2.3", "dependencies": {"left-pad": "^1.3.0", "gitdep": "git+https://user:FAKEPW123@example.com/r.git"},
            "peerDependencies": {"openclaw": "2026.9.6"}, "optionalDependencies": {"fsevents": "2.3.3"},
            "openclaw": {"extensions": ["./index.js"], "runtimeExtensions": ["./dist/index.js"], "setupEntry": "./setup.js",
                         "install": {"npmSpec": "@scope/demo@1.2.3", "minHostVersion": ">=2026.9.6", "expectedIntegrity": "sha512-FAKEINTEGRITYVALUE",
                                     "requiredPlatformPackages": ["@scope/demo-linux-x64"]},
                         "compat": {"pluginApi": ">=2026.9.6"}}}
    base.update(extra)
    return base


def plugin_of(tmp_path, pkg, manifest=MANIFEST):
    d = make_plugin(tmp_path, manifest, pkg)
    return run(plugin_dirs=[d])["plugins"][0]


def test_entry_points_dependencies_and_install_hints_are_recorded_as_declared_values(tmp_path):
    p = plugin_of(tmp_path, package())
    pkg = p["package"]
    assert pkg["entry_points"]["extensions"] == ["./index.js"] and pkg["entry_points"]["runtimeExtensions"] == ["./dist/index.js"]
    assert pkg["entry_points"]["setupEntry"] == "./setup.js" and pkg["entry_points"]["executed_or_loaded_by_scanner"] is False
    assert pkg["entry_points"]["outside_package_dir_declared"] is False
    assert pkg["required_platform_packages"] == ["@scope/demo-linux-x64"]
    deps = pkg["dependencies"]
    assert deps["dependencies"]["count"] == 2 and {"name": "left-pad", "spec": "^1.3.0"} in deps["dependencies"]["entries"]
    assert deps["peerDependencies"]["entries"] == [{"name": "openclaw", "spec": "2026.9.6"}] and deps["optionalDependencies"]["count"] == 1
    assert p["supply_source"]["install_hints"]["npmSpec"] == "@scope/demo@1.2.3"


def test_manifest_activation_and_contract_keys_are_recorded_without_interpretation(tmp_path):
    d = plugin_of(tmp_path, package())["manifest"]["declared"]
    assert d["activation_keys"] == ["onStartup", "onCommands"]
    assert d["contracts"]["tools"] == ["demo_tool"] and d["contracts"]["odd"] == {"type": "object"}


def test_integrity_is_only_declared_never_verified_and_values_are_not_stored(tmp_path):
    p = plugin_of(tmp_path, package())
    assert p["supply_source"]["integrity"]["expected_integrity_declared"] is True
    assert p["supply_source"]["integrity"]["verification"] == "not_performed"
    out = json.dumps(p)
    assert "FAKEINTEGRITYVALUE" not in out and "FAKEPW123" not in out          # 무결성 값·URL 인증정보는 남지 않는다
    none = plugin_of(tmp_path / "n", package(openclaw={"extensions": ["./i.js"]}))
    assert none["supply_source"]["integrity"]["expected_integrity_declared"] is False


def test_entry_points_outside_the_package_are_flagged_and_not_read(tmp_path):
    p = plugin_of(tmp_path, package(openclaw={"extensions": ["../evil.js", "/abs/x.js", "C:\\x.js"]}))
    assert p["package"]["entry_points"]["outside_package_dir_declared"] is True
    assert any(i["code"] == "entry_point_outside_package" for i in p["issues"])


def test_packages_without_these_fields_do_not_gain_invented_values(tmp_path):
    p = plugin_of(tmp_path, {"name": "x", "version": "1"})
    assert "entry_points" not in p["package"] and "dependencies" not in p["package"] and "required_platform_packages" not in p["package"]


def test_declared_source_kinds_are_derived_only_from_documented_install_hint_keys(tmp_path):
    p = plugin_of(tmp_path, package(openclaw={"install": {"npmSpec": "@scope/demo@1.2.3", "clawhubSpec": "clawhub:demo", "localPath": "./local", "defaultChoice": "npm"}}))
    assert p["supply_source"]["declared_source_kinds"] == ["npm", "clawhub", "local_path"]
    none = plugin_of(tmp_path / "n", package(openclaw={"extensions": ["./i.js"]}))
    assert none["supply_source"]["declared_source_kinds"] == []                     # 힌트가 없으면 출처를 추정하지 않는다
    assert "provider" not in none["supply_source"]                                   # OpenClaw 문서에 공급자 필드가 없어 만들지 않는다



def test_package_json_provider_hints_and_git_head_are_recorded_as_declared_values(tmp_path):
    # package.json의 표준 필드(author·repository·homepage·gitHead)는 OpenClaw 문서의 필드가 아니라 npm 패키지 메타데이터다.
    # "공급자"의 정의는 팀 합의 사항이므로 provider 필드로 확정하지 않고 선언된 힌트로만 기록한다. 이메일·URL 인증정보는 저장하지 않는다.
    head = "a" * 40
    pkg = package(author="Jane Doe <jane@example.com> (https://jane.example)", repository={"type": "git", "url": "git+https://u:FAKEPWREPO@example.com/o/r.git"},
                  homepage="https://example.com/p", gitHead=head)
    p = plugin_of(tmp_path, pkg)
    h = p["package"]["declared_provider_hints"]
    assert h["author_name"] == "Jane Doe" and h["homepage"] == "https://example.com/p" and h["repository"].startswith("git+https://")
    assert p["package"]["git_head"] == {"value": head, "format": "sha1_hex40", "verified_by_scanner": False}
    text = json.dumps(p)
    assert "jane@example.com" not in text and "FAKEPWREPO" not in text
    assert "provider" not in p["supply_source"]                                       # 정의가 합의되기 전에는 provider 필드를 만들지 않는다


def test_provider_hints_and_git_head_are_not_invented_and_odd_values_are_flagged(tmp_path):
    none = plugin_of(tmp_path / "n", package())
    assert "declared_provider_hints" not in none["package"] and "git_head" not in none["package"]
    odd = plugin_of(tmp_path / "o", package(author={"name": "N"}, gitHead="not-a-sha", repository=5))
    assert odd["package"]["declared_provider_hints"] == {"author_name": "N"} and odd["package"]["git_head"]["format"] == "unrecognized"
