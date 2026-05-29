@echo off
:: ============================================================
::  GitHub Intelligence Suite — Setup
::  Run this once after extracting the zip.
::  Creates a virtual environment and installs all dependencies.
:: ============================================================
setlocal EnableDelayedExpansion
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

title GitHub Intelligence Suite — Setup

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   GitHub Intelligence Suite — Setup         ║
echo  ╚══════════════════════════════════════════════╝
echo.

:: ── 1. Check Python ──────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found. Please install Python 3.10 or later from:
    echo          https://python.org/downloads
    echo.
    echo          Make sure to tick "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  ✓ Python %PY_VER% found.
echo.

:: ── 2. Create virtual environment ────────────────────────────
if exist ".venv\Scripts\activate.bat" (
    echo  ✓ Virtual environment already exists.
) else (
    echo  Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo  [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  ✓ Virtual environment created.
)
echo.

:: ── 3. Activate ───────────────────────────────────────────────
call ".venv\Scripts\activate.bat"
echo  ✓ Virtual environment activated.
echo.

:: ── 4. Upgrade pip ────────────────────────────────────────────
echo  Upgrading pip...
python -m pip install --upgrade pip --quiet
echo.

:: ── 5. Install extractor requirements ────────────────────────
echo  Installing GitHub Extractor dependencies...
python -m pip install PyGithub requests scrapling
if %errorlevel% neq 0 (
    echo  [WARN] Some extractor packages may have failed. Continuing...
)
echo.

:: ── 6. Install PIA requirements ───────────────────────────────
if exist "pia\requirements.txt" (
    echo  Installing PIA dependencies (this may take a few minutes)...
    python -m pip install -r pia\requirements.txt
    if %errorlevel% neq 0 (
        echo  [WARN] Some PIA packages may have failed. Check the output above.
    )
    echo.
) else (
    echo  [WARN] pia\requirements.txt not found — skipping PIA deps.
    echo         Extract pia_v3_reputation.zip to get pia\
    echo.
)

:: ── 7. Scrapling browser backend (optional) ──────────────────
echo  Installing optional Scrapling browser backend for stealth scraping...
python -m scrapling install 2>nul
echo  (You can skip this — basic scraping still works without it)
echo.

:: ── 8. Summary ────────────────────────────────────────────────
echo  ══════════════════════════════════════════════
echo   Setup complete!
echo  ══════════════════════════════════════════════
echo.
echo   Next steps:
echo   1. Edit pia\config.yaml  with your API keys and project paths
echo   2. Double-click  run_gui.bat   to open the graphical interface
echo      OR run        launcher.bat  for the command-line menu
echo.
echo   Quick start (command line):
echo      launcher.bat
echo.
echo   The virtual environment has been created at:
echo      %SCRIPT_DIR%.venv\
echo   All future launches activate it automatically.
echo.

pause
