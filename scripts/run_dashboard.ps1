$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "ambiente .venv nao encontrado. rode: .\scripts\setup_env.ps1"
}

Set-Location $projectRoot
& $pythonExe -m dashboard.app
