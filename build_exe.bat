@echo off
:: ============================================================
::  GitHub Intelligence Suite — Build Standalone EXE
::
::  Creates a single distributable .exe using PyInstaller.
::  The output is in dist\GithubIntelSuite\
::
::  Run this from the suite folder after setup.bat.
::  Share the resulting dist\ folder with non-technical users —
::  they only need to double-click GithubIntelSuite.exe.
::
::  Requirements:  pip install pyinstaller  (done automatically)
:: ============================================================
setlocal EnableDelayedExpansion
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

title Building GitHub Intelligence Suite EXE...

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   Building Standalone Installer / EXE       ║
echo  ╚══════════════════════════════════════════════╝
echo.

:: Activate venv
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo  [WARN] .venv not found. Run setup.bat first.
)

:: Install PyInstaller
echo  Installing PyInstaller...
pip install pyinstaller --quiet
echo.

:: Clean previous build
if exist "build\"   rd /s /q "build"
if exist "dist\"    rd /s /q "dist"
if exist "*.spec"   del /q *.spec

echo  Building EXE (this takes 1-3 minutes)...
echo.

:: Build the GUI app as a windowed EXE (no console window)
pyinstaller ^
    --name "GithubIntelSuite" ^
    --onedir ^
    --windowed ^
    --add-data "pia;pia" ^
    --add-data "github_extractor_v2.py;." ^
    --add-data "platform_extractor.py;." ^
    --add-data "github_viewer_v2.py;." ^
    --hidden-import "tkinter" ^
    --hidden-import "tkinter.ttk" ^
    --hidden-import "tkinter.scrolledtext" ^
    --hidden-import "tkinter.filedialog" ^
    --hidden-import "tkinter.messagebox" ^
    gui_app.py

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] PyInstaller build failed. Check the output above.
    pause
    exit /b 1
)

echo.
echo  ══════════════════════════════════════════════
echo   Build successful!
echo  ══════════════════════════════════════════════
echo.
echo   Distributable folder:
echo     %SCRIPT_DIR%dist\GithubIntelSuite\
echo.
echo   Share the entire  dist\GithubIntelSuite\  folder.
echo   Users double-click  GithubIntelSuite.exe  to launch.
echo.
echo   NOTE: The EXE bundles the GUI app and launcher scripts.
echo         Python scripts (extractor, viewer) are included too.
echo         The user still needs to:
echo           1. Edit config.yaml for their API keys
echo           2. Have internet access for the extractors
echo.

:: Open the output folder
explorer "dist\GithubIntelSuite" 2>nul

pause
