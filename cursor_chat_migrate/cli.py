from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .discover import list_chats, list_workspaces
from .export_chats import export_chats
from .import_chats import import_bundle
from .paths import is_cursor_running, resolve_paths


def _print_table(chats) -> None:
    if not chats:
        print("No chats found.")
        return
    print(f"{'#':>4}  {'Updated':<20}  {'Msgs':>4}  {'Mode':<8}  {'Name'}")
    print("-" * 80)
    for i, chat in enumerate(chats, 1):
        ts = chat.last_updated_at or chat.created_at
        updated = ""
        if ts:
            from datetime import datetime, timezone

            updated = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            )
        mode = (chat.unified_mode or "-")[:8]
        name = chat.name.replace("\n", " ")[:48]
        ws = chat.workspace_label or chat.workspace_id or "-"
        print(
            f"{i:>4}  {updated:<20}  {chat.message_count:>4}  {mode:<8}  {name}"
        )
        print(f"      id={chat.composer_id}")
        print(f"      workspace={ws}")


def cmd_paths(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.user_dir)
    print(f"user_dir={paths.user_dir}")
    print(f"global_db={paths.global_db} exists={paths.global_db.is_file()}")
    print(
        f"workspace_storage={paths.workspace_storage} "
        f"exists={paths.workspace_storage.is_dir()}"
    )
    if is_cursor_running(paths):
        print(
            "warning: Cursor may be running (WAL present). "
            "Close Cursor before import.",
            file=sys.stderr,
        )
    return 0


def cmd_workspaces(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.user_dir)
    for ws in list_workspaces(paths):
        print(f"{ws.id}  {ws.label}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.user_dir)
    chats = list_chats(paths, workspace_filter=args.workspace)
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "composerId": c.composer_id,
                        "name": c.name,
                        "createdAt": c.created_at,
                        "lastUpdatedAt": c.last_updated_at,
                        "unifiedMode": c.unified_mode,
                        "workspaceId": c.workspace_id,
                        "workspaceLabel": c.workspace_label,
                        "messageCount": c.message_count,
                        "sources": c.sources,
                    }
                    for c in chats
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_table(chats)
        print(f"\nTotal: {len(chats)}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.user_dir)
    result = export_chats(
        paths,
        output=Path(args.output),
        composer_ids=args.id,
        workspace_filter=args.workspace,
        all_chats=args.all,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["errors"]:
        return 1
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.user_dir)
    if is_cursor_running(paths) and not args.force:
        print(
            "Cursor appears to be running (WAL present). "
            "Fully quit Cursor, then retry. Use --force to override.",
            file=sys.stderr,
        )
        return 2
    result = import_bundle(
        paths,
        Path(args.bundle),
        project_path=args.workspace,
        workspace_id=args.workspace_id,
        composer_ids=args.id,
        dry_run=args.dry_run,
        backup_dir=Path(args.backup_dir) if args.backup_dir else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.dry_run and result.get("imported", 0) > 0:
        print(
            "\nDone. Fully quit and reopen Cursor (reload window is not enough).",
            file=sys.stderr,
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cursor-chat-migrate",
        description=(
            "Export/import Cursor IDE chats between machines or accounts. "
            "Chats live in local SQLite (state.vscdb), not in the cloud account."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--user-dir",
        help="Path to Cursor User dir (contains globalStorage/). "
        "Or set CURSOR_USER_DIR.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_paths = sub.add_parser("paths", help="Show detected Cursor data paths")
    p_paths.set_defaults(func=cmd_paths)

    p_ws = sub.add_parser("workspaces", help="List known workspaces")
    p_ws.set_defaults(func=cmd_workspaces)

    p_list = sub.add_parser("list", help="List chats")
    p_list.add_argument(
        "--workspace",
        help="Filter by workspace path or id substring",
    )
    p_list.add_argument("--json", action="store_true", help="JSON output")
    p_list.set_defaults(func=cmd_list)

    p_export = sub.add_parser("export", help="Export chats to a portable bundle")
    p_export.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output .json bundle path",
    )
    p_export.add_argument(
        "--id",
        action="append",
        help="Composer id to export (repeatable)",
    )
    p_export.add_argument(
        "--workspace",
        help="Only export chats matching this workspace path/id substring",
    )
    p_export.add_argument(
        "--all",
        action="store_true",
        help="Export all chats (optionally filtered by --workspace)",
    )
    p_export.set_defaults(func=cmd_export)

    p_import = sub.add_parser(
        "import",
        help="Import a bundle into this Cursor install / account data dir",
    )
    p_import.add_argument("bundle", help="Bundle .json from export")
    p_import.add_argument(
        "--workspace",
        help="Target project folder path (created in workspaceStorage if needed)",
    )
    p_import.add_argument(
        "--workspace-id",
        help="Existing workspaceStorage hash id",
    )
    p_import.add_argument(
        "--id",
        action="append",
        help="Only import these original composer ids",
    )
    p_import.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be imported without writing",
    )
    p_import.add_argument(
        "--backup-dir",
        help="Directory for state.vscdb backups (default: next to DB)",
    )
    p_import.add_argument(
        "--force",
        action="store_true",
        help="Import even if Cursor WAL suggests the app is open",
    )
    p_import.set_defaults(func=cmd_import)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
