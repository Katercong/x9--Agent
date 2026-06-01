@echo off
REM Atomic restart for X9 desktop FastAPI backend on :8000.
REM Used to apply new /portal/* SPA routes after editing desktop/backend/main.py.
REM
REM What it does:
REM   1. Find PID listening on :8000 (uvicorn)
REM   2. Stop it
REM   3. Immediately start a fresh uvicorn with the new code
REM   4. Cloudflare Tunnel auto-reconnects in 1-2s -> usx9.us/portal/ goes live
REM
REM Old routes (/, /login, /workspace/cross-border/, /api/local/*) are unchanged.
REM Chrome extension loses one heartbeat but auto-reconnects.

setlocal enabledelayedexpansion
set PORT=8000
set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe
set HERE=%~dp0
cd /d "%HERE%\.."

echo [restart_desktop] Looking up PID on :%PORT%...
set FOUND=
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    set FOUND=%%P
)

if not "%FOUND%"=="" (
    echo [restart_desktop] Stopping PID=%FOUND%
    taskkill /PID %FOUND% /T /F >nul 2>nul
    timeout /t 1 /nobreak >nul
) else (
    echo [restart_desktop] No process on :%PORT% — starting fresh.
)

echo [restart_desktop] Starting new backend with /portal/* routes...
set X9_NO_BROWSER=1

REM Foreground uvicorn (this window stays open until Ctrl+C).
"%PY%" -m uvicorn desktop.backend.main:app --host 127.0.0.1 --port %PORT%
