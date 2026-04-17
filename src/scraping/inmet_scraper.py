import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def raspar_inmet_tabela():
    print("\nIniciando Web Scraping Dinâmico (Selenium - Versão Robusta)...")
    url = "https://tempo.inmet.gov.br/TabelaEstacoes/A702"
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # AJUSTE 1: Definir tamanho de tela Desktop para garantir renderização
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        print(f"Acessando portal INMET: {url}")
        driver.get(url)
        
        # AJUSTE 2: Esperar até 40 segundos. O INMET às vezes é realmente LENTO.
        print("Aguardando a tabela carregar (pode levar até 40s)...")
        # Vamos procurar por qualquer TAG de tabela que contenha dados
        espera = WebDriverWait(driver, 40)
        tabela_presente = espera.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        
        # AJUSTE 3: Pequena pausa para o JavaScript preencher as células
        time.sleep(5)
        
        soup = BeautifulSoup(driver.page_source, 'lxml')
        tabela = soup.find('table')
        
        if not tabela:
             raise ValueError("O navegador carregou a página, mas a tabela sumiu.")

        linhas = tabela.find('tbody').find_all('tr')
        dados = []
        
        for linha in linhas:
             cols = linha.find_all('td')
             # Verificamos se a linha tem colunas antes de tentar pegar os dados
             if len(cols) > 0:
                 # Pegamos a última coluna (-1), que é sempre a 'Chuva (mm)'
                 chuva_valor = cols[-1].text.strip().replace(',', '.')
                 
                 # Pegamos os índices 0 e 1 para Data e Hora
                 if chuva_valor:
                    hora_raw = cols[1].text.strip()
                    hora_formatada = f"{hora_raw[:2]}:{hora_raw[2:]}" if len(hora_raw) == 4 else hora_raw
    
                    dados.append({
                        'Data': cols[0].text.strip(),
                        'Hora (UTC)': hora_formatada,
                        'Chuva (mm)': float(chuva_valor) if chuva_valor != "" else 0.0
                    })
                      
        df = pd.DataFrame(dados)
        
        if df.empty:
             print("⚠️ Tabela encontrada, mas estava vazia. Verifique se há dados no site.")
             return pd.DataFrame([{'Data': 'INMET VAZIO', 'Hora (UTC)': 'HOJE', 'Chuva (mm)': '0.0'}])
             
        print("✅ SUCESSO: Dados extraídos via Selenium!")
        return df.tail(5)

    except Exception as e:
        print(f"❌ Erro no Scraping: {e}")
        # Retorno de segurança para o dashboard não ficar feio
        return pd.DataFrame([{'Data': 'INMET OFFLINE', 'Hora (UTC)': 'TIMEOUT', 'Chuva (mm)': '---'}])
        
    finally:
        if driver:
            driver.quit()

def coletar_dados_chuva():
    """
    Mantemos a nossa API primária (Open-Meteo) intacta para o gráfico de risco.
    """
    url = "https://api.open-meteo.com/v1/forecast?latitude=-20.4428&longitude=-54.6464&daily=precipitation_sum&timezone=America%2FSao_Paulo&past_days=5&forecast_days=1"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        df = pd.DataFrame({
            'Data': data['daily']['time'],
            'Precipitacao_mm': data['daily']['precipitation_sum']
        })
        return df
    except Exception as e:
        return pd.DataFrame({'Data': [datetime.now().strftime('%Y-%m-%d')], 'Precipitacao_mm': [0.0]})

def coletar_detalhes_horarios_api():
    """
    Coleta os dados horários da API para criar uma tabela de auditoria digital
    que permita comparar com o scraping do sensor físico.
    """
    url = "https://api.open-meteo.com/v1/forecast?latitude=-20.4428&longitude=-54.6464&hourly=precipitation&timezone=America%2FSao_Paulo&past_days=1&forecast_days=1"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        df_hora = pd.DataFrame({
            'Data_Hora': data['hourly']['time'],
            'Chuva_Digital (mm)': data['hourly']['precipitation']
        })
        
        # Formatamos para ficar igual à tabela do INMET
        df_hora['Data'] = pd.to_datetime(df_hora['Data_Hora']).dt.strftime('%d/%m/%Y')
        df_hora['Hora'] = pd.to_datetime(df_hora['Data_Hora']).dt.strftime('%H:%M')
        
        return df_hora[['Data', 'Hora', 'Chuva_Digital (mm)']].tail(8)
    except Exception as e:
        return pd.DataFrame()

if __name__ == '__main__':
    print(raspar_inmet_tabela())