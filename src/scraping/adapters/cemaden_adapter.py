from __future__ import annotations

from datetime import datetime
from io import StringIO
import os

import pandas as pd
import requests

from .base import AdapterResult, BaseAdapter


class CemadenAdapter(BaseAdapter):
    source_name = "cemaden"
    _fallback = pd.DataFrame([{"Estacao": "MS-CG", "UmidadeSolo_pct": 37.0}])

    def __init__(self, csv_url: str | None = None):
        self.csv_url = csv_url or os.getenv("CEMADEN_SOIL_URL", "")

    def fetch(self) -> AdapterResult:
        if not self.csv_url:
            return self.unavailable(
                "URL do CEMADEN nao configurada. Defina CEMADEN_SOIL_URL para dados reais.",
                payload={"table": self._fallback.copy(), "mean_soil_moisture": 37.0},
            )

        try:
            response = requests.get(self.csv_url, timeout=20)
            response.raise_for_status()
            parsed = self._select_fields(pd.read_csv(StringIO(response.text), sep=None, engine="python"))
            if parsed.empty:
                raise ValueError("CSV do CEMADEN nao possui colunas de umidade do solo reconhecidas")
            return AdapterResult(
                source=self.source_name,
                status="ok",
                updated_at=datetime.now(),
                payload={"table": parsed.tail(20), "mean_soil_moisture": float(parsed["UmidadeSolo_pct"].mean())},
            )
        except Exception as exc:
            return self.unavailable(
                str(exc),
                payload={"table": self._fallback.copy(), "mean_soil_moisture": 37.0},
            )

    @staticmethod
    def _select_fields(df: pd.DataFrame) -> pd.DataFrame:
        normalized = {col.lower().strip(): col for col in df.columns}
        soil_col = next((normalized[key] for key in ["umidade_solo", "umidade_solo_pct", "umidadesolo", "soil_moisture", "soil_moisture_pct"] if key in normalized), None)
        if soil_col is None:
            return pd.DataFrame()

        station_col = next((normalized[key] for key in ["estacao", "estacao_nome", "station", "nome"] if key in normalized), None)
        out = pd.DataFrame({"UmidadeSolo_pct": pd.to_numeric(df[soil_col], errors="coerce")}).dropna(subset=["UmidadeSolo_pct"])
        out.insert(0, "Estacao", df.loc[out.index, station_col].astype(str) if station_col else "CEMADEN")
        return out
