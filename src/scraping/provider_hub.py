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
        return {key: adapter.fetch() for key, adapter in self.adapters.items()}
