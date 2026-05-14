# start_all: one-click launcher for the X9 local stack.
#
# Boot order:
#   1. PostgreSQL container (if not running)
#   2. Desktop FastAPI UI    (127.0.0.1:8000, reached publicly through cloudflared/usx9.us)
#   3. Open the current workspace dashboard
#
# Optional:
#   .\start_all.ps1 -NoBrowser
#   .\start_all.ps1 -StartCore   # legacy local API, normally off

param(
    [switch]$NoBrowser,
    [switch]$StartCore
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$corePort = 18765
$desktopPort = 8000
$workspaceSlug = if ($env:X9_WORKSPACE_SLUG) { $env:X9_WORKSPACE_SLUG } else { "cross-border" }
$coreUrl = "http://localhost:$corePort"
$desktopUrl = "http://localhost:$desktopPort"
$workspaceUrl = "$desktopUrl/workspace/$workspaceSlug/"

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

function Resolve-PythonCommand {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{ File = "py"; Args = @("-3.11") }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{ File = "python"; Args = @() }
    }
    throw "Python 3.11 launcher not found. Install Python or add python.exe to PATH."
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
if ($docker) {
    $dockerUsable = Test-DockerUsable
}
if (Test-PortListening 15432) {
    Write-Host "[start_all] postgres is already listening on :15432"
} elseif ($dockerUsable) {
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

# ----- 2. Legacy core backend (:18765) -----
if (-not $StartCore) {
    Write-Host "[start_all] skipping legacy core (:18765)"
} elseif (Test-PortListening $corePort) {
    Write-Host "[start_all] core is already running on :$corePort"
} else {
    Write-Host "[start_all] starting core API (:$corePort)..."
    $coreCmd = "set X9_NO_BROWSER=1&& call `"$root\core\run.bat`""
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $coreCmd -WindowStyle Minimized
}

# ----- 3. Desktop backend (:8000) -----
$dtRunning = Test-PortListening $desktopPort
if ($dtRunning) {
    Write-Host "[start_all] desktop is already running on :$desktopPort"
} else {
    Write-Host "[start_all] starting desktop UI (:$desktopPort)..."
    # Bind to loopback only. Public traffic enters through Cloudflare Tunnel/usx9.us.
    $python = Resolve-PythonCommand
    $args = @($python.Args) + @("-m", "uvicorn", "desktop.backend.main:app", "--host", "127.0.0.1", "--port", "$desktopPort")
    Start-Process -FilePath $python.File -ArgumentList $args -WorkingDirectory $root -WindowStyle Minimized
}

# Wait until both ports are ready
Write-Host "[start_all] waiting for ports to be ready..."
$desktopReady = Wait-Port $desktopPort 60
$coreReady = (-not $StartCore) -or (Wait-Port $corePort 60)

if ($desktopReady -and $coreReady) {
    Write-Host ""
    if ($StartCore) { Write-Host "OK Core API : $coreUrl" }
    Write-Host "OK Desktop : $workspaceUrl"
    Write-Host ""
    if (-not $NoBrowser) {
        Start-Process $workspaceUrl
    }
} else {
    Write-Warning "ports did not become ready within 60s; check core/logs or desktop/logs"
    Write-Warning "Core ready=$coreReady Desktop ready=$desktopReady"
    exit 1
}
