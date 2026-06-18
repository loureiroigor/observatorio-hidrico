from __future__ import annotations

import time
from datetime import date, timedelta

import pandas as pd
import requests

from .base import BaseAdapter


class InmetAdapter(BaseAdapter):
    source_name = "inmet"
    _fallback = pd.DataFrame([{"Data": "INMET OFFLINE", "Hora (UTC)": "--:--", "Chuva (mm)": 0.0}])

    def __init__(self, station_code: str = "A702"):
        self.station_code = station_code
        self._api_error = "API INMET nao consultada"

    def fetch(self) -> AdapterResult:
        api_result = self._fetch_from_api()
        if api_result is not None:
            return api_result

        url = f"https://tempo.inmet.gov.br/TabelaEstacoes/{self.station_code}"
        driver = None

        try:
            from bs4 import BeautifulSoup
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.edge.options import Options as EdgeOptions
            from selenium.webdriver.edge.service import Service as EdgeService
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
            from webdriver_manager.chrome import ChromeDriverManager
            from webdriver_manager.microsoft import EdgeChromiumDriverManager
        except ImportError:
            return self.unavailable(
                "Dependencias do INMET ausentes: instale selenium, webdriver-manager e beautifulsoup4.",
                payload={"table": self._fallback.copy(), "last_rain_mm": 0.0},
            )

        options = Options()
        for arg in ("--headless", "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1920,1080"):
            options.add_argument(arg)

        try:
            driver = self._build_browser_driver(webdriver, options, ChromeDriverManager, EdgeOptions, EdgeService, EdgeChromiumDriverManager)
            driver.get(url)
            WebDriverWait(driver, 40).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
            time.sleep(4)

            table = BeautifulSoup(driver.page_source, "lxml").find("table")
            if table is None or table.find("tbody") is None:
                raise ValueError("Tabela da estacao nao encontrada no portal INMET")

            rows = table.find("tbody").find_all("tr")
            data = [parsed for parsed in (self._parse_row(row) for row in rows) if parsed is not None]
            df = pd.DataFrame(data).tail(8)
            if df.empty:
                raise ValueError("Tabela carregada sem linhas de chuva")

            return self.success(payload={"table": df, "last_rain_mm": float(df["Chuva (mm)"].iloc[-1])})
        except Exception as exc:
            # fallback evita parar o calculo quando scraping dinamico falha
            error = str(exc)
            if "cannot find Chrome binary" in error:
                error = f"{self._api_error}; fallback Selenium indisponivel porque Chrome/Edge nao foi encontrado."
            return self.unavailable(error, payload={"table": self._fallback.copy(), "last_rain_mm": 0.0})
        finally:
            if driver is not None:
                driver.quit()

    @staticmethod
    def _build_browser_driver(webdriver, chrome_options, ChromeDriverManager, EdgeOptions, EdgeService, EdgeChromiumDriverManager):
        try:
            from selenium.webdriver.chrome.service import Service as ChromeService

            return webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        except Exception as chrome_exc:
            edge_options = EdgeOptions()
            for arg in ("--headless", "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1920,1080"):
                edge_options.add_argument(arg)
            try:
                return webdriver.Edge(service=EdgeService(EdgeChromiumDriverManager().install()), options=edge_options)
            except Exception as edge_exc:
                raise RuntimeError(f"Chrome falhou: {chrome_exc}; Edge falhou: {edge_exc}") from edge_exc

    def _fetch_from_api(self) -> AdapterResult | None:
        for days_ago in range(11):
            day = date.today() - timedelta(days=days_ago)
            url = f"https://apitempo.inmet.gov.br/estacao/dados/{day.isoformat()}/{self.station_code}"
            try:
                response = requests.get(url, timeout=20)
                if response.status_code == 204:
                    continue
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError) as exc:
                self._api_error = f"API INMET falhou: {exc}"
                return None

            if isinstance(payload, list) and payload:
                break
        else:
            self._api_error = f"API INMET sem dados recentes para a estacao {self.station_code}"
            return None

        data = [parsed for parsed in (self._parse_api_record(record) for record in payload) if parsed is not None]
        df = pd.DataFrame(data).tail(8)
        if df.empty:
            self._api_error = f"API INMET retornou dados sem chuva parseavel para a estacao {self.station_code}"
            return None

        return self.success(payload={"table": df, "last_rain_mm": float(df["Chuva (mm)"].iloc[-1])})

    @staticmethod
    def _parse_api_record(record: dict) -> dict | None:
        if not isinstance(record, dict):
            return None

        rain_raw = record.get("CHUVA")
        if rain_raw in (None, ""):
            rain_mm = 0.0
        else:
            rain_mm = float(str(rain_raw).replace(",", "."))

        hour_raw = str(record.get("HR_MEDICAO", "")).zfill(4)
        return {
            "Data": str(record.get("DT_MEDICAO", "")),
            "Hora (UTC)": f"{hour_raw[:2]}:{hour_raw[2:4]}" if len(hour_raw) >= 4 else hour_raw,
            "Chuva (mm)": rain_mm,
        }

    @staticmethod
    def _parse_row(row) -> dict | None:
        cols = row.find_all("td")
        if len(cols) < 3:
            return None
        rain_raw = cols[-1].text.strip().replace(",", ".")
        hour_raw = cols[1].text.strip()
        return {
            "Data": cols[0].text.strip(),
            "Hora (UTC)": f"{hour_raw[:2]}:{hour_raw[2:]}" if len(hour_raw) == 4 else hour_raw,
            "Chuva (mm)": float(rain_raw) if rain_raw else 0.0,
        }
