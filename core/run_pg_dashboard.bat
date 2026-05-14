@echo off
REM X9 PostgreSQL dashboard launcher - opens http://localhost:18766/

setlocal
set PY=D:\Python\python.exe
set PORT=18766
set HERE=%~dp0
cd /d "%HERE%"

if not exist "%PY%" (
    echo [ERROR] Python not found at %PY%
    pause
    exit /b 1
)

netstat -an | findstr ":%PORT% " | findstr "LISTENING" >NUL
if not errorlevel 1 (
    echo [run_pg_dashboard] Already running on http://localhost:%PORT%/
    start "" http://localhost:%PORT%/
    exit /b 0
)

echo [run_pg_dashboard] Starting PostgreSQL dashboard on http://localhost:%PORT%/
echo [run_pg_dashboard] Close this window or run stop_pg_dashboard.bat to stop.
start "" http://localhost:%PORT%/
"%PY%" -m uvicorn app.pg_dashboard:app --host 127.0.0.1 --port %PORT%

