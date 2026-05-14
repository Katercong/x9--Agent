$ErrorActionPreference = "Stop"

$RemoteApiUrl = "http://192.168.1.171:18765"
$StartDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-SystemDir {
  param([string]$BaseDir)

  $candidates = @(
    (Join-Path $BaseDir "x9_creator_desktop_system"),
    $BaseDir,
    (Join-Path $BaseDir "Auto boker grab\x9_creator_desktop_system"),
    (Join-Path $BaseDir "auto-boker-grab-deploy\x9_creator_desktop_system")
  )

  foreach ($candidate in $candidates) {
    if (Test-Path (Join-Path $candidate "backend\main.py")) {
      return [System.IO.Path]::GetFullPath($candidate)
    }
  }

  $found = Get-ChildItem -Path $BaseDir -Recurse -Filter main.py -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "backend\\main\.py$" } |
    Select-Object -First 1

  if (-not $found) {
    throw "Cannot find backend\main.py under $BaseDir. Put this script in the extracted project folder."
  }

  return [System.IO.Path]::GetFullPath((Split-Path -Parent (Split-Path -Parent $found.FullName)))
}

function Set-RemoteApiInEnv {
  param([string]$EnvPath)

  if (Test-Path $EnvPath) {
    $content = Get-Content -Raw -LiteralPath $EnvPath
    if ($content -match "(?m)^REMOTE_API_URL=") {
      $content = $content -replace "(?m)^REMOTE_API_URL=.*$", "REMOTE_API_URL=$RemoteApiUrl"
    } else {
      $content = $content.TrimEnd() + "`r`nREMOTE_API_URL=$RemoteApiUrl`r`n"
    }
    Set-Content -LiteralPath $EnvPath -Value $content -Encoding UTF8
  } else {
    Set-Content -LiteralPath $EnvPath -Value "REMOTE_API_URL=$RemoteApiUrl`r`nREMOTE_TABLE=tk_creators`r`nREMOTE_TIMEOUT=10`r`n" -Encoding UTF8
  }
}

function Set-RemoteApiInConfig {
  param([string]$ConfigPath)

  $content = Get-Content -Raw -LiteralPath $ConfigPath
  $content = $content -replace 'os\.getenv\("REMOTE_API_URL",\s*"http://[^"]+"\)', "os.getenv(`"REMOTE_API_URL`", `"$RemoteApiUrl`")"
  Set-Content -LiteralPath $ConfigPath -Value $content -Encoding UTF8
}

function Stop-OldBackendOn8000 {
  try {
    $listeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction Stop
  } catch {
    return
  }

  foreach ($listener in $listeners) {
    $pidToStop = [int]$listener.OwningProcess
    if ($pidToStop -le 0 -or $pidToStop -eq $PID) {
      continue
    }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pidToStop" -ErrorAction SilentlyContinue
    $cmd = $proc.CommandLine
    if ($cmd -match "uvicorn|x9_creator_desktop_system|backend\.main") {
      Write-Host "Stopping old backend on port 8000, PID=$pidToStop"
      Stop-Process -Id $pidToStop -Force
      Start-Sleep -Seconds 1
    } else {
      throw "Port 8000 is occupied by PID=$pidToStop. Close that program first. CommandLine=$cmd"
    }
  }
}

$SystemDir = Find-SystemDir -BaseDir $StartDir
$ProjectRoot = if ((Split-Path -Leaf $SystemDir) -eq "x9_creator_desktop_system") {
  Split-Path -Parent $SystemDir
} else {
  $SystemDir
}

$UsePackagePrefix = (Split-Path -Leaf $SystemDir) -eq "x9_creator_desktop_system"
$WorkDir = if ($UsePackagePrefix) { $ProjectRoot } else { $SystemDir }
$MigrationModule = if ($UsePackagePrefix) {
  "x9_creator_desktop_system.backend.migrations.001_init"
} else {
  "backend.migrations.001_init"
}
$AppModule = if ($UsePackagePrefix) {
  "x9_creator_desktop_system.backend.main:app"
} else {
  "backend.main:app"
}

$EnvPath = Join-Path $SystemDir ".env"
$ConfigPath = Join-Path $SystemDir "backend\config.py"
$RequirementsPath = Join-Path $SystemDir "requirements.txt"

Set-RemoteApiInEnv -EnvPath $EnvPath
Set-RemoteApiInConfig -ConfigPath $ConfigPath
$env:REMOTE_API_URL = $RemoteApiUrl
$env:REMOTE_TABLE = "tk_creators"

Write-Host ""
Write-Host "Project root: $ProjectRoot"
Write-Host "System dir:   $SystemDir"
Write-Host "Remote DB:    $RemoteApiUrl"
Write-Host ""

Write-Host "Checking remote table..."
$remote = Invoke-RestMethod -Uri "$RemoteApiUrl/api/v1/data/tk_creators?limit=1&offset=0" -TimeoutSec 10
Write-Host "Remote tk_creators total: $($remote.total)"

Write-Host ""
Write-Host "Installing backend requirements..."
& py -3.11 -m pip install -r $RequirementsPath

Write-Host ""
Write-Host "Running migration..."
Push-Location $WorkDir
try {
  & py -3.11 -m $MigrationModule

  Stop-OldBackendOn8000

  Write-Host ""
  Write-Host "Starting UI: http://127.0.0.1:8000/ui/"
  Start-Process "http://127.0.0.1:8000/ui/"
  & py -3.11 -m uvicorn $AppModule --host 127.0.0.1 --port 8000
} finally {
  Pop-Location
}
