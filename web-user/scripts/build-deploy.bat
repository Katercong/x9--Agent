@echo off
REM One-shot: build user portal with /portal/ base and copy into desktop/backend/ui/portal/.

pushd "%~dp0\.."
echo [build-deploy] Building user portal with base=/portal/...
call npm run build:deploy
if errorlevel 1 (
    echo [build-deploy] Build failed.
    popd
    exit /b 1
)
echo [build-deploy] Copying to desktop/backend/ui/portal/...
call npm run deploy
if errorlevel 1 (
    echo [build-deploy] Deploy failed.
    popd
    exit /b 1
)
echo [build-deploy] All done. Visit http://localhost:8000/portal/
popd
