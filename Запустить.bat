@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ========================================
echo   Perenos chatov Cursor
echo ========================================
echo.
echo Papka: %CD%
echo.

where python >nul 2>&1
if errorlevel 1 goto try_py
set "PY=python"
goto have_python

:try_py
where py >nul 2>&1
if errorlevel 1 goto no_python
set "PY=py -3"
goto have_python

:no_python
echo [OSHIBKA] Python ne nayden.
echo.
echo 1. Skachayte Python 3.10+ :
echo    https://www.python.org/downloads/
echo 2. Pri ustanovke otmet'te:
echo    [x] Add python.exe to PATH
echo 3. Zakroyte eto okno, ustanovite Python, zapustite bat snova.
echo.
pause
exit /b 1

:have_python
echo Python:
%PY% --version
if errorlevel 1 (
  echo [OSHIBKA] Python ne zapuskaetsya.
  pause
  exit /b 1
)
echo.

echo Ustanovka paketa...
%PY% -m pip install -e .
if errorlevel 1 (
  echo.
  echo [OSHIBKA] pip install ne udalsya.
  echo Poprobuyte v cmd:
  echo   %PY% -m pip install -e .
  echo.
  pause
  exit /b 1
)
echo.

echo Zapusk okna...
echo Esli okno srazu zakroetsya - nicheje budet tekst oshibki.
echo.
%PY% run_gui.py
set "ERR=%ERRORLEVEL%"
echo.
if not "%ERR%"=="0" (
  echo [OSHIBKA] Kod vyhoda: %ERR%
  echo.
  echo Chasto pomogaet:
  echo  - perezapustit' bat ot imeni administratora
  echo  - pereustanovit' Python s galochkoy tcl/tk / Add to PATH
  echo  - zapustit' v cmd:  %PY% run_gui.py
  echo.
) else (
  echo Prilozhenie zakryto.
  echo.
)

echo ----------------------------------------
echo Okno ne zakroetsya samo - nazhmite klavishu.
pause
endlocal
exit /b %ERR%
