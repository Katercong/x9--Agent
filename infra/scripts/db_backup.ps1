# db_backup: run pg_dump against x9-postgres, write to F:\backup\
#
# Usage:  .\infra\scripts\db_backup.ps1
#
# Each run produces a new file named x9db_YYYYMMDD_HHMM.sql.

$ErrorActionPreference = "Stop"
$backupDir = "F:\backup"
if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir -Force | Out-Null }

$ts = Get-Date -Format "yyyyMMdd_HHmm"
$out = Join-Path $backupDir "x9db_$ts.sql"

Write-Host "[db_backup] dumping x9db -> $out"
docker exec x9-postgres pg_dump -U x9 -d x9db --format=plain --no-owner --no-privileges | Out-File -FilePath $out -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed" }

$size = [math]::Round((Get-Item $out).Length / 1MB, 2)
Write-Host "[db_backup] done: $out ($size MB)"
