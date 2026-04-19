from __future__ import annotations

from datetime import datetime
import re

import requests

from .base import AdapterResult, BaseAdapter


class AnaSecaAdapter(BaseAdapter):
    source_name = "ana"
    monitor_url = "https://monitordesecas.ana.gov.br/"
    monitor_bundle_url = "https://monitordesecas.ana.gov.br/main-es2015.b6d0cdcd81879044913a.js"
    seca_proxy_meta_url = "https://mapasecas.cemaden.gov.br/rest/product/meta/secadiagnostico"

    def fetch(self) -> AdapterResult:
        try:
            monitor_html = requests.get(self.monitor_url, timeout=20)
            monitor_html.raise_for_status()

            classification = self._extract_class_from_monitor_bundle() or self._extract_class_from_public_proxy()
            if not classification:
                raise ValueError("Nao foi possivel identificar classificacao ANA para MS")

            return AdapterResult(
                source=self.source_name,
                status="ok",
                updated_at=datetime.now(),
                payload={
                    "classification": classification,
                    "region": "Mato Grosso do Sul",
                    "source_url": self.monitor_url,
                },
            )
        except Exception as exc:
            return self.unavailable(
                str(exc),
                payload={"classification": "S1", "region": "Mato Grosso do Sul", "source_url": self.monitor_url},
            )

    def _extract_class_from_monitor_bundle(self) -> str | None:
        response = requests.get(self.monitor_bundle_url, timeout=30)
        response.raise_for_status()
        text = response.text

        patterns = [
            r'"uf":"MS".{0,160}"classe":"(S[0-4])"',
            r'"sigla":"MS".{0,220}"seca":"(S[0-4])"',
            r'"Mato\s+Grosso\s+do\s+Sul".{0,220}"(S[0-4])"',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return self._normalize_class(match.group(1))
        return None

    def _extract_class_from_public_proxy(self) -> str | None:
        # usa camada publica de diagnostico de seca enquanto o monitor ANA nao expõe endpoint simples
        meta = requests.get(self.seca_proxy_meta_url, timeout=20).json()
        timesteps = meta.get("timesteps", {}) if isinstance(meta, dict) else {}
        if not timesteps:
            return None

        latest_key = sorted(timesteps.keys(), reverse=True)[0]
        timestep = timesteps.get(latest_key, {})
        if not isinstance(timestep, dict):
            return None

        params = {
            "SERVICE": "WMS",
            "VERSION": "1.1.1",
            "REQUEST": "GetFeatureInfo",
            "LAYERS": timestep.get("layer", "produtos:secadiagnostico"),
            "QUERY_LAYERS": timestep.get("layer", "produtos:secadiagnostico"),
            "STYLES": "",
            "BBOX": "-55.0,-21.0,-54.0,-20.0",
            "SRS": "EPSG:4326",
            "WIDTH": "101",
            "HEIGHT": "101",
            "X": "50",
            "Y": "50",
            "INFO_FORMAT": "application/json",
            "FEATURE_COUNT": "1",
            "viewparams": timestep.get("viewparams", ""),
        }

        layer_server = meta.get("layerserver", "")
        if not layer_server:
            return None

        response = requests.get(layer_server, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        features = payload.get("features", []) if isinstance(payload, dict) else []
        if not features:
            return None

        level = float(features[0].get("properties", {}).get("nivel", 3.0))
        return self._normalize_class(self._level_to_class(level))

    @staticmethod
    def _level_to_class(level: float) -> str:
        if level <= 1:
            return "S0"
        if level <= 2:
            return "S1"
        if level <= 3:
            return "S2"
        if level <= 4:
            return "S3"
        return "S4"

    @staticmethod
    def _normalize_class(value: str) -> str:
        text = str(value).strip().upper()
        if text in {"S0", "S1", "S2", "S3", "S4"}:
            return text
        match = re.search(r"S[0-4]", text)
        return match.group(0) if match else "S1"
