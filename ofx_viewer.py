"""
Script para visualizar todas as transações de um arquivo OFX.
Uso:
  python erro_ofx/ofx_viewer.py caminho/para/seu.arquivo.ofx

No Colab, você pode fazer upload do arquivo OFX manualmente.
"""

import re
import sys
import os
from datetime import datetime

try:
    from google.colab import files
    _IN_COLAB = True
except Exception:
    _IN_COLAB = False


def read_ofx(path):
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
    blocks = pattern.findall(text)
    if not blocks:
        blocks = [text]
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


def parse_stmttrn(block):
    fields = {}
    for tag in ['TRNTYPE', 'DTPOSTED', 'TRNAMT', 'FITID', 'CHECKNUM', 'NAME', 'MEMO']:
        fields[tag] = extract_field(block, tag)
    return fields


def format_date(dtposted):
    if not dtposted:
        return ''
    dt = dtposted.strip()
    if len(dt) >= 8 and dt[:8].isdigit():
        try:
            return datetime.strptime(dt[:8], '%Y%m%d').strftime('%Y-%m-%d')
        except ValueError:
            return dt
    return dt


def extract_stmttrn_blocks(text):
    pattern = re.compile(r'<STMTTRN>(.*?)</STMTTRN>', re.DOTALL | re.IGNORECASE)
    return ['<STMTTRN>' + m + '</STMTTRN>' for m in pattern.findall(text)]


def parse_amount(value):
    if not value:
        return 0.0
    normalized = value.strip().replace('.', '').replace(',', '.')
    try:
        return float(normalized)
    except ValueError:
        return 0.0


def format_amount(value):
    sign = '-' if value < 0 else ''
    return f'{sign}R$ {abs(value):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def print_movements(blocks):
    if not blocks:
        print('Nenhuma transação <STMTTRN> encontrada.')
        return

    total_credit = 0.0
    total_debit = 0.0
    type_totals = {}
    print(f'Total de movimentos encontrados: {len(blocks)}\n')
    for idx, block in enumerate(blocks, 1):
        data = parse_stmttrn(block)
        amount = parse_amount(data['TRNAMT'])
        trn_type = data['TRNTYPE'].strip().upper()
        if amount >= 0:
            total_credit += amount
        else:
            total_debit += amount
        if trn_type:
            type_totals[trn_type] = type_totals.get(trn_type, 0.0) + amount

        date_str = format_date(data['DTPOSTED'])
        print(f'Movimento {idx}')
        print(f'  Data postada : {date_str}')
        print(f'  Tipo         : {data["TRNTYPE"]}')
        print(f'  Valor        : {data["TRNAMT"]}')
        print(f'  ID (FITID)   : {data["FITID"]}')
        if data['CHECKNUM']:
            print(f'  CHECKNUM     : {data["CHECKNUM"]}')
        if data['NAME']:
            print(f'  Nome         : {data["NAME"]}')
        if data['MEMO']:
            print(f'  Memo         : {data["MEMO"]}')
        print('-' * 50)

    print('\nResumo:')
    print(f'  Total de entradas : {format_amount(total_credit)}')
    print(f'  Total de saídas   : {format_amount(total_debit)}')
    if type_totals:
        print('\nResumo por tipo:')
        for trn_type, total in sorted(type_totals.items()):
            print(f'  {trn_type:10} : {format_amount(total)}')


def main():
    if _IN_COLAB:
        name, text = upload_ofx_colab()
    else:
        if len(sys.argv) > 1:
            path = sys.argv[1]
            name = os.path.basename(path)
            text = read_ofx(path)
        else:
            path = input('Caminho para o arquivo OFX: ').strip()
            if not path:
                raise SystemExit('Arquivo não informado.')
            name = os.path.basename(path)
            text = read_ofx(path)

    statements = extract_statement_blocks(text)
    if len(statements) > 1:
        print('\nContas encontradas no OFX:')
        for i, stmt in enumerate(statements, 1):
            acctid, bankid, accttype, curdef, label = parse_statement_info(stmt)
            blocks = extract_stmttrn_blocks(stmt)
            print(f'{i}) {label} — {len(blocks)} transação(ões)')
        print('')

    total_blocks = 0
    for idx, stmt in enumerate(statements, 1):
        acctid, bankid, accttype, curdef, label = parse_statement_info(stmt)
        print(f'\n=== Conta {idx}: {label} ===')
        blocks = extract_stmttrn_blocks(stmt)
        total_blocks += len(blocks)
        print_movements(blocks)

    if len(statements) == 1:
        print(f'\nTotal de contas no arquivo: 1')
    else:
        print(f'\nTotal de contas no arquivo: {len(statements)} (movimentos totais: {total_blocks})')


if __name__ == '__main__':
    main()
