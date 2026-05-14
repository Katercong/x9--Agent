# db_init: make sure x9-postgres container is running.
#
# Usage:  .\infra\scripts\db_init.ps1
#
# First run creates the x9_pgdata volume and starts the container.
# Otherwise just ensures it is running.

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$compose = Join-Path $here "..\docker\docker-compose.yml"

function Test-X9PostgresExists {
    $id = docker ps -a --filter "name=^/x9-postgres$" --format "{{.ID}}" 2>$null
    return [bool]$id
}

function Test-X9PostgresRunning {
    $status = docker inspect x9-postgres --format "{{.State.Status}}" 2>$null
    return ($status -eq "running")
}

function Test-X9PostgresReady {
    $health = docker inspect x9-postgres --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}" 2>$null
    if ($health -eq "healthy") {
        return $true
    }
    & cmd.exe /c "docker exec x9-postgres pg_isready -U x9 -d x9db >nul 2>nul"
    return ($LASTEXITCODE -eq 0)
}

# Volume must exist (compose declares it as external: true). pg_dump backups depend on it.
$volExists = docker volume ls --filter "name=x9_pgdata" --format "{{.Name}}" 2>$null
if (-not $volExists) {
    Write-Host "[db_init] creating volume x9_pgdata"
    docker volume create x9_pgdata | Out-Null
}

if (Test-X9PostgresExists) {
    if (Test-X9PostgresRunning) {
        Write-Host "[db_init] existing x9-postgres container is already running"
    } else {
        Write-Host "[db_init] starting existing x9-postgres container"
        docker start x9-postgres | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "docker start x9-postgres failed" }
    }
} else {
    Write-Host "[db_init] docker compose up -d"
    docker compose -f $compose up -d
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }
}

# Wait for health
Write-Host "[db_init] waiting for postgres to be ready..."
$timeout = 60
$elapsed = 0
while ($elapsed -lt $timeout) {
    if (Test-X9PostgresReady) {
        Write-Host "[db_init] postgres is healthy (port 15432)"
        exit 0
    }
    Start-Sleep -Seconds 2
    $elapsed += 2
}
Write-Warning "[db_init] postgres did not become ready within ${timeout}s; check 'docker logs x9-postgres'"
exit 1
