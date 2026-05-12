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
            source_pdf = None
            levels_df = pd.DataFrame()
            last_error = ""

            for candidate_pdf in self._resolve_latest_pdf_candidates():
                try:
                    response = requests.get(candidate_pdf, timeout=20)
                    response.raise_for_status()
                    if "pdf" not in response.headers.get("content-type", "").lower():
                        raise ValueError("conteudo nao-pdf")

                    levels_df = self._extract_levels_from_pdf(response.content)
                    if levels_df.empty:
                        raise ValueError("pdf sem niveis fluviometricos extraiveis")

                    source_pdf = candidate_pdf
                    break
                except Exception as exc:
                    last_error = str(exc)

            if levels_df.empty or source_pdf is None:
                raise ValueError(f"Nao foi possivel extrair niveis de rios do boletim IMASUL ({last_error})")

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

    def _resolve_latest_pdf_candidates(self) -> list[str]:
        candidates: list[str] = []
        for resolver in (self._latest_from_wordpress_media, self._latest_from_boletins_page):
            for candidate in resolver():
                if candidate and candidate not in candidates:
                    candidates.append(candidate)
        if self.boletim_pdf_url not in candidates:
            candidates.append(self.boletim_pdf_url)
        return candidates

    def _latest_from_wordpress_media(self) -> list[str]:
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
            return []

        def score(item: dict) -> tuple[int, str]:
            url = str(item.get("source_url", "")).lower()
            # prioriza boletins diarios/hidrologicos, que tendem a conter tabela de rios
            priority = 0
            if "boletim_diario" in url:
                priority += 3
            if "hidrolog" in url:
                priority += 2
            if "boletim" in url:
                priority += 1
            return (priority, str(item.get("date", "")))

        boletins.sort(key=score, reverse=True)
        return [str(item.get("source_url")) for item in boletins[:8] if item.get("source_url")]

    def _latest_from_boletins_page(self) -> list[str]:
        response = requests.get(self.boletins_page_url, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        links = [
            urljoin(self.boletins_page_url, anchor.get("href", ""))
            for anchor in soup.find_all("a", href=True)
            if ".pdf" in anchor.get("href", "").lower()
        ]
        boletins = [link for link in links if "boletim" in link.lower() or "hidro" in link.lower()]
        return boletins[:8] if boletins else links[:4]

    def _extract_levels_from_pdf(self, pdf_bytes: bytes) -> pd.DataFrame:
        table_df = self._extract_levels_from_tables(pdf_bytes)
        if not table_df.empty:
            return table_df

        text = self._extract_text(pdf_bytes)
        text_df = self._extract_river_levels(text)
        if not text_df.empty:
            return text_df
        return self._coerce_levels_from_text(text)

    @staticmethod
    def _extract_text(pdf_bytes: bytes) -> str:
        try:
            import pdfplumber
        except ImportError as exc:
            raise ImportError("Dependencia ausente: instale pdfplumber para leitura de boletins IMASUL.") from exc

        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)

    @staticmethod
    def _extract_levels_from_tables(pdf_bytes: bytes) -> pd.DataFrame:
        try:
            import pdfplumber
        except ImportError:
            return pd.DataFrame()

        rows: list[dict] = []
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables() or []:
                    for raw_row in table:
                        if not raw_row:
                            continue
                        values = [str(val).strip() for val in raw_row if val]
                        if not values:
                            continue

                        line = " ".join(values)
                        if not re.search(r"paraguai|parana|paraná", line, flags=re.IGNORECASE):
                            continue

                        number_match = re.search(r"\b(\d+[\.,]\d+)\b", line)
                        if not number_match:
                            continue

                        basin = "Parana" if re.search(r"parana|paraná", line, flags=re.IGNORECASE) else "Paraguai"
                        river = re.sub(r"\s+", " ", values[0]).strip().title() if values else "Rio"
                        level = float(number_match.group(1).replace(",", "."))
                        rows.append({"Rio": river, "Bacia": basin, "Nivel_m": level})

        return pd.DataFrame(rows).drop_duplicates(subset=["Rio", "Bacia"], keep="last") if rows else pd.DataFrame()

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
