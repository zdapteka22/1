from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional


def _decode_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        try:
            text = value.decode("utf-8")
        except UnicodeDecodeError:
            return value
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _encode_value(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8")
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class CursorDB:
    """Thin wrapper around Cursor's state.vscdb key-value tables."""

    def __init__(self, path: Path, *, readonly: bool = True):
        self.path = Path(path)
        self.readonly = readonly
        self._conn: Optional[sqlite3.Connection] = None
        self._temp_copy: Optional[Path] = None

    def open(self) -> None:
        if self._conn is not None:
            return
        if self.readonly:
            if not self.path.is_file():
                raise FileNotFoundError(f"Database not found: {self.path}")
            # Copy with WAL siblings so reads stay consistent while Cursor may be open.
            self._temp_copy = self._copy_with_wal()
            uri = self._temp_copy.as_uri() + "?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self.ensure_tables()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        if self._temp_copy is not None:
            parent = self._temp_copy.parent
            shutil.rmtree(parent, ignore_errors=True)
            self._temp_copy = None

    def __enter__(self) -> "CursorDB":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._conn is not None and not self.readonly:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        self.close()

    def _copy_with_wal(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="cursor-chat-migrate-"))
        dest = tmp / self.path.name
        shutil.copy2(self.path, dest)
        for suffix in ("-wal", "-shm"):
            sibling = Path(str(self.path) + suffix)
            if sibling.is_file():
                shutil.copy2(sibling, Path(str(dest) + suffix))
        # Checkpoint WAL into the copy when possible
        try:
            conn = sqlite3.connect(str(dest))
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
        except sqlite3.Error:
            pass
        return dest

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not open")
        return self._conn

    def get(self, table: str, key: str) -> Any:
        row = self.conn.execute(
            f"SELECT value FROM {table} WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        return _decode_value(row[0])

    def put(self, table: str, key: str, value: Any) -> None:
        if self.readonly:
            raise RuntimeError("Cannot write to a readonly database")
        encoded = _encode_value(value)
        self.conn.execute(
            f"INSERT INTO {table}(key, value) VALUES(?, ?) "
            f"ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, encoded),
        )

    def delete_like(self, table: str, prefix: str) -> int:
        if self.readonly:
            raise RuntimeError("Cannot write to a readonly database")
        cur = self.conn.execute(
            f"DELETE FROM {table} WHERE key LIKE ?", (prefix + "%",)
        )
        return cur.rowcount

    def keys_like(self, table: str, prefix: str) -> list[str]:
        rows = self.conn.execute(
            f"SELECT key FROM {table} WHERE key LIKE ? ORDER BY key",
            (prefix + "%",),
        ).fetchall()
        return [r[0] for r in rows]

    def items_like(self, table: str, prefix: str) -> list[tuple[str, Any]]:
        rows = self.conn.execute(
            f"SELECT key, value FROM {table} WHERE key LIKE ?",
            (prefix + "%",),
        ).fetchall()
        return [(r[0], _decode_value(r[1])) for r in rows]

    def ensure_tables(self) -> None:
        if self.readonly:
            raise RuntimeError("Cannot write to a readonly database")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS ItemTable (key TEXT UNIQUE, value BLOB)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS cursorDiskKV (key TEXT UNIQUE, value BLOB)"
        )


def backup_file(path: Path, backup_dir: Path | None = None) -> Path:
    if not path.is_file():
        raise FileNotFoundError(path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_dir = backup_dir or (path.parent / "backups")
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / f"{path.name}.{stamp}.bak"
    shutil.copy2(path, dest)
    for suffix in ("-wal", "-shm"):
        sibling = Path(str(path) + suffix)
        if sibling.is_file():
            shutil.copy2(sibling, Path(str(dest) + suffix))
    return dest


@contextmanager
def open_db(path: Path, *, readonly: bool = True) -> Iterator[CursorDB]:
    db = CursorDB(path, readonly=readonly)
    with db:
        yield db
