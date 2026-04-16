import requests
from bs4 import BeautifulSoup
import pandas as pd

def coletar_dados_chuva():
    """
    coleta dados de chuva simulando o acesso a uma página de dados meteorológicos só pra ver se tá dando o cheiro.
    
    essa função simula a extraçao de uma tabela com 'Data' e 'Precipitacao_mm',
    e retorna os dados formatados em um DataFrame do Pandas.
    bizarro.
    """
    url = 'https://exemplo-clima.gov.br'
    
    # Mock do conteúdo HTML da página
    html_content = """
    <html>
    <body>
        <h2>Dados de Precipitação</h2>
        <table border="1">
            <thead>
                <tr>
                    <th>Data</th>
                    <th>Precipitação (mm)</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>2024-01-01</td>
                    <td>10.5</td>
                </tr>
                <tr>
                    <td>2024-01-02</td>
                    <td>5.2</td>
                </tr>
                <tr>
                    <td>2024-01-03</td>
                    <td>8.0</td>
                </tr>
                <tr>
                    <td>2024-01-04</td>
                    <td>15.7</td>
                </tr>
            </tbody>
        </table>
    </body>
    </html>
    """
    
    # analisa o HTML com BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # encontrando tabela e extraindo os dados
    table = soup.find('table')
    dados = []
    for row in table.find('tbody').find_all('tr'):
        cols = row.find_all('td')
        data = cols[0].text.strip()
        precipitacao = float(cols[1].text.strip())
        dados.append({'Data': data, 'Precipitacao_mm': precipitacao})
        
    df = pd.DataFrame(dados)
    
    return df

if __name__ == '__main__':
    df_chuva = coletar_dados_chuva()
    print(df_chuva)