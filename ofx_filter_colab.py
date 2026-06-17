"""
Script para executar no Google Colab ou localmente para filtrar transações de um arquivo OFX.
- Faz upload do OFX (no Colab) ou lê via caminho
- Identifica contas dentro do OFX
- Permite escolher conta e mês
- Gera OFX filtrado mantendo estrutura original
Uso: execute em uma célula do Colab ou python local
"""

import calendar
import re
import sys
import os
from datetime import datetime, date
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
    print('Selecione o arquivo OFX para upload (Colab).')
    uploaded = files.upload()
    if not uploaded:
        raise SystemExit('Nenhum arquivo enviado.')
    name = next(iter(uploaded.keys()))
    text = uploaded[name].decode('utf-8', errors='ignore')
    return name, text


def extract_field(text, tag):
    m = re.search(rf'<{tag}>(.*?)\s*(?=<|$)', text, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ''


def extract_statement_blocks(text):
    pattern = re.compile(r'(<STMTTRNRS.*?</STMTTRNRS>)', re.DOTALL | re.IGNORECASE)
    blocks = []
    for m in pattern.finditer(text):
        blocks.append((m.group(1), m.start(), m.end()))
    if not blocks:
        # fallback para OFX simples sem STMTTRNRS
        blocks.append((text, 0, len(text)))
    return blocks


def parse_statement_info(statement):
    acctid = extract_field(statement, 'ACCTID')
    bankid = extract_field(statement, 'BANKID')
    accttype = extract_field(statement, 'ACCTTYPE')
    curdef = extract_field(statement, 'CURDEF')
    label = acctid or 'sem conta'
    if accttype:
        label += f' ({accttype})'
    if bankid:
        label += f' - banco {bankid}'
    if curdef:
        label += f' - moeda {curdef}'
    return acctid, bankid, accttype, curdef, label


def extract_stmttrn_blocks(text):
    pattern = re.compile(r'(<STMTTRN>.*?</STMTTRN>)', re.DOTALL | re.IGNORECASE)
    return pattern.findall(text)


def extract_dtposted(block):
    m = re.search(r'<DTPOSTED>\s*(\d+)', block, re.IGNORECASE)
    if not m:
        return None
    dt = m.group(1)
    if len(dt) >= 8:
        year = dt[0:4]
        month = dt[4:6]
        return f'{year}-{month}'
    return None


def parse_amount(value):
    if not value:
        return 0.0
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
    sign = '-' if value < 0 else ''
    return f'{sign}R$ {abs(value):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def build_filtered_statement(text, kept_blocks, chosen_key=None):
    pattern = re.compile(r'(<STMTTRN>.*?</STMTTRN>)', re.DOTALL | re.IGNORECASE)
    matches = list(pattern.finditer(text))
    if not matches:
        return text
    start_idx = matches[0].start()
    end_idx = matches[-1].end()
    before = text[:start_idx]
    after = text[end_idx:]
    new_inside = '\n'.join(kept_blocks)
    if new_inside:
        new_inside = '\n' + new_inside + '\n'
    filtered_text = before + new_inside + after
    if chosen_key is not None:
        filtered_text = update_banktranlist_dates(filtered_text, chosen_key)
    return filtered_text


def update_banktranlist_dates(bank_content, chosen_key):
    year, month = chosen_key.split('-')
    start_date = f'{year}{month}01'
    last_day = calendar.monthrange(int(year), int(month))[1]
    end_date = f'{year}{month}{last_day:02d}'

    bank_content = re.sub(r'<DTSTART>\s*\d+', f'<DTSTART>{start_date}', bank_content, flags=re.IGNORECASE)
    bank_content = re.sub(r'<DTEND>\s*\d+', f'<DTEND>{end_date}', bank_content, flags=re.IGNORECASE)
    return bank_content


def main():
    if _IN_COLAB:
        name, text = upload_ofx_colab()
    else:
        if len(sys.argv) > 1:
            path = sys.argv[1]
            name = os.path.basename(path)
            text = read_ofx_from_file(path)
        else:
            path = input('Caminho para o arquivo OFX (ou pressione Enter para escolher pelo Colab): ').strip()
            if path:
                name = os.path.basename(path)
                text = read_ofx_from_file(path)
            else:
                if _IN_COLAB:
                    name, text = upload_ofx_colab()
                else:
                    raise SystemExit('Arquivo não informado.')

    statements = extract_statement_blocks(text)
    if not statements:
        print('Nenhuma declaração de conta encontrada no arquivo OFX.')
        return

    account_infos = []
    for stmt, start, end in statements:
        acctid, bankid, accttype, curdef, label = parse_statement_info(stmt)
        blocks = extract_stmttrn_blocks(stmt)
        month_map = defaultdict(list)
        month_totals = defaultdict(float)
        
        valid_blocks = []
        for b in blocks:
            name = extract_field(b, 'NAME').upper()
            memo = extract_field(b, 'MEMO').upper()
            
            if 'SALDO ANTERIOR' in name or 'SALDO ANTERIOR' in memo or \
               'ULTIMOS LANCAMENTOS' in name or 'ÚLTIMOS LANÇAMENTOS' in name or \
               'ULTIMOS LANCAMENTOS' in memo or 'ÚLTIMOS LANÇAMENTOS' in memo:
                detected_term = name if 'SALDO' in name or 'LANCAMENTO' in name or 'LANÇAMENTO' in name else memo
                print(f"\n[Aviso] Marcador de corte detectado ('{detected_term}') na conta {label}. Ignorando os lançamentos seguintes.")
                break
                
            if 'SALDO DO DIA' in name or 'SALDO DO DIA' in memo or \
               'SALDO FINAL' in name or 'SALDO FINAL' in memo or \
               'S A L D O' in name or 'S A L D O' in memo:
                continue
                
            is_invest = ('INVEST FACIL' in name or 'INVEST FACIL' in memo or \
                         'APLIC.INVEST' in name or 'APLIC.INVEST' in memo or \
                         'RESGATE INVEST' in name or 'RESGATE INVEST' in memo)
            
            if 'RENTAB.INVEST' in name or 'RENTAB.INVEST' in memo:
                is_invest = False
            
            if is_invest:
                continue
                
            valid_blocks.append(b)
            
        for b in valid_blocks:
            key = extract_dtposted(b)
            month_map[key].append(b)
            month_totals[key] += parse_amount(extract_field(b, 'TRNAMT'))
            
        account_infos.append({
            'statement': stmt,
            'start': start,
            'end': end,
            'acctid': acctid,
            'bankid': bankid,
            'accttype': accttype,
            'curdef': curdef,
            'label': label,
            'blocks': valid_blocks,
            'month_map': month_map,
            'month_totals': month_totals,
        })

    print('\nContas encontradas no OFX:')
    for i, info in enumerate(account_infos, 1):
        total_tx = len(info['blocks'])
        print(f'{i}) {info["label"]} — {total_tx} transação(ões)')

    if len(account_infos) > 1:
        sel = input('\nDigite o número da conta que deseja manter: ').strip()
        try:
            si = int(sel) - 1
            assert 0 <= si < len(account_infos)
        except Exception:
            print('Seleção inválida.')
            return
    else:
        si = 0

    selected = account_infos[si]
    print(f'Conta selecionada: {selected["label"]}')

    keys = sorted([k for k in selected['month_map'].keys() if k is not None], reverse=True)
    if None in selected['month_map']:
        keys.append(None)

    print('\nMeses detectados e contagem de transações para a conta selecionada:')
    for i, k in enumerate(keys, 1):
        label = (k.replace('-', '/') if k else 'Sem data detectada')
        count = len(selected['month_map'][k])
        total_label = format_amount(selected['month_totals'][k]) if k is not None else ''
        print(f'{i}) {label} — {count} transação(s)' + (f' — total {total_label}' if total_label else ''))

    sel = input('\nDigite o número do mês que deseja manter (ex: 1): ').strip()
    try:
        mi = int(sel) - 1
        assert 0 <= mi < len(keys)
    except Exception:
        print('Seleção inválida.')
        return

    chosen_key = keys[mi]
    kept_blocks = selected['month_map'][chosen_key]

    print('\n--- Lançamentos do Mês Selecionado ---')
    for i, b in enumerate(kept_blocks, 1):
        dt_raw = extract_field(b, 'DTPOSTED')
        dt_formatted = f"{dt_raw[6:8]}/{dt_raw[4:6]}/{dt_raw[0:4]}" if len(dt_raw) >= 8 else "Sem data"
        fitid = extract_field(b, 'FITID')
        amt = parse_amount(extract_field(b, 'TRNAMT'))
        name = extract_field(b, 'NAME')
        memo = extract_field(b, 'MEMO')
        desc = f"{name} {memo}".strip()[:50]
        print(f"{i:03d} | {dt_formatted} | ID: {fitid:<15} | {format_amount(amt):>15} | {desc}")
    
    print(f"\nTotal de transações listadas: {len(kept_blocks)}")

    # Fluxo de Intervalo
    print(f"\n--- Seleção de Intervalo ---")
    try:
        inicio_input = input(f'Linha INICIAL (pressione Enter para 1): ').strip()
        inicio = int(inicio_input) - 1 if inicio_input else 0
        
        fim_input = input(f'Linha FINAL (pressione Enter para {len(kept_blocks)}): ').strip()
        fim = int(fim_input) if fim_input else len(kept_blocks)
        
        inicio = max(0, min(inicio, len(kept_blocks) - 1))
        fim = max(inicio + 1, min(fim, len(kept_blocks)))
        
        final_blocks = kept_blocks[inicio:fim]
    except ValueError:
        print("Entrada inválida.")
        return
    
    total_entrada = 0.0
    total_saida = 0.0
    for b in final_blocks:
        amt = parse_amount(extract_field(b, 'TRNAMT'))
        if amt >= 0:
            total_entrada += amt
        else:
            total_saida += amt
    
    print(f"\n--- Resumo do Intervalo Selecionado (Linhas {inicio + 1} até {fim}) ---")
    print(f"Total Entradas: {format_amount(total_entrada)}")
    print(f"Total Saídas:   {format_amount(total_saida)}")
    print(f"Saldo Líquido:  {format_amount(total_entrada + total_saida)}")
    
    conf = input('\nConfirmar exportação e gerar novo arquivo? (S/N): ').strip().upper()
    if conf != 'S' and conf != '':
        print("Operação cancelada.")
        return

    filtered_statement = build_filtered_statement(selected['statement'], final_blocks, chosen_key)

    output_before = text[:statements[0][1]]
    output_after = text[statements[-1][2]:]
    new_text = output_before + filtered_statement + output_after

    out_name = os.path.splitext(name)[0] + f'_filtered_{(selected["acctid"] or "account")}_{(chosen_key or "nodate").replace("-","")}.ofx'
    with open(out_name, 'w', encoding='utf-8', errors='ignore') as f:
        f.write(new_text)

    print(f'OFX filtrado salvo em: {out_name}')

    if _IN_COLAB:
        try:
            files.download(out_name)
        except Exception:
            print('Falha ao iniciar download automático. Baixe manualmente do diretório do runtime.')


if __name__ == '__main__':
    main()
