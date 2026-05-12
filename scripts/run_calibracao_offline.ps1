param(
    [int]$Dias = 150,
    [int]$Top = 30,
    [string]$OutDir = "reports"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "ambiente .venv nao encontrado. rode: .\scripts\setup_env.ps1"
}

Set-Location $projectRoot

Write-Host "[calibracao] iniciando calibracao offline"

& $pythonExe -m scripts.calibracao_offline --dias $Dias --top $Top --outdir $OutDir
if (-not $?) { throw "falha na etapa de calibracao_offline" }

Write-Host "[calibracao] concluida com sucesso"
Write-Host "- $OutDir/calibracao_offline_ranking.csv"
Write-Host "- $OutDir/calibracao_offline_melhor.csv"
