"""원본 보존과 '조회·실행 없음' 검증."""

import hashlib
import json
import os
import shutil
import socket
import subprocess

import pytest

from asset_scanner import cli
from conftest import EXAMPLES, run_cli


def _fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest(), os.stat(path).st_mtime_ns


def test_original_config_is_not_modified(tmp_path):
    for name in ("two-servers.json5", "fake-secrets.json5", "include-and-refs.json5",
                 "review-r1-secrets.json5"):
        cfg = tmp_path / name
        shutil.copy2(EXAMPLES / name, cfg)
        before = _fingerprint(cfg)
        run_cli(cfg, tmp_path / f"{name}.out.json")
        assert _fingerprint(cfg) == before, name


def test_output_path_equal_to_config_is_refused(tmp_path, capsys):
    cfg = tmp_path / "openclaw.json5"
    shutil.copy2(EXAMPLES / "two-servers.json5", cfg)
    before = _fingerprint(cfg)
    assert cli.main(["--config", str(cfg), "--output", str(cfg)]) == cli.EXIT_OUTPUT_ERROR
    assert _fingerprint(cfg) == before


def test_no_process_execution_or_network_access(tmp_path, monkeypatch, capsys):
    """수집 중 프로세스 실행·네트워크 연결이 시도되면 즉시 실패하도록 막고 실행한다."""

    def forbidden(*args, **kwargs):
        raise AssertionError("수집 중 실행/접속이 시도되었습니다")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)

    for name in ("two-servers.json5", "fake-secrets.json5"):
        out = tmp_path / f"{name}.json"
        code = cli.main(["--config", str(EXAMPLES / name), "--output", str(out)])
        assert code in (0, 1)
        report = json.loads(out.read_text(encoding="utf-8"))
        # 확인하지 않은 항목은 결과에 확인된 것처럼 들어가지 않는다
        for server in report["servers"]:
            for key in ("tools", "capabilities", "protocol_version", "connected", "callable", "exposed"):
                assert key not in server
        assert "tools" in report["scope"]["not_verified"]


@pytest.mark.parametrize("name, expected", [
    ("two-servers.json5", 0),
    ("include-and-refs.json5", 1),
])
def test_cli_exit_codes(tmp_path, name, expected):
    proc = run_cli(EXAMPLES / name, tmp_path / "o.json")
    assert proc.returncode == expected, proc.stderr


def test_cli_missing_file_still_writes_failure_report(tmp_path):
    out = tmp_path / "o.json"
    proc = run_cli(tmp_path / "missing.json5", out)
    assert proc.returncode == 3
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["collection"]["outcome"] == "file_not_found"
    assert report["servers"] == []
