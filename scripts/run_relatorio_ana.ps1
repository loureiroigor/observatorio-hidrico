param(
    [Parameter(Mandatory = $true)][string]$Modelo,
    [Parameter(Mandatory = $true)][string]$Ana,
    [string]$OutDir = "reports"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "ambiente .venv nao encontrado. rode: .\scripts\setup_env.ps1"
}

Set-Location $projectRoot
& $pythonExe -m src.processing.relatorio_ana --modelo $Modelo --ana $Ana --outdir $OutDir
