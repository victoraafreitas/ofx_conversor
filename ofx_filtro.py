import calendar
import re
import sys
import os
from datetime import datetime
from collections import defaultdict

try:
    from google.colab import files
    _IN_COLAB = True
except Exception:
    _IN_COLAB = False

def read_ofx_from_file(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def upload_ofx_colab():
    print('Selecione o arquivo OFX para upload.')
    uploaded = files.upload()
    if not uploaded:
        raise SystemExit('Nenhum arquivo enviado.')
    name = next(iter(uploaded.keys()))
    text = uploaded[name].decode('utf-8', errors='ignore')
    return name, text

def extract_field(text, tag):
    m = re.search(rf'<{tag}>(.*?)\s*(?=<|$)', text, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ''

def parse_amount(value):
    if not value: return 0.0
    val = value.strip()
    
    # Se o valor contiver pontos E vírgulas (ex: 246.659,22), limpa o ponto de milhar
    if '.' in val and ',' in val:
        val = val.replace('.', '').replace(',', '.')
    # Se contiver apenas um ponto e ele parecer separador de milhar (ex: 246.659 de um total inteiro)
    elif '.' in val and len(val.split('.')[-1]) > 2:
        val = val.replace('.', '')
    else:
        val = val.replace(',', '.')
        
    val = re.sub(r'[^\d\.\-]', '', val)
    try:
        return float(val)
    except ValueError:
        return 0.0

def format_amount(value):
    return f"{'-' if value < 0 else ''}R$ {abs(value):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def is_valid_transaction(block):
    name = extract_field(block, 'NAME').upper()
    memo = extract_field(block, 'MEMO').upper()
    
    # IMPORTANTE: Filtro ultra estrito. Só barra se for informativo de Saldo do Banco.
    # Não barra palavras como "Lançamento" isoladas, pois o banco usa isso em tarifas/aplicações.
    termos_saldo_puros = ['SALDO DO DIA', 'SALDO ANTERIOR', 'SALDO FINAL', 'FIM DE EXTRATO']
    if any(t in name or t in memo for t in termos_saldo_puros):
        return False
        
    # Se for apenas uma linha de texto sem valor nenhum cadastrado
    if parse_amount(extract_field(block, 'TRNAMT')) == 0.0:
        # Só ignora se não tiver nome descritivo (evita barrar transações de R$ 0,00 raras)
        if not name and not memo:
            return False
            
    return True

def main():
    if _IN_COLAB:
        name, text = upload_ofx_colab()
    else:
        path = input('Caminho do arquivo OFX: ').strip()
        if not path:
            raise SystemExit('Arquivo não informado.')
        name = os.path.basename(path)
        text = read_ofx_from_file(path)

    # Extração de blocos de transação (<STMTTRN>)
    stmt_pattern = re.compile(r'(<STMTTRN>.*?</STMTTRN>)', re.DOTALL | re.IGNORECASE)
    all_blocks = stmt_pattern.findall(text)
    
    if not all_blocks:
        print('Nenhuma transação encontrada no arquivo OFX.')
        return

    # Filtra mantendo absolutamente tudo que movimenta dinheiro
    valid_blocks = [b for b in all_blocks if is_valid_transaction(b)]
    
    print(f'\nTotal de transações válidas encontradas: {len(valid_blocks)}')
    print("-" * 90)
    
    for i, b in enumerate(valid_blocks, 1):
        dt = extract_field(b, 'DTPOSTED')
        dt_fmt = f"{dt[6:8]}/{dt[4:6]}/{dt[0:4]}" if len(dt) >= 8 else "---"
        amt = parse_amount(extract_field(b, 'TRNAMT'))
        
        favorecido = extract_field(b, 'NAME')
        memo = extract_field(b, 'MEMO')
        descricao_completa = f"{favorecido} {memo}".strip()
        
        print(f"{i:03d} | {dt_fmt} | {format_amount(amt):>15} | {descricao_completa[:55]}")

    print("-" * 90)

    # Fluxo de Intervalo
    print(f"\n--- Seleção de Intervalo ---")
    try:
        inicio_input = input(f'Linha INICIAL (pressione Enter para 1): ').strip()
        inicio = int(inicio_input) - 1 if inicio_input else 0
        
        fim_input = input(f'Linha FINAL (pressione Enter para {len(valid_blocks)}): ').strip()
        fim = int(fim_input) if fim_input else len(valid_blocks)
        
        inicio = max(0, min(inicio, len(valid_blocks) - 1))
        fim = max(inicio + 1, min(fim, len(valid_blocks)))
        
        final_blocks = valid_blocks[inicio:fim]
    except ValueError:
        print("Entrada inválida.")
        return

    # Cálculo refeito com os novos blocos estáveis
    total_entrada = sum(parse_amount(extract_field(b, 'TRNAMT')) for b in final_blocks if parse_amount(extract_field(b, 'TRNAMT')) >= 0)
    total_saida = sum(parse_amount(extract_field(b, 'TRNAMT')) for b in final_blocks if parse_amount(extract_field(b, 'TRNAMT')) < 0)

    print(f"\n--- Resumo do Intervalo Selecionado (Linhas {inicio + 1} até {fim}) ---")
    print(f"Total Entradas: {format_amount(total_entrada)}")
    print(f"Total Saídas:   {format_amount(total_saida)}")
    print(f"Saldo Líquido:  {format_amount(total_entrada + total_saida)}")

    conf = input('\nConfirmar exportação e gerar novo arquivo? (S/N): ').strip().upper()
    if conf == 'S' or conf == '':
        idx_primeiro = text.find('<STMTTRN>')
        idx_ultimo = text.rfind('</STMTTRN>') + 10
        
        header = text[:idx_primeiro]
        footer = text[idx_ultimo:]
        
        new_text = header + '\n' + '\n'.join(final_blocks) + '\n' + footer
        
        out_name = f"filtrado_{name}"
        with open(out_name, 'w', encoding='utf-8') as f:
            f.write(new_text)
            
        print(f'\n[Sucesso] Arquivo salvo como: {out_name}')
        if _IN_COLAB: 
            files.download(out_name)

if __name__ == '__main__':
    main()