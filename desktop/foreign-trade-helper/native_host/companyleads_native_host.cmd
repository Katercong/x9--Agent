@echo off
setlocal

set "APP_DIR=%LOCALAPPDATA%\CompanyLeads"
set "PYTHON=%APP_DIR%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

"%PYTHON%" "%~dp0companyleads_native_host.py"
