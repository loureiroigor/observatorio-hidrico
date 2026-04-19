"""fachada de compatibilidade para scraping antigo via novo ecossistema de adapters.

para rodar: py -m src.scraping.inmet_scraper
"""

from __future__ import annotations

import pandas as pd

from .adapters.inmet_adapter import InmetAdapter
from .adapters.openmeteo_adapter import OpenMeteoAdapter


def _payload_or_empty(adapter_result, key: str) -> pd.DataFrame:
    return adapter_result.payload.get(key, pd.DataFrame())


def raspar_inmet_tabela() -> pd.DataFrame:
    return _payload_or_empty(InmetAdapter().fetch(), "table")


def coletar_dados_chuva() -> pd.DataFrame:
    return _payload_or_empty(OpenMeteoAdapter().fetch(), "daily")


def coletar_detalhes_horarios_api() -> pd.DataFrame:
    return _payload_or_empty(OpenMeteoAdapter().fetch(), "hourly")


if __name__ == "__main__":
    print(raspar_inmet_tabela())
