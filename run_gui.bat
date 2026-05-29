@echo off
:: ============================================================
::  GitHub Intelligence Suite — GUI Launcher
::  Non-technical users: double-click this file.
::  (Run setup.bat first if you haven't already.)
:: ============================================================
setlocal
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

title GitHub Intelligence Suite

:: Activate virtual environment (if present)
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo  No .venv found — using system Python.
    echo  If the app fails to open, run setup.bat first.
    echo.
)

:: Check tkinter is available
python -c "import tkinter" 2>nul
if %errorlevel% neq 0 (
    echo  [ERROR] tkinter not found.
    echo  Reinstall Python from https://python.org and ensure "tcl/tk and IDLE" is selected.
    pause
    exit /b 1
)

:: Launch the GUI (pythonw hides the console window on Windows)
start "" pythonw gui_app.py

:: If pythonw isn't available, fall back to python
if %errorlevel% neq 0 (
    python gui_app.py
)
