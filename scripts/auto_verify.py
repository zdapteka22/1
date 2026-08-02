"""Automated export/import/reverse roundtrip check."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cursor_chat_migrate.db import open_db
from cursor_chat_migrate.discover import list_chats
from cursor_chat_migrate.export_chats import export_chats
from cursor_chat_migrate.import_chats import import_bundle
from cursor_chat_migrate.paths import CursorPaths
from tests.test_migrate import _init_db, _put, make_dest_install, make_source_install


def main() -> int:
    td = Path(tempfile.mkdtemp(prefix="auto-verify-"))
    print("temp:", td)

    src = make_source_install(td / "A")
    chats = list_chats(src)
    assert len(chats) == 1, chats
    print("OK account A chat:", chats[0].name, "msgs=", chats[0].message_count)

    bundle1 = td / "export.bundle.json"
    r1 = export_chats(src, output=bundle1, all_chats=True)
    assert r1["exported"] == 1 and bundle1.is_file()
    print("OK export:", bundle1, "bytes=", bundle1.stat().st_size)

    dst, proj_b = make_dest_install(td / "B")
    dry = import_bundle(dst, bundle1, project_path=str(proj_b), dry_run=True)
    assert dry["dryRun"] and dry["wouldImport"]
    print("OK dry-run import:", len(dry["wouldImport"]))

    imp = import_bundle(dst, bundle1, project_path=str(proj_b))
    assert imp["imported"] == 1
    chats_b = list_chats(dst)
    assert len(chats_b) == 1 and chats_b[0].name == "Source chat"
    print("OK import A->B:", chats_b[0].composer_id)

    bundle2 = td / "reverse.bundle.json"
    r2 = export_chats(dst, output=bundle2, all_chats=True)
    assert r2["exported"] == 1
    print("OK reverse export B->file")

    user_c = td / "C" / "Cursor" / "User"
    (user_c / "globalStorage").mkdir(parents=True)
    _init_db(user_c / "globalStorage" / "state.vscdb")
    _put(
        user_c / "globalStorage" / "state.vscdb",
        "ItemTable",
        "composer.composerHeaders",
        {"allComposers": []},
    )
    proj_c = td / "C" / "project"
    proj_c.mkdir(parents=True)
    c_paths = CursorPaths(user_dir=user_c)
    imp2 = import_bundle(c_paths, bundle2, project_path=str(proj_c))
    assert imp2["imported"] == 1
    chats_c = list_chats(c_paths)
    with open_db(c_paths.global_db, readonly=True) as gdb:
        cid = chats_c[0].composer_id
        bubbles = gdb.keys_like("cursorDiskKV", f"bubbleId:{cid}:")
        texts = [gdb.get("cursorDiskKV", k).get("text", "") for k in bubbles]
    assert len(bubbles) == 2
    assert any("old account" in t for t in texts)
    print("OK reverse import B->C, messages preserved:", texts)

    appdata = Path.home() / "AppData" / "Roaming" / "Cursor" / "User"
    linux = Path.home() / ".config" / "Cursor" / "User"
    for candidate in (appdata, linux):
        db = candidate / "globalStorage" / "state.vscdb"
        if db.is_file():
            print("Found local Cursor User:", candidate)
            local = list_chats(CursorPaths(user_dir=candidate))
            print("Local chats:", len(local))
            out = Path.home() / "Desktop" / "cursor_export_test.bundle.json"
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                er = export_chats(
                    CursorPaths(user_dir=candidate), output=out, all_chats=True
                )
                print("OK local export:", er["exported"], "->", out)
            except Exception as exc:
                print("Local export skipped:", exc)
            break

    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
