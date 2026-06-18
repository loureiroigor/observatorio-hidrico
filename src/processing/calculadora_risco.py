"""motor de risco hidrico com consenso multiprovedor e validacao contra ana.

para rodar: py -m src.processing.calculadora_risco
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any

import numpy as np
import pandas as pd

from src.scraping.provider_hub import ProviderHub


ANA_RISK_MAP = {"S0": 0.20, "S1": 0.35, "S2": 0.55, "S3": 0.78, "S4": 0.95}
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


def _safe_float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _series_to_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def _inverse_linear(value: float, low_ref: float, high_ref: float) -> float:
    if high_ref == low_ref:
        return 0.5
    return _clip(1.0 - ((value - low_ref) / (high_ref - low_ref)))


def normalize_river_level(level_m: float, drought_floor: float = 1.0, healthy_level: float = 5.0) -> float:
    return _inverse_linear(level_m, drought_floor, healthy_level)


def normalize_soil_moisture(soil_pct: float, dry_pct: float = 20.0, healthy_pct: float = 60.0) -> float:
    return _inverse_linear(soil_pct, dry_pct, healthy_pct)


def normalize_precipitation(precip_mm: float, wet_ref: float = 25.0) -> float:
    return _clip(1.0 - (_safe_float(precip_mm) / wet_ref))


def normalize_recent_precipitation(precip_series: pd.Series) -> float:
    return _clip(1.0 - _rain_recovery_pressure(precip_series))


def ana_class_to_risk(classification: str) -> float:
    return ANA_RISK_MAP.get(str(classification).strip().upper(), ANA_RISK_MAP["S1"])


def risco_para_classe_ana(indice_risco: float) -> str:
    return "S0" if indice_risco <= 2.8 else "S1" if indice_risco <= 4.6 else "S2" if indice_risco <= 6.4 else "S3" if indice_risco <= 8.2 else "S4"


def _weighted_consensus(signals: list[ConsensusSignal]) -> float:
    valid = [signal for signal in signals if signal.status == "ok"]
    if not valid:
        return 0.5
    weights = [signal.weight for signal in valid]
    if sum(weights) <= 0:
        return 0.5
    values = [signal.normalized_risk for signal in valid]
    return float(np.average(values, weights=weights))


def _rainy_streak(precip_series: pd.Series, threshold_mm: float = 5.0) -> int:
    streak = 0
    for value in reversed(_series_to_float(precip_series).tolist()):
        if value < threshold_mm:
            break
        streak += 1
    return streak


def _rain_recovery_pressure(precip_series: pd.Series) -> float:
    series = _series_to_float(precip_series)
    if series.empty:
        return 0.0
    rain_3d, rain_7d = float(series.tail(3).sum()), float(series.tail(7).sum())
    # pondera 3d e 7d pra reduzir efeito de pancada isolada
    p3, p7, ps = min(rain_3d / 60.0, 1.0), min(rain_7d / 120.0, 1.0), min(_rainy_streak(series) / 5.0, 1.0)
    return _clip((0.45 * p3) + (0.35 * p7) + (0.20 * ps))


def _recovery_factor_dynamic(precip_series: pd.Series, river_risk_norm: float, soil_risk_norm: float) -> float:
    pressure = _rain_recovery_pressure(precip_series)
    # aplica inercia hidrologica porque solo e rios nao recuperam no mesmo dia da chuva
    hydro_inertia = _clip((river_risk_norm + soil_risk_norm) / 2.0)
    effective_pressure = pressure * (1.0 - 0.55 * hydro_inertia)
    return _clip(math.exp(-1.6 * effective_pressure), 0.2, 1.0)


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
    history["Precipitacao_mm"] = _series_to_float(history["Precipitacao_mm"])

    base_values, adjusted_values = [], []
    for idx, precip in enumerate(history["Precipitacao_mm"].tolist()):
        base = (0.8 * base_consensus) + (0.2 * normalize_precipitation(precip))
        factor = _recovery_factor_dynamic(history.iloc[: idx + 1]["Precipitacao_mm"], river_risk_norm, soil_risk_norm)
        base_values.append(base)
        adjusted_values.append(ana_anchor + (base - ana_anchor) * factor)

    history = history.assign(
        Risco_Base=base_values,
        Risco_Ajustado=adjusted_values,
        Indice_Risco=lambda frame: 1.0 + 9.0 * frame["Risco_Ajustado"],
        Data=lambda frame: frame["Data"].dt.strftime("%Y-%m-%d"),
    )
    return history.tail(7)


def _extract_data_timestamp_from_payload(payload: dict[str, Any]) -> datetime | None:
    for key in ("daily", "table"):
        frame = payload.get(key)
        if isinstance(frame, pd.DataFrame) and not frame.empty and "Data" in frame.columns:
            parsed = pd.to_datetime(frame["Data"], errors="coerce", dayfirst=True).dropna()
            if not parsed.empty:
                return parsed.iloc[-1].to_pydatetime()
    return None


def calculate_confidence_score(
    collected: dict[str, Any],
    now: datetime | None = None,
    max_age_hours: float = 72.0,
    w_availability: float = 0.7,
    w_recency: float = 0.3,
) -> tuple[float, dict[str, Any]]:
    now_utc = _to_utc(now) or datetime.now(timezone.utc)
    if not collected:
        return 0.0, {"availability": 0.0, "recency": 0.0, "per_source": {}}

    items = []
    for source, result in collected.items():
        status_ok = 1.0 if result.status == "ok" else 0.0
        ref_ts = _to_utc(_extract_data_timestamp_from_payload(result.payload)) or _to_utc(getattr(result, "updated_at", None)) or now_utc
        age_h = max((now_utc - ref_ts).total_seconds() / 3600.0, 0.0)
        recency = max(0.0, 1.0 - (age_h / max_age_hours))
        recency_eff = recency * (1.0 if status_ok else 0.6)
        items.append((source, status_ok, age_h, recency_eff))

    availability = sum(item[1] for item in items) / len(items)
    recency_mean = float(np.mean([item[3] for item in items])) if items else 0.0
    score = round(100.0 * ((w_availability * availability) + (w_recency * recency_mean)), 2)

    per_source = {
        source: {"status_ok": ok, "age_hours": round(age_h, 2), "recency_score": round(recency, 3)}
        for source, ok, age_h, recency in items
    }
    return score, {"availability": round(availability, 3), "recency": round(recency_mean, 3), "per_source": per_source}


def detect_trend(
    df_historico: pd.DataFrame,
    col_data: str = "Data",
    col_risco: str = "Indice_Risco",
    window: int = 7,
    slope_threshold: float = 0.12,
) -> dict[str, Any]:
    if df_historico.empty or col_risco not in df_historico.columns:
        return {"trend": "estavel", "slope": 0.0, "window": 0}

    df = df_historico.tail(window).copy()
    df[col_data] = pd.to_datetime(df[col_data], errors="coerce")
    df[col_risco] = pd.to_numeric(df[col_risco], errors="coerce")
    df = df.dropna(subset=[col_data, col_risco]).sort_values(col_data)
    if len(df) < 3:
        return {"trend": "estavel", "slope": 0.0, "window": int(len(df))}

    x = (df[col_data] - df[col_data].min()).dt.total_seconds().to_numpy() / 86400.0
    slope = float(np.polyfit(x, df[col_risco].to_numpy(dtype=float), 1)[0])
    trend = "agravando" if slope > slope_threshold else "recuperando" if slope < -slope_threshold else "estavel"
    return {"trend": trend, "slope": round(slope, 4), "window": int(len(df))}


def validar_modelo_vs_ana(
    df_modelo: pd.DataFrame,
    df_ana: pd.DataFrame,
    col_data_modelo: str = "Data",
    col_risco: str = "Indice_Risco",
    col_data_ana: str = "Data",
    col_classe_ana: str = "Classe_ANA",
) -> dict[str, Any]:
    try:
        from sklearn.metrics import cohen_kappa_score, confusion_matrix
    except ImportError as exc:
        raise ImportError("dependencia ausente: instale scikit-learn para rodar a validacao ana.") from exc

    model = df_modelo.copy()
    truth = df_ana.copy()
    model[col_data_modelo] = pd.to_datetime(model[col_data_modelo], errors="coerce")
    truth[col_data_ana] = pd.to_datetime(truth[col_data_ana], errors="coerce")

    model = model.dropna(subset=[col_data_modelo, col_risco]).assign(Classe_Modelo=lambda frame: frame[col_risco].apply(risco_para_classe_ana))
    truth = truth.dropna(subset=[col_data_ana, col_classe_ana]).assign(
        **{col_classe_ana: lambda frame: frame[col_classe_ana].astype(str).str.upper().str.strip()}
    )

    merged = model[[col_data_modelo, "Classe_Modelo"]].merge(
        truth[[col_data_ana, col_classe_ana]],
        left_on=col_data_modelo,
        right_on=col_data_ana,
        how="inner",
    )
    if merged.empty:
        return {"n_amostras": 0, "kappa_ponderado": None, "acuracia": None, "matriz_confusao": pd.DataFrame(), "comparativo": merged}

    y_pred = pd.Categorical(merged["Classe_Modelo"], categories=ANA_CLASSES, ordered=True)
    y_true = pd.Categorical(merged[col_classe_ana], categories=ANA_CLASSES, ordered=True)
    matrix = confusion_matrix(y_true, y_pred, labels=ANA_CLASSES)
    matrix_df = pd.DataFrame(matrix, index=[f"real_{label}" for label in ANA_CLASSES], columns=[f"pred_{label}" for label in ANA_CLASSES])

    return {
        "n_amostras": int(len(merged)),
        "kappa_ponderado": float(cohen_kappa_score(y_true, y_pred, labels=ANA_CLASSES, weights="quadratic")),
        "acuracia": float((y_true == y_pred).mean()),
        "matriz_confusao": matrix_df,
        "comparativo": merged,
    }


def _build_signals(
    collected: dict[str, Any],
    river_level: float,
    soil_moisture: float,
    recent_precip_mm: float,
    precipitation_risk: float,
) -> list[ConsensusSignal]:
    return [
        ConsensusSignal("Nivel dos rios (IMASUL)", 0.40, normalize_river_level(river_level), collected["imasul"].status, river_level, "m"),
        ConsensusSignal("Umidade do solo (CEMADEN)", 0.40, normalize_soil_moisture(soil_moisture), collected["cemaden"].status, soil_moisture, "%"),
        ConsensusSignal(
            "Precipitacao recente (INMET/Open-Meteo)",
            0.20,
            precipitation_risk,
            "ok" if {collected["open_meteo"].status, collected["inmet"].status} & {"ok"} else "unavailable",
            recent_precip_mm,
            "mm",
        ),
    ]


def _last_table_rain_mm(frame: pd.DataFrame, column: str) -> float | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.iloc[-1]) if not values.empty else None


def _build_data_verdict(
    collected: dict[str, Any],
    confidence_score: float,
    risk_index: float,
    ana_class: str,
    signals: list[ConsensusSignal],
) -> dict[str, Any]:
    active = [name for name, result in collected.items() if result.status == "ok"]
    warnings: list[str] = []
    evidence: list[str] = []

    if len(active) < len(collected):
        missing = [name.upper() for name, result in collected.items() if result.status != "ok"]
        warnings.append(f"Fontes em fallback: {', '.join(missing)}.")

    inmet_rain = _last_table_rain_mm(collected["inmet"].payload.get("table", pd.DataFrame()), "Chuva (mm)")
    openmeteo_rain = _last_table_rain_mm(collected["open_meteo"].payload.get("hourly", pd.DataFrame()), "Chuva_Digital (mm)")
    if inmet_rain is not None and openmeteo_rain is not None:
        diff = abs(inmet_rain - openmeteo_rain)
        if diff <= 2.0:
            evidence.append(f"INMET e Open-Meteo concordam na chuva recente ({inmet_rain:.1f} mm vs {openmeteo_rain:.1f} mm).")
        else:
            warnings.append(f"Divergencia de chuva recente entre INMET ({inmet_rain:.1f} mm) e Open-Meteo ({openmeteo_rain:.1f} mm).")

    high_signals = [signal.name for signal in signals if signal.normalized_risk >= 0.75]
    if high_signals:
        evidence.append(f"Sinais criticos convergentes: {', '.join(high_signals)}.")

    if ana_class.upper() in {"S3", "S4"}:
        evidence.append(f"ANA indica seca severa/regional ({ana_class.upper()}).")

    if confidence_score >= 90 and not warnings:
        status = "Validado"
        message = "Dados consistentes para uso analitico neste painel."
    elif confidence_score >= 75:
        status = "Valido com ressalvas"
        message = "Dados utilizaveis, mas exigem leitura das ressalvas antes de conclusao externa."
    else:
        status = "Baixa confianca"
        message = "Dados insuficientes para um veredito robusto sem verificacao manual."

    risk_verdict = "Critico" if risk_index >= 8.2 else "Alto" if risk_index >= 6.4 else "Moderado" if risk_index >= 4.6 else "Baixo"
    return {
        "status": status,
        "risco": risk_verdict,
        "mensagem": message,
        "evidencias": evidence,
        "ressalvas": warnings or ["Nenhuma ressalva automatica encontrada."],
    }


def montar_painel_risco() -> dict[str, Any]:
    collected = ProviderHub().collect_all()

    daily_precip = collected["open_meteo"].payload.get("daily", pd.DataFrame()).copy()
    if "Precipitacao_mm" not in daily_precip.columns:
        daily_precip = pd.DataFrame([{"Data": datetime.now().strftime("%Y-%m-%d"), "Precipitacao_mm": 0.0}])

    precip_series = _series_to_float(daily_precip["Precipitacao_mm"])
    last_precip = _safe_float(precip_series.iloc[-1]) if not precip_series.empty else 0.0
    recent_precip_mm = float(precip_series.tail(7).sum()) if not precip_series.empty else 0.0
    precipitation_risk = normalize_recent_precipitation(precip_series)
    river_level = _safe_float(collected["imasul"].payload.get("mean_level_m", 2.2), 2.2)
    soil_moisture = _safe_float(collected["cemaden"].payload.get("mean_soil_moisture", 37.0), 37.0)
    ana_class = str(collected["ana"].payload.get("classification", "S1"))

    signals = _build_signals(collected, river_level, soil_moisture, recent_precip_mm, precipitation_risk)
    river_risk_norm, soil_risk_norm = signals[0].normalized_risk, signals[1].normalized_risk

    # calculo final do indice (passo a passo):
    # 1) cada fonte vira risco normalizado [0,1] (rio, solo e chuva)
    # 2) consenso base = media ponderada 40/40/20 apenas das fontes ativas
    # 3) ancora ana traduz s0..s4 para risco esperado de contexto regional
    # 4) recuperacao dinamica usa chuva recente (3d/7d + sequencia) com inercia hidrologica
    #    pra evitar queda brusca irreal quando chove pouco, mas solo/rios seguem pressionados
    # 5) consenso ajustado = ana_anchor + (consenso_base - ana_anchor) * fator_recuperacao
    # 6) indice final = 1 + 9 * consenso_ajustado (escala publica de 1 a 10)
    base_consensus = _weighted_consensus(signals)
    recovery_multiplier = _recovery_factor_dynamic(precip_series, river_risk_norm, soil_risk_norm)

    ana_anchor = ana_class_to_risk(ana_class)
    adjusted_consensus = ana_anchor + (base_consensus - ana_anchor) * recovery_multiplier
    risk_index = 1.0 + (9.0 * _clip(adjusted_consensus))

    weekly = _weekly_history(daily_precip, base_consensus, ana_anchor, river_risk_norm, soil_risk_norm)
    trend_info = detect_trend(weekly)
    confidence_score, confidence_meta = calculate_confidence_score(collected)
    data_verdict = _build_data_verdict(collected, confidence_score, risk_index, ana_class, signals)

    diagnostics = pd.DataFrame(
        [
            {
                "Fonte": signal.name,
                "Status": "Ativo" if signal.status == "ok" else "Fallback",
                "Valor": f"{signal.raw_value:.2f} {signal.unit}",
                "Risco Normalizado": round(signal.normalized_risk, 3),
                "Peso": f"{int(signal.weight * 100)}%",
                "Contribuicao": round(signal.weight * signal.normalized_risk, 3),
            }
            for signal in signals
        ]
    )

    resumo_semanal = {
        "risco_medio": float(weekly["Indice_Risco"].mean()) if not weekly.empty else risk_index,
        "chuva_media": float(weekly["Precipitacao_mm"].mean()) if not weekly.empty else last_precip,
        "dias_chuvosos": int((weekly["Precipitacao_mm"] >= 5.0).sum()) if not weekly.empty else 0,
    }

    return {
        "coleta": collected,
        "df_precipitacao": daily_precip,
        "df_historico_semanal": weekly,
        "indice_risco": risk_index,
        "consenso_base": base_consensus,
        "consenso_ajustado": adjusted_consensus,
        "fator_recuperacao": recovery_multiplier,
        "dias_chuva_consecutivos": _rainy_streak(precip_series),
        "classificacao_ana": ana_class,
        "diagnostico_df": diagnostics,
        "status_provedores": {name: result.status for name, result in collected.items()},
        "confidence_score": confidence_score,
        "confidence_meta": confidence_meta,
        "trend": trend_info,
        "resumo_semanal": resumo_semanal,
        "veredito_dados": data_verdict,
    }


if __name__ == "__main__":
    painel = montar_painel_risco()
    print(f"Indice de risco atual: {painel['indice_risco']:.2f}")
    print(f"Confidence score: {painel['confidence_score']:.2f}")
    print(f"Trend: {painel['trend']}")
