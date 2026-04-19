"""backtesting preliminar de 150 dias usando historico open-meteo.

para rodar: py -m scripts.backtesting_5meses
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from src.processing.calculadora_risco import (
    _recovery_factor_dynamic,
    ana_class_to_risk,
    normalize_precipitation,
    normalize_river_level,
    normalize_soil_moisture,
    risco_para_classe_ana,
    validar_modelo_vs_ana,
)


LAT_CG = -20.4697
LON_CG = -54.6201


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def coletar_chuva_historica(dias: int = 150) -> pd.DataFrame:
    end_date = date.today()
    start_date = end_date - timedelta(days=dias - 1)
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={LAT_CG}&longitude={LON_CG}"
        f"&start_date={start_date.isoformat()}&end_date={end_date.isoformat()}"
        "&daily=precipitation_sum&timezone=America%2FSao_Paulo"
    )

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    daily = response.json().get("daily", {})

    df = pd.DataFrame(
        {
            "Data": pd.to_datetime(daily.get("time", []), errors="coerce"),
            "Precipitacao_mm": pd.to_numeric(daily.get("precipitation_sum", []), errors="coerce"),
        }
    ).dropna(subset=["Data"])

    return df.fillna({"Precipitacao_mm": 0.0}).sort_values("Data").reset_index(drop=True)


def simular_variaveis_lentas(df_chuva: pd.DataFrame) -> pd.DataFrame:
    # simulacao dinamica para prova de conceito: chuva recarrega, estiagem drena lentamente
    soil = 38.0
    river = 2.3
    dry_days = 0
    rows = []

    for precip in df_chuva["Precipitacao_mm"].tolist():
        dry_days = dry_days + 1 if precip < 2.0 else 0
        soil = _clip(soil + (0.22 * min(precip, 18.0)) - 0.55 - (0.03 * dry_days), 18.0, 65.0)
        river = _clip(river + (0.012 * precip) - 0.018 - (0.002 * dry_days) + (0.0015 * (soil - 40.0)), 1.0, 5.5)
        rows.append((river, soil))

    out = df_chuva.copy()
    out[["NivelRio_m", "UmidadeSolo_pct"]] = pd.DataFrame(rows, index=out.index)
    return out


def montar_truth_ana_por_mes(df: pd.DataFrame) -> pd.DataFrame:
    monthly = (
        df.assign(Mes=df["Data"].dt.to_period("M"))
        .groupby("Mes", as_index=False)["Precipitacao_mm"]
        .sum()
    )

    def classe_por_chuva_total(total_mm: float) -> str:
        if total_mm <= 20:
            return "S4"
        if total_mm <= 45:
            return "S3"
        if total_mm <= 75:
            return "S2"
        if total_mm <= 115:
            return "S1"
        return "S0"

    monthly["Classe_ANA"] = monthly["Precipitacao_mm"].map(classe_por_chuva_total)
    merged = df.assign(Mes=df["Data"].dt.to_period("M")).merge(monthly[["Mes", "Classe_ANA"]], on="Mes", how="left")
    return merged[["Data", "Classe_ANA"]]


def aplicar_motor(df_base: pd.DataFrame, df_truth: pd.DataFrame) -> pd.DataFrame:
    joined = df_base.merge(df_truth, on="Data", how="left")
    riscos = []
    chuva_series = joined["Precipitacao_mm"].astype(float)

    for idx, row in joined.iterrows():
        river_norm = normalize_river_level(float(row["NivelRio_m"]))
        soil_norm = normalize_soil_moisture(float(row["UmidadeSolo_pct"]))
        precip_norm = normalize_precipitation(float(row["Precipitacao_mm"]))

        consenso_base = (0.4 * river_norm) + (0.4 * soil_norm) + (0.2 * precip_norm)
        recovery = _recovery_factor_dynamic(chuva_series.iloc[: idx + 1], river_norm, soil_norm)
        ana_anchor = ana_class_to_risk(str(row["Classe_ANA"]))

        consenso_ajustado = ana_anchor + (consenso_base - ana_anchor) * recovery
        riscos.append(1.0 + 9.0 * _clip(consenso_ajustado, 0.0, 1.0))

    out = joined[["Data"]].copy()
    out["Indice_Risco"] = riscos
    out["Classe_Modelo"] = out["Indice_Risco"].map(risco_para_classe_ana)
    return out


def main() -> None:
    output_dir = Path("reports")
    output_dir.mkdir(parents=True, exist_ok=True)

    df_chuva = coletar_chuva_historica(dias=150)
    df_base = simular_variaveis_lentas(df_chuva)
    df_ana = montar_truth_ana_por_mes(df_base)
    df_modelo = aplicar_motor(df_base, df_ana)

    modelo_path = output_dir / "dados_modelo_150.csv"
    ana_path = output_dir / "dados_ana_150.csv"
    metricas_path = output_dir / "relatorio_metricas_ana_150.csv"
    matriz_path = output_dir / "relatorio_matriz_confusao_ana_150.csv"

    df_modelo.assign(Data=df_modelo["Data"].dt.strftime("%Y-%m-%d"))[["Data", "Indice_Risco"]].to_csv(modelo_path, index=False)
    df_ana.assign(Data=df_ana["Data"].dt.strftime("%Y-%m-%d"))[["Data", "Classe_ANA"]].to_csv(ana_path, index=False)

    resultado = validar_modelo_vs_ana(
        df_modelo=df_modelo.assign(Data=df_modelo["Data"].dt.strftime("%Y-%m-%d")),
        df_ana=df_ana.assign(Data=df_ana["Data"].dt.strftime("%Y-%m-%d")),
    )

    pd.DataFrame(
        [
            {
                "n_amostras": resultado.get("n_amostras"),
                "kappa_ponderado": resultado.get("kappa_ponderado"),
                "acuracia": resultado.get("acuracia"),
            }
        ]
    ).to_csv(metricas_path, index=False)

    matriz = resultado.get("matriz_confusao", pd.DataFrame())
    if isinstance(matriz, pd.DataFrame):
        matriz.to_csv(matriz_path, index=True)

    print("backtesting 150 dias concluido")
    print(f"modelo: {modelo_path}")
    print(f"ana: {ana_path}")
    print(f"metricas: {metricas_path}")
    print(f"matriz: {matriz_path}")


if __name__ == "__main__":
    main()
