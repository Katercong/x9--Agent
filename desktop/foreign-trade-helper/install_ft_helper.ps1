# ==========================================================================
# X9 Foreign-Trade - Batch Collection helper installer (one-click)
# ==========================================================================
# Registers a Chrome native messaging host so the merged extension's
# "batch collection" can drive a controlled Chrome to auto-paginate and
# push results to X9.
#
# Why manual install is required: Chrome forbids web pages/extensions from
# silently installing native programs or writing the registry, so the native
# host must be registered once per collection machine.
#
# Usage (run in PowerShell on the collection PC, single line):
#   powershell -ExecutionPolicy Bypass -File "<full path to this file>"
#
# Optional parameters:
#   -BackendUrl   X9 backend URL (default https://usx9.us; local test can use http://127.0.0.1:8000)
#   -ExtensionId  Merged extension ID (default = fixed-key ID; usually leave it)
#   -SkipPythonInstall  Skip venv creation + dependency install (re-register only)
# ==========================================================================
param(
  [string]$ExtensionId = "idahdepjhfmldleebihlbnkmfhjbjbde",
  [string]$BackendUrl = "https://usx9.us",
  [string]$Department = "foreign_trade",
  [switch]$SkipPythonInstall
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$appDir = Join-Path $env:LOCALAPPDATA "CompanyLeads"   # reuse original host name/dir so extension NATIVE_HOST stays the same
$venvDir = Join-Path $appDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$nativeManifestPath = Join-Path $appDir "companyleads_native_host.json"
$nativeCmd = Join-Path $root "native_host\companyleads_native_host.cmd"
$configPath = Join-Path $appDir "config.json"
$chromeProfileDir = Join-Path $appDir "chrome-profile"

if (-not (Test-Path -LiteralPath $appDir)) { New-Item -ItemType Directory -Force -Path $appDir | Out-Null }
if (-not (Test-Path -LiteralPath $chromeProfileDir)) { New-Item -ItemType Directory -Force -Path $chromeProfileDir | Out-Null }

if (-not (Test-Path -LiteralPath $nativeCmd)) {
  throw "Native host launcher not found: $nativeCmd (run this script from inside the foreign-trade-helper folder)"
}

# ---- 1. Python venv + dependencies (incl. Playwright Chromium) ----
if (-not $SkipPythonInstall) {
  if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "[1/4] Creating Python venv: $venvDir"
    python -m venv $venvDir
  } else {
    Write-Host "[1/4] venv already exists, skip create"
  }
  Write-Host "[2/4] Installing Python deps (fastapi/httpx/playwright ...)"
  & $venvPython -m pip install --upgrade pip
  & $venvPython -m pip install -r (Join-Path $root "requirements.txt")
  Write-Host "[3/4] Installing Playwright Chromium browser (network download, may take minutes)"
  & $venvPython -m playwright install chromium
} else {
  Write-Host "[1-3/4] -SkipPythonInstall: skipping dependency install"
}

$pythonForConfig = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

# ---- 2. Write config.json (push target = X9, department = foreign_trade) ----
@{
  root = $root
  python = $pythonForConfig
  mode = "client"
  backendUrl = $BackendUrl.TrimEnd("/")
  dashboardUrl = "https://usx9.us/workspace/foreign-trade/"
  backendHost = "127.0.0.1"
  backendPort = [int]([uri]$BackendUrl).Port
  department = $Department
  apiToken = ""
  helperUrl = "http://127.0.0.1:8765"
  chromeProfileDir = $chromeProfileDir
  installedAt = (Get-Date).ToString("o")
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $configPath -Encoding UTF8

# ---- 3. Write native host manifest + registry key (bind fixed extension ID) ----
@{
  name = "com.companyleads.helper"
  description = "X9 foreign-trade batch collection helper"
  path = $nativeCmd
  type = "stdio"
  allowed_origins = @("chrome-extension://$ExtensionId/")
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $nativeManifestPath -Encoding UTF8

$registryKey = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.companyleads.helper"
if (-not (Test-Path -LiteralPath $registryKey)) { New-Item -Path $registryKey -Force | Out-Null }
Set-Item -Path $registryKey -Value $nativeManifestPath

Write-Host ""
Write-Host "[4/4] DONE - batch collection helper installed"
Write-Host "  Backend  : $($BackendUrl.TrimEnd('/'))  (leads -> department: $Department)"
Write-Host "  Ext ID   : $ExtensionId"
Write-Host "  Manifest : $nativeManifestPath"
Write-Host "  Config   : $configPath"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1) Load the merged extension in Chrome (chrome://extensions -> Load unpacked -> extension folder)"
Write-Host "  2) Confirm side panel status shows backend=$($BackendUrl.TrimEnd('/')), department=$Department, root=$root"
Write-Host "  3) Open extension side panel -> Recruitment -> Batch collection -> Start"
Write-Host "  (First run auto-launches a controlled Chrome window; log in there for Zhaopin/talent if needed.)"
