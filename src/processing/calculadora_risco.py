from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Dict, List

import pandas as pd

from src.scraping.provider_hub import ProviderHub


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _safe_float(value: object, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def normalize_river_level(level_m: float, drought_floor: float = 1.0, healthy_level: float = 5.0) -> float:
    position = (level_m - drought_floor) / (healthy_level - drought_floor)
    return _clip(1.0 - position)


def normalize_soil_moisture(soil_pct: float, dry_pct: float = 20.0, healthy_pct: float = 60.0) -> float:
    position = (soil_pct - dry_pct) / (healthy_pct - dry_pct)
    return _clip(1.0 - position)


def normalize_precipitation(precip_mm: float, wet_ref: float = 25.0) -> float:
    return _clip(1.0 - (precip_mm / wet_ref))


ANA_RISK_MAP = {
    "S0": 0.20,
    "S1": 0.35,
    "S2": 0.55,
    "S3": 0.78,
    "S4": 0.95,
}


def ana_class_to_risk(classification: str) -> float:
    key = str(classification).strip().upper()
    return ANA_RISK_MAP.get(key, ANA_RISK_MAP["S1"])


@dataclass
class ConsensusSignal:
    name: str
    weight: float
    normalized_risk: float
    status: str
    raw_value: float
    unit: str


def _weighted_consensus(signals: List[ConsensusSignal]) -> float:
    available = [s for s in signals if s.status == "ok"]
    if not available:
        return 0.5

    total_weight = sum(s.weight for s in available)
    if total_weight <= 0:
        return 0.5

    return sum((s.weight / total_weight) * s.normalized_risk for s in available)


def _rainy_streak(precip_series: pd.Series, threshold_mm: float = 5.0) -> int:
    streak = 0
    for value in reversed(precip_series.fillna(0.0).tolist()):
        if value >= threshold_mm:
            streak += 1
        else:
            break
    return streak


def _recovery_factor(rainy_days: int, decay_rate: float = 0.45) -> float:
    return math.exp(-decay_rate * rainy_days)


def _weekly_history(df_daily: pd.DataFrame, base_consensus: float, ana_anchor: float) -> pd.DataFrame:
    if df_daily.empty:
        return pd.DataFrame(columns=["Data", "Precipitacao_mm", "Risco_Base", "Risco_Ajustado"])

    history = df_daily.copy()
    history["Data"] = pd.to_datetime(history["Data"], errors="coerce")
    history = history.dropna(subset=["Data"]).sort_values("Data")
    history["Precipitacao_mm"] = pd.to_numeric(history["Precipitacao_mm"], errors="coerce").fillna(0.0)

    streak = 0
    adjusted_values: List[float] = []
    base_values: List[float] = []

    for precip in history["Precipitacao_mm"].tolist():
        precip_risk = normalize_precipitation(float(precip))
        estimated_base = (0.8 * base_consensus) + (0.2 * precip_risk)
        base_values.append(estimated_base)

        if precip >= 5.0:
            streak += 1
        else:
            streak = 0

        recovery = _recovery_factor(streak)
        adjusted_values.append(ana_anchor + (estimated_base - ana_anchor) * recovery)

    history["Risco_Base"] = base_values
    history["Risco_Ajustado"] = adjusted_values
    history["Indice_Risco"] = 1.0 + 9.0 * history["Risco_Ajustado"]
    history["Data"] = history["Data"].dt.strftime("%Y-%m-%d")
    return history.tail(7)


def montar_painel_risco() -> Dict[str, object]:
    hub = ProviderHub()
    collected = hub.collect_all()

    daily_precip = collected["open_meteo"].payload.get("daily", pd.DataFrame())
    daily_precip = daily_precip.copy()
    if "Precipitacao_mm" not in daily_precip.columns:
        daily_precip = pd.DataFrame(
            [{"Data": datetime.now().strftime("%Y-%m-%d"), "Precipitacao_mm": 0.0}]
        )

    last_precip = 0.0
    if not daily_precip.empty:
        last_precip = _safe_float(daily_precip["Precipitacao_mm"].iloc[-1], 0.0)

    river_level = _safe_float(collected["imasul"].payload.get("mean_level_m", 2.2), 2.2)
    soil_moisture = _safe_float(collected["cemaden"].payload.get("mean_soil_moisture", 37.0), 37.0)
    ana_class = str(collected["ana"].payload.get("classification", "S1"))

    signals = [
        ConsensusSignal(
            name="Nivel dos rios (IMASUL)",
            weight=0.40,
            normalized_risk=normalize_river_level(river_level),
            status=collected["imasul"].status,
            raw_value=river_level,
            unit="m",
        ),
        ConsensusSignal(
            name="Umidade do solo (CEMADEN)",
            weight=0.40,
            normalized_risk=normalize_soil_moisture(soil_moisture),
            status=collected["cemaden"].status,
            raw_value=soil_moisture,
            unit="%",
        ),
        ConsensusSignal(
            name="Precipitacao diaria (INMET/Open-Meteo)",
            weight=0.20,
            normalized_risk=normalize_precipitation(last_precip),
            status="ok" if collected["open_meteo"].status == "ok" or collected["inmet"].status == "ok" else "unavailable",
            raw_value=last_precip,
            unit="mm",
        ),
    ]

    base_consensus = _weighted_consensus(signals)
    rainy_days = _rainy_streak(pd.to_numeric(daily_precip["Precipitacao_mm"], errors="coerce"), threshold_mm=5.0)
    recovery_multiplier = _recovery_factor(rainy_days)
    ana_anchor = ana_class_to_risk(ana_class)
    adjusted_consensus = ana_anchor + (base_consensus - ana_anchor) * recovery_multiplier
    risk_index = 1.0 + (9.0 * _clip(adjusted_consensus))

    weekly = _weekly_history(daily_precip, base_consensus, ana_anchor)
    weekly_avg_risk = float(weekly["Indice_Risco"].mean()) if not weekly.empty else risk_index
    weekly_avg_precip = float(weekly["Precipitacao_mm"].mean()) if not weekly.empty else last_precip

    diagnostics = []
    for signal in signals:
        contribution = signal.weight * signal.normalized_risk
        diagnostics.append(
            {
                "Fonte": signal.name,
                "Status": "Ativo" if signal.status == "ok" else "Fallback",
                "Valor": f"{signal.raw_value:.2f} {signal.unit}",
                "Risco Normalizado": round(signal.normalized_risk, 3),
                "Peso": f"{int(signal.weight * 100)}%",
                "Contribuicao": round(contribution, 3),
            }
        )

    status_map = {name: result.status for name, result in collected.items()}

    return {
        "coleta": collected,
        "df_precipitacao": daily_precip,
        "df_historico_semanal": weekly,
        "indice_risco": risk_index,
        "consenso_base": base_consensus,
        "consenso_ajustado": adjusted_consensus,
        "fator_recuperacao": recovery_multiplier,
        "dias_chuva_consecutivos": rainy_days,
        "classificacao_ana": ana_class,
        "diagnostico_df": pd.DataFrame(diagnostics),
        "status_provedores": status_map,
        "resumo_semanal": {
            "risco_medio": weekly_avg_risk,
            "chuva_media": weekly_avg_precip,
            "dias_chuvosos": int((weekly["Precipitacao_mm"] >= 5.0).sum()) if not weekly.empty else 0,
        },
    }


def calcular_vulnerabilidade(df_chuva: pd.DataFrame) -> pd.DataFrame:
    df = df_chuva.copy()
    if "Precipitacao_mm" not in df.columns:
        df["Precipitacao_mm"] = 0.0

    df["Risco_Normalizado"] = df["Precipitacao_mm"].apply(lambda x: normalize_precipitation(_safe_float(x, 0.0)))
    df["Indice_Risco"] = 1.0 + (9.0 * df["Risco_Normalizado"])
    return df


if __name__ == "__main__":
    painel = montar_painel_risco()
    print(f"Indice de risco atual: {painel['indice_risco']:.2f}")
