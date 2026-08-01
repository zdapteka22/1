from __future__ import annotations

import tempfile
import tkinter as tk
import traceback
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Optional

from . import __version__
from .accounts import (
    Account,
    add_account,
    ensure_default_account,
    guess_account_name,
    load_accounts,
    remove_account,
    save_accounts,
)
from .discover import ChatSummary, list_chats, list_workspaces
from .export_chats import export_chats
from .import_chats import import_bundle
from .paths import CursorPaths, is_cursor_running


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Перенос чатов Cursor  ·  v{__version__}")
        self.geometry("980x640")
        self.minsize(820, 520)

        self.accounts: list[Account] = ensure_default_account()
        # account_id -> list[ChatSummary]
        self.chats_by_account: dict[str, list[ChatSummary]] = {}
        # tree iid -> payload
        self._node_data: dict[str, dict[str, Any]] = {}

        self._build_style()
        self._build_ui()
        self.refresh_all()

    def _build_style(self) -> None:
        self.configure(bg="#1e2430")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#1e2430")
        style.configure("TLabel", background="#1e2430", foreground="#e8ecf4")
        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"), foreground="#ffffff")
        style.configure("Sub.TLabel", foreground="#9aa6b8")
        style.configure("TButton", padding=(10, 6))
        style.configure(
            "Treeview",
            background="#2a3140",
            fieldbackground="#2a3140",
            foreground="#e8ecf4",
            rowheight=26,
            borderwidth=0,
        )
        style.configure("Treeview.Heading", background="#343c4f", foreground="#e8ecf4")
        style.map("Treeview", background=[("selected", "#3d6df0")])

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(root)
        header.pack(fill=tk.X)
        ttk.Label(header, text="Перенос чатов Cursor", style="Header.TLabel").pack(
            side=tk.LEFT
        )
        ttk.Label(
            header,
            text="Аккаунты → чаты. Выберите чат и нажмите «Перенести».",
            style="Sub.TLabel",
        ).pack(side=tk.LEFT, padx=(14, 0))

        toolbar = ttk.Frame(root)
        toolbar.pack(fill=tk.X, pady=(12, 8))

        buttons = [
            ("Добавить аккаунт", self.on_add_account),
            ("Переименовать", self.on_rename_account),
            ("Удалить аккаунт", self.on_remove_account),
            ("Обновить", self.refresh_all),
            ("Открыть папку", self.on_open_folder),
            ("Перенести", self.on_transfer),
            ("Экспорт в файл", self.on_export_file),
            ("Импорт из файла", self.on_import_file),
        ]
        for text, cmd in buttons:
            ttk.Button(toolbar, text=text, command=cmd).pack(side=tk.LEFT, padx=(0, 6))

        tree_frame = ttk.Frame(root)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 8))

        cols = ("info", "msgs", "mode")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=cols,
            show="tree headings",
            selectmode="extended",
        )
        self.tree.heading("#0", text="Аккаунт / чат", anchor=tk.W)
        self.tree.heading("info", text="Проект / путь", anchor=tk.W)
        self.tree.heading("msgs", text="Сообщ.", anchor=tk.CENTER)
        self.tree.heading("mode", text="Режим", anchor=tk.W)
        self.tree.column("#0", width=340, minwidth=180)
        self.tree.column("info", width=360, minwidth=160)
        self.tree.column("msgs", width=70, minwidth=50, anchor=tk.CENTER)
        self.tree.column("mode", width=90, minwidth=60)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-1>", self.on_double_click)

        self.status = tk.StringVar(value="Готово")
        status_bar = ttk.Label(root, textvariable=self.status, style="Sub.TLabel")
        status_bar.pack(fill=tk.X, pady=(4, 0))

    # ----- data -----

    def refresh_all(self) -> None:
        self.accounts = load_accounts() or ensure_default_account()
        self.chats_by_account.clear()
        errors: list[str] = []
        for acc in self.accounts:
            try:
                paths = CursorPaths(user_dir=acc.path)
                if not paths.user_dir.is_dir():
                    raise FileNotFoundError(f"Нет папки: {paths.user_dir}")
                self.chats_by_account[acc.id] = list_chats(paths)
            except Exception as exc:  # noqa: BLE001
                self.chats_by_account[acc.id] = []
                errors.append(f"{acc.name}: {exc}")
        self._rebuild_tree()
        total = sum(len(v) for v in self.chats_by_account.values())
        msg = f"Аккаунтов: {len(self.accounts)} · чатов: {total}"
        if errors:
            msg += f" · ошибки: {len(errors)}"
            self.status.set(msg)
            if len(errors) <= 3:
                messagebox.showwarning("Часть аккаунтов не прочиталась", "\n".join(errors))
        else:
            self.status.set(msg)

    def _rebuild_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._node_data.clear()
        for acc in self.accounts:
            chats = self.chats_by_account.get(acc.id, [])
            acc_iid = f"acc:{acc.id}"
            self._node_data[acc_iid] = {"kind": "account", "account": acc}
            self.tree.insert(
                "",
                tk.END,
                iid=acc_iid,
                text=f"👤  {acc.name}  ({len(chats)})",
                values=(acc.user_dir, "", ""),
                open=True,
            )
            if not chats:
                empty_iid = f"empty:{acc.id}"
                self._node_data[empty_iid] = {"kind": "empty", "account": acc}
                self.tree.insert(
                    acc_iid,
                    tk.END,
                    iid=empty_iid,
                    text="  (чатов не найдено)",
                    values=("", "", ""),
                )
                continue
            for chat in chats:
                chat_iid = f"chat:{acc.id}:{chat.composer_id}"
                self._node_data[chat_iid] = {
                    "kind": "chat",
                    "account": acc,
                    "chat": chat,
                }
                when = ""
                ts = chat.last_updated_at or chat.created_at
                if ts:
                    when = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime(
                        "%Y-%m-%d"
                    )
                label = chat.name.replace("\n", " ") or "Без названия"
                if when:
                    label = f"{label}  ·  {when}"
                self.tree.insert(
                    acc_iid,
                    tk.END,
                    iid=chat_iid,
                    text=f"  💬  {label}",
                    values=(
                        chat.workspace_label or chat.workspace_id or "—",
                        str(chat.message_count),
                        chat.unified_mode or "—",
                    ),
                )

    def _selected_payloads(self) -> list[dict[str, Any]]:
        out = []
        for iid in self.tree.selection():
            data = self._node_data.get(iid)
            if data:
                out.append(data)
        return out

    def _selected_chats(self) -> list[tuple[Account, ChatSummary]]:
        result = []
        for data in self._selected_payloads():
            if data["kind"] == "chat":
                result.append((data["account"], data["chat"]))
        return result

    def _selected_account(self) -> Optional[Account]:
        for data in self._selected_payloads():
            return data.get("account")
        return None

    # ----- actions -----

    def on_add_account(self) -> None:
        path = filedialog.askdirectory(
            title="Выберите папку Cursor User (внутри globalStorage)",
        )
        if not path:
            return
        user_dir = Path(path)
        # If user picked Cursor root, descend into User
        if (user_dir / "User" / "globalStorage").is_dir():
            user_dir = user_dir / "User"
        elif (user_dir / "globalStorage").is_dir():
            pass
        elif user_dir.name == "globalStorage":
            user_dir = user_dir.parent
        else:
            messagebox.showerror(
                "Не та папка",
                "Нужна папка User, где есть globalStorage и workspaceStorage.\n"
                "Примеры:\n"
                "• Windows: %APPDATA%\\Cursor\\User\n"
                "• macOS: ~/Library/Application Support/Cursor/User\n"
                "• Linux: ~/.config/Cursor/User",
            )
            return

        suggested = guess_account_name(user_dir)
        name = simpledialog.askstring(
            "Название аккаунта",
            "Как назвать этот аккаунт в списке?",
            initialvalue=suggested,
            parent=self,
        )
        if not name:
            return
        self.accounts = add_account(name, user_dir)
        self.refresh_all()
        self.status.set(f"Добавлен аккаунт: {name}")

    def on_rename_account(self) -> None:
        acc = self._selected_account()
        if not acc:
            messagebox.showinfo("Нет выбора", "Выберите аккаунт или чат внутри него.")
            return
        name = simpledialog.askstring(
            "Переименовать",
            "Новое название аккаунта:",
            initialvalue=acc.name,
            parent=self,
        )
        if not name:
            return
        acc.name = name.strip()
        save_accounts(self.accounts)
        self.refresh_all()

    def on_remove_account(self) -> None:
        acc = self._selected_account()
        if not acc:
            messagebox.showinfo("Нет выбора", "Выберите аккаунт в списке.")
            return
        if not messagebox.askyesno(
            "Удалить из списка?",
            f"Убрать «{acc.name}» из приложения?\n"
            "Сами чаты Cursor на диске не удаляются.",
        ):
            return
        self.accounts = remove_account(acc.id, self.accounts)
        self.refresh_all()

    def on_open_folder(self) -> None:
        acc = self._selected_account()
        if not acc:
            messagebox.showinfo("Нет выбора", "Выберите аккаунт.")
            return
        path = acc.path
        if not path.is_dir():
            messagebox.showerror("Нет папки", str(path))
            return
        try:
            import os
            import subprocess
            import sys

            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
            self.status.set(f"Открыта папка: {path}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Не удалось открыть", str(exc))

    def on_double_click(self, _event=None) -> None:
        data = self._selected_payloads()
        if data and data[0]["kind"] == "account":
            self.on_open_folder()

    def on_export_file(self) -> None:
        selected = self._selected_chats()
        if not selected:
            messagebox.showinfo(
                "Нет выбора",
                "Выберите один или несколько чатов (не только аккаунт).",
            )
            return
        # All selected chats must be from same account for one export call
        by_acc: dict[str, list[tuple[Account, ChatSummary]]] = {}
        for acc, chat in selected:
            by_acc.setdefault(acc.id, []).append((acc, chat))
        if len(by_acc) > 1:
            messagebox.showinfo(
                "Разные аккаунты",
                "Для экспорта в один файл выберите чаты только из одного аккаунта.\n"
                "Или используйте «Перенести» между аккаунтами.",
            )
            return
        acc, _ = next(iter(by_acc.values()))[0]
        out = filedialog.asksaveasfilename(
            title="Сохранить bundle",
            defaultextension=".json",
            filetypes=[("Cursor chat bundle", "*.json"), ("All", "*.*")],
            initialfile=f"{acc.name}-chats.bundle.json",
        )
        if not out:
            return
        ids = [chat.composer_id for _, chat in by_acc[acc.id]]
        try:
            result = export_chats(
                CursorPaths(user_dir=acc.path),
                output=Path(out),
                composer_ids=ids,
            )
            messagebox.showinfo(
                "Экспорт готов",
                f"Сохранено чатов: {result['exported']}\n{out}",
            )
            self.status.set(f"Экспорт: {result['exported']} → {out}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Ошибка экспорта", f"{exc}\n\n{traceback.format_exc()}")

    def on_import_file(self) -> None:
        acc = self._selected_account()
        if not acc:
            messagebox.showinfo(
                "Куда импортировать?",
                "Сначала выберите целевой аккаунт в списке.",
            )
            return
        bundle = filedialog.askopenfilename(
            title="Выберите bundle.json",
            filetypes=[("Cursor chat bundle", "*.json"), ("All", "*.*")],
        )
        if not bundle:
            return
        workspace = self._ask_workspace(acc)
        if workspace is None:
            return
        if not self._confirm_cursor_closed(acc):
            return
        try:
            result = import_bundle(
                CursorPaths(user_dir=acc.path),
                Path(bundle),
                project_path=workspace,
            )
            messagebox.showinfo(
                "Импорт готов",
                f"Импортировано: {result.get('imported', 0)}\n"
                f"Аккаунт: {acc.name}\n"
                "Полностью перезапустите Cursor.",
            )
            self.refresh_all()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Ошибка импорта", f"{exc}\n\n{traceback.format_exc()}")

    def on_transfer(self) -> None:
        selected = self._selected_chats()
        if not selected:
            messagebox.showinfo(
                "Нет выбора",
                "Отметьте чат(ы) в аккаунте-источнике, затем нажмите «Перенести».",
            )
            return
        sources = {acc.id: acc for acc, _ in selected}
        if len(sources) > 1:
            messagebox.showinfo(
                "Разные источники",
                "Выберите чаты только из одного аккаунта-источника.",
            )
            return
        source = next(iter(sources.values()))
        targets = [a for a in self.accounts if a.id != source.id]
        if not targets:
            messagebox.showinfo(
                "Нужен второй аккаунт",
                "Добавьте аккаунт-получатель кнопкой «Добавить аккаунт».\n"
                "Укажите папку User другого профиля Cursor.",
            )
            return

        dialog = TransferDialog(self, source=source, targets=targets, count=len(selected))
        self.wait_window(dialog)
        if not dialog.result:
            return
        target: Account = dialog.result["target"]
        workspace: str = dialog.result["workspace"]

        if not self._confirm_cursor_closed(target):
            return

        ids = [chat.composer_id for _, chat in selected]
        try:
            with tempfile.TemporaryDirectory(prefix="cursor-migrate-") as tmp:
                bundle = Path(tmp) / "transfer.bundle.json"
                export_chats(
                    CursorPaths(user_dir=source.path),
                    output=bundle,
                    composer_ids=ids,
                )
                result = import_bundle(
                    CursorPaths(user_dir=target.path),
                    bundle,
                    project_path=workspace,
                )
            messagebox.showinfo(
                "Перенесено",
                f"Чатов: {result.get('imported', 0)}\n"
                f"Из «{source.name}» → в «{target.name}»\n"
                f"Проект: {workspace}\n\n"
                "Полностью закройте и снова откройте Cursor.",
            )
            self.refresh_all()
            self.status.set(
                f"Перенесено {result.get('imported', 0)}: {source.name} → {target.name}"
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Ошибка переноса", f"{exc}\n\n{traceback.format_exc()}")

    def _ask_workspace(self, account: Account) -> Optional[str]:
        paths = CursorPaths(user_dir=account.path)
        workspaces = list_workspaces(paths)
        labels = []
        for ws in workspaces:
            if ws.folder:
                labels.append(ws.folder)
        choice = WorkspaceDialog(self, account_name=account.name, folders=labels)
        self.wait_window(choice)
        return choice.result

    def _confirm_cursor_closed(self, account: Account) -> bool:
        paths = CursorPaths(user_dir=account.path)
        if is_cursor_running(paths):
            return messagebox.askyesno(
                "Cursor, похоже, открыт",
                f"Для аккаунта «{account.name}» есть активный WAL.\n"
                "Лучше полностью закрыть Cursor перед записью.\n\n"
                "Всё равно продолжить?",
            )
        return True


class TransferDialog(tk.Toplevel):
    def __init__(
        self,
        master: App,
        *,
        source: Account,
        targets: list[Account],
        count: int,
    ) -> None:
        super().__init__(master)
        self.title("Перенести чаты")
        self.resizable(False, False)
        self.result: Optional[dict[str, Any]] = None
        self.targets = targets
        self.transient(master)
        self.grab_set()

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text=f"Перенос {count} чат(ов) из «{source.name}»",
            style="Header.TLabel",
        ).pack(anchor=tk.W)

        ttk.Label(frame, text="Куда (аккаунт):").pack(anchor=tk.W, pady=(12, 4))
        self.target_var = tk.StringVar(value=targets[0].name)
        self.target_box = ttk.Combobox(
            frame,
            textvariable=self.target_var,
            values=[t.name for t in targets],
            state="readonly",
            width=48,
        )
        self.target_box.pack(fill=tk.X)
        self.target_box.bind("<<ComboboxSelected>>", self._reload_workspaces)

        ttk.Label(frame, text="Проект (папка workspace):").pack(anchor=tk.W, pady=(12, 4))
        row = ttk.Frame(frame)
        row.pack(fill=tk.X)
        self.workspace_var = tk.StringVar()
        self.workspace_box = ttk.Combobox(row, textvariable=self.workspace_var, width=44)
        self.workspace_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="Обзор…", command=self._browse).pack(side=tk.LEFT, padx=(6, 0))

        btns = ttk.Frame(frame)
        btns.pack(fill=tk.X, pady=(16, 0))
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Перенести", command=self._ok).pack(side=tk.RIGHT, padx=(0, 8))

        self._reload_workspaces()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.update_idletasks()
        self.geometry(f"+{master.winfo_rootx() + 80}+{master.winfo_rooty() + 80}")

    def _current_target(self) -> Account:
        name = self.target_var.get()
        for t in self.targets:
            if t.name == name:
                return t
        return self.targets[0]

    def _reload_workspaces(self, _event=None) -> None:
        target = self._current_target()
        folders = []
        try:
            for ws in list_workspaces(CursorPaths(user_dir=target.path)):
                if ws.folder:
                    folders.append(ws.folder)
        except Exception:
            folders = []
        self.workspace_box["values"] = folders
        if folders and not self.workspace_var.get():
            self.workspace_var.set(folders[0])

    def _browse(self) -> None:
        path = filedialog.askdirectory(title="Папка проекта для чатов", parent=self)
        if path:
            self.workspace_var.set(path)

    def _ok(self) -> None:
        ws = self.workspace_var.get().strip()
        if not ws:
            messagebox.showerror("Нужен проект", "Укажите папку проекта.", parent=self)
            return
        self.result = {"target": self._current_target(), "workspace": ws}
        self.destroy()


class WorkspaceDialog(tk.Toplevel):
    def __init__(self, master: tk.Tk, *, account_name: str, folders: list[str]) -> None:
        super().__init__(master)
        self.title("Проект для импорта")
        self.result: Optional[str] = None
        self.transient(master)
        self.grab_set()

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            frame,
            text=f"Куда положить чаты в «{account_name}»?",
        ).pack(anchor=tk.W)

        self.var = tk.StringVar(value=folders[0] if folders else "")
        box = ttk.Combobox(frame, textvariable=self.var, values=folders, width=56)
        box.pack(fill=tk.X, pady=(10, 0))

        row = ttk.Frame(frame)
        row.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(row, text="Обзор…", command=self._browse).pack(side=tk.LEFT)
        ttk.Button(row, text="Отмена", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(row, text="OK", command=self._ok).pack(side=tk.RIGHT, padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _browse(self) -> None:
        path = filedialog.askdirectory(parent=self)
        if path:
            self.var.set(path)

    def _ok(self) -> None:
        value = self.var.get().strip()
        if not value:
            messagebox.showerror("Нужен путь", "Укажите папку проекта.", parent=self)
            return
        self.result = value
        self.destroy()


def run_gui() -> int:
    app = App()
    app.mainloop()
    return 0


def main() -> int:
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
