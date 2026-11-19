"""OVA 보고서에서 확인한 배포용 dist/extensions 경로의 탐색 회귀.

실제 VM 파일을 복제하지 않고, 두 설치 레이아웃과 경계 조건을 가상 파일로 재현한다.
"""
import json
import subprocess
import sys

import pytest

from asset_scanner import installation_inventory as inv
from conftest import SCANNER_ROOT


def plugin(root, pid="bundled-demo"):
    root.mkdir(parents=True)
    manifest = root / "openclaw.plugin.json"
    manifest.write_text(json.dumps({"id": pid, "configSchema": {"type": "object"}}))
    (root / "package.json").write_text(json.dumps({"name": pid, "version": "1.0.0"}))
    return manifest


@pytest.mark.parametrize("layout", ["extensions", "dist/extensions"])
def test_selected_installation_finds_source_or_built_layout_without_modifying_inputs(tmp_path, layout):
    installed = tmp_path / "openclaw"
    manifest = plugin(installed / layout / "demo")
    before = manifest.read_bytes()
    report = inv.collect_installations(installation_roots=[installed])
    assert report["collection"]["status"] == "complete"
    assert report["collection"]["plugin_count"] == 1
    assert report["assets"]["plugins"][0]["identity"]["id"]["original_value"] == "bundled-demo"
    assert report["assets"]["plugins"][0]["root_dir"]["value"] == str(manifest.parent)
    assert manifest.read_bytes() == before


def test_both_layouts_keep_same_id_in_different_installations_separate(tmp_path):
    installed = tmp_path / "openclaw"
    paths = {plugin(installed / layout / "demo").parent for layout in ("extensions", "dist/extensions")}
    report = inv.collect_installations(installation_roots=[installed])
    assert report["collection"]["status"] == "complete"
    assert report["collection"]["plugin_count"] == 2
    assert {p["root_dir"]["value"] for p in report["assets"]["plugins"]} == {str(p) for p in paths}


def test_built_layout_symlink_cannot_authorize_an_external_plugin(tmp_path):
    installed = tmp_path / "openclaw"
    outside = plugin(tmp_path / "outside" / "demo").parent.parent
    (installed / "dist").mkdir(parents=True)
    try:
        (installed / "dist" / "extensions").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("디렉터리 심볼릭 링크 생성 권한 없음")
    report = inv.collect_installations(installation_roots=[installed])
    assert report["collection"]["plugin_count"] == 0
    assert report["collection"]["status"] == "failed"
    assert any(i["code"] == "discovery_path_outside_selected_roots_or_linked" for i in report["issues"])


def test_cli_discovers_built_layout_and_preserves_output_boundary(tmp_path):
    installed = tmp_path / "openclaw"
    manifest = plugin(installed / "dist" / "extensions" / "demo")
    before = manifest.read_bytes()
    argv = [sys.executable, "-m", "asset_scanner.installation_inventory", "--installation-root", str(installed), "--output"]
    output = tmp_path / "result.json"
    result = subprocess.run(argv + [str(output)], cwd=SCANNER_ROOT, capture_output=True)
    assert result.returncode == 0
    assert json.loads(output.read_text())["collection"]["plugin_count"] == 1
    refused = subprocess.run(argv + [str(manifest)], cwd=SCANNER_ROOT, capture_output=True)
    assert refused.returncode == 2
    assert manifest.read_bytes() == before


def test_state_root_does_not_opt_into_installation_layout(tmp_path):
    state = tmp_path / "state"
    plugin(state / "dist" / "extensions" / "demo")
    report = inv.collect_installations(state_dirs=[state])
    assert report["collection"]["status"] == "complete"
    assert report["collection"]["plugin_count"] == 0
