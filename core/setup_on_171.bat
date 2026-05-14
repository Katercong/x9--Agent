@echo off
REM First-time setup on 192.168.1.171. Run AFTER migrate_to_171.bat completed.
REM Auto-detects Python (PATH or common install locations).

setlocal enabledelayedexpansion
set HERE=%~dp0
cd /d "%HERE%"

set PY=
for %%C in (python.exe py.exe) do (
    where %%C >NUL 2>&1 && (for /f "delims=" %%P in ('where %%C') do if not defined PY set PY=%%P)
)
if not defined PY (
    for %%P in (
        "C:\Python311\python.exe"
        "C:\Python312\python.exe"
        "C:\Python310\python.exe"
        "C:\Program Files\Python311\python.exe"
        "C:\Program Files\Python312\python.exe"
        "C:\Program Files\Python310\python.exe"
        "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
        "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe"
        "C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe"
        "D:\Python311\python.exe"
        "D:\Python312\python.exe"
    ) do if exist %%P if not defined PY set PY=%%~P
)
if not defined PY (
    echo [ERROR] Could not locate python.exe. Edit this script and add the path.
    pause
    exit /b 1
)
echo [setup] Using Python: %PY%

if not exist ".venv\Scripts\python.exe" (
    echo [setup] Creating venv ...
    "%PY%" -m venv .venv || goto :err
)

echo [setup] Installing dependencies ...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >NUL
pip install -r requirements.txt || goto :err

echo [setup] Running migrations ...
for %%V in (v2 v3 v4 v5 v6 v7 v8 v9 v10 v11 v12 v13 v14 v15) do (
    python scripts\migrate_%%V.py >NUL 2>&1
)

echo.
echo [setup] DONE. Start service: run_on_171.bat
echo.
pause
goto :eof

:err
echo [ERROR] setup failed.
pause
exit /b 1
