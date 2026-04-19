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

## estrutura principal

- `src/scraping/adapters/`: conectores por fonte (imasul, cemaden, ana, inmet, open-meteo).
- `src/scraping/provider_hub.py`: orquestra coleta e garante fallback para nao derrubar o painel.
- `src/processing/calculadora_risco.py`: motor cientifico do indice, confidence score e tendencia.
- `src/processing/relatorio_ana.py`: validacao estatistica contra classes ana (matriz + kappa).
- `dashboard/app.py`: visualizacao unificada e explicavel para tomada de decisao.

## logica do calculo (resumo objetivo)

1. normaliza sinais para escala `[0,1]`.
2. aplica consenso ponderado: `40% rios + 40% solo + 20% chuva`.
3. usa ancora da ana (`S0..S4`) para contexto regional.
4. aplica recuperacao exponencial com inercia hidrologica.
5. converte para indice publico `1..10`.

## evidencias para banca (checklist)

### 1) status 5/5 provedores ativos

rode:

```powershell
.\.venv\Scripts\python.exe -c "from src.processing.calculadora_risco import montar_painel_risco; p=montar_painel_risco(); print(p['status_provedores'])"
```

resultado esperado: dicionario com 5 fontes em `ok`.

### 2) validacao cientifica (matriz + kappa)

preencha os templates:

- `data/templates/dados_modelo.csv`
- `data/templates/dados_ana.csv`

rode:

```powershell
.\scripts\run_relatorio_ana.ps1 -Modelo "data/templates/dados_modelo.csv" -Ana "data/templates/dados_ana.csv" -OutDir "reports"
```

artefatos para anexar no artigo:

- `reports/relatorio_metricas_ana.csv`
- `reports/relatorio_matriz_confusao_ana.csv`
- `reports/matriz_confusao_ana.png`

### 3) evidencias visuais do painel

rode:

```powershell
.\scripts\run_dashboard.ps1
```

capture 3 prints:

- cards principais (indice, confidence score, tendencia)
- bloco "status dos provedores" (ativos/fallback)
- tabela "diagnostico de convergencia"

## observacoes

- o vscode ja esta configurado para usar `./.venv` em `.vscode/settings.json`.
- para recriar ambiente do zero: `./scripts/setup_env.ps1 -ForceRecreate`.
- cache `__pycache__` e saidas de `reports/` nao sao codigo-fonte do projeto.
