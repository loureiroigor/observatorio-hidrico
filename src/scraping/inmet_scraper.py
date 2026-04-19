from __future__ import annotations

import pandas as pd

from .adapters.inmet_adapter import InmetAdapter
from .adapters.openmeteo_adapter import OpenMeteoAdapter


def raspar_inmet_tabela() -> pd.DataFrame:
    result = InmetAdapter().fetch()
    return result.payload.get("table", pd.DataFrame())


def coletar_dados_chuva() -> pd.DataFrame:
    result = OpenMeteoAdapter().fetch()
    return result.payload.get("daily", pd.DataFrame())


def coletar_detalhes_horarios_api() -> pd.DataFrame:
    result = OpenMeteoAdapter().fetch()
    return result.payload.get("hourly", pd.DataFrame())


if __name__ == "__main__":
    print(raspar_inmet_tabela())
