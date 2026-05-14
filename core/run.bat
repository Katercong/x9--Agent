@echo off
REM X9 Database launcher - opens browser at http://localhost:PORT/
REM Edit PORT below if 18765 is taken.

setlocal
set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe
set PORT=18765
set HERE=%~dp0
cd /d "%HERE%"

REM Default: local browser requests do not need X-API-Key.
REM Set X9_CORE_API_AUTH_DISABLED=0 before running this file to require API login again.
if "%X9_CORE_API_AUTH_DISABLED%"=="" set X9_CORE_API_AUTH_DISABLED=1

if not exist "%PY%" (
    echo [ERROR] Python 3.11 not found at %PY%
    echo Edit run.bat to point at your python.exe
    pause
    exit /b 1
)

netstat -an | findstr ":%PORT% " | findstr "LISTENING" >NUL 2>NUL
if not errorlevel 1 (
    echo [ERROR] Port %PORT% is already in use.
    echo Edit run.bat and change "set PORT=%PORT%" to a free port ^(e.g. 18766, 8910, 9100^).
    pause
    exit /b 1
)

if not exist "%HERE%database.db" (
    echo [run.bat] database.db not found - initializing ...
    "%PY%" scripts\db_init.py        || goto :err
    "%PY%" scripts\import_products.py || goto :err
    "%PY%" scripts\import_images.py   || goto :err
    "%PY%" scripts\import_creators.py || goto :err
)

REM Always run pending migrations (idempotent)
"%PY%" scripts\migrate_v2.py  >NUL 2>NUL
"%PY%" scripts\migrate_v3.py  >NUL 2>NUL
"%PY%" scripts\migrate_v4.py  >NUL 2>NUL
"%PY%" scripts\migrate_v5.py  >NUL 2>NUL
"%PY%" scripts\migrate_v6.py  >NUL 2>NUL
"%PY%" scripts\migrate_v7.py  >NUL 2>NUL
"%PY%" scripts\migrate_v8.py  >NUL 2>NUL
"%PY%" scripts\migrate_v9.py  >NUL 2>NUL
"%PY%" scripts\migrate_v10.py >NUL 2>NUL
"%PY%" scripts\migrate_v11.py >NUL 2>NUL
"%PY%" scripts\migrate_v12.py >NUL 2>NUL
"%PY%" scripts\migrate_v13.py >NUL 2>NUL
"%PY%" scripts\migrate_v14.py >NUL 2>NUL
"%PY%" scripts\migrate_v15.py >NUL 2>NUL
"%PY%" scripts\migrate_v16_creator_unify.py         >NUL 2>NUL
"%PY%" scripts\migrate_v17_fix_creators_date_types.py >NUL 2>NUL

echo.
echo [run.bat] Starting server on http://localhost:%PORT%/  (--reload enabled)
echo [run.bat] Local API auth bypass: %X9_CORE_API_AUTH_DISABLED%
echo [run.bat] Code changes under app/ auto-reload in ~1-2s. Ctrl+C to stop.
echo.
if /I not "%X9_NO_BROWSER%"=="1" start "" http://localhost:%PORT%/
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% --reload --reload-dir app --reload-dir scripts
goto :eof

:err
echo.
echo [ERROR] Initialization failed. See messages above.
pause
exit /b 1
