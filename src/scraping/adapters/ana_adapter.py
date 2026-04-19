from __future__ import annotations

from datetime import datetime
import os
import re

import pandas as pd
import requests

from .base import AdapterResult, BaseAdapter


class AnaSecaAdapter(BaseAdapter):
    source_name = "ana"

    def __init__(self, endpoint: str | None = None):
        self.endpoint = endpoint or os.getenv("ANA_MONITOR_ENDPOINT", "")

    def fetch(self) -> AdapterResult:
        if not self.endpoint:
            return self.unavailable(
                "Endpoint ANA nao configurado. Defina ANA_MONITOR_ENDPOINT.",
                payload={"classification": "S1", "region": "Campo Grande/MS"},
            )

        try:
            response = requests.get(self.endpoint, timeout=20)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")

            if "json" in content_type:
                parsed = self._from_json(response.json())
            else:
                parsed = self._from_text(response.text)

            classification = parsed.get("classification", "S1")
            region = parsed.get("region", "Campo Grande/MS")

            return AdapterResult(
                source=self.source_name,
                status="ok",
                updated_at=datetime.now(),
                payload={"classification": classification, "region": region},
            )
        except Exception as exc:
            return self.unavailable(
                str(exc), payload={"classification": "S1", "region": "Campo Grande/MS"}
            )

    @staticmethod
    def _from_json(data: dict) -> dict:
        if isinstance(data, dict):
            region = data.get("region") or data.get("regiao") or "Campo Grande/MS"
            raw = data.get("classification") or data.get("classe") or data.get("seca") or "S1"
            return {"region": region, "classification": AnaSecaAdapter._normalize_class(raw)}
        return {"region": "Campo Grande/MS", "classification": "S1"}

    @staticmethod
    def _from_text(text: str) -> dict:
        match = re.search(r"\bS[0-4]\b", text.upper())
        classification = match.group(0) if match else "S1"
        return {"region": "Campo Grande/MS", "classification": classification}

    @staticmethod
    def _normalize_class(value: str) -> str:
        text = str(value).strip().upper()
        if text in {"S0", "S1", "S2", "S3", "S4"}:
            return text
        match = re.search(r"S[0-4]", text)
        return match.group(0) if match else "S1"
