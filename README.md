# observatorio hidrico - campo grande/ms

plataforma de monitoramento de risco hidrico com adapters multiprovedor, consenso ponderado e validacao com classes da ana.

## setup rapido (windows powershell)

1. preparar ambiente virtual e dependencias:

```powershell
.\scripts\setup_env.ps1
```

2. iniciar dashboard:

```powershell
.\scripts\run_dashboard.ps1
```

3. gerar relatorio de validacao ana:

```powershell
.\scripts\run_relatorio_ana.ps1 -Modelo "data/templates/dados_modelo.csv" -Ana "data/templates/dados_ana.csv" -OutDir "reports"
```

## observacoes

- o vscode ja esta configurado para usar `./.venv` em `.vscode/settings.json`.
- se quiser recriar o ambiente do zero: `./scripts/setup_env.ps1 -ForceRecreate`.
