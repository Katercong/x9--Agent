@echo off
REM Reset (or add) an API key for a user. Run this when:
REM   - Someone (incl. yourself) lost their token
REM   - You can't log into the web UI any more
REM   - You want to rotate a key

setlocal
set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe
set HERE=%~dp0
cd /d "%HERE%"

if "%~1"=="" (
    echo Usage:
    echo     reset_key.bat ^<username^>          rotate (revoke old, issue new)
    echo     reset_key.bat ^<username^> --add    add another key without revoking
    echo     reset_key.bat --list              list all users
    echo.
    "%PY%" scripts\reset_user_key.py --list
    pause
    exit /b 0
)

"%PY%" scripts\reset_user_key.py %*
echo.
echo Press any key to close...
pause >/dev/null
