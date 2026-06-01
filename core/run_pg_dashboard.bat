@echo off
REM X9 PostgreSQL dashboard launcher - opens http://localhost:18766/

setlocal
set PORT=18766
set HERE=%~dp0
cd /d "%HERE%"

set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not exist ".venv\Scripts\python.exe" (
    py -3.11 --version >NUL 2>NUL
    if not errorlevel 1 set "PY=py -3.11"
)
%PY% --version >NUL 2>NUL
if errorlevel 1 (
    echo [ERROR] Python 3.11 not found. Install Python or add python.exe to PATH.
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
%PY% -m uvicorn app.pg_dashboard:app --host 127.0.0.1 --port %PORT%

