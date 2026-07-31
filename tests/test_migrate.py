from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from cursor_chat_migrate.db import open_db
from cursor_chat_migrate.discover import list_chats
from cursor_chat_migrate.export_chats import export_chats
from cursor_chat_migrate.import_chats import import_bundle
from cursor_chat_migrate.paths import CursorPaths


def _init_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE ItemTable (key TEXT UNIQUE, value BLOB)")
    conn.execute("CREATE TABLE cursorDiskKV (key TEXT UNIQUE, value BLOB)")
    conn.commit()
    conn.close()


def _put(path: Path, table: str, key: str, value) -> None:
    with open_db(path, readonly=False) as db:
        db.put(table, key, value)


def make_source_install(root: Path) -> CursorPaths:
    user = root / "Cursor" / "User"
    global_db = user / "globalStorage" / "state.vscdb"
    ws_id = "abc123workspace"
    project = root / "project-a"
    project.mkdir(parents=True)
    (project / "readme.txt").write_text("hi", encoding="utf-8")

    _init_db(global_db)
    ws_dir = user / "workspaceStorage" / ws_id
    ws_dir.mkdir(parents=True)
    folder_uri = "file://" + str(project.resolve())
    (ws_dir / "workspace.json").write_text(
        json.dumps({"folder": folder_uri}), encoding="utf-8"
    )
    _init_db(ws_dir / "state.vscdb")

    composer_id = "11111111-1111-1111-1111-111111111111"
    bubble_user = "22222222-2222-2222-2222-222222222222"
    bubble_ai = "33333333-3333-3333-3333-333333333333"

    composer = {
        "_v": 13,
        "composerId": composer_id,
        "name": "Source chat",
        "fullConversationHeadersOnly": [
            {"bubbleId": bubble_user, "type": 1},
            {"bubbleId": bubble_ai, "type": 2},
        ],
        "conversationMap": {},
        "unifiedMode": "agent",
        "createdAt": 1_700_000_000_000,
        "lastUpdatedAt": 1_700_000_100_000,
        "status": "completed",
    }
    _put(global_db, "cursorDiskKV", f"composerData:{composer_id}", composer)
    _put(
        global_db,
        "cursorDiskKV",
        f"bubbleId:{composer_id}:{bubble_user}",
        {"bubbleId": bubble_user, "type": 1, "text": "hello from old account"},
    )
    _put(
        global_db,
        "cursorDiskKV",
        f"bubbleId:{composer_id}:{bubble_ai}",
        {"bubbleId": bubble_ai, "type": 2, "text": "hi, migrated reply"},
    )
    _put(
        global_db,
        "ItemTable",
        "composer.composerHeaders",
        {
            "allComposers": [
                {
                    "composerId": composer_id,
                    "name": "Source chat",
                    "createdAt": 1_700_000_000_000,
                    "lastUpdatedAt": 1_700_000_100_000,
                    "unifiedMode": "agent",
                    "workspaceIdentifier": {
                        "id": ws_id,
                        "uri": {
                            "fsPath": str(project.resolve()),
                            "scheme": "file",
                            "external": folder_uri,
                        },
                    },
                }
            ]
        },
    )
    _put(
        ws_dir / "state.vscdb",
        "ItemTable",
        "composer.composerData",
        {
            "selectedComposerIds": [composer_id],
            "lastFocusedComposerIds": [composer_id],
            "hasMigratedComposerData": True,
            "hasMigratedMultipleComposers": True,
        },
    )
    return CursorPaths(user_dir=user)


def make_dest_install(root: Path) -> tuple[CursorPaths, Path]:
    user = root / "CursorDest" / "User"
    global_db = user / "globalStorage" / "state.vscdb"
    _init_db(global_db)
    _put(global_db, "ItemTable", "composer.composerHeaders", {"allComposers": []})
    project = root / "project-b"
    project.mkdir(parents=True)
    return CursorPaths(user_dir=user), project


def test_export_import_roundtrip(tmp_path: Path) -> None:
    source = make_source_install(tmp_path / "src")
    chats = list_chats(source)
    assert len(chats) == 1
    assert chats[0].name == "Source chat"
    assert chats[0].message_count == 2

    bundle = tmp_path / "bundle.json"
    result = export_chats(source, output=bundle, all_chats=True)
    assert result["exported"] == 1
    assert bundle.is_file()

    dest, project = make_dest_install(tmp_path / "dst")
    imported = import_bundle(dest, bundle, project_path=str(project))
    assert imported["imported"] == 1
    new_id = imported["results"][0]["newComposerId"]
    assert new_id != "11111111-1111-1111-1111-111111111111"

    dest_chats = list_chats(dest)
    assert len(dest_chats) == 1
    assert dest_chats[0].composer_id == new_id
    assert dest_chats[0].name == "Source chat"

    with open_db(dest.global_db, readonly=True) as gdb:
        data = gdb.get("cursorDiskKV", f"composerData:{new_id}")
        assert data["name"] == "Source chat"
        assert len(data["fullConversationHeadersOnly"]) == 2
        bubbles = gdb.keys_like("cursorDiskKV", f"bubbleId:{new_id}:")
        assert len(bubbles) == 2
        text = gdb.get("cursorDiskKV", bubbles[0])["text"]
        assert "old account" in text or "migrated" in text

        headers = gdb.get("ItemTable", "composer.composerHeaders")
        assert headers["allComposers"][0]["composerId"] == new_id


def test_dry_run_no_write(tmp_path: Path) -> None:
    source = make_source_install(tmp_path / "src")
    bundle = tmp_path / "bundle.json"
    export_chats(source, output=bundle, all_chats=True)
    dest, project = make_dest_install(tmp_path / "dst")
    result = import_bundle(
        dest, bundle, project_path=str(project), dry_run=True
    )
    assert result["dryRun"] is True
    assert list_chats(dest) == []
