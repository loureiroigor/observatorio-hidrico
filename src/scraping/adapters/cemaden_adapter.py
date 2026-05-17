from __future__ import annotations

from datetime import datetime

import pandas as pd
import requests

from .base import BaseAdapter


class CemadenAdapter(BaseAdapter):
    source_name = "cemaden"
    product_meta_url = "https://mapasecas.cemaden.gov.br/rest/product/meta/iis3"
    target_bbox = "-55.0,-21.0,-54.0,-20.0"

    def fetch(self) -> AdapterResult:
        try:
            meta = requests.get(self.product_meta_url, timeout=20).json()
            timestep = self._latest_timestep(meta.get("timesteps", {}))
            if not timestep:
                raise ValueError("CEMADEN nao retornou timesteps para IIS3")

            feature = self._fetch_feature(meta.get("layerserver", ""), timestep)
            if not feature:
                raise ValueError("CEMADEN nao retornou feature para Campo Grande/MS")

            props = feature.get("properties", {})
            nivel = float(props.get("nivel", 3.0))
            umidade_proxy = max(8.0, min(72.0, 72.0 - (nivel * 8.0)))

            table = pd.DataFrame(
                [
                    {
                        "Estacao": f"{props.get('nm_mun', 'Campo Grande')} - {props.get('sigla_uf', 'MS')}",
                        "UmidadeSolo_pct": round(umidade_proxy, 2),
                        "IndiceIntegradoSeca_nivel": nivel,
                        "Referencia": props.get("referencia", datetime.now().isoformat()),
                    }
                ]
            )

            return self.success(
                payload={
                    "table": table,
                    "mean_soil_moisture": float(table["UmidadeSolo_pct"].mean()),
                    "source_url": self.product_meta_url,
                }
            )
        except Exception as exc:
            fallback = pd.DataFrame([{"Estacao": "MS-CG", "UmidadeSolo_pct": 37.0}])
            return self.unavailable(
                str(exc),
                payload={"table": fallback, "mean_soil_moisture": 37.0, "source_url": self.product_meta_url},
            )

    @staticmethod
    def _latest_timestep(timesteps: dict) -> dict:
        if not isinstance(timesteps, dict) or not timesteps:
            return {}
        latest_key = sorted(timesteps.keys(), reverse=True)[0]
        value = timesteps.get(latest_key, {})
        return value if isinstance(value, dict) else {}

    def _fetch_feature(self, layer_server: str, timestep: dict) -> dict:
        if not layer_server:
            return {}
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.1.1",
            "REQUEST": "GetFeatureInfo",
            "LAYERS": timestep.get("layer", "produtos:iis3"),
            "QUERY_LAYERS": timestep.get("layer", "produtos:iis3"),
            "STYLES": "",
            "BBOX": self.target_bbox,
            "SRS": "EPSG:4326",
            "WIDTH": "101",
            "HEIGHT": "101",
            "X": "50",
            "Y": "50",
            "INFO_FORMAT": "application/json",
            "FEATURE_COUNT": "1",
            "viewparams": timestep.get("viewparams", ""),
        }
        response = requests.get(layer_server, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        features = payload.get("features", []) if isinstance(payload, dict) else []
        return features[0] if features else {}
