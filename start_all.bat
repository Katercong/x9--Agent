@echo off
REM X9 system one-click launcher - double-click to start everything.
REM Real logic lives in start_all.ps1; this .bat just invokes it.

setlocal
set HERE=%~dp0

powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%start_all.ps1"
if errorlevel 1 (
    echo.
    echo [start_all] Startup failed. See logs above.
    pause
    exit /b 1
)

echo.
echo [start_all] Done. X9 services are running in the background.
echo   Workspace : http://localhost:8000/workspace/cross-border/
echo   Desktop   : http://localhost:8000
echo   Public    : https://usx9.us
echo.
echo Closing this window will NOT stop the servers. To stop them:
echo   stop_desktop.bat                (kills :8000)
echo.
pause
