#!/usr/bin/env bash
cd "$(dirname "$0")"
echo "Перенос чатов Cursor"
python3 -m pip install -e . -q
exec python3 run_gui.py
