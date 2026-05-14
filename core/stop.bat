@echo off
REM Stop the X9 Database server (kills whichever python process holds port 18765 / your PORT).

setlocal enabledelayedexpansion
set PORT=18765
set HERE=%~dp0
cd /d "%HERE%"

REM Find PID of process listening on PORT
set FOUND=
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    set FOUND=%%P
)

if "%FOUND%"=="" (
    echo [stop] Nothing listening on port %PORT%. Server is already stopped.
    timeout /t 2 >/dev/null
    exit /b 0
)

echo [stop] Found server process PID=%FOUND% on port %PORT%
echo [stop] Killing PID %FOUND% and its children...

REM Kill the process and any child processes (uvicorn --reload sometimes spawns a worker)
taskkill /PID %FOUND% /T /F

REM Belt-and-braces: nuke any python.exe processes whose parent was the killed PID
REM (commented out - too aggressive for shared machines)

echo.
echo [stop] Verifying...
timeout /t 1 >/dev/null
netstat -an | findstr ":%PORT% " | findstr "LISTENING" >/dev/null
if errorlevel 1 (
    echo [stop] OK: port %PORT% is now free.
) else (
    echo [stop] WARN: something is still listening on %PORT%. Try Task Manager.
)

echo.
echo Press any key to close...
pause >/dev/null
