@echo off
REM Re-import all source data + regenerate exports.
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

%PY% scripts\import_products.py || goto :err
%PY% scripts\import_images.py   || goto :err
%PY% scripts\import_creators.py || goto :err
%PY% scripts\export_json.py     || goto :err
%PY% scripts\export_xlsx.py     || goto :err
echo.
echo Done. Press any key to close.
pause >NUL
goto :eof

:err
echo.
echo [ERROR] Re-import failed. See messages above.
pause
exit /b 1
