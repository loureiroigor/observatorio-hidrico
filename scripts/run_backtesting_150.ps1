param(
    [string]$OutDir = "reports"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "ambiente .venv nao encontrado. rode: .\scripts\setup_env.ps1"
}

Set-Location $projectRoot

Write-Host "[backtesting] iniciando pipeline 150 dias"

& $pythonExe -m scripts.backtesting_5meses
if (-not $?) { throw "falha na etapa de backtesting_5meses" }

& $pythonExe -m scripts.plot_backtesting_5meses --matrix-csv "$OutDir/relatorio_matriz_confusao_ana_150.csv" --metrics-csv "$OutDir/relatorio_metricas_ana_150.csv" --output-png "$OutDir/matriz_confusao_ana_150.png"
if (-not $?) { throw "falha na etapa de plot_backtesting_5meses" }

Write-Host "[backtesting] pipeline concluido com sucesso"
Write-Host "- $OutDir/dados_modelo_150.csv"
Write-Host "- $OutDir/dados_ana_150.csv"
Write-Host "- $OutDir/relatorio_metricas_ana_150.csv"
Write-Host "- $OutDir/relatorio_matriz_confusao_ana_150.csv"
Write-Host "- $OutDir/matriz_confusao_ana_150.png"
