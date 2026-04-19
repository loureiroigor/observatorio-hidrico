from __future__ import annotations

from datetime import datetime
from io import BytesIO
import re

import pandas as pd
import requests

from .base import AdapterResult, BaseAdapter


class ImasulAdapter(BaseAdapter):
    source_name = "imasul"

    def __init__(self, boletim_pdf_url: str | None = None):
        self.boletim_pdf_url = boletim_pdf_url or "https://www.imasul.ms.gov.br/wp-content/uploads/boletim_hidrologico_ms.pdf"

    def fetch(self) -> AdapterResult:
        try:
            response = requests.get(self.boletim_pdf_url, timeout=20)
            response.raise_for_status()
            levels_df = self._extract_river_levels(self._extract_text(response.content))
            if levels_df.empty:
                raise ValueError("Nao foi possivel extrair niveis de rios do boletim IMASUL")

            selected = levels_df[
                levels_df["Bacia"].isin(["Paraguai", "Parana"]) | levels_df["Bacia"].str.contains("MS")
            ]
            selected = selected if not selected.empty else levels_df
            return AdapterResult(
                source=self.source_name,
                status="ok",
                updated_at=datetime.now(),
                payload={
                    "table": selected.sort_values("Rio").reset_index(drop=True),
                    "mean_level_m": float(selected["Nivel_m"].mean()),
                    "source_url": self.boletim_pdf_url,
                },
            )
        except Exception as exc:
            # fallback mantem o painel ativo quando boletim some ou muda formato
            fallback = pd.DataFrame([{"Rio": "Sem dado IMASUL", "Bacia": "Paraguai/Parana", "Nivel_m": 2.2}])
            return self.unavailable(
                str(exc),
                payload={"table": fallback, "mean_level_m": 2.2, "source_url": self.boletim_pdf_url},
            )

    @staticmethod
    def _extract_text(pdf_bytes: bytes) -> str:
        try:
            import pdfplumber
        except ImportError as exc:
            raise ImportError("Dependencia ausente: instale pdfplumber para leitura de boletins IMASUL.") from exc

        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)

    @staticmethod
    def _extract_river_levels(text: str) -> pd.DataFrame:
        pattern = re.compile(
            r"(?P<rio>[A-Za-z\-\s]{3,40})\s+(?P<bacia>Paraguai|Parana|Paraná)\s+(?P<nivel>\d+[\.,]\d+)",
            re.IGNORECASE,
        )
        rows = [
            {
                "Rio": re.sub(r"\s+", " ", match.group("rio")).strip().title(),
                "Bacia": "Parana" if "parana" in match.group("bacia").strip().lower() else "Paraguai",
                "Nivel_m": float(match.group("nivel").replace(",", ".")),
            }
            for match in pattern.finditer(text)
        ]
        if rows:
            return pd.DataFrame(rows).drop_duplicates(subset=["Rio", "Bacia"], keep="last")

        line_pattern = re.compile(r"([A-Za-z\-\s]{3,35})\s+(\d+[\.,]\d+)")
        for line in text.splitlines():
            if not re.search(r"paraguai|parana|paraná", line, flags=re.IGNORECASE):
                continue
            basin = "Parana" if re.search(r"parana|paraná", line, flags=re.IGNORECASE) else "Paraguai"
            rows.extend(
                {
                    "Rio": re.sub(r"\s+", " ", match.group(1)).strip().title(),
                    "Bacia": basin,
                    "Nivel_m": float(match.group(2).replace(",", ".")),
                }
                for match in line_pattern.finditer(line)
            )
        return pd.DataFrame(rows)
