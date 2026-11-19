"""D1 회귀 테스트: cp949 콘솔에서 요약 출력이 UnicodeEncodeError로 끝나지 않아야 한다.

실제 별도 프로세스로 CLI를 실행하고, 표준출력·오류출력을 바이트로 캡처해 cp949로 해석한다.
PYTHONUTF8은 설정하지 않는다 (사용자가 따로 설정하지 않는 상황 재현).
"""

import json
import os
import subprocess
import sys

import pytest

from conftest import SCANNER_ROOT


def run_cli_cp949(config, output):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env["PYTHONIOENCODING"] = "cp949"  # 콘솔 코드페이지가 cp949인 Windows 상황 재현
    return subprocess.run(
        [sys.executable, "-m", "asset_scanner", "--config", str(config), "--output", str(output)],
        cwd=SCANNER_ROOT, env=env, capture_output=True,
    )


def test_d1_registry_absent_reason_with_em_dash(write_config, tmp_path):
    cfg = write_config('{"agents": {}}')
    out = tmp_path / "r.json"
    proc = run_cli_cp949(cfg, out)
    assert proc.returncode == 0, proc.stderr.decode("cp949", "replace")
    assert b"Traceback" not in proc.stderr and proc.stderr == b""
    assert "registry_absent".encode() in proc.stdout
    assert json.loads(out.read_text(encoding="utf-8"))["collection"]["outcome"] == "registry_absent"


def test_d1_cp949_encodable_text_is_kept(write_config, tmp_path):
    cfg = write_config('{ mcp: { servers: { "파일서버": { command: "x" } } } }')
    out = tmp_path / "r.json"
    proc = run_cli_cp949(cfg, out)
    assert proc.returncode == 0, proc.stderr.decode("cp949", "replace")
    assert proc.stderr == b""
    assert 'mcp.servers["파일서버"]'.encode("cp949") in proc.stdout  # 표현 가능한 문자는 그대로
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["servers"][0]["registration_key"] == "파일서버"
    assert report["collection"]["status"] == "complete"


def test_d1_unencodable_server_name_is_shown_safely(write_config, tmp_path):
    # 이모지·유럽 문자 등 cp949로 표현할 수 없는 이름
    cfg = write_config('{ mcp: { servers: { "srv😀é—": { command: "x" } } } }')
    out = tmp_path / "r.json"
    proc = run_cli_cp949(cfg, out)
    assert proc.returncode == 0, proc.stderr.decode("cp949", "replace")
    assert proc.stderr == b""
    text = proc.stdout.decode("cp949")
    assert "srv" in text and "\\U0001f600" in text  # 안전하게 이스케이프 표시
    # 결과 JSON에는 원문 이름이 그대로 보존된다
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["servers"][0]["registration_key"] == "srv😀é—"


def test_d1_exit_code_rules_unchanged_under_cp949(write_config, tmp_path):
    partial = write_config('{ mcp: { servers: { a: { command: "${X}" } } } }', name="p.json5")
    failed = write_config("{ broken", name="f.json5")
    assert run_cli_cp949(partial, tmp_path / "p.json").returncode == 1
    assert run_cli_cp949(failed, tmp_path / "f.json").returncode == 3
    assert run_cli_cp949(tmp_path / "missing.json", tmp_path / "m.json").returncode == 3
