"""명시한 수집 원천의 제한된 읽기. DB는 사본에서만 열고 원본·WAL·SHM을 쓰지 않는다."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import time

MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_DB_BYTES = 64 * 1024 * 1024
MAX_ROWS = 1000


class SourceError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _stamp(path):
    s = path.stat(follow_symlinks=False)
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns


def read_regular(path: Path, limit=MAX_JSON_BYTES) -> bytes:
    """최종 파일의 링크·비일반 파일·크기·읽기 중 변경을 거부한다. 예외에 원문을 넣지 않는다."""
    path = Path(path)
    try:
        st = path.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_nlink > 1:
            raise SourceError("source_not_regular_or_linked")
        if st.st_size > limit:
            raise SourceError("source_too_large")
        before = _stamp(path)
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
        with os.fdopen(fd, "rb") as stream:
            current = os.fstat(stream.fileno())
            if (current.st_dev, current.st_ino) != before[:2] or not stat.S_ISREG(current.st_mode):
                raise SourceError("source_changed_during_read")
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise SourceError("source_too_large")
        if before != _stamp(path):
            raise SourceError("source_changed_during_read")
        return data
    except SourceError:
        raise
    except OSError:
        raise SourceError("source_unreadable") from None


class SourceMap(dict):
    def __init__(self, pairs):
        super().__init__()
        self.duplicates = []
        for key, value in pairs:
            if key in self:
                self.duplicates.append(key)
            self[key] = value


def parse_source_json(data: bytes | str):
    try:
        def nonfinite(_):
            raise ValueError()
        result = json.loads(data, object_pairs_hook=SourceMap, parse_constant=nonfinite)
        stack = [(result, 0)]
        nodes = 0
        while stack:
            value, depth = stack.pop()
            nodes += 1
            if depth > 40 or nodes > 50000:
                raise SourceError("source_json_limit")
            if isinstance(value, dict):
                stack.extend((x, depth + 1) for x in value.values())
            elif isinstance(value, list):
                stack.extend((x, depth + 1) for x in value)
        return result
    except SourceError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise SourceError("source_json_invalid") from None


def read_source_json(path):
    return parse_source_json(read_regular(Path(path)))


def duplicate_count(value):
    count = len(getattr(value, "duplicates", []))
    if isinstance(value, dict):
        count += sum(duplicate_count(v) for v in value.values())
    elif isinstance(value, list):
        count += sum(duplicate_count(v) for v in value)
    return count


def read_state_rows(path: Path, kind: str):
    """선택한 고정 원천 테이블만 조회한다. JSON은 아직 비밀을 포함할 수 있으므로 호출자가 허용 필드만 고른다.

    공식 eb377ac: installed-plugin-index-row.ts, mcp-oauth-store.kernel.ts.
    DB·WAL을 임시 사본으로 읽으며 원본 잠금·마이그레이션·복구를 실행하지 않는다.
    """
    contracts = {
        "plugin_index": ("config_machine_state", {"state_key", "value_json"},
                         "SELECT substr(value_json,1,?) FROM config_machine_state WHERE state_key=? LIMIT 2",
                         (MAX_JSON_BYTES + 1, "plugins.installedIndex")),
        "mcp_oauth": ("mcp_oauth_stores", {"store_key", "format_version", "store_json"},
                      "SELECT store_key,format_version,substr(store_json,1,?) FROM mcp_oauth_stores LIMIT ?",
                      (MAX_JSON_BYTES + 1, MAX_ROWS + 1)),
        "model_accounts": ("secret_store_entries", {"scope_kind", "scope_id", "name", "kind", "allowed_hosts", "deleted_at_ms", "value"},
                           "SELECT scope_id,name,kind,allowed_hosts,substr(value,1,?) FROM secret_store_entries WHERE scope_kind=? AND substr(name,1,14)=? AND deleted_at_ms IS NULL LIMIT ?",
                           (MAX_JSON_BYTES + 1, "identity", "model-account:", MAX_ROWS + 1)),
    }
    if kind not in contracts:
        raise SourceError("state_source_kind_unsupported")
    path = Path(path)
    wal = Path(str(path) + "-wal")
    try:
        before = {p: _stamp(p) for p in (path, wal) if p.exists() or p.is_symlink()}
        main_data = read_regular(path, MAX_DB_BYTES)
        wal_data = read_regular(wal, MAX_DB_BYTES) if wal in before else None
        if any(_stamp(p) != stamp for p, stamp in before.items()) or (wal not in before and wal.exists()):
            raise SourceError("source_changed_during_snapshot")
    except OSError:
        raise SourceError("source_unreadable") from None
    table, columns, query, params = contracts[kind]
    try:
        with tempfile.TemporaryDirectory(prefix="scanner-state-") as folder:
            target = Path(folder) / "snapshot.sqlite"
            target.write_bytes(main_data)
            if wal_data is not None:
                Path(str(target) + "-wal").write_bytes(wal_data)
            conn = sqlite3.connect(target.as_uri() + "?mode=ro", uri=True, timeout=0.2)
            try:
                conn.execute("PRAGMA query_only=ON")
                conn.execute("PRAGMA trusted_schema=OFF")
                deadline = time.monotonic() + 2
                conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
                schema = conn.execute("SELECT type,sql FROM sqlite_master WHERE name=?", (table,)).fetchone()
                if schema is None:
                    return []
                if schema[0] != "table" or not isinstance(schema[1], str) or "VIRTUAL TABLE" in schema[1].upper():
                    raise SourceError("state_schema_unsupported")
                present = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
                if not columns <= present:
                    raise SourceError("state_schema_unsupported")
                def authorize(action, one, two, _db, _trigger):
                    if action == sqlite3.SQLITE_SELECT:
                        return sqlite3.SQLITE_OK
                    if action == sqlite3.SQLITE_READ and one == table:
                        return sqlite3.SQLITE_OK
                    if action == sqlite3.SQLITE_FUNCTION and two in {"substr"}:
                        return sqlite3.SQLITE_OK
                    return sqlite3.SQLITE_DENY
                conn.set_authorizer(authorize)
                rows = conn.execute(query, params).fetchall()
                if len(rows) > (1 if kind == "plugin_index" else MAX_ROWS):
                    raise SourceError("state_row_limit_or_ambiguous")
                if any(not isinstance(r[-1], str) or len(r[-1].encode("utf-8")) > MAX_JSON_BYTES for r in rows):
                    raise SourceError("state_payload_too_large_or_invalid")
                return rows
            finally:
                conn.close()
    except SourceError:
        raise
    except (sqlite3.Error, OSError, UnicodeError):
        raise SourceError("state_database_unreadable") from None
