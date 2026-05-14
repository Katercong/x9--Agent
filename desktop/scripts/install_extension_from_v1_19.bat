@echo off
REM Wrapper for install_extension_from_v1_19.ps1 so you can double-click.
setlocal
set HERE=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%install_extension_from_v1_19.ps1"
pause
