@echo off
REM Stop the X9 Desktop backend (port 8000).

setlocal enabledelayedexpansion
set PORT=8000

set FOUND=
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    set FOUND=%%P
)

if "%FOUND%"=="" (
    echo [stop_desktop] Nothing listening on port %PORT%. Already stopped.
    timeout /t 2 >nul
    exit /b 0
)

echo [stop_desktop] Found PID=%FOUND% on port %PORT%
echo [stop_desktop] Killing PID %FOUND% and children...
taskkill /PID %FOUND% /T /F

timeout /t 1 >nul
netstat -an | findstr ":%PORT% " | findstr "LISTENING" >nul
if errorlevel 1 (
    echo [stop_desktop] OK: port %PORT% is now free.
) else (
    echo [stop_desktop] WARN: something is still listening on %PORT%.
)

echo.
echo Press any key to close...
pause >nul
