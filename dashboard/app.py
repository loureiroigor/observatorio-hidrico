import os
import sys

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.processing.calculadora_risco import montar_painel_risco


painel = montar_painel_risco()

df_precip = painel["df_precipitacao"].copy()
df_precip["Data"] = pd.to_datetime(df_precip["Data"], errors="coerce")
df_precip = df_precip.dropna(subset=["Data"]).sort_values("Data")

df_hist = painel["df_historico_semanal"].copy()
if not df_hist.empty:
    df_hist["Data"] = pd.to_datetime(df_hist["Data"], errors="coerce")

df_diagnostico = painel["diagnostico_df"]
df_imasul = painel["coleta"]["imasul"].payload.get("table", pd.DataFrame())
df_inmet = painel["coleta"]["inmet"].payload.get("table", pd.DataFrame())
df_openmeteo = painel["coleta"]["open_meteo"].payload.get("hourly", pd.DataFrame())

risco_atual = float(painel["indice_risco"])
risco_cor = "#e85d04" if risco_atual >= 8 else "#f48c06" if risco_atual >= 5 else "#2a9d8f"
confidence_score = float(painel.get("confidence_score", 0.0))
trend_info = painel.get("trend", {"trend": "estavel", "slope": 0.0})
trend_label = str(trend_info.get("trend", "estavel")).capitalize()
trend_slope = float(trend_info.get("slope", 0.0))
trend_color = "#e63946" if trend_label.lower() == "agravando" else "#2a9d8f" if trend_label.lower() == "recuperando" else "#577590"

fig_principal = go.Figure()
fig_principal.add_trace(
    go.Scatter(
        x=df_hist["Data"] if not df_hist.empty else df_precip["Data"],
        y=df_hist["Indice_Risco"] if not df_hist.empty else [],
        mode="lines+markers",
        name="Risco Ajustado",
        line=dict(color="#e76f51", width=3),
        marker=dict(size=8),
        yaxis="y1",
    )
)
fig_principal.add_trace(
    go.Bar(
        x=df_precip["Data"],
        y=df_precip["Precipitacao_mm"],
        name="Precipitacao (mm)",
        marker_color="#264653",
        opacity=0.45,
        yaxis="y2",
    )
)
fig_principal.update_layout(
    margin=dict(l=20, r=20, t=20, b=20),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(title="Data", showgrid=False),
    yaxis=dict(title="Indice de Risco (1-10)", range=[1, 10], gridcolor="rgba(38,70,83,0.12)"),
    yaxis2=dict(title="Chuva (mm)", overlaying="y", side="right", showgrid=False, rangemode="tozero"),
    legend=dict(orientation="h", y=1.07, x=0.5, xanchor="center"),
    hovermode="x unified",
)

fig_weekly = go.Figure()
if not df_hist.empty:
    fig_weekly.add_trace(
        go.Scatter(
            x=df_hist["Data"],
            y=df_hist["Risco_Base"],
            name="Consenso Base",
            mode="lines",
            line=dict(color="#577590", width=2, dash="dot"),
        )
    )
    fig_weekly.add_trace(
        go.Scatter(
            x=df_hist["Data"],
            y=df_hist["Risco_Ajustado"],
            name="Consenso Ajustado",
            mode="lines+markers",
            line=dict(color="#f94144", width=3),
            marker=dict(size=7),
        )
    )

fig_weekly.update_layout(
    margin=dict(l=20, r=20, t=20, b=20),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(title="Semana", showgrid=False),
    yaxis=dict(title="Risco normalizado", range=[0, 1], gridcolor="rgba(87,117,144,0.15)"),
    legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
)

provedores = painel["status_provedores"]
ativos = sum(1 for status in provedores.values() if status == "ok")

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server
app.title = "Observatorio Hidrico"

app.layout = dbc.Container(
    [
        html.Div(
            [
                html.H1("Observatorio Hidrico", className="hero-title"),
                html.P(
                    "Campo Grande/MS | consenso multiprovedor com fator de recuperacao hidrica",
                    className="hero-subtitle",
                ),
            ],
            className="hero",
        ),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.P("Indice Atual", className="metric-label"),
                                html.H2(f"{risco_atual:.2f}", className="metric-value", style={"color": risco_cor}),
                                html.P(
                                    f"ANA: {painel['classificacao_ana']} | Dias de chuva consecutivos: {painel['dias_chuva_consecutivos']}",
                                    className="metric-footnote",
                                ),
                            ]
                        ),
                        className="glass-card h-100",
                    ),
                    md=4,
                ),
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.P("Convergencia de Fontes", className="metric-label"),
                                html.H2(f"{ativos}/5 provedores ativos", className="metric-value"),
                                html.P(
                                    f"Fator de recuperacao: {painel['fator_recuperacao']:.3f}",
                                    className="metric-footnote",
                                ),
                            ]
                        ),
                        className="glass-card h-100",
                    ),
                    md=4,
                ),
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.P("Historico Semanal", className="metric-label"),
                                html.H2(
                                    f"Risco medio: {painel['resumo_semanal']['risco_medio']:.2f}",
                                    className="metric-value",
                                ),
                                html.P(
                                    f"Chuva media: {painel['resumo_semanal']['chuva_media']:.1f} mm | Dias chuvosos: {painel['resumo_semanal']['dias_chuvosos']}",
                                    className="metric-footnote",
                                ),
                            ]
                        ),
                        className="glass-card h-100",
                    ),
                    md=4,
                ),
            ],
            className="g-4 mb-4",
        ),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.P("Confidence Score", className="metric-label"),
                                html.H2(f"{confidence_score:.1f}/100", className="metric-value"),
                                html.P(
                                    "Disponibilidade e recencia das fontes em tempo real.",
                                    className="metric-footnote",
                                ),
                            ]
                        ),
                        className="glass-card h-100",
                    ),
                    md=6,
                ),
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.P("Tendencia do Risco", className="metric-label"),
                                html.H2(trend_label, className="metric-value", style={"color": trend_color}),
                                html.P(
                                    f"Inclinacao: {trend_slope:+.3f} ponto/dia",
                                    className="metric-footnote",
                                ),
                            ]
                        ),
                        className="glass-card h-100",
                    ),
                    md=6,
                ),
            ],
            className="g-4 mb-4",
        ),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H4("Diagnostico de Convergencia", className="section-title"),
                                html.P(
                                    "O risco final considera 40% nivel de rios (IMASUL), 40% umidade do solo (CEMADEN) e 20% precipitacao."
                                    " Em periodos de chuva consecutiva, o motor aplica decaimento exponencial e aproxima o indicador da classe ANA.",
                                    className="section-description",
                                ),
                                dbc.Table.from_dataframe(df_diagnostico, striped=True, bordered=False, hover=True, size="sm"),
                            ]
                        ),
                        className="panel-card",
                    ),
                    md=12,
                )
            ],
            className="mb-4",
        ),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody([html.H4("Risco x Precipitacao", className="section-title"), dcc.Graph(figure=fig_principal)]),
                        className="panel-card",
                    ),
                    md=8,
                ),
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody([html.H4("Recuperacao Semanal", className="section-title"), dcc.Graph(figure=fig_weekly)]),
                        className="panel-card",
                    ),
                    md=4,
                ),
            ],
            className="g-4 mb-4",
        ),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H4("Auditoria IMASUL", className="section-title"),
                                dbc.Table.from_dataframe(df_imasul, striped=True, bordered=False, hover=True, size="sm"),
                            ]
                        ),
                        className="panel-card",
                    ),
                    md=4,
                ),
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H4("Auditoria INMET", className="section-title"),
                                dbc.Table.from_dataframe(df_inmet, striped=True, bordered=False, hover=True, size="sm"),
                            ]
                        ),
                        className="panel-card",
                    ),
                    md=4,
                ),
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H4("Open-Meteo Horario", className="section-title"),
                                dbc.Table.from_dataframe(df_openmeteo, striped=True, bordered=False, hover=True, size="sm"),
                            ]
                        ),
                        className="panel-card",
                    ),
                    md=4,
                ),
            ],
            className="g-4 mb-5",
        ),
    ],
    fluid=True,
    className="dashboard-root",
)

if __name__ == "__main__":
    app.run(debug=True)
