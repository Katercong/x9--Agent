param(
  [int]$Port = 8000,
  # ngrok v3 serves its local inspection API on 127.0.0.1:4040 by default.
  [int]$NgrokApiPort = 4040,
  [string]$Domain = "",
  [string]$NgrokAuthtoken = "",
  [switch]$NoInstall,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$StartDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$NgrokZipUrl = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"

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

function Stop-OldNgrokForPort {
  param([int]$Port)

  $procs = Get-CimInstance Win32_Process -Filter "name='ngrok.exe'" -ErrorAction SilentlyContinue
  foreach ($proc in $procs) {
    $cmd = [string]$proc.CommandLine
    if ($cmd -match "\bhttp\b" -and $cmd -match [regex]::Escape([string]$Port)) {
      Write-Host "Stopping old ngrok tunnel for port $Port, PID=$($proc.ProcessId)"
      Stop-Process -Id $proc.ProcessId -Force
      Start-Sleep -Seconds 1
    }
  }
}

function Find-OrInstallNgrok {
  param(
    [string]$RootDir,
    [switch]$NoInstall
  )

  $cmd = Get-Command ngrok -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }

  $toolsDir = Join-Path $RootDir ".tools\ngrok"
  $localExe = Join-Path $toolsDir "ngrok.exe"
  if (Test-Path $localExe) {
    return $localExe
  }

  if ($NoInstall) {
    throw "ngrok is not installed. Install ngrok or run this script without -NoInstall."
  }

  New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null
  $zipPath = Join-Path $toolsDir "ngrok.zip"
  Write-Host "Downloading ngrok to $toolsDir ..."
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  Invoke-WebRequest -Uri $NgrokZipUrl -OutFile $zipPath
  Expand-Archive -LiteralPath $zipPath -DestinationPath $toolsDir -Force
  Remove-Item -LiteralPath $zipPath -Force

  if (-not (Test-Path $localExe)) {
    throw "ngrok download finished, but ngrok.exe was not found at $localExe"
  }
  return $localExe
}

function Wait-HttpOk {
  param(
    [string]$Url,
    [int]$Seconds = 30
  )

  for ($i = 0; $i -lt $Seconds; $i++) {
    try {
      Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
      return $true
    } catch {
      Start-Sleep -Seconds 1
    }
  }
  return $false
}

function Read-NgrokHttpsUrl {
  param(
    [int]$ApiPort,
    [int]$TargetPort,
    [System.Diagnostics.Process]$NgrokProcess,
    [string]$NgrokLog,
    [string]$NgrokErr
  )

  for ($i = 0; $i -lt 45; $i++) {
    if ($NgrokProcess.HasExited) {
      $logText = ""
      if (Test-Path $NgrokLog) { $logText += (Get-Content -Path $NgrokLog -Raw -ErrorAction SilentlyContinue) }
      if (Test-Path $NgrokErr) { $logText += (Get-Content -Path $NgrokErr -Raw -ErrorAction SilentlyContinue) }
      throw "ngrok exited before creating a tunnel. Log: $logText"
    }

    try {
      $data = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/tunnels" -TimeoutSec 2
      $tunnel = $data.tunnels |
        Where-Object {
          $_.public_url -like "https://*" -and
          ([string]$_.config.addr -match [regex]::Escape([string]$TargetPort))
        } |
        Select-Object -First 1
      if (-not $tunnel) {
        $tunnel = $data.tunnels |
          Where-Object { $_.public_url -like "https://*" } |
          Select-Object -First 1
      }
      if ($tunnel) {
        return ([string]$tunnel.public_url).TrimEnd("/")
      }
    } catch {
      # Keep waiting while ngrok opens its local API before the cloud tunnel exists.
    }
    Start-Sleep -Seconds 1
  }

  throw "ngrok did not expose an HTTPS URL within 45 seconds. Check $NgrokLog and $NgrokErr"
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
$LogsDir = Join-Path $SystemDir "logs"
New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null

$NgrokExe = Find-OrInstallNgrok -RootDir $ProjectRoot -NoInstall:$NoInstall
if (-not $NgrokAuthtoken -and $env:NGROK_AUTHTOKEN) {
  $NgrokAuthtoken = $env:NGROK_AUTHTOKEN
}
if ($NgrokAuthtoken) {
  Write-Host "Saving ngrok authtoken ..."
  & $NgrokExe config add-authtoken $NgrokAuthtoken | Out-Null
}

$LanIp = Get-LanIp
$BackendLog = Join-Path $LogsDir "x9_ngrok_backend.log"
$BackendErr = Join-Path $LogsDir "x9_ngrok_backend.err.log"
$NgrokLog = Join-Path $LogsDir "x9_ngrok.log"
$NgrokErr = Join-Path $LogsDir "x9_ngrok.err.log"

Write-Host ""
Write-Host "Project root: $ProjectRoot"
Write-Host "System dir:   $SystemDir"
Write-Host "ngrok exe:    $NgrokExe"
Write-Host "Local URL:    http://127.0.0.1:$Port/ui/"
Write-Host "LAN URL:      http://$LanIp`:$Port/ui/"
Write-Host ""

Write-Host "Installing backend requirements..."
& py -3.11 -m pip install -r $RequirementsPath

Push-Location $WorkDir
$backendProc = $null
$ngrokProc = $null
try {
  Write-Host ""
  Write-Host "Running migration..."
  & py -3.11 -m $MigrationModule

  Stop-OldBackend -Port $Port
  Stop-OldNgrokForPort -Port $Port

  $ngrokArgs = @(
    "http",
    [string]$Port,
    "--log=stdout"
  )
  if ($Domain) {
    $ngrokUrl = $Domain
    if ($ngrokUrl -notmatch "^https?://") {
      $ngrokUrl = "https://$ngrokUrl"
    }
    $ngrokArgs += "--url=$ngrokUrl"
  }

  Write-Host ""
  Write-Host "Starting ngrok HTTPS tunnel..."
  $ngrokProc = Start-Process `
    -FilePath $NgrokExe `
    -ArgumentList $ngrokArgs `
    -RedirectStandardOutput $NgrokLog `
    -RedirectStandardError $NgrokErr `
    -WindowStyle Hidden `
    -PassThru

  $PublicUrl = Read-NgrokHttpsUrl `
    -ApiPort $NgrokApiPort `
    -TargetPort $Port `
    -NgrokProcess $ngrokProc `
    -NgrokLog $NgrokLog `
    -NgrokErr $NgrokErr

  $env:BACKEND_PORT = [string]$Port
  $env:X9_PUBLIC_BASE_URL = $PublicUrl
  $env:GMAIL_OAUTH_REDIRECT_URI = "$PublicUrl/api/local/outreach/gmail/callback"

  Write-Host ""
  Write-Host "Starting X9 dashboard backend..."
  $backendArgs = @(
    "-3.11",
    "-m",
    "uvicorn",
    $AppModule,
    "--host",
    "0.0.0.0",
    "--port",
    [string]$Port,
    "--proxy-headers",
    "--forwarded-allow-ips=*"
  )
  $backendProc = Start-Process `
    -FilePath "py" `
    -ArgumentList $backendArgs `
    -WorkingDirectory $WorkDir `
    -RedirectStandardOutput $BackendLog `
    -RedirectStandardError $BackendErr `
    -WindowStyle Hidden `
    -PassThru

  if (-not (Wait-HttpOk -Url "http://127.0.0.1:$Port/health" -Seconds 45)) {
    throw "Backend did not answer /health within 45 seconds. Check $BackendLog and $BackendErr"
  }

  Write-Host ""
  Write-Host "X9 dashboard is running through ngrok:"
  Write-Host "  $PublicUrl/ui/"
  Write-Host ""
  Write-Host "Add these in Google Cloud Console for the SAME OAuth Web client:"
  Write-Host "  Authorized JavaScript origins:"
  Write-Host "  $PublicUrl"
  Write-Host ""
  Write-Host "  Authorized redirect URIs:"
  Write-Host "  $PublicUrl/api/local/outreach/gmail/callback"
  Write-Host ""
  Write-Host "Keep this window open. Press Ctrl+C to stop backend and ngrok."
  Write-Host "Logs:"
  Write-Host "  Backend: $BackendLog"
  Write-Host "  ngrok:   $NgrokLog"
  Write-Host ""

  if (-not $NoBrowser) {
    Start-Process "$PublicUrl/ui/"
  }

  while ($true) {
    if ($backendProc.HasExited) {
      throw "Backend process exited. Check $BackendLog and $BackendErr"
    }
    if ($ngrokProc.HasExited) {
      throw "ngrok process exited. Check $NgrokLog and $NgrokErr"
    }
    Start-Sleep -Seconds 5
  }
} finally {
  Pop-Location
  if ($backendProc -and -not $backendProc.HasExited) {
    Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
  }
  if ($ngrokProc -and -not $ngrokProc.HasExited) {
    Stop-Process -Id $ngrokProc.Id -Force -ErrorAction SilentlyContinue
  }
}
