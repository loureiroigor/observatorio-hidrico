from __future__ import annotations

from datetime import datetime

import pandas as pd
import requests

from .base import BaseAdapter


class OpenMeteoAdapter(BaseAdapter):
    source_name = "open_meteo"

    def __init__(self, latitude: float = -20.4428, longitude: float = -54.6464):
        self.latitude = latitude
        self.longitude = longitude

    def _url(self, mode: str) -> str:
        common = f"?latitude={self.latitude}&longitude={self.longitude}&timezone=America%2FSao_Paulo"
        return (
            f"https://api.open-meteo.com/v1/forecast{common}&daily=precipitation_sum&past_days=7&forecast_days=1"
            if mode == "daily"
            else f"https://api.open-meteo.com/v1/forecast{common}&hourly=precipitation&past_days=1&forecast_days=1"
        )

    def fetch(self) -> AdapterResult:
        try:
            daily_data = requests.get(self._url("daily"), timeout=15)
            daily_data.raise_for_status()
            daily = daily_data.json().get("daily", {})
            df_daily = pd.DataFrame({"Data": daily.get("time", []), "Precipitacao_mm": daily.get("precipitation_sum", [])})

            hourly_data = requests.get(self._url("hourly"), timeout=15)
            hourly_data.raise_for_status()
            hourly = hourly_data.json().get("hourly", {})
            df_hourly = pd.DataFrame({"Data_Hora": hourly.get("time", []), "Chuva_Digital (mm)": hourly.get("precipitation", [])})

            if not df_hourly.empty:
                dt = pd.to_datetime(df_hourly["Data_Hora"], errors="coerce")
                df_hourly = df_hourly.assign(Data=dt.dt.strftime("%d/%m/%Y"), Hora=dt.dt.strftime("%H:%M"))[["Data", "Hora", "Chuva_Digital (mm)"]].tail(8)

            return self.success(
                payload={
                    "daily": df_daily,
                    "hourly": df_hourly,
                    "last_precipitation_mm": float(df_daily["Precipitacao_mm"].iloc[-1]) if not df_daily.empty else 0.0,
                }
            )
        except Exception as exc:
            # fallback garante serie minima pra motor de risco nao estourar
            return self.unavailable(
                error=str(exc),
                payload={
                    "daily": pd.DataFrame({"Data": [datetime.now().strftime("%Y-%m-%d")], "Precipitacao_mm": [0.0]}),
                    "hourly": pd.DataFrame(),
                    "last_precipitation_mm": 0.0,
                },
            )
