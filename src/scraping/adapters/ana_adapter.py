from __future__ import annotations

from datetime import datetime
import os
import re

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
            is_json = "json" in response.headers.get("content-type", "")
            parsed = self._from_json(response.json()) if is_json else self._from_text(response.text)
            return AdapterResult(
                source=self.source_name,
                status="ok",
                updated_at=datetime.now(),
                payload={"classification": parsed.get("classification", "S1"), "region": parsed.get("region", "Campo Grande/MS")},
            )
        except Exception as exc:
            return self.unavailable(str(exc), payload={"classification": "S1", "region": "Campo Grande/MS"})

    @staticmethod
    def _from_json(data: dict) -> dict:
        if not isinstance(data, dict):
            return {"region": "Campo Grande/MS", "classification": "S1"}
        region = data.get("region") or data.get("regiao") or "Campo Grande/MS"
        raw = data.get("classification") or data.get("classe") or data.get("seca") or "S1"
        return {"region": region, "classification": AnaSecaAdapter._normalize_class(raw)}

    @staticmethod
    def _from_text(text: str) -> dict:
        match = re.search(r"\bS[0-4]\b", text.upper())
        return {"region": "Campo Grande/MS", "classification": match.group(0) if match else "S1"}

    @staticmethod
    def _normalize_class(value: str) -> str:
        text = str(value).strip().upper()
        match = re.search(r"S[0-4]", text)
        return text if text in {"S0", "S1", "S2", "S3", "S4"} else (match.group(0) if match else "S1")
