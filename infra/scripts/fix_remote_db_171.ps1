$ErrorActionPreference = "Stop"

$RemoteApiUrl = "http://192.168.1.171:18765"
$StartDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-ProjectRoot {
  param([string]$BaseDir)

  $candidates = @(
    $BaseDir,
    (Join-Path $BaseDir "Auto boker grab"),
    (Join-Path $BaseDir "auto-boker-grab-deploy")
  )

  foreach ($candidate in $candidates) {
    if (Test-Path (Join-Path $candidate "x9_creator_desktop_system\backend\config.py")) {
      return $candidate
    }
    if (Test-Path (Join-Path $candidate "backend\config.py")) {
      return $candidate
    }
  }

  $found = Get-ChildItem -Path $BaseDir -Recurse -Filter config.py -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "backend\\config\.py$" } |
    Select-Object -First 1

  if ($found) {
    $backendDir = Split-Path -Parent $found.FullName
    $systemDir = Split-Path -Parent $backendDir
    if ((Split-Path -Leaf $systemDir) -eq "x9_creator_desktop_system") {
      return Split-Path -Parent $systemDir
    }
    return $systemDir
  }

  throw "Cannot find backend\config.py under $BaseDir"
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

  if (-not (Test-Path $ConfigPath)) {
    throw "Missing config.py: $ConfigPath"
  }

  $content = Get-Content -Raw -LiteralPath $ConfigPath
  $content = $content -replace 'os\.getenv\("REMOTE_API_URL",\s*"http://[^"]+"\)', "os.getenv(`"REMOTE_API_URL`", `"$RemoteApiUrl`")"
  Set-Content -LiteralPath $ConfigPath -Value $content -Encoding UTF8
}

$ProjectRoot = Find-ProjectRoot -BaseDir $StartDir

if (Test-Path (Join-Path $ProjectRoot "x9_creator_desktop_system\backend\config.py")) {
  $SystemDir = Join-Path $ProjectRoot "x9_creator_desktop_system"
} else {
  $SystemDir = $ProjectRoot
}

$EnvPath = Join-Path $SystemDir ".env"
$ConfigPath = Join-Path $SystemDir "backend\config.py"

Set-RemoteApiInEnv -EnvPath $EnvPath
Set-RemoteApiInConfig -ConfigPath $ConfigPath

Write-Host ""
Write-Host "Remote database config fixed."
Write-Host "Project root: $ProjectRoot"
Write-Host ".env:         $EnvPath"
Write-Host "config.py:    $ConfigPath"
Write-Host "REMOTE_API_URL=$RemoteApiUrl"
Write-Host ""
Write-Host "Now restart the backend/app."
