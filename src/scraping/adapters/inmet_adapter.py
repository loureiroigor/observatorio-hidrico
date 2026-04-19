from __future__ import annotations

from datetime import datetime
import time

import pandas as pd

from .base import AdapterResult, BaseAdapter


class InmetAdapter(BaseAdapter):
    source_name = "inmet"

    def __init__(self, station_code: str = "A702"):
        self.station_code = station_code

    def fetch(self) -> AdapterResult:
        url = f"https://tempo.inmet.gov.br/TabelaEstacoes/{self.station_code}"
        driver = None

        try:
            from bs4 import BeautifulSoup
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError as exc:
            fallback = pd.DataFrame(
                [{"Data": "INMET OFFLINE", "Hora (UTC)": "--:--", "Chuva (mm)": 0.0}]
            )
            return self.unavailable(
                "Dependencias do INMET ausentes: instale selenium, webdriver-manager e beautifulsoup4.",
                payload={"table": fallback, "last_rain_mm": 0.0},
            )

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")

        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.get(url)

            WebDriverWait(driver, 40).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
            time.sleep(4)

            soup = BeautifulSoup(driver.page_source, "lxml")
            table = soup.find("table")
            if table is None or table.find("tbody") is None:
                raise ValueError("Tabela da estacao nao encontrada no portal INMET")

            rows = table.find("tbody").find_all("tr")
            data = []
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 3:
                    continue

                rain_raw = cols[-1].text.strip().replace(",", ".")
                hour_raw = cols[1].text.strip()
                hour = f"{hour_raw[:2]}:{hour_raw[2:]}" if len(hour_raw) == 4 else hour_raw

                try:
                    rain_value = float(rain_raw) if rain_raw else 0.0
                except ValueError:
                    rain_value = 0.0

                data.append(
                    {
                        "Data": cols[0].text.strip(),
                        "Hora (UTC)": hour,
                        "Chuva (mm)": rain_value,
                    }
                )

            df = pd.DataFrame(data).tail(8)
            if df.empty:
                raise ValueError("Tabela carregada sem linhas de chuva")

            return AdapterResult(
                source=self.source_name,
                status="ok",
                updated_at=datetime.now(),
                payload={"table": df, "last_rain_mm": float(df["Chuva (mm)"].iloc[-1])},
            )
        except Exception as exc:
            fallback = pd.DataFrame(
                [{"Data": "INMET OFFLINE", "Hora (UTC)": "--:--", "Chuva (mm)": 0.0}]
            )
            return self.unavailable(str(exc), payload={"table": fallback, "last_rain_mm": 0.0})
        finally:
            if driver is not None:
                driver.quit()
