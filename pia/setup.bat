@echo off
REM ============================================================
REM  PIA — Project Intelligence Analyst
REM  Windows 10 Setup Script
REM  Run once: setup.bat
REM  Then run weekly: run.bat
REM ============================================================

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║  PIA Setup — Project Intelligence Analyst║
echo  ╚══════════════════════════════════════════╝
echo.

REM ── Check Python ─────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+ from https://python.org
    echo         Make sure to tick "Add Python to PATH" during install.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% found

REM ── Create virtual environment ───────────────────────────────
if not exist ".venv" (
    echo [SETUP] Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
) else (
    echo [OK] Virtual environment already exists
)

REM ── Activate venv ────────────────────────────────────────────
call .venv\Scripts\activate.bat
echo [OK] Virtual environment activated

REM ── Upgrade pip ──────────────────────────────────────────────
echo [SETUP] Upgrading pip...
python -m pip install --upgrade pip --quiet

REM ── Install CPU-only PyTorch first (smaller download) ────────
echo [SETUP] Installing PyTorch (CPU-only, ~250MB)...
pip install torch --index-url https://download.pytorch.org/whl/cpu --quiet
if %errorlevel% neq 0 (
    echo [WARN] PyTorch CPU install failed — trying standard install...
    pip install torch --quiet
)

REM ── Install all other requirements ───────────────────────────
echo [SETUP] Installing requirements (this may take a few minutes)...
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERROR] Requirements install failed. Check your internet connection.
    pause
    exit /b 1
)

echo [OK] All packages installed

REM ── Download embedding model ─────────────────────────────────
echo [SETUP] Downloading embedding model (all-MiniLM-L6-v2, ~90MB)...
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
if %errorlevel% neq 0 (
    echo [WARN] Model download failed — will retry on first run.
)
echo [OK] Embedding model ready

REM ── Create output directories ────────────────────────────────
echo [SETUP] Creating output directories...
mkdir "reports" 2>nul

REM ── Remind user about config ──────────────────────────────────
echo.
echo  ┌─────────────────────────────────────────────────────┐
echo  │  SETUP COMPLETE                                      │
echo  │                                                      │
echo  │  NEXT STEPS:                                         │
echo  │  1. Edit config.yaml — fill in all ^<REPLACE_THIS^>   │
echo  │     values (API keys, project paths, etc.)           │
echo  │                                                      │
echo  │  2. Run the pipeline:                                │
echo  │     run.bat                                          │
echo  │                                                      │
echo  │  3. (Optional) Schedule weekly runs:                 │
echo  │     setup_scheduler.bat                              │
echo  └─────────────────────────────────────────────────────┘
echo.

pause
