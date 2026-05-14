@echo off
REM Re-import all source data + regenerate exports.
setlocal
set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe
set HERE=%~dp0
cd /d "%HERE%"

if not exist "%PY%" (
    echo [ERROR] Python 3.11 not found at %PY%
    pause
    exit /b 1
)

"%PY%" scripts\import_products.py || goto :err
"%PY%" scripts\import_images.py   || goto :err
"%PY%" scripts\import_creators.py || goto :err
"%PY%" scripts\export_json.py     || goto :err
"%PY%" scripts\export_xlsx.py     || goto :err
echo.
echo Done. Press any key to close.
pause >NUL
goto :eof

:err
echo.
echo [ERROR] Re-import failed. See messages above.
pause
exit /b 1
