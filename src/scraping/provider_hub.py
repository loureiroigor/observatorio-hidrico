from __future__ import annotations

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

    def collect_all(self) -> dict[str, AdapterResult]:
        results: dict[str, AdapterResult] = {}
        for key, adapter in self.adapters.items():
            try:
                results[key] = adapter.fetch()
            except Exception as exc:
                results[key] = adapter.unavailable(f"falha nao tratada no adapter {key}: {exc}")
        return results
