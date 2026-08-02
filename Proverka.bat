@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo   Avto-proverka perenosa chatov
echo ========================================
echo.
echo Papka: %CD%
echo.

where python >nul 2>&1
if errorlevel 1 (
  where py >nul 2>&1
  if errorlevel 1 (
    echo [OSHIBKA] Python ne nayden.
    echo Ustani Python s https://www.python.org/downloads/
    echo Galochka: Add python.exe to PATH
    pause
    exit /b 1
  )
  set "PY=py -3"
) else (
  set "PY=python"
)

%PY% --version
echo.

echo [1/3] Ustanovka...
%PY% -m pip install -e ".[dev]"
if errorlevel 1 (
  echo pip FAILED
  pause
  exit /b 1
)

echo.
echo [2/3] pytest...
%PY% -m pytest -q
if errorlevel 1 (
  echo pytest FAILED
  pause
  exit /b 1
)

echo.
echo [3/3] Roundtrip export/import/obratnyy import...
%PY% scripts\auto_verify.py
if errorlevel 1 (
  echo auto_verify FAILED
  pause
  exit /b 1
)

echo.
echo ========================================
echo   VSE PROVERKI PROYDENY
echo ========================================
pause
endlocal
