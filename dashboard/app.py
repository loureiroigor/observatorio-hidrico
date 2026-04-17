# -*- coding: utf-8 -*-
import sys
import os
import pandas as pd
import dash
from dash import dcc, html
import plotly.graph_objects as go
import dash_bootstrap_components as dbc

# Ajuste de caminho para os módulos internos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importação do pipeline de dados
from src.scraping.inmet_scraper import coletar_dados_chuva
from src.processing.calculadora_risco import calcular_vulnerabilidade

# 1. Coleta e Processamento
df_chuva = coletar_dados_chuva()
df_final = calcular_vulnerabilidade(df_chuva)
df_final['Data'] = pd.to_datetime(df_final['Data'])

# Extração de métricas para os Cards
last_data_leitura = df_final['Data'].iloc[-1].strftime('%d/%m/%Y %H:%M')
risco_hidrico_atual = df_final['Indice_Risco'].iloc[-1]

# 2. Configuração do Gráfico de Eixo Duplo (V2)
fig = go.Figure()

# Linha de Risco (Eixo Y1)
fig.add_trace(go.Scatter(
    x=df_final['Data'], 
    y=df_final['Indice_Risco'], 
    mode='lines+markers', 
    name='Nível de Risco (1-10)',
    line=dict(color='crimson', width=4),
    yaxis='y1'
))

# Barras de Chuva (Eixo Y2)
fig.add_trace(go.Bar(
    x=df_final['Data'], 
    y=df_final['Precipitacao_mm'], 
    name='Chuva Acumulada (mm)',
    marker_color='royalblue',
    yaxis='y2'
))

fig.update_layout(
    xaxis_title='Data de Coleta',
    yaxis=dict(
        title='Risco Hídrico',
        range=[0, 10],
        side='left',
        showgrid=True,
        gridcolor='lightgrey'
    ),
    yaxis2=dict(
        title='Precipitação (mm)',
        overlaying='y',
        side='right',
        showgrid=False,
        rangemode='tozero'
    ),
    legend=dict(
        x=0.5,
        y=1.05, 
        xanchor='center',
        yanchor='bottom',
        orientation='h'
    ),
    template='plotly_white',
    hovermode='x unified'
)

# 3. Layout da Interface (V2 Sólida com Bootstrap)
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])
server = app.server

app.layout = dbc.Container([
    # Cabeçalho
    html.H2("Observatório Hídrico - Campo Grande / MS", className="text-center my-4"),
    html.P("Monitoramento em Tempo Real de Risco Hídrico via API Open-Meteo", className="text-center text-muted mb-5"),

    # Linha de Métricas (Cartões Coloridos)
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader("Status do Sistema", className="fw-bold"),
            dbc.CardBody([
                html.H4("Operacional", className="card-title"),
                html.P("O sistema está coletando e processando dados ativamente.", className="card-text"),
            ])
        ], color="success", inverse=True, className="h-100 shadow"), md=4),
        
        dbc.Col(dbc.Card([
            dbc.CardHeader("Data da Última Leitura", className="fw-bold"),
            dbc.CardBody([
                html.H4(last_data_leitura, className="card-title"),
                html.P("Última atualização dos dados de precipitação.", className="card-text"),
            ])
        ], color="info", inverse=True, className="h-100 shadow"), md=4),
        
        dbc.Col(dbc.Card([
            dbc.CardHeader("Risco Hídrico Atual", className="fw-bold"),
            dbc.CardBody([
                html.H4(f"{risco_hidrico_atual:.2f}", className="card-title"),
                html.P("Índice de risco atual (1-10).", className="card-text"),
            ])
        ], color="warning", inverse=True, className="h-100 shadow"), md=4),
    ], className="mb-4 g-4"),

    # Gráfico Principal
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(id='risk-graph', figure=fig)), className="shadow"))
    ]),

    # Nova Linha: Glossário e Contexto ODS 6 (Adicionada agora)
    dbc.Row([
        # Card explicativo dos níveis de risco
        dbc.Col(dbc.Card([
            dbc.CardHeader("Interpretando o Índice de Risco", className="fw-bold"),
            dbc.CardBody([
                html.Ul([
                    html.Li([html.B("8.0 a 10.0: Risco Crítico"), " - Escassez severa. Medidas de economia urgentes são recomendadas."]),
                    html.Li([html.B("4.0 a 7.0: Risco Moderado"), " - Atenção aos níveis de reservatórios e consumo consciente."]),
                    html.Li([html.B("1.0 a 3.0: Risco Baixo"), " - Abastecimento seguro. Condições climáticas favoráveis."]),
                ], className="card-text")
            ])
        ], color="light", className="shadow"), md=7),

        # Card de Alinhamento com a ONU (ODS 6)
        dbc.Col(dbc.Card([
            dbc.CardHeader("Compromisso ODS 6", className="fw-bold"),
            dbc.CardBody([
                html.P("Este projeto automatiza a transparência hídrica para assegurar a gestão sustentável da água e o saneamento para todos.", className="card-text small"),
                html.A("Saiba mais sobre o ODS 6", href="https://brasil.un.org/pt-br/sdgs/6", target="_blank", className="btn btn-outline-primary btn-sm")
            ])
        ], color="light", className="shadow"), md=5),
    ], className="mt-4 mb-5 g-4")

], fluid=True)

if __name__ == '__main__':
    app.run(debug=True)