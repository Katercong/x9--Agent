@echo off
REM Restart the X9 Database server. Stops then starts.

setlocal
set HERE=%~dp0
cd /d "%HERE%"

call "%HERE%stop.bat" 2>/dev/null
echo.
echo [restart] Restarting in 2 seconds...
timeout /t 2 >/dev/null
call "%HERE%run.bat"
