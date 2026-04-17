# -*- coding: utf-8 -*-
import sys
import os
import pandas as pd
import dash
from dash import dcc, html
import plotly.graph_objects as go

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# importando função do pipeline de dados
from src.scraping.inmet_scraper import coletar_dados_chuva
from src.processing.calculadora_risco import calcular_vulnerabilidade

df_chuva = coletar_dados_chuva()

df_final = calcular_vulnerabilidade(df_chuva)
print(df_final) 

app = dash.Dash(__name__)
server = app.server

# criaçao do grafico 

fig = go.Figure()

fig.add_trace(go.Scatter(
    x=df_final['Data'], 
    y=df_final['Indice_Risco'], 
    mode='lines+markers', 
    name='Nível de Risco (1-10)',
    line=dict(color='crimson', width=4),
    yaxis='y1'
))

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

app.layout = html.Div(children=[
    html.H1(
        children='Observatório Hídrico - Campo Grande / MS',
        style={'textAlign': 'center', 'color': '#007BFF'}
    ),

    html.Div(
        children='Monitoramento em Tempo Real de Risco Hídrico via API Open-Meteo',
        style={'textAlign': 'center', 'marginBottom': '20px'}
    ),

    dcc.Graph(
        id='risk-graph',
        figure=fig,
        style={'marginTop': '20px'}
    )
])


if __name__ == '__main__':
    app.run(debug=True)
