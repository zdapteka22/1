@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ========================================
echo   Перенос чатов Cursor
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  where py >nul 2>&1
  if errorlevel 1 (
    echo [Ошибка] Python не найден.
    echo Установите Python 3.10+ с https://www.python.org/downloads/
    echo При установке отметьте "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
  )
  set "PY=py -3"
) else (
  set "PY=python"
)

echo Установка / обновление...
%PY% -m pip install -e . -q
if errorlevel 1 (
  echo [Ошибка] Не удалось установить пакет.
  pause
  exit /b 1
)

echo Запуск окна...
%PY% run_gui.py
if errorlevel 1 (
  echo.
  echo [Ошибка] Приложение завершилось с ошибкой.
  echo Если пишет про tkinter — переустановите Python с галочкой tcl/tk.
  echo.
  pause
  exit /b 1
)

endlocal
