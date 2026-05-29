@echo off
REM ============================================================
REM  PIA — Register Windows Task Scheduler job
REM  Run as Administrator for best results
REM ============================================================

REM Read schedule from config (simplified — hardcoded defaults here;
REM edit below to match your config.yaml schedule settings)

set TASK_NAME=PIA_ProjectIntelligenceAnalyst
set SCRIPT_DIR=%~dp0
set RUN_SCRIPT=%SCRIPT_DIR%run.bat

REM Weekly on Monday at 09:00
set SCHEDULE_TYPE=WEEKLY
set SCHEDULE_DAY=MON
set SCHEDULE_TIME=09:00

echo.
echo [SCHEDULER] Registering Windows Task: %TASK_NAME%
echo             Schedule: %SCHEDULE_TYPE% on %SCHEDULE_DAY% at %SCHEDULE_TIME%
echo             Script: %RUN_SCRIPT%
echo.

REM Delete old task if exists
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

REM Create the scheduled task
schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "\"%RUN_SCRIPT%\" --scheduled" ^
    /sc %SCHEDULE_TYPE% ^
    /d %SCHEDULE_DAY% ^
    /st %SCHEDULE_TIME% ^
    /rl HIGHEST ^
    /f

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Task creation failed.
    echo         Try running this script as Administrator.
    pause
    exit /b 1
)

echo.
echo [OK] Task '%TASK_NAME%' created successfully.
echo      It will run every Monday at 09:00.
echo.
echo      To run it immediately for testing:
echo        schtasks /run /tn "%TASK_NAME%"
echo.
echo      To view task:
echo        Task Scheduler ^> Task Scheduler Library ^> %TASK_NAME%
echo.
echo      To delete task:
echo        schtasks /delete /tn "%TASK_NAME%" /f
echo.

pause
