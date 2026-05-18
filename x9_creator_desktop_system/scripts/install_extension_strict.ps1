# install_extension_strict.ps1
#
# Unzips the v1.0.19 extension into x9_creator_desktop_system\chrome-extension\,
# drops in the two relay files (x9_sw.js + x9_relay.js), and patches
# ONLY the manifest:
#   * background.service_worker -> "x9_sw.js" (the shim that loads
#     background.js + x9_relay.js)
#   * host_permissions += "http://127.0.0.1:8000/*" + "http://localhost:8000/*"
#
# NO source file from the v1.0.19 extension is modified. The collection
# logic stays exactly as you had it. The dashboard relay is purely an
# additional listener on the extension's existing storage events.
#
# Run from PowerShell (one-time):
#   cd "F:\AI Agent\Auto boker grab\x9_creator_desktop_system"
#   powershell -ExecutionPolicy Bypass -File scripts\install_extension_strict.ps1

$ErrorActionPreference = "Stop"
$ROOT = Resolve-Path "$PSScriptRoot\.."
$PARENT = Resolve-Path "$ROOT\.."
$ZIP_PATHS = @(
  (Join-Path $PARENT "tiktok-creator-lead-browser-extension-1.0.19.zip"),
  (Join-Path $PARENT "tiktok-creator-lead-browser\dist\tiktok-creator-lead-browser-extension-1.0.19.zip"),
  (Join-Path $PARENT "tiktok-creator-lead-browser\dist\tiktok-creator-lead-browser-extension-1.0.21.zip")
)

$DEST = Join-Path $ROOT "chrome-extension"
$RELAY = Join-Path $ROOT "chrome-extension-relay"

function Assert-PathUnder {
  param([string]$Path, [string]$Parent)
  $resolvedParent = [System.IO.Path]::GetFullPath($Parent)
  $resolvedPath = [System.IO.Path]::GetFullPath($Path)
  if (-not $resolvedPath.StartsWith($resolvedParent, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to touch path outside expected directory: $resolvedPath"
  }
}

# 1. Find the source zip.
$ZIP = $null
foreach ($p in $ZIP_PATHS) {
  if (Test-Path $p) { $ZIP = $p; break }
}
if (-Not $ZIP) {
  Write-Error "Could not find the v1.0.19 extension zip. Looked in:`n$($ZIP_PATHS -join ""`n"")"
  exit 1
}
Write-Host "Source zip: $ZIP"

# 2. Wipe any previous extension dir, then unzip the v1.0.19 archive.
if (Test-Path $DEST) {
  Assert-PathUnder -Path $DEST -Parent $ROOT
  Write-Host "Removing existing $DEST"
  Remove-Item -Recurse -Force $DEST
}
New-Item -ItemType Directory -Force -Path $DEST | Out-Null
Write-Host "Unzipping into $DEST"
Expand-Archive -LiteralPath $ZIP -DestinationPath $DEST -Force

# Some zips wrap their contents in a top-level folder. Flatten if so.
$inner = Get-ChildItem $DEST | Where-Object { $_.PSIsContainer }
if ($inner.Count -eq 1 -and -Not (Test-Path (Join-Path $DEST "manifest.json"))) {
  $innerDir = $inner[0].FullName
  Assert-PathUnder -Path $innerDir -Parent $DEST
  Write-Host "Flattening nested folder $($inner[0].Name)"
  Get-ChildItem -Force $innerDir | Move-Item -Destination $DEST -Force
  Remove-Item -Recurse -Force $innerDir
}

# 3. Drop in the relay files (NEW, not from the old extension).
foreach ($f in @("x9_sw.js", "x9_relay.js")) {
  Copy-Item -Force (Join-Path $RELAY $f) (Join-Path $DEST $f)
  Write-Host "  added $f"
}

# 4. Patch manifest.json:
#    * background.service_worker -> x9_sw.js (which loads background.js + x9_relay.js)
#    * set X9 extension version -> 2.0
#    * add v3 backend to host_permissions
#    * ensure 'alarms' permission is present (relay uses chrome.alarms)
$manifestPath = Join-Path $DEST "manifest.json"
$manifest = Get-Content -Raw $manifestPath | ConvertFrom-Json

$manifest.background = @{ service_worker = "x9_sw.js" }
$manifest.version = "2.0"

$hosts = @($manifest.host_permissions)
foreach ($h in @("http://127.0.0.1:8000/*", "http://localhost:8000/*")) {
  if ($hosts -notcontains $h) { $hosts += $h }
}
$manifest.host_permissions = $hosts

$perms = @($manifest.permissions)
if ($perms -notcontains "alarms") { $perms += "alarms" }
$manifest.permissions = $perms

$manifest | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 $manifestPath
Write-Host "  patched manifest.json"

Write-Host ""
Write-Host "=== Done ==="
Write-Host "v1.0.19 source files: untouched"
Write-Host "added: x9_sw.js, x9_relay.js"
Write-Host "manifest changes: version=2.0, background.service_worker, host_permissions, alarms"
Write-Host ""
Write-Host "Next:"
Write-Host "  1. Make sure backend is running:"
Write-Host "       cd $ROOT"
Write-Host "       py -3.11 -m x9_creator_desktop_system.backend.migrations.001_init"
Write-Host "       .\start_desktop.bat"
Write-Host "  2. chrome://extensions -> Load unpacked -> $DEST"
Write-Host "  3. Use the extension exactly as you did before. Each lead it"
Write-Host "     produces also lands in http://127.0.0.1:8000/ui/"
