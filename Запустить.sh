#!/usr/bin/env bash
cd "$(dirname "$0")"
set -e
echo "Перенос чатов Cursor"
echo "Папка: $(pwd)"
python3 --version
python3 -m pip install -e .
python3 run_gui.py
status=$?
echo "Код выхода: $status"
read -r -p "Нажмите Enter..." _
exit "$status"
