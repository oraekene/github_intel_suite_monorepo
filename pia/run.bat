@echo off
REM ============================================================
REM  PIA — Project Intelligence Analyst
REM  Run Script — double-click or call from Task Scheduler
REM ============================================================

REM Get the directory this script lives in
set SCRIPT_DIR=%~dp0

REM Activate virtual environment
call "%SCRIPT_DIR%.venv\Scripts\activate.bat"
if %errorlevel% neq 0 (
    echo [ERROR] Could not activate virtual environment.
    echo         Run setup.bat first.
    pause
    exit /b 1
)

REM Log file (append each run)
set LOGFILE=%SCRIPT_DIR%pia_run.log

echo. >> "%LOGFILE%"
echo ======================================== >> "%LOGFILE%"
echo Run started: %date% %time% >> "%LOGFILE%"
echo ======================================== >> "%LOGFILE%"

REM Run the pipeline
cd /d "%SCRIPT_DIR%"
python scheduler\run_pipeline.py %* 2>&1 | tee -a "%LOGFILE%"

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Pipeline failed. Check pia_run.log for details.
) else (
    echo.
    echo [DONE] Pipeline complete. Reports saved to your configured output folder.
)

echo.
echo Log: %LOGFILE%
echo.

REM Only pause if run interactively (not from Task Scheduler)
if "%1"=="" (
    pause
)
