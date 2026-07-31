# cursor-chat-migrate

Перенос чатов Cursor между машинами и аккаунтами.

Cursor **не хранит** историю чатов в облачном аккаунте — она лежит локально в SQLite (`state.vscdb`). Этот CLI экспортирует чаты в портативный bundle и импортирует их в данные другого аккаунта/установки.

## Установка

```bash
python3 -m pip install -e .
# или без установки:
python3 -m cursor_chat_migrate --help
```

## Перенос с другого аккаунта

### 1. На старом аккаунте (откуда забираете)

1. Полностью закройте Cursor.
2. Найдите и экспортируйте чаты:

```bash
# Показать, куда смотрит инструмент
python3 -m cursor_chat_migrate paths

# Список чатов
python3 -m cursor_chat_migrate list

# Экспорт всех
python3 -m cursor_chat_migrate export --all -o ~/cursor-chats.bundle.json

# Или только один чат
python3 -m cursor_chat_migrate export --id <composerId> -o ~/one-chat.bundle.json

# Или чаты одного проекта
python3 -m cursor_chat_migrate export --workspace /path/to/project --all -o ~/project.bundle.json
```

3. Скопируйте `*.bundle.json` на машину/профиль нового аккаунта (флешка, облако, мессенджер).

### 2. На новом аккаунте (куда переносите)

1. Войдите в нужный аккаунт Cursor и **полностью закройте** приложение.
2. Импортируйте bundle в нужный проект:

```bash
python3 -m cursor_chat_migrate import ~/cursor-chats.bundle.json \
  --workspace /path/to/same-or-new-project
```

3. Снова откройте Cursor (обычного Reload Window недостаточно).
4. Откройте указанный проект — импортированные чаты должны появиться в списке.

Перед записью инструмент делает backup `state.vscdb` рядом с БД (или в `--backup-dir`).

## Полезные команды

| Команда | Назначение |
|--------|------------|
| `paths` | Путь к `User/` текущего Cursor |
| `workspaces` | Список workspaceStorage |
| `list [--workspace …] [--json]` | Чаты |
| `export --all/-o/--id` | Выгрузка |
| `import bundle --workspace …` | Загрузка |
| `import … --dry-run` | Проверка без записи |

### Свой путь к данным Cursor

```bash
# macOS
python3 -m cursor_chat_migrate --user-dir "$HOME/Library/Application Support/Cursor/User" list

# Linux
python3 -m cursor_chat_migrate --user-dir "$HOME/.config/Cursor/User" list

# Windows (PowerShell)
python -m cursor_chat_migrate --user-dir "$env:APPDATA\Cursor\User" list
```

Или переменная окружения: `CURSOR_USER_DIR`.

## Что переносится

- Метаданные чата (`composerData`)
- Сообщения (`bubbleId`)
- Checkpoints агента (`checkpointId`)
- Request context и content-blobs, если есть
- Привязка к workspace (Cursor 3.0 `composer.composerHeaders` + selected tabs)

При импорте создаются **новые UUID**, поэтому один и тот же bundle можно импортировать повторно без конфликтов.

## Чего инструмент не делает

- Не читает чаты «из облака другого аккаунта» — нужен доступ к файлам старого профиля Cursor на диске.
- Не переносит cloud agent runs с `cursor.com/agents` между аккаунтами (это серверные объекты).
- Не гарантирует продолжение агент-сессии, если checkpoint-пути ссылались на другую машину — **история сообщений** при этом читается.

## Тесты

```bash
python3 -m pip install -e ".[dev]"
pytest -q
```

## License

MIT
