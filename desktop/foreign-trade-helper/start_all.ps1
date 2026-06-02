$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$configPath = Join-Path $env:LOCALAPPDATA "CompanyLeads\config.json"
if (Test-Path -LiteralPath $configPath) {
  try {
    $cfg = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
    if (-not $env:COMPANYLEADS_MODE -and $cfg.mode) { $env:COMPANYLEADS_MODE = [string]$cfg.mode }
    if (-not $env:COMPANYLEADS_BACKEND_URL -and $cfg.backendUrl) { $env:COMPANYLEADS_BACKEND_URL = [string]$cfg.backendUrl }
    if (-not $env:COMPANYLEADS_DEPARTMENT -and $cfg.department) { $env:COMPANYLEADS_DEPARTMENT = [string]$cfg.department }
    if (-not $env:COMPANYLEADS_BACKEND_HOST -and $cfg.backendHost) { $env:COMPANYLEADS_BACKEND_HOST = [string]$cfg.backendHost }
    if (-not $env:COMPANYLEADS_BACKEND_PORT -and $cfg.backendPort) { $env:COMPANYLEADS_BACKEND_PORT = [string]$cfg.backendPort }
    if (-not $env:COMPANYLEADS_API_TOKEN -and $cfg.apiToken) { $env:COMPANYLEADS_API_TOKEN = [string]$cfg.apiToken }
  } catch {
    Write-Host "Could not read CompanyLeads config; using defaults"
  }
}
$mode = if ($env:COMPANYLEADS_MODE) { $env:COMPANYLEADS_MODE } else { "client" }
$backendUrl = if ($env:COMPANYLEADS_BACKEND_URL) { $env:COMPANYLEADS_BACKEND_URL.TrimEnd("/") } else { "https://usx9.us" }
$backendPort = if ($env:COMPANYLEADS_BACKEND_PORT) { [int]$env:COMPANYLEADS_BACKEND_PORT } else { 8000 }
$localPython = Join-Path $env:LOCALAPPDATA "CompanyLeads\.venv\Scripts\python.exe"
$python = if ($env:COMPANYLEADS_PYTHON) {
  $env:COMPANYLEADS_PYTHON
} elseif (Test-Path -LiteralPath $localPython) {
  $localPython
} else {
  # Fallback to PATH python. The installed config.json normally points
  # COMPANYLEADS_PYTHON / the local venv to the right interpreter.
  "python"
}

if (-not (Test-Path -LiteralPath $python)) {
  $python = "python"
}

function Test-LocalPortListening {
  param([int]$Port)

  $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  return $null -ne $listener
}

$env:COMPANYLEADS_CHROME_DEBUG_PORT = if ($env:COMPANYLEADS_CHROME_DEBUG_PORT) { $env:COMPANYLEADS_CHROME_DEBUG_PORT } else { "9222" }

Write-Host "Ensuring Chrome CDP on http://127.0.0.1:$env:COMPANYLEADS_CHROME_DEBUG_PORT"
if ($env:COMPANYLEADS_RESTART_CHROME_FOR_CDP -eq "1") {
  & (Join-Path $root "start_chrome_cdp.ps1") -RestartChrome
} else {
  & (Join-Path $root "start_chrome_cdp.ps1")
}

$cdpRuntimePath = Join-Path $root "data\runtime\chrome-cdp.json"
if (Test-Path -LiteralPath $cdpRuntimePath) {
  try {
    $cdpRuntime = Get-Content -Raw -LiteralPath $cdpRuntimePath | ConvertFrom-Json
    if ($cdpRuntime.port) {
      $env:COMPANYLEADS_CHROME_DEBUG_PORT = [string]$cdpRuntime.port
    }
  } catch {
    Write-Host "Could not read Chrome CDP runtime file; keeping port $env:COMPANYLEADS_CHROME_DEBUG_PORT"
  }
}

if ($mode -eq "client") {
  Write-Host "Client mode: using central backend $backendUrl"
} elseif (Test-LocalPortListening -Port $backendPort) {
  Write-Host "CompanyLeads backend already running on $backendUrl"
} else {
  Write-Host "Starting CompanyLeads backend on $backendUrl"
  Start-Process -FilePath $python -ArgumentList "run.py" -WorkingDirectory $root -WindowStyle Hidden
}

if (Test-LocalPortListening -Port 8765) {
  Write-Host "CDP helper already running on http://127.0.0.1:8765"
} else {
  Write-Host "Starting CDP helper on http://127.0.0.1:8765"
  Start-Process -FilePath $python -ArgumentList "scraper/cdp_helper.py" -WorkingDirectory $root -WindowStyle Hidden
}

Start-Sleep -Seconds 2
Write-Host "Ready:"
Write-Host "  Backend: $backendUrl"
Write-Host "  CDP helper: http://127.0.0.1:8765/health"
Write-Host "  Chrome CDP: http://127.0.0.1:$env:COMPANYLEADS_CHROME_DEBUG_PORT/json/version"
