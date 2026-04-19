from __future__ import annotations

from datetime import datetime

import pandas as pd
import requests

from .base import AdapterResult, BaseAdapter


class OpenMeteoAdapter(BaseAdapter):
    source_name = "open_meteo"

    def __init__(self, latitude: float = -20.4428, longitude: float = -54.6464):
        self.latitude = latitude
        self.longitude = longitude

    def fetch(self) -> AdapterResult:
        daily_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={self.latitude}&longitude={self.longitude}"
            "&daily=precipitation_sum&timezone=America%2FSao_Paulo"
            "&past_days=7&forecast_days=1"
        )

        hourly_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={self.latitude}&longitude={self.longitude}"
            "&hourly=precipitation&timezone=America%2FSao_Paulo"
            "&past_days=1&forecast_days=1"
        )

        try:
            daily_response = requests.get(daily_url, timeout=15)
            daily_response.raise_for_status()
            daily_data = daily_response.json().get("daily", {})

            df_daily = pd.DataFrame(
                {
                    "Data": daily_data.get("time", []),
                    "Precipitacao_mm": daily_data.get("precipitation_sum", []),
                }
            )

            hourly_response = requests.get(hourly_url, timeout=15)
            hourly_response.raise_for_status()
            hourly_data = hourly_response.json().get("hourly", {})
            df_hourly = pd.DataFrame(
                {
                    "Data_Hora": hourly_data.get("time", []),
                    "Chuva_Digital (mm)": hourly_data.get("precipitation", []),
                }
            )

            if not df_hourly.empty:
                dt = pd.to_datetime(df_hourly["Data_Hora"], errors="coerce")
                df_hourly["Data"] = dt.dt.strftime("%d/%m/%Y")
                df_hourly["Hora"] = dt.dt.strftime("%H:%M")
                df_hourly = df_hourly[["Data", "Hora", "Chuva_Digital (mm)"]].tail(8)

            last_precip = 0.0
            if not df_daily.empty:
                last_precip = float(df_daily["Precipitacao_mm"].iloc[-1])

            return AdapterResult(
                source=self.source_name,
                status="ok",
                updated_at=datetime.now(),
                payload={
                    "daily": df_daily,
                    "hourly": df_hourly,
                    "last_precipitation_mm": last_precip,
                },
            )
        except Exception as exc:
            return self.unavailable(
                error=str(exc),
                payload={
                    "daily": pd.DataFrame(
                        {
                            "Data": [datetime.now().strftime("%Y-%m-%d")],
                            "Precipitacao_mm": [0.0],
                        }
                    ),
                    "hourly": pd.DataFrame(),
                    "last_precipitation_mm": 0.0,
                },
            )
