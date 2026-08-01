from __future__ import annotations

from pathlib import Path

import cursor_chat_migrate.accounts as accounts_mod
from cursor_chat_migrate.accounts import add_account, load_accounts, remove_account


def test_add_and_load_accounts(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "accounts.json"
    monkeypatch.setattr(accounts_mod, "config_path", lambda: cfg)

    user = tmp_path / "UserA"
    user.mkdir()
    saved = add_account("Работа", user)
    assert len(saved) == 1
    assert saved[0].name == "Работа"

    loaded = load_accounts()
    assert len(loaded) == 1
    assert loaded[0].user_dir == str(user.resolve())

    # Same path updates name
    add_account("Work", user)
    loaded = load_accounts()
    assert len(loaded) == 1
    assert loaded[0].name == "Work"

    remove_account(loaded[0].id)
    assert load_accounts() == []
