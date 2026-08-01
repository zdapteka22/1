from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from .paths import default_user_dirs, resolve_paths


def config_path() -> Path:
    return Path.home() / ".cursor-chat-migrate" / "accounts.json"


@dataclass
class Account:
    id: str
    name: str
    user_dir: str

    @property
    def path(self) -> Path:
        return Path(self.user_dir).expanduser()


def load_accounts() -> list[Account]:
    path = config_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    result: list[Account] = []
    for item in data.get("accounts") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        user_dir = str(item.get("user_dir") or "").strip()
        if not name or not user_dir:
            continue
        result.append(
            Account(
                id=str(item.get("id") or uuid.uuid4()),
                name=name,
                user_dir=user_dir,
            )
        )
    return result


def save_accounts(accounts: list[Account]) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "accounts": [asdict(a) for a in accounts],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def add_account(name: str, user_dir: str | Path, accounts: list[Account] | None = None) -> list[Account]:
    current = list(accounts) if accounts is not None else load_accounts()
    resolved = str(Path(user_dir).expanduser().resolve())
    for acc in current:
        if Path(acc.user_dir).expanduser().resolve() == Path(resolved):
            acc.name = name.strip() or acc.name
            save_accounts(current)
            return current
    current.append(
        Account(id=str(uuid.uuid4()), name=name.strip() or "Аккаунт", user_dir=resolved)
    )
    save_accounts(current)
    return current


def remove_account(account_id: str, accounts: list[Account] | None = None) -> list[Account]:
    current = list(accounts) if accounts is not None else load_accounts()
    current = [a for a in current if a.id != account_id]
    save_accounts(current)
    return current


def ensure_default_account() -> list[Account]:
    """If no saved accounts, try to detect the local Cursor profile."""
    accounts = load_accounts()
    if accounts:
        return accounts
    try:
        paths = resolve_paths(None)
        return add_account("Этот компьютер", paths.user_dir, accounts=[])
    except FileNotFoundError:
        # Still offer candidates that exist as directories
        for candidate in default_user_dirs():
            if candidate.is_dir():
                return add_account("Этот компьютер", candidate, accounts=[])
        return []


def guess_account_name(user_dir: Path) -> str:
    """Best-effort label from Cursor storage / parent folder."""
    # Common places Cursor may store identity hints
    candidates = [
        user_dir.parent / "sentry" / "scope_v3.json",
        user_dir / "globalStorage" / "storage.json",
        Path.home() / ".cursor" / "argv.json",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            data = json.loads(text) if text.strip().startswith("{") else None
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            for key in ("email", "userEmail", "account", "login"):
                val = data.get(key)
                if isinstance(val, str) and "@" in val:
                    return val
    # Fall back to parent folder name
    parent = user_dir.parent.name
    if parent and parent.lower() != "cursor":
        return parent
    return user_dir.name
