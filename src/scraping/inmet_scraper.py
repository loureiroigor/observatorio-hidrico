import requests
import pandas as pd

def coletar_dados_chuva():
    """
    consome dados reais da API Open-Meteo para Campo Grande/MS.
    mantém o Fallback de segurança caso a internet falhe.
    """
    # coordenadas de nosso campo grande - MS
    url = "https://api.open-meteo.com/v1/forecast?latitude=-20.4428&longitude=-54.6464&daily=precipitation_sum&timezone=America%2FSao_Paulo&past_days=5&forecast_days=1"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        datas = data['daily']['time']
        chuvas = data['daily']['precipitation_sum']
        
        df = pd.DataFrame({
            'Data': datas,
            'Precipitacao_mm': chuvas
        })
        print("[SUCESSO] Dados reais de Campo Grande obtidos via API.")
        return df

    except Exception as e:
        print(f"\n[AVISO] Falha na API: {e}")
        print("-> Usando dados de contingência para o dashboard não ficar vazio.\n")
        
        mock_dados = [
            {'Data': '2024-01-01', 'Precipitacao_mm': 12.0},
            {'Data': '2024-01-02', 'Precipitacao_mm': 2.0},
            {'Data': '2024-01-03', 'Precipitacao_mm': 0.0},
            {'Data': '2024-01-04', 'Precipitacao_mm': 25.5},
            {'Data': '2024-01-05', 'Precipitacao_mm': 5.0}
        ]
        return pd.DataFrame(mock_dados)

if __name__ == '__main__':
    print(coletar_dados_chuva())