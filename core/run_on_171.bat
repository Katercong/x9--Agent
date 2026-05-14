@echo off
REM Server launcher for 192.168.1.171 (uses venv .venv, listens on 0.0.0.0:18765).
REM Other machines access via http://192.168.1.171:18765/

setlocal
set PORT=18765
set HERE=%~dp0
cd /d "%HERE%"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] venv not found. Run setup_on_171.bat first.
    pause
    exit /b 1
)
set PY=.venv\Scripts\python.exe

netstat -an | findstr ":%PORT% " | findstr "LISTENING" >NUL
if not errorlevel 1 (
    echo [ERROR] Port %PORT% already in use.
    pause
    exit /b 1
)

echo [run] Starting server on http://0.0.0.0:%PORT%/  (--reload)
echo [run] LAN access: http://192.168.1.171:%PORT%/
echo.
"%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT% --reload --reload-dir app --reload-dir scripts
