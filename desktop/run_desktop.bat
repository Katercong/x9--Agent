@echo off
REM X9 Desktop UI launcher
REM Starts FastAPI on http://localhost:8000/ and opens the workspace in browser.
REM Run from project root: F:\Claude_Project\X9_AI_system\desktop\run_desktop.bat

setlocal
set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe
set PORT=8000
set HERE=%~dp0
REM Working directory must be the project root (one level up from desktop/)
cd /d "%HERE%\.."

if not exist "%PY%" (
    echo [ERROR] Python 3.11 not found at %PY%
    echo Edit run_desktop.bat to point at your python.exe
    pause
    exit /b 1
)

netstat -an | findstr ":%PORT% " | findstr "LISTENING" >NUL 2>NUL
if not errorlevel 1 (
    echo [ERROR] Port %PORT% is already in use.
    echo Stop whatever is using it, then re-run.
    pause
    exit /b 1
)

REM One-time: initialise DB tables + seed tag_definitions (idempotent)
echo [run_desktop] Running migration 001_init...
"%PY%" -m desktop.backend.migrations.001_init >NUL 2>NUL

echo.
echo [run_desktop] Starting desktop API on http://localhost:%PORT%/workspace/cross-border/
echo [run_desktop] Ctrl+C to stop.
echo.
if /I not "%X9_NO_BROWSER%"=="1" start "" "http://localhost:%PORT%/workspace/cross-border/"
"%PY%" -m uvicorn desktop.backend.main:app --host 127.0.0.1 --port %PORT% --reload --reload-dir desktop\backend
goto :eof
