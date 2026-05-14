@echo off
REM One-shot: build frontend with /web-preview/ base and copy into FastAPI static dir.
REM Run from web/ directory or anywhere — paths are auto-resolved.

pushd "%~dp0\.."
echo [build-deploy] Building frontend with base=/web-preview/...
call npm run build:deploy
if errorlevel 1 (
    echo [build-deploy] Build failed.
    popd
    exit /b 1
)
echo [build-deploy] Copying to core/app/static/web-preview/...
call npm run deploy
if errorlevel 1 (
    echo [build-deploy] Deploy failed.
    popd
    exit /b 1
)
echo [build-deploy] All done. Visit http://localhost:18765/web-preview/
popd
