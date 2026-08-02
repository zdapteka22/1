@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

set "APPDIR=%~dp0cursor-chat-migrate"
set "ZIP=%TEMP%\cursor-chat-migrate.zip"
set "URL=https://github.com/zdapteka22/1/archive/refs/heads/cursor/chat-migrate-cli-0eee.zip"

echo ========================================
echo   Perenos chatov Cursor
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  where py >nul 2>&1
  if errorlevel 1 (
    echo [OSHIBKA] Python ne nayden.
    echo Skachayte: https://www.python.org/downloads/
    echo Otmet'te: Add python.exe to PATH
    pause
    exit /b 1
  )
  set "PY=py -3"
) else (
  set "PY=python"
)

%PY% --version
echo.

if not exist "%APPDIR%\run_gui.py" (
  echo Skachivayu programmu...
  powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%URL%' -OutFile '%ZIP%' -UseBasicParsing } catch { exit 1 }"
  if errorlevel 1 (
    echo [OSHIBKA] Ne udalos skachat arhiv.
    echo %URL%
    pause
    exit /b 1
  )
  if exist "%APPDIR%" rmdir /s /q "%APPDIR%"
  mkdir "%APPDIR%" >nul 2>&1
  powershell -NoProfile -Command "Expand-Archive -Path '%ZIP%' -DestinationPath '%TEMP%\cursor-chat-migrate-unpack' -Force"
  if errorlevel 1 (
    echo [OSHIBKA] Ne udalos raspakovat.
    pause
    exit /b 1
  )
  for /d %%D in ("%TEMP%\cursor-chat-migrate-unpack\*") do (
    xcopy "%%~fD\*" "%APPDIR%\" /E /I /Y >nul
  )
  rmdir /s /q "%TEMP%\cursor-chat-migrate-unpack" >nul 2>&1
  del "%ZIP%" >nul 2>&1
  echo Gotovo.
  echo.
)

cd /d "%APPDIR%"
echo Papka: %CD%
echo.
echo Ustanovka...
%PY% -m pip install -e .
if errorlevel 1 (
  echo [OSHIBKA] pip install.
  pause
  exit /b 1
)

echo.
echo Zapusk okna...
%PY% run_gui.py
set "ERR=%ERRORLEVEL%"
echo.
if not "%ERR%"=="0" echo [OSHIBKA] Kod: %ERR%
pause
exit /b %ERR%
