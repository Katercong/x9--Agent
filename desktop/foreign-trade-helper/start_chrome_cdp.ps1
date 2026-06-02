param(
  [switch]$RestartChrome
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeDir = Join-Path $root "data\runtime"
$runtimeFile = Join-Path $runtimeDir "chrome-cdp.json"

function Test-CdpReady {
  param([int]$Port)

  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $pending = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
    if (-not $pending.AsyncWaitHandle.WaitOne(300)) {
      return $false
    }
    $client.EndConnect($pending)
  } catch {
    return $false
  } finally {
    $client.Close()
  }

  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/json/version" -TimeoutSec 1
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

function Test-PortHasListener {
  param([int]$Port)

  $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  return $null -ne $listener
}

function Write-CdpRuntime {
  param(
    [int]$Port,
    [string]$UserDataDir,
    [string]$ProfileDirectory,
    [string]$ChromePath
  )

  if (-not (Test-Path -LiteralPath $runtimeDir)) {
    New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
  }

  $existing = $null
  if (Test-Path -LiteralPath $runtimeFile) {
    try {
      $existing = Get-Content -Raw -LiteralPath $runtimeFile | ConvertFrom-Json
    } catch {
      $existing = $null
    }
  }

  if ([string]::IsNullOrWhiteSpace($UserDataDir) -and $existing.userDataDir) {
    $UserDataDir = [string]$existing.userDataDir
  }
  if ([string]::IsNullOrWhiteSpace($ProfileDirectory) -and $existing.profileDirectory) {
    $ProfileDirectory = [string]$existing.profileDirectory
  }
  if ([string]::IsNullOrWhiteSpace($ChromePath) -and $existing.chromePath) {
    $ChromePath = [string]$existing.chromePath
  }

  @{
    port = $Port
    url = "http://127.0.0.1:$Port"
    userDataDir = $UserDataDir
    profileDirectory = $ProfileDirectory
    chromePath = $ChromePath
    updatedAt = (Get-Date).ToString("o")
  } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $runtimeFile -Encoding UTF8
}

function Get-AbsolutePath {
  param([string]$PathValue)

  if ([string]::IsNullOrWhiteSpace($PathValue)) {
    return $null
  }

  if ([System.IO.Path]::IsPathRooted($PathValue)) {
    return [System.IO.Path]::GetFullPath($PathValue)
  }

  return [System.IO.Path]::GetFullPath((Join-Path $root $PathValue))
}

function Get-DefaultChromeUserDataDir {
  return (Join-Path $env:LOCALAPPDATA "Google\Chrome\User Data")
}

function Get-ControlledChromeUserDataDir {
  $dir = Join-Path $env:LOCALAPPDATA "CompanyLeads\chrome-profile"
  if (-not (Test-Path -LiteralPath $dir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
  }
  return $dir
}

function Get-DefaultChromeProfileDirectory {
  param([string]$UserDataDir)

  if ($env:COMPANYLEADS_CHROME_PROFILE_DIRECTORY) {
    return $env:COMPANYLEADS_CHROME_PROFILE_DIRECTORY
  }

  if ($env:QCWY_CHROME_PROFILE_DIRECTORY) {
    return $env:QCWY_CHROME_PROFILE_DIRECTORY
  }

  $localStatePath = Join-Path $UserDataDir "Local State"
  if (Test-Path -LiteralPath $localStatePath) {
    try {
      $localStateText = Get-Content -Raw -LiteralPath $localStatePath
      $localState = $localStateText | ConvertFrom-Json
      if ($localState.profile.last_used) {
        return [string]$localState.profile.last_used
      }
    } catch {
      $localStateText = Get-Content -Raw -LiteralPath $localStatePath
      $match = [regex]::Match($localStateText, '"last_used"\s*:\s*"([^"]+)"')
      if ($match.Success) {
        return $match.Groups[1].Value
      }
      Write-Host "Could not read Chrome Local State profile, using Default."
    }
  }

  return "Default"
}

function Ensure-DailyProfileLink {
  param([string]$DailyUserDataDir)

  if (-not (Test-Path -LiteralPath $DailyUserDataDir)) {
    throw "Daily Chrome user data dir was not found: $DailyUserDataDir"
  }

  $linkPath = Join-Path $root "data\chrome-user-data-link"

  if (Test-Path -LiteralPath $linkPath) {
    $item = Get-Item -LiteralPath $linkPath -Force
    if ($item.LinkType -eq "Junction" -and $item.Target -eq $DailyUserDataDir) {
      return $linkPath
    }
    if ($item.LinkType -eq "Junction") {
      Remove-Item -LiteralPath $linkPath -Force
    } else {
      throw "Chrome CDP link path already exists and is not a junction: $linkPath"
    }
  }

  $parent = Split-Path -Parent $linkPath
  if (-not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
  }

  New-Item -ItemType Junction -Path $linkPath -Target $DailyUserDataDir | Out-Null
  return $linkPath
}

function Resolve-UserDataDir {
  param(
    [bool]$RestartRequested,
    [bool]$ChromeIsRunning
  )

  $explicitDir = if ($env:COMPANYLEADS_CHROME_USER_DATA_DIR) {
    $env:COMPANYLEADS_CHROME_USER_DATA_DIR
  } elseif ($env:QCWY_CHROME_USER_DATA_DIR) {
    $env:QCWY_CHROME_USER_DATA_DIR
  } else {
    $null
  }

  if ($explicitDir) {
    return (Get-AbsolutePath -PathValue $explicitDir)
  }

  if ($env:COMPANYLEADS_USE_DAILY_CHROME_PROFILE -eq "1" -or $env:QCWY_USE_DAILY_CHROME_PROFILE -eq "1") {
    $dailyDir = Get-DefaultChromeUserDataDir
    return (Ensure-DailyProfileLink -DailyUserDataDir $dailyDir)
  }

  return (Get-ControlledChromeUserDataDir)
}

$restartRequested = $RestartChrome -or $env:COMPANYLEADS_RESTART_CHROME_FOR_CDP -eq "1"

$preferredPort = if ($env:COMPANYLEADS_CHROME_DEBUG_PORT) {
  [int]$env:COMPANYLEADS_CHROME_DEBUG_PORT
} elseif ($env:QCWY_CHROME_DEBUG_PORT) {
  [int]$env:QCWY_CHROME_DEBUG_PORT
} else {
  9222
}

$port = $preferredPort
for ($candidate = $preferredPort; $candidate -le ($preferredPort + 20); $candidate++) {
  if (Test-CdpReady -Port $candidate) {
    $port = $candidate
    $env:COMPANYLEADS_CHROME_DEBUG_PORT = [string]$port
    Write-Host "Chrome CDP already available: http://127.0.0.1:$port"
    Write-CdpRuntime -Port $port -UserDataDir "" -ProfileDirectory "" -ChromePath ""
    return
  }

  if (-not (Test-PortHasListener -Port $candidate)) {
    $port = $candidate
    break
  }

  Write-Host "Port $candidate is occupied but not a Chrome CDP endpoint; trying next port."
}

$candidatePaths = @(
  $env:COMPANYLEADS_CHROME_PATH,
  $env:QCWY_CHROME_PATH,
  $env:CHROME_PATH,
  "C:\Program Files\Google\Chrome\Application\chrome.exe",
  "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
  (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
)

$candidates = @()
foreach ($candidate in $candidatePaths) {
  if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $candidate)) {
    $candidates += (Resolve-Path -LiteralPath $candidate).Path
  }
}

if (-not $candidates -or $candidates.Count -eq 0) {
  throw "Chrome executable was not found. Set COMPANYLEADS_CHROME_PATH or QCWY_CHROME_PATH."
}

$chrome = $candidates[0]
$chromeProcesses = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue
$chromeIsRunning = $null -ne ($chromeProcesses | Select-Object -First 1)
$userDataDir = Resolve-UserDataDir -RestartRequested $restartRequested -ChromeIsRunning $chromeIsRunning
$profileDirectory = Get-DefaultChromeProfileDirectory -UserDataDir $userDataDir

if ($restartRequested -and $chromeIsRunning -and ($env:COMPANYLEADS_USE_DAILY_CHROME_PROFILE -eq "1" -or $env:QCWY_USE_DAILY_CHROME_PROFILE -eq "1")) {
  Write-Host "Restart requested for daily Chrome profile: closing existing Chrome processes before opening CDP."
  foreach ($proc in $chromeProcesses) {
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Seconds 2
}

$args = @(
  "--user-data-dir=$userDataDir",
  "--profile-directory=$profileDirectory",
  "--remote-debugging-address=127.0.0.1",
  "--remote-debugging-port=$port",
  "--remote-allow-origins=*",
  "about:blank"
)

Write-Host "Starting Chrome CDP: http://127.0.0.1:$port"
Write-Host "Chrome: $chrome"
Write-Host "User data dir: $userDataDir"
Write-Host "Profile directory: $profileDirectory"
Start-Process -FilePath $chrome -ArgumentList $args -WindowStyle Normal

for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Milliseconds 500
  if (Test-CdpReady -Port $port) {
    $env:COMPANYLEADS_CHROME_DEBUG_PORT = [string]$port
    Write-CdpRuntime -Port $port -UserDataDir $userDataDir -ProfileDirectory $profileDirectory -ChromePath $chrome
    Write-Host "Chrome CDP is ready: http://127.0.0.1:$port"
    return
  }
}

throw "Chrome CDP is still unavailable at http://127.0.0.1:$port. Try setting COMPANYLEADS_CHROME_USER_DATA_DIR to another non-default Chrome user data directory, then run start_all.ps1 again."
