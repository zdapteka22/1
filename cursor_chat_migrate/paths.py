from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CursorPaths:
    user_dir: Path

    @property
    def global_db(self) -> Path:
        return self.user_dir / "globalStorage" / "state.vscdb"

    @property
    def workspace_storage(self) -> Path:
        return self.user_dir / "workspaceStorage"

    def workspace_db(self, workspace_id: str) -> Path:
        return self.workspace_storage / workspace_id / "state.vscdb"

    def workspace_json(self, workspace_id: str) -> Path:
        return self.workspace_storage / workspace_id / "workspace.json"


def default_user_dirs() -> list[Path]:
    """Candidate Cursor User directories for the current OS."""
    system = platform.system()
    home = Path.home()
    candidates: list[Path] = []

    if system == "Darwin":
        candidates.append(home / "Library" / "Application Support" / "Cursor" / "User")
    elif system == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "Cursor" / "User")
        # WSL reading Windows Cursor install
        for drive in ("/mnt/c", "C:"):
            users = Path(drive) / "Users"
            if users.is_dir():
                for user_home in users.iterdir():
                    roaming = user_home / "AppData" / "Roaming" / "Cursor" / "User"
                    candidates.append(roaming)
    else:
        candidates.append(home / ".config" / "Cursor" / "User")
        # Cursor remote / server
        candidates.append(home / ".cursor-server" / "data" / "User")

    env = os.environ.get("CURSOR_USER_DIR")
    if env:
        candidates.insert(0, Path(env).expanduser())

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in candidates:
        resolved = path.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def resolve_paths(user_dir: str | Path | None = None) -> CursorPaths:
    if user_dir is not None:
        path = Path(user_dir).expanduser().resolve()
        if not path.is_dir():
            raise FileNotFoundError(f"Cursor User directory not found: {path}")
        return CursorPaths(user_dir=path)

    for candidate in default_user_dirs():
        if (candidate / "globalStorage" / "state.vscdb").is_file() or (
            candidate / "workspaceStorage"
        ).is_dir():
            return CursorPaths(user_dir=candidate.resolve())

    searched = ", ".join(str(p) for p in default_user_dirs())
    raise FileNotFoundError(
        "Could not find Cursor data. Pass --user-dir or set CURSOR_USER_DIR. "
        f"Searched: {searched}"
    )


def is_cursor_running(paths: CursorPaths) -> bool:
    """Heuristic: WAL lock / exclusive lock files suggest Cursor is open."""
    for db in (paths.global_db,):
        if not db.is_file():
            continue
        wal = Path(str(db) + "-wal")
        shm = Path(str(db) + "-shm")
        # Presence alone is normal; a non-empty WAL while we cannot open
        # in exclusive mode is checked separately in db layer.
        if wal.is_file() and wal.stat().st_size > 0 and shm.is_file():
            return True
    return False
