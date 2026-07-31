from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from .db import backup_file, open_db
from .discover import find_workspace_for_path, list_workspaces
from .export_chats import BUNDLE_FORMAT
from .paths import CursorPaths


def _new_id() -> str:
    return str(uuid.uuid4())


def _remap_key(key: str, id_map: dict[str, str]) -> str:
    if key.startswith("composerData:"):
        old = key.split(":", 1)[1]
        return f"composerData:{id_map.get(old, old)}"
    for prefix in ("bubbleId:", "checkpointId:", "messageRequestContext:"):
        if key.startswith(prefix):
            rest = key[len(prefix) :]
            parts = rest.split(":", 1)
            if len(parts) != 2:
                return key
            old_composer, rest_id = parts
            new_composer = id_map.get(old_composer, old_composer)
            # Remap bubble/checkpoint ids when they collide with known composer map
            # (we remap all bubble ids separately below)
            return f"{prefix}{new_composer}:{rest_id}"
    return key


def _deep_remap_ids(value: Any, id_map: dict[str, str]) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if k in {
                "composerId",
                "bubbleId",
                "checkpointId",
                "serverBubbleId",
                "messageId",
            } and isinstance(v, str) and v in id_map:
                out[k] = id_map[v]
            else:
                out[k] = _deep_remap_ids(v, id_map)
        return out
    if isinstance(value, list):
        return [_deep_remap_ids(v, id_map) for v in value]
    if isinstance(value, str):
        # Replace exact UUID occurrences carefully via map
        if value in id_map:
            return id_map[value]
        return value
    return value


def _build_id_map(kv: dict[str, Any], composer_id: str) -> dict[str, str]:
    id_map: dict[str, str] = {composer_id: _new_id()}
    # Remap every bubble / checkpoint id to avoid collisions on re-import
    for key in kv:
        if key.startswith("bubbleId:"):
            parts = key.split(":")
            if len(parts) >= 3:
                bid = parts[2]
                if bid not in id_map:
                    id_map[bid] = _new_id()
        elif key.startswith("checkpointId:"):
            parts = key.split(":")
            if len(parts) >= 3:
                cpid = parts[2]
                if cpid not in id_map:
                    id_map[cpid] = _new_id()
        elif key.startswith("messageRequestContext:"):
            parts = key.split(":")
            if len(parts) >= 3:
                mid = parts[2]
                if mid not in id_map:
                    id_map[mid] = _new_id()
    return id_map


def _workspace_identifier(workspace_id: str, folder: Optional[str]) -> dict[str, Any]:
    if folder:
        # Build a file URI; keep path as-is for POSIX / Windows
        if folder.startswith("/"):
            external = "file://" + quote(folder, safe="/")
        else:
            external = "file:///" + quote(folder.replace("\\", "/"), safe="/:")
        return {
            "id": workspace_id,
            "uri": {
                "fsPath": folder,
                "path": folder if folder.startswith("/") else "/" + folder.replace("\\", "/"),
                "scheme": "file",
                "external": external,
            },
        }
    return {"id": workspace_id}


def _ensure_workspace(
    paths: CursorPaths,
    *,
    project_path: Optional[str],
    workspace_id: Optional[str],
    create: bool = True,
) -> tuple[str, Optional[str]]:
    if workspace_id:
        ws_path = paths.workspace_storage / workspace_id
        if not ws_path.is_dir():
            raise FileNotFoundError(f"Workspace id not found: {workspace_id}")
        folder = None
        meta = paths.workspace_json(workspace_id)
        if meta.is_file():
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                folder = data.get("folder") or data.get("workspace")
                if isinstance(folder, str) and folder.startswith("file://"):
                    from urllib.parse import unquote, urlparse

                    folder = unquote(urlparse(folder).path)
            except (OSError, json.JSONDecodeError):
                folder = None
        return workspace_id, folder

    if not project_path:
        raise ValueError("Provide --workspace path or --workspace-id")

    existing = find_workspace_for_path(paths, project_path)
    if existing:
        return existing.id, existing.folder

    folder = str(Path(project_path).expanduser().resolve())
    new_id = hashlib.md5(f"file://{folder}".encode("utf-8")).hexdigest()
    while (paths.workspace_storage / new_id).exists():
        new_id = _new_id().replace("-", "")

    if not create:
        return new_id, folder

    # Create a new workspace storage entry so Cursor can adopt it.
    ws_dir = paths.workspace_storage / new_id
    ws_dir.mkdir(parents=True, exist_ok=True)
    uri = "file://" + quote(folder, safe="/")
    (ws_dir / "workspace.json").write_text(
        json.dumps({"folder": uri}, indent=2) + "\n", encoding="utf-8"
    )

    db_path = ws_dir / "state.vscdb"
    with open_db(db_path, readonly=False) as wdb:
        wdb.put(
            "ItemTable",
            "composer.composerData",
            {
                "selectedComposerIds": [],
                "lastFocusedComposerIds": [],
                "hasMigratedComposerData": True,
                "hasMigratedMultipleComposers": True,
            },
        )
    return new_id, folder


def _register_chat(
    paths: CursorPaths,
    *,
    new_composer_id: str,
    meta: dict[str, Any],
    header_template: Optional[dict[str, Any]],
    workspace_id: str,
    folder: Optional[str],
) -> None:
    # Global headers (Cursor 3.0+)
    if paths.global_db.is_file():
        with open_db(paths.global_db, readonly=False) as gdb:
            headers = gdb.get("ItemTable", "composer.composerHeaders")
            if not isinstance(headers, dict):
                headers = {"allComposers": []}
            all_composers = list(headers.get("allComposers") or [])
            entry = dict(header_template) if isinstance(header_template, dict) else {}
            entry["composerId"] = new_composer_id
            entry["name"] = meta.get("name") or entry.get("name") or "Imported chat"
            if meta.get("createdAt") is not None:
                entry["createdAt"] = meta["createdAt"]
            if meta.get("lastUpdatedAt") is not None:
                entry["lastUpdatedAt"] = meta["lastUpdatedAt"]
            if meta.get("unifiedMode") is not None:
                entry["unifiedMode"] = meta["unifiedMode"]
            entry["workspaceIdentifier"] = _workspace_identifier(workspace_id, folder)
            # Drop any stale selected flags
            all_composers = [
                e
                for e in all_composers
                if not (isinstance(e, dict) and e.get("composerId") == new_composer_id)
            ]
            all_composers.insert(0, entry)
            headers["allComposers"] = all_composers
            gdb.put("ItemTable", "composer.composerHeaders", headers)

    # Workspace selected tabs + legacy allComposers
    ws_db = paths.workspace_db(workspace_id)
    if not ws_db.is_file():
        with open_db(ws_db, readonly=False) as wdb:
            wdb.ensure_tables()
            data = {
                "allComposers": [],
                "selectedComposerIds": [],
                "lastFocusedComposerIds": [],
            }
            wdb.put("ItemTable", "composer.composerData", data)

    with open_db(ws_db, readonly=False) as wdb:
        data = wdb.get("ItemTable", "composer.composerData")
        if not isinstance(data, dict):
            data = {}
        migrated = bool(data.get("hasMigratedComposerData")) and (
            "allComposers" not in data
        )
        legacy_entry = {
            "composerId": new_composer_id,
            "name": meta.get("name") or "Imported chat",
            "createdAt": meta.get("createdAt"),
            "lastUpdatedAt": meta.get("lastUpdatedAt"),
            "unifiedMode": meta.get("unifiedMode") or "agent",
        }
        if not migrated:
            all_composers = [
                e
                for e in (data.get("allComposers") or [])
                if not (isinstance(e, dict) and e.get("composerId") == new_composer_id)
            ]
            all_composers.insert(
                0, {k: v for k, v in legacy_entry.items() if v is not None}
            )
            data["allComposers"] = all_composers

        selected = list(data.get("selectedComposerIds") or [])
        if new_composer_id not in selected:
            selected.insert(0, new_composer_id)
        data["selectedComposerIds"] = selected
        focused = list(data.get("lastFocusedComposerIds") or [])
        if new_composer_id not in focused:
            focused.insert(0, new_composer_id)
        data["lastFocusedComposerIds"] = focused
        wdb.put("ItemTable", "composer.composerData", data)


def import_bundle(
    paths: CursorPaths,
    bundle_path: Path,
    *,
    project_path: Optional[str] = None,
    workspace_id: Optional[str] = None,
    composer_ids: Optional[list[str]] = None,
    dry_run: bool = False,
    backup_dir: Optional[Path] = None,
) -> dict[str, Any]:
    data = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    if data.get("format") != BUNDLE_FORMAT:
        raise ValueError(
            f"Unsupported bundle format: {data.get('format')!r}. "
            f"Expected {BUNDLE_FORMAT!r}"
        )

    chats = data.get("chats") or []
    if composer_ids:
        wanted = set(composer_ids)
        chats = [c for c in chats if c.get("meta", {}).get("composerId") in wanted]

    if not chats:
        return {"imported": 0, "results": [], "dryRun": dry_run}

    workspace_id, folder = _ensure_workspace(
        paths,
        project_path=project_path,
        workspace_id=workspace_id,
        create=not dry_run,
    )

    if dry_run:
        return {
            "imported": 0,
            "dryRun": True,
            "workspaceId": workspace_id,
            "folder": folder,
            "wouldImport": [
                {
                    "composerId": c.get("meta", {}).get("composerId"),
                    "name": c.get("meta", {}).get("name"),
                    "keys": len(c.get("kv") or {}),
                }
                for c in chats
            ],
        }

    backups: list[str] = []
    if paths.global_db.is_file():
        backups.append(str(backup_file(paths.global_db, backup_dir)))
    ws_db = paths.workspace_db(workspace_id)
    if ws_db.is_file():
        backups.append(str(backup_file(ws_db, backup_dir)))

    # Ensure global DB exists
    if not paths.global_db.is_file():
        paths.global_db.parent.mkdir(parents=True, exist_ok=True)
        with open_db(paths.global_db, readonly=False) as gdb:
            gdb.ensure_tables()

    results: list[dict[str, Any]] = []
    for chat in chats:
        meta = chat.get("meta") or {}
        kv = chat.get("kv") or {}
        old_composer = meta.get("composerId")
        if not old_composer:
            continue
        id_map = _build_id_map(kv, old_composer)
        new_composer = id_map[old_composer]

        remapped_kv: dict[str, Any] = {}
        for key, value in kv.items():
            # Remap composer-scoped keys; keep content-addressed blobs as-is
            if key.startswith("composer.content."):
                remapped_kv[key] = value
                continue
            # Rebuild bubble/checkpoint keys with new ids
            new_key = key
            if key.startswith("bubbleId:"):
                parts = key.split(":")
                if len(parts) >= 3:
                    new_key = f"bubbleId:{new_composer}:{id_map.get(parts[2], parts[2])}"
            elif key.startswith("checkpointId:"):
                parts = key.split(":")
                if len(parts) >= 3:
                    new_key = (
                        f"checkpointId:{new_composer}:{id_map.get(parts[2], parts[2])}"
                    )
            elif key.startswith("messageRequestContext:"):
                parts = key.split(":")
                if len(parts) >= 3:
                    new_key = (
                        f"messageRequestContext:{new_composer}:"
                        f"{id_map.get(parts[2], parts[2])}"
                    )
            elif key.startswith("composerData:"):
                new_key = f"composerData:{new_composer}"
            else:
                new_key = _remap_key(key, id_map)

            remapped_kv[new_key] = _deep_remap_ids(value, id_map)

        with open_db(paths.global_db, readonly=False) as gdb:
            for key, value in remapped_kv.items():
                gdb.put("cursorDiskKV", key, value)

        _register_chat(
            paths,
            new_composer_id=new_composer,
            meta=meta,
            header_template=meta.get("header"),
            workspace_id=workspace_id,
            folder=folder,
        )
        results.append(
            {
                "oldComposerId": old_composer,
                "newComposerId": new_composer,
                "name": meta.get("name"),
                "keys": len(remapped_kv),
            }
        )

    return {
        "imported": len(results),
        "dryRun": False,
        "workspaceId": workspace_id,
        "folder": folder,
        "backups": backups,
        "results": results,
        "workspacesKnown": [ws.label for ws in list_workspaces(paths)[:20]],
    }
