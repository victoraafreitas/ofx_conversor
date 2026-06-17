"""
Script para contar a quantidade de movimentações em um extrato bancário em PDF.
A contagem para automaticamente ao encontrar a primeira linha de "Total".

Uso:
  python pdf_transaction_counter.py caminho/para/seu_extrato.pdf

No Colab, execute e ele pedirá o upload do arquivo.
"""

import re
import sys
import os

try:
    from google.colab import files
    _IN_COLAB = True
except Exception:
    _IN_COLAB = False

try:
    import pypdf
except ImportError:
    try:
        import PyPDF2 as pypdf
    except ImportError:
        print("Biblioteca 'pypdf' não encontrada. Instalando automaticamente...")
        os.system(f"{sys.executable} -m pip install pypdf")
        import pypdf


def upload_pdf_colab():
    print('Selecione o arquivo PDF do extrato para upload (Colab).')
    uploaded = files.upload()
    if not uploaded:
        raise SystemExit('Nenhum arquivo enviado.')
    name = next(iter(uploaded.keys()))
    return name


def count_transactions_in_pdf(pdf_path):
    # Regex para identificar formato de moeda brasileira: ex: 100,00 ou -2.174,95
    money_pattern = r'-?\d{1,3}(?:\.\d{3})*,\d{2}'
    
    # Regex para capturar linhas de transação. 
    # Uma linha de transação válida termina com DOIS valores monetários (Valor e Saldo).
    # Exemplo: "... 146181     100,00    18.851,61"
    transaction_pattern = re.compile(rf'{money_pattern}\s+{money_pattern}\s*$', re.IGNORECASE)

    count = 0
    found_total = False
    started_extrato = False

    print("\n--- INÍCIO DA LEITURA DAS LINHAS CONTABILIZADAS ---")
    with open(pdf_path, 'rb') as file:
        reader = pypdf.PdfReader(file)
        
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            text = page.extract_text()
            
            if not text:
                continue

            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                line_lower = line.lower()
                
                # Gatilho para iniciar a leitura apenas na tabela de transações reais
                if 'extrato de:' in line_lower or ('crédito' in line_lower and 'débito' in line_lower):
                    started_extrato = True
                    continue
                
                # Se encontrar a linha de Total real ou Últimos Lançamentos, paramos a contagem
                if line_lower.startswith('total'):
                    # Ignorar os cabeçalhos que contêm "Disponível" ou "(R$)"
                    if 'dispon' not in line_lower and '(r$)' not in line_lower:
                        found_total = True
                        break
                        
                if 'últimos lançamentos' in line_lower or 'ultimos lancamentos' in line_lower:
                    found_total = True
                    break
                
                # Verifica se a linha termina com os dois valores (Valor da transação e Saldo)
                if transaction_pattern.search(line):
                    # Iniciar a contagem apenas se já passamos do cabeçalho do extrato
                    if not started_extrato:
                        continue
                        
                    # Ignorar a linha de cabeçalho "Agência | Conta" que repete no topo de cada página
                    if re.search(r'\d+\s*\|\s*\d+-\w+', line):
                        continue
                        
                    # Ignorar linha de SALDO ANTERIOR se ela por acaso bater
                    if 'SALDO ANTERIOR' not in line.upper() and 'SALDO INICIAL' not in line.upper():
                        count += 1
                        # Imprimir as linhas contadas para auditoria
                        print(f"[{count}] {line}")
            
            if found_total:
                break

    return count, found_total


def main():
    if _IN_COLAB:
        pdf_path = upload_pdf_colab()
    else:
        if len(sys.argv) > 1:
            pdf_path = sys.argv[1]
        else:
            pdf_path = input('Caminho para o arquivo PDF: ').strip()
            if not pdf_path:
                if _IN_COLAB:
                    pdf_path = upload_pdf_colab()
                else:
                    raise SystemExit('Arquivo não informado.')

    if not os.path.exists(pdf_path):
        raise SystemExit(f'Arquivo não encontrado: {pdf_path}')

    print(f"\nLendo o arquivo PDF: {os.path.basename(pdf_path)}...")
    total_transactions, stopped_at_total = count_transactions_in_pdf(pdf_path)
    
    print("\n" + "="*50)
    print(f"RESULTADO DA CONTAGEM:")
    print(f"Total de movimentações: {total_transactions}")
    if stopped_at_total:
        print("Status: Contagem encerrada com sucesso ao encontrar o 'Total' do mês.")
    else:
        print("Status: Linha de 'Total' não encontrada. O arquivo foi lido até o final.")
    print("="*50 + "\n")


if __name__ == '__main__':
    main()
