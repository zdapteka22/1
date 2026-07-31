from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from . import __version__
from .db import open_db
from .discover import ChatSummary, list_chats, list_workspaces
from .paths import CursorPaths

BUNDLE_FORMAT = "cursor-chat-migrate/v1"

KV_PREFIXES = (
    "composerData:",
    "bubbleId:",
    "checkpointId:",
    "messageRequestContext:",
)


def _content_hashes_from_value(value: Any, found: set[str]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if k in {"contentHash", "hash", "blobHash"} and isinstance(v, str):
                found.add(v)
            _content_hashes_from_value(v, found)
    elif isinstance(value, list):
        for item in value:
            _content_hashes_from_value(item, found)
    elif isinstance(value, str):
        for match in re.finditer(r"composer\.content\.([a-fA-F0-9]+)", value):
            found.add(match.group(1))


def collect_chat_payload(
    paths: CursorPaths, composer_id: str, summary: Optional[ChatSummary] = None
) -> dict[str, Any]:
    if not paths.global_db.is_file():
        raise FileNotFoundError(f"Global DB missing: {paths.global_db}")

    kv: dict[str, Any] = {}
    content_hashes: set[str] = set()

    with open_db(paths.global_db, readonly=True) as gdb:
        composer_key = f"composerData:{composer_id}"
        composer = gdb.get("cursorDiskKV", composer_key)
        if composer is None:
            raise KeyError(f"composerData not found for {composer_id}")
        kv[composer_key] = composer
        _content_hashes_from_value(composer, content_hashes)

        for prefix in ("bubbleId:", "checkpointId:", "messageRequestContext:"):
            for key, value in gdb.items_like(
                "cursorDiskKV", f"{prefix}{composer_id}:"
            ):
                kv[key] = value
                _content_hashes_from_value(value, content_hashes)

        for h in sorted(content_hashes):
            key = f"composer.content.{h}"
            value = gdb.get("cursorDiskKV", key)
            if value is not None:
                kv[key] = value

        header_entry = None
        headers = gdb.get("ItemTable", "composer.composerHeaders")
        if isinstance(headers, dict):
            for entry in headers.get("allComposers") or []:
                if isinstance(entry, dict) and entry.get("composerId") == composer_id:
                    header_entry = entry
                    break

    meta = {
        "composerId": composer_id,
        "name": (summary.name if summary else None)
        or (composer.get("name") if isinstance(composer, dict) else None)
        or "Untitled",
        "createdAt": (summary.created_at if summary else None)
        or (composer.get("createdAt") if isinstance(composer, dict) else None),
        "lastUpdatedAt": (summary.last_updated_at if summary else None)
        or (composer.get("lastUpdatedAt") if isinstance(composer, dict) else None),
        "unifiedMode": (summary.unified_mode if summary else None)
        or (composer.get("unifiedMode") if isinstance(composer, dict) else None),
        "workspaceId": summary.workspace_id if summary else None,
        "workspaceLabel": summary.workspace_label if summary else None,
        "header": header_entry,
        "keyCount": len(kv),
    }
    return {"meta": meta, "kv": kv}


def export_chats(
    paths: CursorPaths,
    *,
    output: Path,
    composer_ids: Optional[Iterable[str]] = None,
    workspace_filter: Optional[str] = None,
    all_chats: bool = False,
) -> dict[str, Any]:
    summaries = list_chats(paths, workspace_filter=workspace_filter)
    by_id = {s.composer_id: s for s in summaries}

    if composer_ids:
        selected = list(composer_ids)
    elif all_chats:
        selected = [s.composer_id for s in summaries]
    else:
        raise ValueError("Specify --all or one or more --id values")

    missing = [cid for cid in selected if cid not in by_id]
    # Still try direct export for IDs not in the index
    chats_out: list[dict[str, Any]] = []
    errors: list[str] = []

    for cid in selected:
        try:
            chats_out.append(collect_chat_payload(paths, cid, by_id.get(cid)))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{cid}: {exc}")

    workspaces = [
        {
            "id": ws.id,
            "folder": ws.folder,
            "uri": ws.uri,
        }
        for ws in list_workspaces(paths)
    ]

    bundle = {
        "format": BUNDLE_FORMAT,
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "toolVersion": __version__,
        "sourceUserDir": str(paths.user_dir),
        "workspaces": workspaces,
        "chats": chats_out,
        "errors": errors,
        "bundleId": str(uuid.uuid4()),
    }

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "path": str(output),
        "exported": len(chats_out),
        "errors": errors,
        "missingFromIndex": missing,
    }
