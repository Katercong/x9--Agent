@echo off
REM Reset (or add) an API key for a user. Run this when:
REM   - Someone (incl. yourself) lost their token
REM   - You can't log into the web UI any more
REM   - You want to rotate a key

setlocal
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

if "%~1"=="" (
    echo Usage:
    echo     reset_key.bat ^<username^>          rotate (revoke old, issue new)
    echo     reset_key.bat ^<username^> --add    add another key without revoking
    echo     reset_key.bat --list              list all users
    echo.
    %PY% scripts\reset_user_key.py --list
    pause
    exit /b 0
)

%PY% scripts\reset_user_key.py %*
echo.
echo Press any key to close...
pause >/dev/null
