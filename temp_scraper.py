import requests
from bs4 import BeautifulSoup

url = "https://tempo.inmet.gov.br/TabelaEstacoes/"
response = requests.get(url)
soup = BeautifulSoup(response.content, 'html.parser')

table = soup.find('table', class_='table table-striped table-bordered')

if table:
    headers = [header.text.strip() for header in table.find_all('th')]
    print(headers)
    
    rows = table.find('tbody').find_all('tr')
    for row in rows[:5]:
        cols = row.find_all('td')
        cols_text = [ele.text.strip() for ele in cols]
        print(cols_text)
else:
    print("Tabela não encontrada")
