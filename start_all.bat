@echo off
REM X9 system one-click launcher - double-click to start everything.
REM Real logic lives in start_all.ps1; this .bat just invokes it.

setlocal
set HERE=%~dp0

powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%start_all.ps1" %*
if errorlevel 1 (
    echo.
    echo [start_all] Startup failed. See logs above.
    pause
    exit /b 1
)

echo.
echo [start_all] Done. X9 services are running in the background.
echo   X9        : https://usx9.us
echo   Workspace : https://usx9.us/workspace/cross-border/
echo   Local     : http://localhost:8000/portal/
echo   Logs      : %HERE%logs\
echo.
echo Closing this window will NOT stop the servers. To stop them:
echo   stop_desktop.bat                (kills :8000)
echo.
pause
