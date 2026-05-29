@echo off
:: ============================================================
::  GitHub Intelligence Suite — CLI / TUI Launcher
::  For developers who prefer the command line.
::  Double-click OR call with an argument for shortcuts:
::    launcher.bat extract
::    launcher.bat view stats
::    launcher.bat pia
:: ============================================================
setlocal EnableDelayedExpansion
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

title GitHub Intelligence Suite

:: ── Activate virtual environment (if present) ─────────────
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo  [WARN] No .venv found. Using system Python. Run setup.bat first if needed.
)

:: ── Launch the Python TUI ──────────────────────────────────
python launcher.py %*

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Launcher exited with error %errorlevel%.
    echo          Make sure you ran setup.bat first.
    pause
)
