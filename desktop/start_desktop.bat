@echo off
REM Start the backend without Electron — opens the UI in your default browser.
REM Use this until you've run `npm install` inside desktop/ to set up Electron.

set HERE=%~dp0
cd /d "%HERE%\.."

py -3.11 -m desktop.backend.migrations.001_init
start "" "https://usx9.us/portal/"
py -3.11 -m uvicorn desktop.backend.main:app --host 127.0.0.1 --port 8000
