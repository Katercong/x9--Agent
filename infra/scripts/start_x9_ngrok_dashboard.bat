@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_x9_ngrok_dashboard.ps1" %*
pause
