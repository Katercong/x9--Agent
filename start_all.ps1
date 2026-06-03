# start_all: one-click launcher for the X9 local stack.
#
# Boot order:
#   1. PostgreSQL container (if not running)
#   2. Desktop FastAPI UI    (127.0.0.1:8000, reached publicly through cloudflared/usx9.us)
#   3. Open the current workspace dashboard
#
# Core (:18765, /api/v1) is OPTIONAL and OFF by default. The public usx9.us face is the
# Desktop app on :8000, so a missing/broken Core must never block the one-click launch.
# Add -StartCore to also launch it.
#
# Optional:
#   .\start_all.ps1 -NoBrowser
#   .\start_all.ps1 -StartCore   # also start Core (:18765, /api/v1)

param(
    [switch]$NoBrowser,
    [switch]$StartCore,   # also start Core (:18765, /api/v1); off by default
    [switch]$SkipCore     # back-compat: force-skip Core even if -StartCore is given
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$corePort = 18765
$desktopPort = 8000
$workspaceSlug = if ($env:X9_WORKSPACE_SLUG) { $env:X9_WORKSPACE_SLUG } else { "cross-border" }
$coreUrl = "http://localhost:$corePort"
$desktopUrl = "http://localhost:$desktopPort"
$publicBaseUrl = if ($env:PUBLIC_BASE_URL) { $env:PUBLIC_BASE_URL.TrimEnd("/") } else { "https://usx9.us" }
$workspaceUrl = "$publicBaseUrl/workspace/$workspaceSlug/"

function Test-PortListening([int]$port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
}

function Wait-Port([int]$port, [int]$timeoutSeconds = 60) {
    $retries = 0
    while ($retries -lt $timeoutSeconds) {
        if (Test-PortListening $port) { return $true }
        Start-Sleep -Seconds 1
        $retries++
    }
    return $false
}

# Confirm an interpreter actually runs (a stub python.exe missing its stdlib must
# never be picked just because it exists on PATH).
function Test-PythonWorks([string]$file, [string[]]$pre) {
    try {
        $callArgs = @($pre) + @("-c", "import sys")
        & $file @callArgs 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Resolve-PythonCommand {
    # The stack targets Python 3.11. Prefer the launcher's explicit 3.11, but VALIDATE
    # it runs so a broken default (e.g. py -> 3.12 with a missing stdlib) can't slip in.
    if (Get-Command py -ErrorAction SilentlyContinue) {
        if (Test-PythonWorks "py" @("-3.11")) { return @{ File = "py"; Args = @("-3.11") } }
    }
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "C:\Python311\python.exe",
        "C:\Program Files\Python311\python.exe"
    )
    foreach ($c in $candidates) {
        if ((Test-Path $c) -and (Test-PythonWorks $c @())) { return @{ File = $c; Args = @() } }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and (Test-PythonWorks $python.Source @())) { return @{ File = $python.Source; Args = @() } }
    throw "No working Python 3.11 found (tried 'py -3.11', %LOCALAPPDATA%\Programs\Python\Python311, PATH python). Install Python 3.11 or fix the py launcher."
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
            Write-Host "[start_all] starting Docker Desktop..."
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
            Write-Host "[start_all] waiting for Docker Desktop... ${elapsed}s"
        }
    }
    return $false
}

# ----- 1. PostgreSQL -----
$docker = Get-Command docker -ErrorAction SilentlyContinue
$dockerUsable = $false
if (Test-PortListening 15432) {
    Write-Host "[start_all] postgres is already listening on :15432"
} else {
    if ($docker) {
        $dockerUsable = Test-DockerUsable
    }
    if ($dockerUsable) {
        $pgRunning = docker ps --filter "name=x9-postgres" --filter "status=running" --format "{{.Names}}" 2>$null
        if (-not $pgRunning) {
            Write-Host "[start_all] postgres is not running, starting..."
            & "$root\infra\scripts\db_init.ps1"
            if ($LASTEXITCODE -ne 0) { throw "db_init failed" }
        } else {
            Write-Host "[start_all] postgres container is running; waiting for :15432"
        }
    } elseif ($docker) {
        if (-not (Start-DockerDesktop)) {
            throw "postgres port 15432 is not listening and Docker Desktop was not found. Start Docker Desktop, then run start_all.bat again."
        }
        if (-not (Wait-Docker 120)) {
            throw "Docker Desktop did not become ready within 120s. Wait until Docker Desktop says it is running, then run start_all.bat again."
        }
        Write-Host "[start_all] Docker is ready; starting postgres..."
        & "$root\infra\scripts\db_init.ps1"
        if ($LASTEXITCODE -ne 0) { throw "db_init failed" }
    } else {
        throw "postgres port 15432 is not listening and docker.exe was not found. Install/start Docker Desktop, then run start_all.bat again."
    }
    if (-not (Wait-Port 15432 30)) { throw "postgres port 15432 not listening" }
}

# ----- 2. Core backend (:18765) — OPTIONAL (/api/v1). Off by default. -----
# Core depends on core/.venv and is not required for the Desktop UI (the public
# usx9.us face is the Desktop app on :8000). Pass -StartCore to launch it; its
# readiness is best-effort and never fails the launch.
$wantCore = $StartCore -and (-not $SkipCore)
if (-not $wantCore) {
    Write-Host "[start_all] core (:$corePort) not started (pass -StartCore to enable /api/v1)"
} elseif (Test-PortListening $corePort) {
    Write-Host "[start_all] core is already running on :$corePort"
} else {
    Write-Host "[start_all] starting core API (:$corePort)..."
    $coreCmd = "set X9_NO_BROWSER=1&& call `"$root\core\run.bat`""
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $coreCmd -WindowStyle Minimized
}

# ----- 3. Desktop backend (:8000) — the required service -----
if (Test-PortListening $desktopPort) {
    Write-Host "[start_all] desktop is already running on :$desktopPort"
} else {
    Write-Host "[start_all] starting desktop UI (:$desktopPort)..."
    # Bind to loopback only. Public traffic enters through Cloudflare Tunnel/usx9.us.
    $python = Resolve-PythonCommand
    Write-Host "[start_all] using python: $($python.File) $($python.Args -join ' ')"
    $uvicornArgs = @($python.Args) + @("-m", "uvicorn", "desktop.backend.main:app", "--host", "127.0.0.1", "--port", "$desktopPort")
    Start-Process -FilePath $python.File -ArgumentList $uvicornArgs -WorkingDirectory $root -WindowStyle Minimized
}

# ----- Readiness: Desktop is required; Core is best-effort and never blocks the launch -----
Write-Host "[start_all] waiting for desktop (:$desktopPort) to be ready..."
$desktopReady = Wait-Port $desktopPort 60

$coreReady = $false
if ($wantCore) {
    $coreReady = Wait-Port $corePort 60
    if (-not $coreReady) {
        Write-Warning "core (:$corePort) did not become ready; /api/v1 features unavailable. Check core/logs (core/.venv may need rebuilding)."
    }
}

if ($desktopReady) {
    Write-Host ""
    if ($wantCore -and $coreReady) { Write-Host "OK Core API : $coreUrl" }
    Write-Host "OK Desktop  : $workspaceUrl"
    Write-Host ""
    if (-not $NoBrowser) {
        Start-Process $workspaceUrl
    }
} else {
    Write-Warning "desktop (:$desktopPort) did not become ready within 60s; check desktop/logs"
    exit 1
}
