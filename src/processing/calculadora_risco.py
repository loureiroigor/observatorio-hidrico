import pandas as pd
import numpy as np

def calcular_vulnerabilidade(df_chuva):
    """
    calcula a vulnerabilidade com base no DataFrame de chuva, adicionando uma
    coluna 'Indice_Risco' baseada na precipitaçao
    """

    condicoes = [
        (df_chuva['Precipitacao_mm'] < 8.0),
        (df_chuva['Precipitacao_mm'] >= 8.0) & (df_chuva['Precipitacao_mm'] <= 12.0),
        (df_chuva['Precipitacao_mm'] > 12.0)
    ]
    
    # Define os valores de risco correspondentes (numéricos de 1 a 10)
    valores = [9, 6, 2] 
    
    df_chuva['Indice_Risco'] = np.select(condicoes, valores, default=0)
    
    return df_chuva

if __name__ == '__main__':
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    from src.scraping.inmet_scraper import coletar_dados_chuva
    
    df_chuva_raw = coletar_dados_chuva()
    
    df_com_risco = calcular_vulnerabilidade(df_chuva_raw)
    
    print("DataFrame com Índice de Risco calculado:")
    print(df_com_risco)
