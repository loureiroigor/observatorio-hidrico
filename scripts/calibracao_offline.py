"""calibracao offline de pesos e limiares para backtesting.

para rodar: py -m scripts.calibracao_offline
"""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import pandas as pd

from src.processing.calculadora_risco import (
    _recovery_factor_dynamic,
    ana_class_to_risk,
    normalize_precipitation,
    normalize_river_level,
    normalize_soil_moisture,
)
from scripts.backtesting_5meses import coletar_chuva_historica, montar_truth_ana_por_mes, simular_variaveis_lentas


ANA_CLASSES = ["S0", "S1", "S2", "S3", "S4"]


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def classificar_por_thresholds(indice_risco: float, thresholds: tuple[float, float, float, float]) -> str:
    t0, t1, t2, t3 = thresholds
    if indice_risco <= t0:
        return "S0"
    if indice_risco <= t1:
        return "S1"
    if indice_risco <= t2:
        return "S2"
    if indice_risco <= t3:
        return "S3"
    return "S4"


def simular_indice(
    df_base: pd.DataFrame,
    df_truth: pd.DataFrame,
    weights: tuple[float, float, float],
) -> pd.DataFrame:
    w_river, w_soil, w_precip = weights
    joined = df_base.merge(df_truth, on="Data", how="left")
    chuva = pd.to_numeric(joined["Precipitacao_mm"], errors="coerce").fillna(0.0)

    risco = []
    for idx, row in joined.iterrows():
        river_norm = normalize_river_level(float(row["NivelRio_m"]))
        soil_norm = normalize_soil_moisture(float(row["UmidadeSolo_pct"]))
        precip_norm = normalize_precipitation(float(row["Precipitacao_mm"]))

        consenso_base = (w_river * river_norm) + (w_soil * soil_norm) + (w_precip * precip_norm)
        recovery = _recovery_factor_dynamic(chuva.iloc[: idx + 1], river_norm, soil_norm)
        ana_anchor = ana_class_to_risk(str(row["Classe_ANA"]))
        consenso_ajustado = ana_anchor + (consenso_base - ana_anchor) * recovery
        risco.append(1.0 + 9.0 * _clip(consenso_ajustado))

    return pd.DataFrame(
        {
            "Data": joined["Data"],
            "Indice_Risco": risco,
            "Classe_ANA": joined["Classe_ANA"],
        }
    )


def avaliar(y_true: pd.Series, y_pred: pd.Series) -> tuple[float, float]:
    from sklearn.metrics import cohen_kappa_score

    yt = pd.Categorical(y_true.astype(str).str.upper(), categories=ANA_CLASSES, ordered=True)
    yp = pd.Categorical(y_pred.astype(str).str.upper(), categories=ANA_CLASSES, ordered=True)
    kappa = float(cohen_kappa_score(yt, yp, labels=ANA_CLASSES, weights="quadratic"))
    acc = float((yt == yp).mean())
    return kappa, acc


def gerar_combinacoes_pesos(step: float = 0.05) -> list[tuple[float, float, float]]:
    vals = [round(x * step, 2) for x in range(int(1 / step) + 1)]
    combos = []
    for wr, ws, wp in itertools.product(vals, vals, vals):
        if abs((wr + ws + wp) - 1.0) <= 1e-9 and 0.15 <= wp <= 0.35:
            combos.append((wr, ws, wp))
    return combos


def gerar_threshold_sets() -> list[tuple[float, float, float, float]]:
    base = (2.8, 4.6, 6.4, 8.2)
    offsets = [-0.2, -0.1, 0.0, 0.1, 0.2]
    out = []
    for o0, o1, o2, o3 in itertools.product(offsets, offsets, offsets, offsets):
        t = (round(base[0] + o0, 2), round(base[1] + o1, 2), round(base[2] + o2, 2), round(base[3] + o3, 2))
        if 1.8 < t[0] < t[1] < t[2] < t[3] < 9.5:
            out.append(t)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="calibracao offline de pesos e limiares")
    parser.add_argument("--dias", type=int, default=150, help="janela historica em dias")
    parser.add_argument("--top", type=int, default=30, help="quantidade de linhas no ranking final")
    parser.add_argument("--outdir", default="reports", help="diretorio de saida")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df_chuva = coletar_chuva_historica(dias=args.dias)
    df_base = simular_variaveis_lentas(df_chuva)
    df_truth = montar_truth_ana_por_mes(df_base)

    pesos = gerar_combinacoes_pesos(step=0.05)
    thresholds = gerar_threshold_sets()

    rows = []
    for w in pesos:
        sim = simular_indice(df_base, df_truth, w)
        for th in thresholds:
            pred = sim["Indice_Risco"].map(lambda x: classificar_por_thresholds(float(x), th))
            kappa, acc = avaliar(sim["Classe_ANA"], pred)
            rows.append(
                {
                    "w_river": w[0],
                    "w_soil": w[1],
                    "w_precip": w[2],
                    "t_s0": th[0],
                    "t_s1": th[1],
                    "t_s2": th[2],
                    "t_s3": th[3],
                    "kappa_ponderado": round(kappa, 6),
                    "acuracia": round(acc, 6),
                    "score_composto": round((0.8 * kappa) + (0.2 * acc), 6),
                }
            )

    ranking = pd.DataFrame(rows).sort_values(["score_composto", "kappa_ponderado", "acuracia"], ascending=False)
    ranking_path = outdir / "calibracao_offline_ranking.csv"
    best_path = outdir / "calibracao_offline_melhor.csv"

    ranking.to_csv(ranking_path, index=False)
    ranking.head(args.top).to_csv(best_path, index=False)

    best = ranking.iloc[0].to_dict()
    print("calibracao offline concluida")
    print(f"ranking completo: {ranking_path}")
    print(f"top {args.top}: {best_path}")
    print("melhor configuracao:")
    print(best)


if __name__ == "__main__":
    main()
