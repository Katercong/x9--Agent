# Windows Task Scheduler entrypoint for X9.
# Keeps auto-start quiet and writes enough output to diagnose boot issues.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logDir = Join-Path $root "desktop\logs"
$logFile = Join-Path $logDir "startup-task.log"
$startScript = Join-Path $root "start_all.ps1"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$startedAt] X9 auto-start requested." | Out-File -FilePath $logFile -Encoding UTF8 -Append

try {
    Set-Location -LiteralPath $root
    & $startScript -NoBrowser *>> $logFile

    $finishedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$finishedAt] X9 auto-start finished." | Out-File -FilePath $logFile -Encoding UTF8 -Append
}
catch {
    $failedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$failedAt] X9 auto-start failed: $($_.Exception.Message)" | Out-File -FilePath $logFile -Encoding UTF8 -Append
    exit 1
}
