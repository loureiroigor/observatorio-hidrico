# -*- coding: utf-8 -*-
import sys
import os
import pandas as pd
import dash
from dash import dcc, html
import plotly.express as px

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

fig = px.line(
    df_final, 
    x='Data', 
    y='Indice_Risco',
    title='Índice de Risco Hídrico ao Longo do Tempo',
    labels={'Data': 'Data de Coleta', 'Indice_Risco': 'Índice de Risco (1-10)'},
    markers=True 
)


fig.update_layout(
    xaxis_title='Data',
    yaxis_title='Índice de Risco',
    yaxis=dict(range=[0, 11]), 
    template='plotly_white'
)

app.layout = html.Div(children=[
    html.H1(
        children='Observatório de Segurança Hídrica',
        style={'textAlign': 'center', 'color': '#007BFF'}
    ),

    html.Div(
        children='Dashboard para monitoramento de risco hídrico baseado em dados de precipitação.',
        style={'textAlign': 'center', 'marginBottom': '20px'}
    ),

    dcc.Graph(
        id='risk-graph',
        figure=fig
    )
])


if __name__ == '__main__':
    app.run(debug=True)
