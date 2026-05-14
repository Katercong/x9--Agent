@echo off
REM Start Electron desktop shell. Requires `npm install` inside desktop/ once.
set HERE=%~dp0
cd /d "%HERE%\desktop"
npm start
