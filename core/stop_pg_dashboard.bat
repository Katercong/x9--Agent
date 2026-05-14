@echo off
REM Stop X9 PostgreSQL dashboard on port 18766.

setlocal
set PORT=18766

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo [stop_pg_dashboard] Killing PID %%a on port %PORT%
    taskkill /PID %%a /F >NUL 2>NUL
)

echo [stop_pg_dashboard] Done.
