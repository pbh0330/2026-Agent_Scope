"""자기 테스트 프로세스·가상 proc·진입점 헤더만 사용한다. 실제 OpenClaw 실행 없음."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from asset_scanner.process_identity import collect_process_identities, inspect_entry_file
from conftest import SCANNER_ROOT


def fake_proc(tmp_path, pid=31):
    root = tmp_path / "proc"
    selected = root / str(pid)
    selected.mkdir(parents=True)
    (selected / "stat").write_text(f"{pid} (FAKE PRIVATE (name)) S 2 " + "0 " * 17 + "1234 0 0")
    (selected / "status").write_text('Name:\tFAKE_PRIVATE_NAME\nUid:\t1000 1001 1002 1003\nGid:\t2000 2001 2002 2003\nGroups:\t2 4\nNoNewPrivs:\t1\nSeccomp:\t2\n')
    (selected / "environ").write_text("FAKE_CREDENTIAL_MUST_NOT_BE_READ")
    (selected / "cmdline").write_text("FAKE_COMMAND_MUST_NOT_BE_READ")
    return root, selected


def test_uid_gid_positions_are_observed_and_private_fields_are_never_exported(tmp_path):
    root, selected = fake_proc(tmp_path)
    before = {p: p.read_bytes() for p in selected.iterdir()}
    report = collect_process_identities([31], proc_root=root)
    record = report["processes"][0]
    assert record["status"] == "complete" and record["uid"] == {"real": 1000, "effective": 1001, "saved": 1002, "filesystem": 1003}
    assert record["gid"]["effective"] == 2001 and record["parent_pid"] == 2 and record["start_ticks"] == 1234
    assert record["NoNewPrivs"] == 1 and record["Seccomp"] == 2
    assert "FAKE" not in json.dumps(report) and before == {p: p.read_bytes() for p in selected.iterdir()}


@pytest.mark.skipif(not Path("/proc/self/status").exists(), reason="Linux /proc가 없는 호스트")
def test_actual_scanner_process_matches_os_uid_gid_without_openclaw():
    report = collect_process_identities([os.getpid()])
    assert report["collection"]["status"] == "complete"
    assert report["processes"][0]["uid"]["effective"] == os.geteuid()
    assert report["processes"][0]["gid"]["effective"] == os.getegid()


@pytest.mark.parametrize("pid", [0, -1, True, "../self", "31"])
def test_bad_pid_never_becomes_a_path(tmp_path, pid):
    report = collect_process_identities([pid], proc_root=tmp_path)
    assert report["collection"]["status"] == "failed" and "uid" not in report["processes"][0]


def test_missing_uid_and_duplicate_uid_are_not_success(tmp_path):
    root, selected = fake_proc(tmp_path)
    for text in ("Uid: 1 2 3\nGid: 1 2 3 4", "Uid: 1 2 3 4\nUid: 1 2 3 4\nGid: 1 2 3 4"):
        (selected / "status").write_text(text)
        report = collect_process_identities([31], proc_root=root)
        assert report["processes"][0]["status"] == "failed" and "uid" not in report["processes"][0]


def test_pid_reuse_during_read_discards_ambiguous_observation(tmp_path, monkeypatch):
    from asset_scanner import process_identity as mod
    root, _ = fake_proc(tmp_path)
    responses = iter([(2, 100), (2, 200)])
    monkeypatch.setattr(mod, "_stat_identity", lambda *a: next(responses))
    record = mod.collect_process_identities([31], proc_root=root)["processes"][0]
    assert record["issue"] == "process_changed_during_read" and "uid" not in record


@pytest.mark.parametrize("prefix,name,kind,basis", [
    (b"\x7fELF" + b"x" * 20, "program", "binary", "elf_magic"),
    (b"#!/usr/bin/env python\nFAKE_BODY", "task", "script", "shebang_present"),
    (b"FAKE_SOURCE_BODY", "entry.ts", "script_hint", "extension_only_not_runtime_verified"),
    (b"data", "unknown", "unknown", "no_recognized_header"),
])
def test_file_facts_never_store_body_hash_or_runtime_claims(tmp_path, prefix, name, kind, basis):
    p = tmp_path / name
    p.write_bytes(prefix)
    before = (p.read_bytes(), p.stat().st_mtime_ns)
    record = inspect_entry_file(p)
    assert record["file_kind"] == kind and record["basis"] == basis and record["status"] == "complete"
    assert record["executed_or_imported"] is False and record["mtime_is_last_updated"] is False
    assert "FAKE_BODY" not in json.dumps(record) and "FAKE_SOURCE_BODY" not in json.dumps(record)
    assert before == (p.read_bytes(), p.stat().st_mtime_ns)


def test_pe_requires_actual_signature_within_prefix_not_only_mz(tmp_path):
    p = tmp_path / "binary.exe"
    body = bytearray(256)
    body[:2] = b"MZ"
    body[60:64] = (128).to_bytes(4, "little")
    body[128:132] = b"PE\0\0"
    p.write_bytes(body)
    assert inspect_entry_file(p)["file_kind"] == "binary"
    body[128:132] = b"nope"
    p.write_bytes(body)
    assert inspect_entry_file(p)["file_kind"] == "unknown"


def test_target_limits_and_cli_overwrite_guard(tmp_path, monkeypatch):
    from asset_scanner import process_identity as mod
    p = tmp_path / "task.py"
    p.write_text("FAKE_PRIVATE_BODY")
    monkeypatch.setattr(mod, "MAX_TARGETS", 1)
    assert mod.collect_process_identities(entry_files=[p, p])["collection"]["status"] == "partial"
    cmd = [sys.executable, "-m", "asset_scanner.process_identity", "--entry-file", str(p), "--output"]
    assert subprocess.run(cmd + [str(p)], cwd=SCANNER_ROOT, capture_output=True).returncode == 2
    assert p.read_text() == "FAKE_PRIVATE_BODY"
    assert subprocess.run(cmd + [str(tmp_path / 'out.json')], cwd=SCANNER_ROOT, capture_output=True).returncode == 0
