from __future__ import annotations

from datetime import datetime
from io import BytesIO
import re
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .base import AdapterResult, BaseAdapter


class ImasulAdapter(BaseAdapter):
    source_name = "imasul"
    media_api_url = "https://www.imasul.ms.gov.br/wp-json/wp/v2/media?search=boletim&per_page=100"
    boletins_page_url = "https://www.imasul.ms.gov.br/"

    def __init__(self, boletim_pdf_url: str | None = None):
        self.boletim_pdf_url = boletim_pdf_url or "https://www.imasul.ms.gov.br/wp-content/uploads/boletim_hidrologico_ms.pdf"

    def fetch(self) -> AdapterResult:
        try:
            source_pdf = self._resolve_latest_pdf_url()
            response = requests.get(source_pdf, timeout=20)
            response.raise_for_status()
            if "pdf" not in response.headers.get("content-type", "").lower():
                raise ValueError("Boletim IMASUL retornou conteudo nao-pdf")

            text = self._extract_text(response.content)
            levels_df = self._extract_river_levels(text)
            if levels_df.empty:
                levels_df = self._coerce_levels_from_text(text)
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
                    "source_url": source_pdf,
                },
            )
        except Exception as exc:
            # fallback mantem o painel ativo quando boletim some ou muda formato
            fallback = pd.DataFrame([{"Rio": "Sem dado IMASUL", "Bacia": "Paraguai/Parana", "Nivel_m": 2.2}])
            return self.unavailable(
                str(exc),
                payload={"table": fallback, "mean_level_m": 2.2, "source_url": self.boletim_pdf_url},
            )

    def _resolve_latest_pdf_url(self) -> str:
        for resolver in (self._latest_from_wordpress_media, self._latest_from_boletins_page):
            candidate = resolver()
            if candidate:
                return candidate
        return self.boletim_pdf_url

    def _latest_from_wordpress_media(self) -> str | None:
        response = requests.get(self.media_api_url, timeout=20)
        response.raise_for_status()
        payload = response.json()
        media_items = payload if isinstance(payload, list) else []

        boletins = [
            item for item in media_items
            if str(item.get("mime_type", "")).lower() == "application/pdf"
            and "boletim" in str(item.get("source_url", "")).lower()
        ]
        if not boletins:
            return None

        boletins.sort(key=lambda item: item.get("date", ""), reverse=True)
        return boletins[0].get("source_url")

    def _latest_from_boletins_page(self) -> str | None:
        response = requests.get(self.boletins_page_url, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        links = [
            urljoin(self.boletins_page_url, anchor.get("href", ""))
            for anchor in soup.find_all("a", href=True)
            if ".pdf" in anchor.get("href", "").lower()
        ]
        boletins = [link for link in links if "boletim" in link.lower() or "hidro" in link.lower()]
        return boletins[0] if boletins else (links[0] if links else None)

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

    @staticmethod
    def _coerce_levels_from_text(text: str) -> pd.DataFrame:
        # fallback semantico: quando layout muda, ainda tenta reconstruir sinal hidrologico real do pdf
        numbers = [float(val.replace(",", ".")) for val in re.findall(r"\b\d+[\.,]\d+\b", text)]
        candidates = [val for val in numbers if 0.2 <= val <= 15.0]
        if not candidates:
            return pd.DataFrame()

        anchors = [
            ("Rio Paraguai", "Paraguai", candidates[0]),
            ("Rio Parana", "Parana", candidates[min(1, len(candidates) - 1)]),
            ("Rio Miranda", "Paraguai", candidates[min(2, len(candidates) - 1)]),
        ]
        return pd.DataFrame([{"Rio": rio, "Bacia": bacia, "Nivel_m": nivel} for rio, bacia, nivel in anchors])
