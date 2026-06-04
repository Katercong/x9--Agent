# X9 one-click launcher for the local stack.
#
# Default boot order:
#   1. PostgreSQL container, if :15432 is not already listening
#   2. Desktop FastAPI backend on 127.0.0.1:8000
#   3. Open the public workspace URL, unless -NoBrowser is passed
#
# Core (:18765, /api/v1) is optional. Start it with -StartCore.
# Use -RequireCore when /api/v1 must be available for the current task.
#
# Examples:
#   .\start_all.ps1
#   .\start_all.ps1 -NoBrowser
#   .\start_all.ps1 -StartCore -NoBrowser
#   .\start_all.ps1 -StartCore -RequireCore -OpenLocal

param(
    [switch]$NoBrowser,
    [switch]$StartCore,
    [switch]$SkipCore,       # Back-compat: force-skip Core even if -StartCore is provided.
    [switch]$RequireCore,    # Fail the launcher if Core does not become healthy.
    [switch]$OpenLocal       # Open http://localhost:8000/portal/ instead of the public URL.
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $root "logs"
$corePort = 18765
$desktopPort = 8000
$pgPort = 15432

$workspaceSlug = if ($env:X9_WORKSPACE_SLUG) { $env:X9_WORKSPACE_SLUG } else { "cross-border" }
$coreUrl = "http://localhost:$corePort"
$desktopUrl = "http://localhost:$desktopPort"
$desktopHealthUrl = "$desktopUrl/health"
$coreHealthUrl = "$coreUrl/api/v1/version"

if ($env:X9_PUBLIC_BASE_URL) {
    $publicBaseUrl = $env:X9_PUBLIC_BASE_URL.TrimEnd("/")
} elseif ($env:PUBLIC_BASE_URL) {
    $publicBaseUrl = $env:PUBLIC_BASE_URL.TrimEnd("/")
} else {
    $publicBaseUrl = "https://usx9.us"
}

if ($env:X9_OPEN_URL) {
    $openUrl = $env:X9_OPEN_URL
} elseif ($OpenLocal) {
    $openUrl = "$desktopUrl/portal/"
} else {
    $openUrl = "$publicBaseUrl/workspace/$workspaceSlug/"
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-Step([string]$message) {
    Write-Host "[start_all] $message"
}

function Write-Ok([string]$message) {
    Write-Host "[start_all] OK $message"
}

function Test-PortListening([int]$port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
}

function Get-PortOwnerSummary([int]$port) {
    $listeners = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if (-not $listeners) { return "" }

    $parts = @()
    foreach ($listener in $listeners) {
        $ownerPid = $listener.OwningProcess
        $name = "unknown"
        try {
            $proc = Get-Process -Id $ownerPid -ErrorAction Stop
            $name = $proc.ProcessName
        } catch {
            $name = "pid-$ownerPid"
        }
        $parts += "$name#$ownerPid"
    }
    return ($parts | Sort-Object -Unique) -join ", "
}

function Wait-Port([int]$port, [int]$timeoutSeconds = 60) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortListening $port) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Get-HttpStatus([string]$url) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 5
        return [int]$response.StatusCode
    } catch {
        $resp = $_.Exception.Response
        if ($resp -and $resp.StatusCode) {
            return [int]$resp.StatusCode
        }
        return 0
    }
}

function Wait-HttpStatus([string]$url, [int[]]$acceptedStatusCodes, [int]$timeoutSeconds = 60) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $status = Get-HttpStatus $url
        if ($acceptedStatusCodes -contains $status) {
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Test-PythonWorks([string]$file, [string[]]$prefixArgs) {
    try {
        $callArgs = @($prefixArgs) + @("-c", "import sys")
        & $file @callArgs 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Resolve-PythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        if (Test-PythonWorks "py" @("-3.11")) {
            return @{ File = "py"; Args = @("-3.11") }
        }
    }

    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "C:\Python311\python.exe",
        "C:\Program Files\Python311\python.exe"
    )
    foreach ($candidate in $candidates) {
        if ((Test-Path $candidate) -and (Test-PythonWorks $candidate @())) {
            return @{ File = $candidate; Args = @() }
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and (Test-PythonWorks $python.Source @())) {
        return @{ File = $python.Source; Args = @() }
    }

    throw "No working Python 3.11 found. Install Python 3.11 or fix the py launcher."
}

function Test-DockerUsable {
    & cmd.exe /c "docker version >nul 2>nul"
    return ($LASTEXITCODE -eq 0)
}

function Start-DockerDesktop {
    $candidates = @(
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
        "$env:LocalAppData\Docker\Docker Desktop.exe"
    )
    $cmd = Get-Command "Docker Desktop.exe" -ErrorAction SilentlyContinue
    if ($cmd) { $candidates += $cmd.Source }

    foreach ($path in $candidates) {
        if ($path -and (Test-Path $path)) {
            Write-Step "starting Docker Desktop"
            Start-Process -FilePath $path -WindowStyle Minimized
            return $true
        }
    }
    return $false
}

function Wait-Docker([int]$timeoutSeconds = 120) {
    $elapsed = 0
    while ($elapsed -lt $timeoutSeconds) {
        if (Test-DockerUsable) { return $true }
        Start-Sleep -Seconds 3
        $elapsed += 3
        if (($elapsed % 15) -eq 0) {
            Write-Step "waiting for Docker Desktop... ${elapsed}s"
        }
    }
    return $false
}

function Ensure-Postgres {
    if (Test-PortListening $pgPort) {
        Write-Ok "PostgreSQL is listening on :$pgPort ($(Get-PortOwnerSummary $pgPort))"
        return
    }

    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        throw "PostgreSQL :$pgPort is not listening and docker.exe was not found. Install/start Docker Desktop, then rerun start_all."
    }

    if (-not (Test-DockerUsable)) {
        if (-not (Start-DockerDesktop)) {
            throw "Docker Desktop was not found. Start Docker Desktop manually, then rerun start_all."
        }
        if (-not (Wait-Docker 120)) {
            throw "Docker Desktop did not become ready within 120 seconds."
        }
    }

    Write-Step "starting or verifying PostgreSQL container"
    & "$root\infra\scripts\db_init.ps1"
    if ($LASTEXITCODE -ne 0) { throw "db_init.ps1 failed" }
    if (-not (Wait-Port $pgPort 30)) { throw "PostgreSQL :$pgPort did not become ready" }
    Write-Ok "PostgreSQL is listening on :$pgPort"
}

function Start-LoggedProcess(
    [string]$name,
    [string]$file,
    [string[]]$arguments,
    [string]$workingDirectory
) {
    $stdout = Join-Path $logDir "$name.out.log"
    $stderr = Join-Path $logDir "$name.err.log"
    Write-Step "starting $name"
    Write-Step "$name stdout: $stdout"
    Write-Step "$name stderr: $stderr"

    Start-Process `
        -FilePath $file `
        -ArgumentList $arguments `
        -WorkingDirectory $workingDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr
}

function Ensure-Desktop {
    if (Test-PortListening $desktopPort) {
        Write-Step "desktop is already listening on :$desktopPort ($(Get-PortOwnerSummary $desktopPort))"
    } else {
        $python = Resolve-PythonCommand
        Write-Step "using python: $($python.File) $($python.Args -join ' ')"
        $args = @($python.Args) + @(
            "-m", "uvicorn",
            "desktop.backend.main:app",
            "--host", "127.0.0.1",
            "--port", "$desktopPort"
        )
        Start-LoggedProcess "desktop-backend" $python.File $args $root
    }

    if (-not (Wait-HttpStatus $desktopHealthUrl @(200) 60)) {
        throw "Desktop backend did not become healthy at $desktopHealthUrl. Check logs\desktop-backend.err.log and logs\desktop-backend.out.log."
    }
    Write-Ok "Desktop health: $desktopHealthUrl"
}

function Ensure-Core {
    if ($SkipCore) {
        Write-Step "core skipped (-SkipCore)"
        return $false
    }
    if (-not $StartCore) {
        Write-Step "core not started (pass -StartCore to enable /api/v1)"
        return $false
    }

    if (Test-PortListening $corePort) {
        Write-Step "core is already listening on :$corePort ($(Get-PortOwnerSummary $corePort))"
    } else {
        $env:X9_NO_BROWSER = "1"
        if (-not $env:X9_CORE_API_AUTH_DISABLED) {
            $env:X9_CORE_API_AUTH_DISABLED = "1"
        }

        $python = Resolve-PythonCommand
        Write-Step "using python for core: $($python.File) $($python.Args -join ' ')"
        $args = @($python.Args) + @(
            "-m", "uvicorn",
            "app.main:app",
            "--host", "127.0.0.1",
            "--port", "$corePort"
        )
        Start-LoggedProcess "core-backend" $python.File $args (Join-Path $root "core")
    }

    $ready = Wait-HttpStatus $coreHealthUrl @(200) 75
    if ($ready) {
        Write-Ok "Core API: $coreHealthUrl"
        return $true
    }

    $message = "Core did not become healthy at $coreHealthUrl. Check logs\core-backend.err.log and logs\core-backend.out.log."
    if ($RequireCore) {
        throw $message
    }
    Write-Warning "$message /api/v1 features may be unavailable."
    return $false
}

Write-Step "root: $root"
Write-Step "logs: $logDir"

Ensure-Postgres
$coreReady = Ensure-Core
Ensure-Desktop

Write-Host ""
Write-Ok "PostgreSQL : localhost:$pgPort"
if ($StartCore -and $coreReady) {
    Write-Ok "Core API   : $coreUrl"
} elseif ($StartCore) {
    Write-Warning "Core API requested but not healthy"
}
Write-Ok "Desktop    : $desktopUrl"
Write-Ok "Open URL   : $openUrl"
Write-Host ""

if (-not $NoBrowser) {
    Start-Process $openUrl
}
