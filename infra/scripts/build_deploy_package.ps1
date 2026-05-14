param(
  [string]$PackageName = "auto-boker-grab-deploy"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DeployDir = Join-Path $ProjectRoot "deploy"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$StageRoot = Join-Path $DeployDir "stage"
$StagePackage = Join-Path $StageRoot $PackageName
$ZipPath = Join-Path $DeployDir "$PackageName-$Stamp.zip"

function Assert-PathUnder {
  param([string]$Path, [string]$Parent)
  $resolvedParent = [System.IO.Path]::GetFullPath($Parent)
  $resolvedPath = [System.IO.Path]::GetFullPath($Path)
  if (-not $resolvedPath.StartsWith($resolvedParent, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to touch path outside deployment directory: $resolvedPath"
  }
}

New-Item -ItemType Directory -Force -Path $DeployDir | Out-Null
Assert-PathUnder -Path $StageRoot -Parent $DeployDir
if (Test-Path $StageRoot) {
  Remove-Item -Recurse -Force -LiteralPath $StageRoot
}
New-Item -ItemType Directory -Force -Path $StagePackage | Out-Null

$excludeDirs = @(
  ".git",
  ".pytest_cache",
  "__pycache__",
  "node_modules",
  "logs",
  "deploy"
)
$excludeFiles = @(
  "*.pyc",
  "*.pyo",
  "*.log",
  "*.err",
  "Thumbs.db",
  ".DS_Store"
)

robocopy $ProjectRoot $StagePackage /E /XD $excludeDirs /XF $excludeFiles /R:1 /W:1 /NFL /NDL /NP | Out-Host
if ($LASTEXITCODE -gt 7) {
  throw "robocopy failed with exit code $LASTEXITCODE"
}

if (Test-Path $ZipPath) {
  Assert-PathUnder -Path $ZipPath -Parent $DeployDir
  Remove-Item -Force -LiteralPath $ZipPath
}
Compress-Archive -LiteralPath $StagePackage -DestinationPath $ZipPath -CompressionLevel Optimal

$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $ZipPath
Write-Host ""
Write-Host "Deployment package created:"
Write-Host "  $ZipPath"
Write-Host "SHA256:"
Write-Host "  $($hash.Hash)"
