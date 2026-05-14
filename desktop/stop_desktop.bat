@echo off
REM Stop the X9 Desktop server (kills whichever python process holds port 8000).

setlocal enabledelayedexpansion
set PORT=8000

set FOUND=
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    set FOUND=%%P
)

if "%FOUND%"=="" (
    echo [stop_desktop] Nothing listening on port %PORT%. Server is already stopped.
    timeout /t 2 >NUL
    exit /b 0
)

echo [stop_desktop] Killing PID=%FOUND% on port %PORT%...
taskkill /PID %FOUND% /T /F

timeout /t 1 >NUL
netstat -an | findstr ":%PORT% " | findstr "LISTENING" >NUL 2>NUL
if errorlevel 1 (
    echo [stop_desktop] OK: port %PORT% is now free.
) else (
    echo [stop_desktop] WARN: something still on %PORT%. Try Task Manager.
)
pause >NUL
