# Перенос чатов Cursor

Оконное приложение: **аккаунты → чаты внутри → кнопки «Перенести / Открыть / Экспорт»**.

Чаты Cursor лежат локально в `state.vscdb`, не в облаке. Добавляете папки разных аккаунтов — и переносите чаты мышкой.

## Быстрый старт

```bash
cd путь/к/репозиторию
python3 -m pip install -e .

# Открыть окошко
python3 run_gui.py
# или
python3 -m cursor_chat_migrate
# или
cursor-chat-migrate-gui
```

Нужен Python 3.10+ и `tkinter` (на Ubuntu: `sudo apt install python3-tk`).

## Как пользоваться в окошке

1. Запустите приложение — откроется окно.
2. Слева/в дереве: **название аккаунта**, внутри него — **его чаты**.
3. **Добавить аккаунт** — укажите папку `User` другого профиля Cursor  
   (Windows: `%APPDATA%\Cursor\User`, macOS: `~/Library/Application Support/Cursor/User`, Linux: `~/.config/Cursor/User`).  
   Можно скопировать папку `User` со старого ПК и указать её.
4. Выберите чат(ы) в одном аккаунте → **Перенести** → выберите аккаунт-получатель и папку проекта.
5. Полностью закройте и снова откройте Cursor.

Другие кнопки:

| Кнопка | Действие |
|--------|----------|
| Открыть папку | Открыть каталог данных выбранного аккаунта |
| Обновить | Перечитать чаты с диска |
| Переименовать | Имя аккаунта в списке |
| Удалить аккаунт | Убрать из приложения (чаты на диске не трогает) |
| Экспорт в файл | Сохранить выбранные чаты в `.json` |
| Импорт из файла | Загрузить `.json` в выбранный аккаунт |

Список аккаунтов сохраняется в `~/.cursor-chat-migrate/accounts.json`.

## CLI (по желанию)

```bash
python3 -m cursor_chat_migrate gui
python3 -m cursor_chat_migrate list
python3 -m cursor_chat_migrate export --all -o chats.bundle.json
python3 -m cursor_chat_migrate import chats.bundle.json --workspace /path/to/project
```

## Тесты

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest -q
```

## License

MIT
