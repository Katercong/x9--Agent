@echo off
REM Push project + database + intern materials to \\192.168.1.171\FShare
REM Run this on YOUR machine (the one currently hosting F:\Claude_Project\Database).

setlocal
set SRC=F:\Claude_Project\Database
set INTERN_SRC=F:\实习生
set DST=\\192.168.1.171\FShare\Database
set INTERN_DST=\\192.168.1.171\FShare\实习生

echo [migrate] Stopping local service if running ...
call "%SRC%\stop.bat" >NUL 2>&1

echo [migrate] Backing up local database.db ...
if exist "%SRC%\database.db" (
    copy /Y "%SRC%\database.db" "%SRC%\database.db.before_migrate.bak" >NUL
)

echo [migrate] Probing share \\192.168.1.171\FShare ...
if not exist "\\192.168.1.171\FShare" (
    echo [ERROR] Cannot reach \\192.168.1.171\FShare. Check network/permissions.
    pause
    exit /b 1
)

echo [migrate] Copying project code + database to %DST% ...
robocopy "%SRC%" "%DST%" /E /XD __pycache__ .venv .git /XF *.pyc *.log /R:1 /W:1 /NFL /NDL
if errorlevel 8 goto :err

echo [migrate] Copying intern materials to %INTERN_DST% ...
robocopy "%INTERN_SRC%" "%INTERN_DST%" /E /R:1 /W:1 /NFL /NDL
if errorlevel 8 goto :err

echo.
echo [migrate] DONE.
echo Next steps on 171:
echo   1. Install Python 3.11 (with "Add to PATH")
echo   2. Open cmd: cd /d F:\Database
echo   3. Run: setup_on_171.bat
echo.
pause
goto :eof

:err
echo [ERROR] robocopy reported a fatal error.
pause
exit /b 1
