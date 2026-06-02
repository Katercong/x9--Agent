# Compatibility entrypoint for older instructions.
# The actual foreign-trade helper installer is install_ft_helper.ps1.
param(
  [string]$ExtensionId = "idahdepjhfmldleebihlbnkmfhjbjbde",
  [string]$BackendUrl = "https://usx9.us",
  [string]$Department = "foreign_trade",
  [switch]$SkipPythonInstall
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$installer = Join-Path $root "install_ft_helper.ps1"
if (-not (Test-Path -LiteralPath $installer)) {
  throw "install_ft_helper.ps1 not found: $installer"
}

$argsMap = @{
  ExtensionId = $ExtensionId
  BackendUrl = $BackendUrl
  Department = $Department
}
if ($SkipPythonInstall) {
  $argsMap.SkipPythonInstall = $true
}

& $installer @argsMap
