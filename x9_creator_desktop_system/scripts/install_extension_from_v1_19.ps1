# Copy the working v1.0.19 chrome extension into the v3 desktop system,
# then patch the two URL constants so it talks to the v3 backend.
#
# Run once from PowerShell:
#   cd "F:\AI Agent\Auto boker grab\x9_creator_desktop_system"
#   powershell -ExecutionPolicy Bypass -File scripts\install_extension_from_v1_19.ps1
#
# After this runs, reload the extension at chrome://extensions
# (Load unpacked -> chrome-extension/) — the v1.0.19 auto-run flow stays
# untouched; only the network destinations point at the local v3 backend.

$ErrorActionPreference = "Stop"
$ROOT  = Resolve-Path "$PSScriptRoot\.."
$SRC   = Join-Path (Resolve-Path "$ROOT\..") "tiktok-creator-lead-browser\chrome-extension"
$DEST  = Join-Path $ROOT "chrome-extension"

if (-Not (Test-Path $SRC)) {
  Write-Error "Source extension folder not found: $SRC"
  exit 1
}

# Files we'll copy verbatim.
$files = @(
  "manifest.json",
  "background.js",
  "contentScript.js",
  "popup.html",
  "popup.css",
  "popup.js",
  "sidepanel.html"
)

Write-Host "Copying v1.0.19 extension files to $DEST"
New-Item -ItemType Directory -Force -Path $DEST | Out-Null
foreach ($f in $files) {
  Copy-Item -Force (Join-Path $SRC $f) (Join-Path $DEST $f)
  Write-Host "  copied $f"
}

# Patch popup.js URL constants -> v3 local backend.
$popup = Join-Path $DEST "popup.js"
$content = Get-Content -Raw $popup
$content = $content -replace "const X9_API_BASE_URL = '[^']*';", "const X9_API_BASE_URL = 'https://usx9.us';"
$content = $content -replace "const X9_API_KEY = '[^']*';", "const X9_API_KEY = '';"
$content = $content -replace "const X9_CREATOR_INGEST_URL = `\$\{X9_API_BASE_URL\}/api/ingest/creators`;", "const X9_CREATOR_INGEST_URL = `${X9_API_BASE_URL}/api/local/extension/x9-compat/ingest-creators`;"
$content = $content -replace "const LAUNCHER_HEARTBEAT_URL = '[^']*';", "const LAUNCHER_HEARTBEAT_URL = 'https://usx9.us/api/local/extension/launcher-heartbeat';"
Set-Content -Path $popup -Value $content -Encoding UTF8
Write-Host "  patched popup.js URL constants"

# Patch manifest host_permissions: keep tiktok, point at v3 backend.
$manifestPath = Join-Path $DEST "manifest.json"
$manifest = Get-Content -Raw $manifestPath | ConvertFrom-Json
$manifest.version = "2.0"
$manifest.host_permissions = @(
  "https://www.tiktok.com/*",
  "https://usx9.us/*",
  "https://*.usx9.us/*"
)
# Also drop the X-API-Key requirement since the v3 backend doesn't use it.
$manifest | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $manifestPath
Write-Host "  patched manifest.json version + host_permissions"

Write-Host ""
Write-Host "Done. Now:"
Write-Host "  1. Reload the extension at chrome://extensions"
Write-Host "  2. Make sure the backend is running (start_desktop.bat)"
Write-Host "  3. Open TikTok and click the extension icon"
Write-Host "  4. Use the side panel exactly as you did with v1.0.19"
