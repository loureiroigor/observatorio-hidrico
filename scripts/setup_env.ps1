param(
    [switch]$ForceRecreate,
    [switch]$InstallDev
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $projectRoot ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$pythonCommand = Get-Command py -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
}
if (-not $pythonCommand) {
    throw "Python nao encontrado. Instale o Python e marque a opcao 'Add python.exe to PATH'."
}

Write-Host "[setup] projeto: $projectRoot"

if ($ForceRecreate -and (Test-Path $venvPath)) {
    Write-Host "[setup] removendo .venv antigo"
    Remove-Item -Recurse -Force $venvPath
}

if (-not (Test-Path $pythonExe)) {
    Write-Host "[setup] criando ambiente virtual"
    & $pythonCommand.Source -m venv $venvPath
}

Write-Host "[setup] atualizando pip/setuptools/wheel"
& $pythonExe -m pip install --upgrade pip setuptools wheel

Write-Host "[setup] instalando dependencias principais"
& $pythonExe -m pip install --only-binary=:all: -r (Join-Path $projectRoot "requirements.txt")

if ($InstallDev) {
    Write-Host "[setup] instalando ferramentas opcionais"
    & $pythonExe -m pip install --only-binary=:all: ipykernel
}

Write-Host "[setup] validando imports principais"
& $pythonExe -c "import dash, dash_bootstrap_components, pandas, plotly, numpy, sklearn, matplotlib, seaborn; print('ok')"

Write-Host "[setup] concluido. para ativar: .\.venv\Scripts\Activate.ps1"
