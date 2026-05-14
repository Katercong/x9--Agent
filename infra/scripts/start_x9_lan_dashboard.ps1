$ErrorActionPreference = "Stop"

$Port = 8000
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

function Get-LanIp {
  $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
      $_.IPAddress -notlike "127.*" -and
      $_.IPAddress -notlike "169.254.*" -and
      $_.PrefixOrigin -ne "WellKnown"
    } |
    Sort-Object InterfaceMetric, InterfaceIndex |
    Select-Object -First 1

  if ($ip) { return $ip.IPAddress }
  return "YOUR-LAN-IP"
}

function Ensure-FirewallRule {
  param([int]$Port)

  $ruleName = "X9 Dashboard LAN $Port"
  try {
    $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    if (-not $existing) {
      New-NetFirewallRule `
        -DisplayName $ruleName `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort $Port `
        -Action Allow `
        -Profile Private | Out-Null
    }
  } catch {
    Write-Warning "Could not create firewall rule automatically. Run PowerShell as Administrator or allow TCP port $Port manually."
  }
}

function Stop-OldBackend {
  param([int]$Port)

  try {
    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
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
      Write-Host "Stopping old X9 backend on port $Port, PID=$pidToStop"
      Stop-Process -Id $pidToStop -Force
      Start-Sleep -Seconds 1
    } else {
      throw "Port $Port is occupied by PID=$pidToStop. Close that program first. CommandLine=$cmd"
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
$RequirementsPath = Join-Path $SystemDir "requirements.txt"
$LanIp = Get-LanIp

Write-Host ""
Write-Host "Project root: $ProjectRoot"
Write-Host "System dir:   $SystemDir"
Write-Host "Local URL:    http://127.0.0.1:$Port/ui/"
Write-Host "LAN URL:      http://$LanIp`:$Port/ui/"
Write-Host ""

Ensure-FirewallRule -Port $Port

Write-Host "Installing backend requirements..."
& py -3.11 -m pip install -r $RequirementsPath

Push-Location $WorkDir
try {
  Write-Host ""
  Write-Host "Running migration..."
  & py -3.11 -m $MigrationModule

  Stop-OldBackend -Port $Port

  Write-Host ""
  Write-Host "Starting X9 dashboard for LAN users..."
  Start-Process "http://127.0.0.1:$Port/ui/"
  & py -3.11 -m uvicorn $AppModule --host 0.0.0.0 --port $Port
} finally {
  Pop-Location
}
