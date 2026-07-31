from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urlparse

from .db import CursorDB, open_db
from .paths import CursorPaths


@dataclass
class WorkspaceInfo:
    id: str
    folder: Optional[str]
    uri: Optional[str]
    path: Path

    @property
    def label(self) -> str:
        if self.folder:
            return self.folder
        if self.uri:
            return self.uri
        return self.id


@dataclass
class ChatSummary:
    composer_id: str
    name: str
    created_at: Optional[int] = None
    last_updated_at: Optional[int] = None
    unified_mode: Optional[str] = None
    workspace_id: Optional[str] = None
    workspace_label: Optional[str] = None
    message_count: int = 0
    sources: list[str] = field(default_factory=list)


def _folder_from_workspace_json(data: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    folder = data.get("folder") or data.get("workspace")
    if not folder or not isinstance(folder, str):
        return None, None
    uri = folder
    if folder.startswith("file://"):
        parsed = urlparse(folder)
        return unquote(parsed.path), uri
    if folder.startswith("vscode-remote://"):
        # vscode-remote://authority/path
        rest = folder[len("vscode-remote://") :]
        slash = rest.find("/")
        if slash >= 0:
            return unquote(rest[slash:]), uri
        return uri, uri
    return folder, uri


def list_workspaces(paths: CursorPaths) -> list[WorkspaceInfo]:
    root = paths.workspace_storage
    if not root.is_dir():
        return []
    result: list[WorkspaceInfo] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        meta_path = child / "workspace.json"
        folder = None
        uri = None
        if meta_path.is_file():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                folder, uri = _folder_from_workspace_json(data)
            except (OSError, json.JSONDecodeError):
                pass
        result.append(
            WorkspaceInfo(id=child.name, folder=folder, uri=uri, path=child)
        )
    return result


def _header_fields(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "composer_id": entry.get("composerId") or entry.get("composer_id"),
        "name": entry.get("name") or "Untitled",
        "created_at": entry.get("createdAt") or entry.get("created_at"),
        "last_updated_at": entry.get("lastUpdatedAt") or entry.get("last_updated_at"),
        "unified_mode": entry.get("unifiedMode") or entry.get("unified_mode"),
        "workspace_identifier": entry.get("workspaceIdentifier"),
    }


def _message_count(composer_data: Any) -> int:
    if not isinstance(composer_data, dict):
        return 0
    headers = composer_data.get("fullConversationHeadersOnly") or []
    if isinstance(headers, list) and headers:
        return len(headers)
    cmap = composer_data.get("conversationMap") or {}
    if isinstance(cmap, dict):
        return len(cmap)
    return 0


def _workspace_id_from_identifier(
    identifier: Any, workspaces: list[WorkspaceInfo]
) -> tuple[Optional[str], Optional[str]]:
    if not isinstance(identifier, dict):
        return None, None
    wid = identifier.get("id")
    uri_obj = identifier.get("uri") or {}
    fs_path = None
    if isinstance(uri_obj, dict):
        fs_path = uri_obj.get("fsPath") or uri_obj.get("path")
    label = fs_path
    if wid:
        for ws in workspaces:
            if ws.id == wid:
                return wid, ws.label
    if fs_path:
        for ws in workspaces:
            if ws.folder == fs_path:
                return ws.id, ws.label
    return wid, label


def list_chats(
    paths: CursorPaths,
    *,
    workspace_filter: Optional[str] = None,
) -> list[ChatSummary]:
    workspaces = list_workspaces(paths)
    by_id: dict[str, ChatSummary] = {}

    def upsert(summary: ChatSummary) -> None:
        existing = by_id.get(summary.composer_id)
        if existing is None:
            by_id[summary.composer_id] = summary
            return
        for src in summary.sources:
            if src not in existing.sources:
                existing.sources.append(src)
        if not existing.name or existing.name == "Untitled":
            existing.name = summary.name
        if existing.created_at is None:
            existing.created_at = summary.created_at
        if existing.last_updated_at is None:
            existing.last_updated_at = summary.last_updated_at
        if existing.unified_mode is None:
            existing.unified_mode = summary.unified_mode
        if existing.workspace_id is None:
            existing.workspace_id = summary.workspace_id
            existing.workspace_label = summary.workspace_label
        if existing.message_count < summary.message_count:
            existing.message_count = summary.message_count

    # Cursor 3.0+ central index
    if paths.global_db.is_file():
        with open_db(paths.global_db, readonly=True) as gdb:
            headers = gdb.get("ItemTable", "composer.composerHeaders")
            if isinstance(headers, dict):
                for entry in headers.get("allComposers") or []:
                    if not isinstance(entry, dict):
                        continue
                    fields = _header_fields(entry)
                    cid = fields["composer_id"]
                    if not cid:
                        continue
                    wid, wlabel = _workspace_id_from_identifier(
                        fields["workspace_identifier"], workspaces
                    )
                    composer = gdb.get("cursorDiskKV", f"composerData:{cid}")
                    upsert(
                        ChatSummary(
                            composer_id=cid,
                            name=fields["name"],
                            created_at=fields["created_at"],
                            last_updated_at=fields["last_updated_at"],
                            unified_mode=fields["unified_mode"],
                            workspace_id=wid,
                            workspace_label=wlabel,
                            message_count=_message_count(composer),
                            sources=["composerHeaders"],
                        )
                    )

            # Also discover any composerData keys not in the index
            for key, value in gdb.items_like("cursorDiskKV", "composerData:"):
                cid = key.split(":", 1)[1]
                if not cid or cid in by_id:
                    # refresh message count if missing
                    if cid in by_id and by_id[cid].message_count == 0:
                        by_id[cid].message_count = _message_count(value)
                    continue
                name = "Untitled"
                created = None
                updated = None
                mode = None
                if isinstance(value, dict):
                    name = value.get("name") or name
                    created = value.get("createdAt")
                    updated = value.get("lastUpdatedAt")
                    mode = value.get("unifiedMode")
                upsert(
                    ChatSummary(
                        composer_id=cid,
                        name=name,
                        created_at=created,
                        last_updated_at=updated,
                        unified_mode=mode,
                        message_count=_message_count(value),
                        sources=["composerData"],
                    )
                )

    # Workspace indexes (Cursor 2.x and residual 3.0 keys)
    for ws in workspaces:
        db_path = paths.workspace_db(ws.id)
        if not db_path.is_file():
            continue
        try:
            with open_db(db_path, readonly=True) as wdb:
                data = wdb.get("ItemTable", "composer.composerData")
                if isinstance(data, dict):
                    for entry in data.get("allComposers") or []:
                        if not isinstance(entry, dict):
                            continue
                        fields = _header_fields(entry)
                        cid = fields["composer_id"]
                        if not cid:
                            continue
                        upsert(
                            ChatSummary(
                                composer_id=cid,
                                name=fields["name"],
                                created_at=fields["created_at"],
                                last_updated_at=fields["last_updated_at"],
                                unified_mode=fields["unified_mode"],
                                workspace_id=ws.id,
                                workspace_label=ws.label,
                                sources=["workspace.allComposers"],
                            )
                        )
                    for key_name in ("selectedComposerIds", "lastFocusedComposerIds"):
                        for cid in data.get(key_name) or []:
                            if not isinstance(cid, str):
                                continue
                            upsert(
                                ChatSummary(
                                    composer_id=cid,
                                    name="Untitled",
                                    workspace_id=ws.id,
                                    workspace_label=ws.label,
                                    sources=[f"workspace.{key_name}"],
                                )
                            )
        except Exception:
            continue

    chats = list(by_id.values())

    if workspace_filter:
        needle = workspace_filter.lower()
        chats = [
            c
            for c in chats
            if (c.workspace_id and needle in c.workspace_id.lower())
            or (c.workspace_label and needle in c.workspace_label.lower())
        ]

    chats.sort(
        key=lambda c: (
            -(c.last_updated_at or c.created_at or 0),
            c.name.lower(),
        )
    )
    return chats


def find_workspace_for_path(
    paths: CursorPaths, project_path: str | Path
) -> Optional[WorkspaceInfo]:
    target = str(Path(project_path).expanduser().resolve())
    matches = [ws for ws in list_workspaces(paths) if ws.folder == target]
    if matches:
        # Prefer the one that has a DB
        for ws in matches:
            if paths.workspace_db(ws.id).is_file():
                return ws
        return matches[0]
    return None
