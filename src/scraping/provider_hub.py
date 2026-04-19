from __future__ import annotations

from typing import Dict

from .adapters import AnaSecaAdapter, CemadenAdapter, ImasulAdapter, InmetAdapter, OpenMeteoAdapter
from .adapters.base import AdapterResult


class ProviderHub:
    def __init__(self):
        self.adapters = {
            "imasul": ImasulAdapter(),
            "cemaden": CemadenAdapter(),
            "ana": AnaSecaAdapter(),
            "inmet": InmetAdapter(),
            "open_meteo": OpenMeteoAdapter(),
        }

    def collect_all(self) -> Dict[str, AdapterResult]:
        results: Dict[str, AdapterResult] = {}
        for key, adapter in self.adapters.items():
            results[key] = adapter.fetch()
        return results
