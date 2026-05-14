@echo off
set HERE=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%start_x9_lan_dashboard.ps1"
pause
