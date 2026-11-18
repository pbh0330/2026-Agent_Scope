"""명시한 Linux PID의 UID/GID 관측과 선택 진입점 파일의 형식 근거를 읽는다.

환경·명령행·메모리·파일 본문은 저장하지 않고 프로세스를 실행·중지하지 않는다.
PID가 OpenClaw 소유라는 판정·영속 식별·최종 권한 판정은 하지 않는다.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import stat
import sys

from .cli import _make_console_output_safe, _same_file
from .output import OutputError, normalize_for_output, write_json_atomic
from .plugin_skill_assets import _safe_path
from .source_io import SourceError, read_regular

MAX_TARGETS = 64


def inspect_entry_file(path):
    path = Path(path)
    result = {"path": _safe_path(path)[0], "status": "failed", "executed_or_imported": False,
              "content_stored": False, "integrity_verified": False}
    try:
        before = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink > 1:
            raise SourceError("entry_not_regular_or_linked")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise SourceError("entry_changed_during_read")
            head = stream.read(4096)
        after = path.stat(follow_symlinks=False)
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise SourceError("entry_changed_during_read")
        kind, basis = "unknown", "no_recognized_header"
        if head.startswith(b"\x7fELF"):
            kind, basis = "binary", "elf_magic"
        elif head.startswith(b"MZ") and len(head) >= 64:
            offset = int.from_bytes(head[60:64], "little")
            if 0 <= offset <= len(head) - 4 and head[offset:offset + 4] == b"PE\0\0":
                kind, basis = "binary", "pe_magic_within_prefix"
        elif head[:4] in (b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe"):
            kind, basis = "binary", "mach_o_magic"
        elif head.startswith(b"#!"):
            kind, basis = "script", "shebang_present"
        elif path.suffix.lower() in (".js", ".mjs", ".cjs", ".ts", ".py", ".sh", ".ps1", ".rb"):
            kind, basis = "script_hint", "extension_only_not_runtime_verified"
        result.update(status="complete", file_kind=kind, basis=basis, file_size_bytes=before.st_size,
                      filesystem_mtime_ns=before.st_mtime_ns, mtime_is_last_updated=False)
    except (OSError, SourceError) as exc:
        result["issue"] = exc.code if isinstance(exc, SourceError) else "entry_unreadable"
    return result


def _stat_identity(path, expected_pid):
    text = read_regular(path, 8192).decode("utf-8")
    close = text.rfind(")")
    tail = text[close + 1:].split()
    if close < 0 or not text.startswith(f"{expected_pid} (") or len(tail) <= 19:
        raise SourceError("process_stat_invalid")
    parent, started = int(tail[1]), int(tail[19])
    if parent < 0 or started < 0:
        raise SourceError("process_stat_invalid")
    return parent, started


def collect_process_identities(pids=(), entry_files=(), proc_root=Path("/proc")):
    result = {"format": "agent-scope.scanner.process-identity", "format_version": "0.1.0-draft",
              "observed_at": datetime.now(timezone.utc).isoformat(), "processes": [], "files": [], "issues": [],
              "scope": {"method": "operator_selected_linux_pids_and_entry_files", "atomic_snapshot": False,
                        "not_collected": ["environment", "command_line", "memory", "file_contents", "windows_or_macos_live_processes"],
                        "not_inferred": ["process_belongs_to_openclaw", "persistent_identity", "effective_permissions", "last_updated_from_mtime"]},
              "basis": "https://github.com/torvalds/linux/blob/v6.12/Documentation/filesystems/proc.rst"}
    if len(pids) > MAX_TARGETS or len(entry_files) > MAX_TARGETS:
        result["issues"].append({"code": "target_limit_exceeded"})
    for pid in list(pids)[:MAX_TARGETS]:
        record = {"pid": pid if type(pid) is int else None, "status": "failed", "source_kind": "linux_proc_observation"}
        result["processes"].append(record)
        try:
            if type(pid) is not int or pid <= 0:
                raise SourceError("pid_invalid")
            directory = Path(proc_root) / str(pid)
            ppid, before_start = _stat_identity(directory / "stat", pid)
            text = read_regular(directory / "status", 65536).decode("utf-8")
            fields = {}
            for line in text.splitlines():
                key, separator, value = line.partition(":")
                if not separator or key not in ("Uid", "Gid", "Groups", "NoNewPrivs", "Seccomp"):
                    continue
                if key in fields:
                    raise SourceError("process_status_duplicate_field")
                values = value.split()
                if len(values) > 1024 or not all(x.isdecimal() for x in values):
                    raise SourceError("process_status_invalid")
                fields[key] = [int(x) for x in values]
            if len(fields.get("Uid", [])) != 4 or len(fields.get("Gid", [])) != 4:
                raise SourceError("process_uid_gid_unavailable")
            after_parent, after_start = _stat_identity(directory / "stat", pid)
            if before_start != after_start or ppid != after_parent:
                raise SourceError("process_changed_during_read")
            record.update(status="complete", parent_pid=ppid, start_ticks=before_start,
                          uid=dict(zip(("real", "effective", "saved", "filesystem"), fields["Uid"])),
                          gid=dict(zip(("real", "effective", "saved", "filesystem"), fields["Gid"])),
                          supplementary_groups=fields.get("Groups", []))
            for key in ("NoNewPrivs", "Seccomp"):
                if key in fields and len(fields[key]) == 1:
                    record[key] = fields[key][0]
        except (SourceError, OSError, UnicodeError, ValueError) as exc:
            record["issue"] = exc.code if isinstance(exc, SourceError) else "process_unreadable_or_invalid"
    result["files"] = [inspect_entry_file(p) for p in list(entry_files)[:MAX_TARGETS]]
    statuses = [x["status"] for x in result["processes"] + result["files"]]
    status = "complete" if statuses and all(x == "complete" for x in statuses) else "failed" if not statuses or all(x == "failed" for x in statuses) else "partial"
    if result["issues"] and status == "complete":
        status = "partial"
    result["collection"] = {"status": status, "process_count": len(result["processes"]), "entry_file_count": len(result["files"])}
    return result


def main(argv=None):
    _make_console_output_safe()
    parser = argparse.ArgumentParser(description="선택한 Linux PID의 UID/GID와 진입점 파일 형식 근거를 읽습니다. 실행·권한 변경 없음.")
    parser.add_argument("--pid", action="append", default=[], type=int)
    parser.add_argument("--entry-file", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if not args.pid and not args.entry_file:
        parser.error("--pid 또는 --entry-file을 지정하세요.")
    if any(_same_file(p, args.output) for p in args.entry_file) or (Path("/proc") in args.output.absolute().parents):
        parser.error("출력은 입력 파일·/proc 밖에 지정하세요.")
    report, _ = normalize_for_output(collect_process_identities(args.pid, args.entry_file))
    try:
        write_json_atomic(args.output, report)
    except OutputError:
        return 4
    print(f"프로세스·진입점 관측: {report['collection']['status']}")
    return {"complete": 0, "partial": 1, "failed": 3}[report["collection"]["status"]]


if __name__ == "__main__":
    sys.exit(main())
