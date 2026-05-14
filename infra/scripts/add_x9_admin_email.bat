@echo off
set HERE=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%add_x9_admin_email.ps1"
pause
