from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from src.scraping.provider_hub import ProviderHub


ANA_RISK_MAP = {
    "S0": 0.20,
    "S1": 0.35,
    "S2": 0.55,
    "S3": 0.78,
    "S4": 0.95,
}

ANA_CLASSES = ["S0", "S1", "S2", "S3", "S4"]


@dataclass
class ConsensusSignal:
    name: str
    weight: float
    normalized_risk: float
    status: str
    raw_value: float
    unit: str


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _safe_float(value: object, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_river_level(level_m: float, drought_floor: float = 1.0, healthy_level: float = 5.0) -> float:
    position = (level_m - drought_floor) / (healthy_level - drought_floor)
    return _clip(1.0 - position)


def normalize_soil_moisture(soil_pct: float, dry_pct: float = 20.0, healthy_pct: float = 60.0) -> float:
    position = (soil_pct - dry_pct) / (healthy_pct - dry_pct)
    return _clip(1.0 - position)


def normalize_precipitation(precip_mm: float, wet_ref: float = 25.0) -> float:
    return _clip(1.0 - (precip_mm / wet_ref))


def ana_class_to_risk(classification: str) -> float:
    key = str(classification).strip().upper()
    return ANA_RISK_MAP.get(key, ANA_RISK_MAP["S1"])


def risco_para_classe_ana(indice_risco: float) -> str:
    if indice_risco <= 2.8:
        return "S0"
    if indice_risco <= 4.6:
        return "S1"
    if indice_risco <= 6.4:
        return "S2"
    if indice_risco <= 8.2:
        return "S3"
    return "S4"


def _weighted_consensus(signals: List[ConsensusSignal]) -> float:
    available = [signal for signal in signals if signal.status == "ok"]
    if not available:
        return 0.5

    total_weight = sum(signal.weight for signal in available)
    if total_weight <= 0:
        return 0.5

    return sum((signal.weight / total_weight) * signal.normalized_risk for signal in available)


def _rainy_streak(precip_series: pd.Series, threshold_mm: float = 5.0) -> int:
    streak = 0
    for value in reversed(precip_series.fillna(0.0).tolist()):
        if value >= threshold_mm:
            streak += 1
        else:
            break
    return streak


def _rain_recovery_pressure(precip_series: pd.Series) -> float:
    series = pd.to_numeric(precip_series, errors="coerce").fillna(0.0)
    if series.empty:
        return 0.0

    rain_3d = float(series.tail(3).sum())
    rain_7d = float(series.tail(7).sum())
    streak = _rainy_streak(series, threshold_mm=5.0)

    pressure_3d = min(rain_3d / 60.0, 1.0)
    pressure_7d = min(rain_7d / 120.0, 1.0)
    pressure_streak = min(streak / 5.0, 1.0)

    pressure = (0.45 * pressure_3d) + (0.35 * pressure_7d) + (0.20 * pressure_streak)
    return _clip(pressure)


def _recovery_factor_dynamic(
    precip_series: pd.Series,
    river_risk_norm: float,
    soil_risk_norm: float,
) -> float:
    pressure = _rain_recovery_pressure(precip_series)

    hydro_inertia = _clip((river_risk_norm + soil_risk_norm) / 2.0)
    effective_pressure = pressure * (1.0 - 0.55 * hydro_inertia)

    factor = math.exp(-1.6 * effective_pressure)
    return _clip(factor, 0.2, 1.0)


def _weekly_history(
    df_daily: pd.DataFrame,
    base_consensus: float,
    ana_anchor: float,
    river_risk_norm: float,
    soil_risk_norm: float,
) -> pd.DataFrame:
    if df_daily.empty:
        return pd.DataFrame(columns=["Data", "Precipitacao_mm", "Risco_Base", "Risco_Ajustado", "Indice_Risco"])

    history = df_daily.copy()
    history["Data"] = pd.to_datetime(history["Data"], errors="coerce")
    history = history.dropna(subset=["Data"]).sort_values("Data")
    history["Precipitacao_mm"] = pd.to_numeric(history["Precipitacao_mm"], errors="coerce").fillna(0.0)

    adjusted_values: List[float] = []
    base_values: List[float] = []

    for index in range(len(history)):
        precip = float(history.iloc[index]["Precipitacao_mm"])
        precip_risk = normalize_precipitation(precip)
        estimated_base = (0.8 * base_consensus) + (0.2 * precip_risk)
        base_values.append(estimated_base)

        rain_slice = history.iloc[: index + 1]["Precipitacao_mm"]
        recovery_factor = _recovery_factor_dynamic(rain_slice, river_risk_norm, soil_risk_norm)
        adjusted_values.append(ana_anchor + (estimated_base - ana_anchor) * recovery_factor)

    history["Risco_Base"] = base_values
    history["Risco_Ajustado"] = adjusted_values
    history["Indice_Risco"] = 1.0 + 9.0 * history["Risco_Ajustado"]
    history["Data"] = history["Data"].dt.strftime("%Y-%m-%d")
    return history.tail(7)


def _extract_data_timestamp_from_payload(payload: dict) -> datetime | None:
    for key in ("daily", "table"):
        frame = payload.get(key)
        if isinstance(frame, pd.DataFrame) and not frame.empty and "Data" in frame.columns:
            dt = pd.to_datetime(frame["Data"], errors="coerce", dayfirst=True).dropna()
            if not dt.empty:
                return dt.iloc[-1].to_pydatetime()
    return None


def calculate_confidence_score(
    collected: Dict[str, object],
    now: datetime | None = None,
    max_age_hours: float = 72.0,
    w_availability: float = 0.7,
    w_recency: float = 0.3,
) -> Tuple[float, dict]:
    if now is None:
        now = datetime.now(timezone.utc)
    else:
        now = _to_utc(now) or datetime.now(timezone.utc)

    if not collected:
        return 0.0, {"availability": 0.0, "recency": 0.0, "per_source": {}}

    total_sources = len(collected)
    ok_count = 0
    recency_scores: List[float] = []
    per_source = {}

    for source, result in collected.items():
        status_ok = 1.0 if result.status == "ok" else 0.0
        ok_count += int(status_ok)

        payload_ts = _extract_data_timestamp_from_payload(result.payload)
        updated_ts = _to_utc(getattr(result, "updated_at", None))
        ref_ts = _to_utc(payload_ts) or updated_ts or now

        age_h = max((now - ref_ts).total_seconds() / 3600.0, 0.0)
        recency = max(0.0, 1.0 - (age_h / max_age_hours))
        recency_effective = recency * (0.6 if status_ok == 0.0 else 1.0)
        recency_scores.append(recency_effective)

        per_source[source] = {
            "status_ok": status_ok,
            "age_hours": round(age_h, 2),
            "recency_score": round(recency_effective, 3),
        }

    availability = ok_count / total_sources
    recency_mean = float(np.mean(recency_scores)) if recency_scores else 0.0

    score_01 = (w_availability * availability) + (w_recency * recency_mean)
    score_100 = round(100.0 * score_01, 2)

    details = {
        "availability": round(availability, 3),
        "recency": round(recency_mean, 3),
        "per_source": per_source,
    }
    return score_100, details


def detect_trend(
    df_historico: pd.DataFrame,
    col_data: str = "Data",
    col_risco: str = "Indice_Risco",
    window: int = 7,
    slope_threshold: float = 0.12,
) -> dict:
    if df_historico.empty or col_risco not in df_historico.columns:
        return {"trend": "estavel", "slope": 0.0, "window": 0}

    df = df_historico.copy().tail(window)
    df[col_data] = pd.to_datetime(df[col_data], errors="coerce")
    df[col_risco] = pd.to_numeric(df[col_risco], errors="coerce")
    df = df.dropna(subset=[col_data, col_risco]).sort_values(col_data)

    if len(df) < 3:
        return {"trend": "estavel", "slope": 0.0, "window": int(len(df))}

    x = (df[col_data] - df[col_data].min()).dt.total_seconds() / 86400.0
    y = df[col_risco].to_numpy(dtype=float)
    slope = float(np.polyfit(x, y, 1)[0])

    if slope > slope_threshold:
        trend = "agravando"
    elif slope < -slope_threshold:
        trend = "recuperando"
    else:
        trend = "estavel"

    return {"trend": trend, "slope": round(slope, 4), "window": int(len(df))}


def validar_modelo_vs_ana(
    df_modelo: pd.DataFrame,
    df_ana: pd.DataFrame,
    col_data_modelo: str = "Data",
    col_risco: str = "Indice_Risco",
    col_data_ana: str = "Data",
    col_classe_ana: str = "Classe_ANA",
) -> dict:
    try:
        from sklearn.metrics import cohen_kappa_score, confusion_matrix
    except ImportError as exc:
        raise ImportError(
            "Dependencia ausente: instale scikit-learn para rodar a validacao ANA."
        ) from exc

    model = df_modelo.copy()
    truth = df_ana.copy()

    model[col_data_modelo] = pd.to_datetime(model[col_data_modelo], errors="coerce")
    truth[col_data_ana] = pd.to_datetime(truth[col_data_ana], errors="coerce")

    model = model.dropna(subset=[col_data_modelo, col_risco])
    truth = truth.dropna(subset=[col_data_ana, col_classe_ana])

    model["Classe_Modelo"] = model[col_risco].apply(risco_para_classe_ana)
    truth[col_classe_ana] = truth[col_classe_ana].astype(str).str.upper().str.strip()

    merged = pd.merge(
        model[[col_data_modelo, "Classe_Modelo"]],
        truth[[col_data_ana, col_classe_ana]],
        left_on=col_data_modelo,
        right_on=col_data_ana,
        how="inner",
    )

    if merged.empty:
        return {
            "n_amostras": 0,
            "kappa_ponderado": None,
            "acuracia": None,
            "matriz_confusao": pd.DataFrame(),
            "comparativo": merged,
        }

    y_pred = pd.Categorical(merged["Classe_Modelo"], categories=ANA_CLASSES, ordered=True)
    y_true = pd.Categorical(merged[col_classe_ana], categories=ANA_CLASSES, ordered=True)

    matrix = confusion_matrix(y_true, y_pred, labels=ANA_CLASSES)
    matrix_df = pd.DataFrame(
        matrix,
        index=[f"real_{label}" for label in ANA_CLASSES],
        columns=[f"pred_{label}" for label in ANA_CLASSES],
    )

    kappa_weighted = cohen_kappa_score(y_true, y_pred, labels=ANA_CLASSES, weights="quadratic")
    accuracy = float((y_true == y_pred).mean())

    return {
        "n_amostras": int(len(merged)),
        "kappa_ponderado": float(kappa_weighted),
        "acuracia": accuracy,
        "matriz_confusao": matrix_df,
        "comparativo": merged,
    }


def montar_painel_risco() -> Dict[str, object]:
    hub = ProviderHub()
    collected = hub.collect_all()

    daily_precip = collected["open_meteo"].payload.get("daily", pd.DataFrame()).copy()
    if "Precipitacao_mm" not in daily_precip.columns:
        daily_precip = pd.DataFrame(
            [{"Data": datetime.now().strftime("%Y-%m-%d"), "Precipitacao_mm": 0.0}]
        )

    precip_series = pd.to_numeric(daily_precip["Precipitacao_mm"], errors="coerce").fillna(0.0)
    last_precip = _safe_float(precip_series.iloc[-1], 0.0) if not precip_series.empty else 0.0

    river_level = _safe_float(collected["imasul"].payload.get("mean_level_m", 2.2), 2.2)
    soil_moisture = _safe_float(collected["cemaden"].payload.get("mean_soil_moisture", 37.0), 37.0)
    ana_class = str(collected["ana"].payload.get("classification", "S1"))

    river_risk_norm = normalize_river_level(river_level)
    soil_risk_norm = normalize_soil_moisture(soil_moisture)

    signals = [
        ConsensusSignal(
            name="Nivel dos rios (IMASUL)",
            weight=0.40,
            normalized_risk=river_risk_norm,
            status=collected["imasul"].status,
            raw_value=river_level,
            unit="m",
        ),
        ConsensusSignal(
            name="Umidade do solo (CEMADEN)",
            weight=0.40,
            normalized_risk=soil_risk_norm,
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
    rainy_days = _rainy_streak(precip_series, threshold_mm=5.0)
    recovery_multiplier = _recovery_factor_dynamic(
        precip_series=precip_series,
        river_risk_norm=river_risk_norm,
        soil_risk_norm=soil_risk_norm,
    )

    ana_anchor = ana_class_to_risk(ana_class)
    adjusted_consensus = ana_anchor + (base_consensus - ana_anchor) * recovery_multiplier
    risk_index = 1.0 + (9.0 * _clip(adjusted_consensus))

    weekly = _weekly_history(
        df_daily=daily_precip,
        base_consensus=base_consensus,
        ana_anchor=ana_anchor,
        river_risk_norm=river_risk_norm,
        soil_risk_norm=soil_risk_norm,
    )

    weekly_avg_risk = float(weekly["Indice_Risco"].mean()) if not weekly.empty else risk_index
    weekly_avg_precip = float(weekly["Precipitacao_mm"].mean()) if not weekly.empty else last_precip
    trend_info = detect_trend(weekly, col_data="Data", col_risco="Indice_Risco", window=7)
    confidence_score, confidence_meta = calculate_confidence_score(collected)

    diagnostics = []
    for signal in signals:
        diagnostics.append(
            {
                "Fonte": signal.name,
                "Status": "Ativo" if signal.status == "ok" else "Fallback",
                "Valor": f"{signal.raw_value:.2f} {signal.unit}",
                "Risco Normalizado": round(signal.normalized_risk, 3),
                "Peso": f"{int(signal.weight * 100)}%",
                "Contribuicao": round(signal.weight * signal.normalized_risk, 3),
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
        "confidence_score": confidence_score,
        "confidence_meta": confidence_meta,
        "trend": trend_info,
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

    df["Risco_Normalizado"] = df["Precipitacao_mm"].apply(
        lambda value: normalize_precipitation(_safe_float(value, 0.0))
    )
    df["Indice_Risco"] = 1.0 + (9.0 * df["Risco_Normalizado"])
    return df


if __name__ == "__main__":
    painel = montar_painel_risco()
    print(f"Indice de risco atual: {painel['indice_risco']:.2f}")
    print(f"Confidence score: {painel['confidence_score']:.2f}")
    print(f"Trend: {painel['trend']}")
