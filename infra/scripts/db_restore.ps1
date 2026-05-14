# db_restore: restore x9db from a pg_dump file.
#
# Usage:  .\infra\scripts\db_restore.ps1 F:\backup\x9db_20260511_1349.sql
#
# WARNING: this DROPs the public schema (and all its data) before importing.
# No backup will recover live data written since then. Be sure before running.

param(
    [Parameter(Mandatory=$true)]
    [string]$BackupFile
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $BackupFile)) { throw "backup file not found: $BackupFile" }

# Double confirm
Write-Host ""
Write-Host "!!! About to restore x9db !!!" -ForegroundColor Yellow
Write-Host "    Backup file: $BackupFile"
Write-Host "    This will DROP SCHEMA public CASCADE and reimport."
Write-Host ""
$confirm = Read-Host "Type RESTORE to proceed, anything else cancels"
if ($confirm -ne "RESTORE") {
    Write-Host "[db_restore] cancelled"
    exit 0
}

Write-Host "[db_restore] dropping public schema..."
docker exec x9-postgres psql -U x9 -d x9db -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
if ($LASTEXITCODE -ne 0) { throw "drop schema failed" }

Write-Host "[db_restore] restoring from $BackupFile..."
Get-Content $BackupFile -Encoding utf8 | docker exec -i x9-postgres psql -U x9 -d x9db
if ($LASTEXITCODE -ne 0) { throw "psql restore failed" }

Write-Host "[db_restore] done. Run 'py tools\x9_creator_db_check.py' to verify."
