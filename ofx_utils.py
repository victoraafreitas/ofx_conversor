"""
Funções auxiliares para processamento de arquivos OFX.
Reutilizáveis em qualquer interface (Streamlit, CLI, etc).
"""

import calendar
import re
from collections import defaultdict


def extract_field(text, tag):
    """Extrai valor de uma tag XML/OFX."""
    m = re.search(rf'<{tag}>(.*?)\s*(?=<|$)', text, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ''


def parse_amount(value):
    """
    Parse robusto para formato brasileiro.
    - 246.659,22 → 246659.22
    - 246.659 → 246659
    - 1000,50 → 1000.50
    """
    if not value:
        return 0.0
    val = value.strip()
    
    # Se contiver pontos E vírgulas (ex: 246.659,22)
    if '.' in val and ',' in val:
        val = val.replace('.', '').replace(',', '.')
    # Se contiver apenas um ponto e parecer milhar (ex: 246.659)
    elif '.' in val and len(val.split('.')[-1]) > 2:
        val = val.replace('.', '')
    else:
        val = val.replace(',', '.')
    
    # Remove caracteres inválidos
    val = re.sub(r'[^\d\.\-]', '', val)
    try:
        return float(val)
    except ValueError:
        return 0.0


def format_amount(value):
    """Formata valor para R$ com separadores brasileiros."""
    sign = '-' if value < 0 else ''
    return f'{sign}R$ {abs(value):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def extract_statement_blocks(text):
    """Extrai blocos de declaração (suporta múltiplas contas)."""
    pattern = re.compile(r'(<STMTTRNRS.*?</STMTTRNRS>)', re.DOTALL | re.IGNORECASE)
    blocks = []
    for m in pattern.finditer(text):
        blocks.append((m.group(1), m.start(), m.end()))
    if not blocks:
        blocks.append((text, 0, len(text)))
    return blocks


def parse_statement_info(statement):
    """Extrai informações da conta (ID, banco, tipo, moeda)."""
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
    """Extrai blocos individuais de transação (<STMTTRN>)."""
    pattern = re.compile(r'(<STMTTRN>.*?</STMTTRN>)', re.DOTALL | re.IGNORECASE)
    return pattern.findall(text)


def extract_dtposted(block):
    """Extrai data como YYYY-MM para agrupamento por mês."""
    m = re.search(r'<DTPOSTED>\s*(\d+)', block, re.IGNORECASE)
    if not m:
        return None
    dt = m.group(1)
    if len(dt) >= 8:
        year = dt[0:4]
        month = dt[4:6]
        return f'{year}-{month}'
    return None


def is_valid_transaction(block):
    """
    Valida transação: remove saldos informativos e investimentos.
    Reutiliza lógica do ofx_filtro.py
    """
    name = extract_field(block, 'NAME').upper()
    memo = extract_field(block, 'MEMO').upper()
    
    # Detecta marcadores de corte
    if 'SALDO ANTERIOR' in name or 'SALDO ANTERIOR' in memo or \
       'ULTIMOS LANCAMENTOS' in name or 'ÚLTIMOS LANÇAMENTOS' in name or \
       'ULTIMOS LANCAMENTOS' in memo or 'ÚLTIMOS LANÇAMENTOS' in memo:
        return False
    
    # Remove saldos do dia
    if 'SALDO DO DIA' in name or 'SALDO DO DIA' in memo or \
       'SALDO FINAL' in name or 'SALDO FINAL' in memo or \
       'S A L D O' in name or 'S A L D O' in memo:
        return False
    
    # Remove investimentos (mantém RENTAB.INVEST)
    is_invest = ('INVEST FACIL' in name or 'INVEST FACIL' in memo or \
                 'APLIC.INVEST' in name or 'APLIC.INVEST' in memo or \
                 'RESGATE INVEST' in name or 'RESGATE INVEST' in memo)
    
    if 'RENTAB.INVEST' in name or 'RENTAB.INVEST' in memo:
        is_invest = False
    
    if is_invest:
        return False
    
    return True


def process_ofx_file(text):
    """
    Processa arquivo OFX completo.
    Retorna dict com contas e suas transações organizadas por mês.
    """
    statements = extract_statement_blocks(text)
    
    account_infos = []
    for stmt, start, end in statements:
        acctid, bankid, accttype, curdef, label = parse_statement_info(stmt)
        blocks = extract_stmttrn_blocks(stmt)
        
        month_map = defaultdict(list)
        month_totals = defaultdict(float)
        
        valid_blocks = []
        for b in blocks:
            if is_valid_transaction(b):
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
    
    return account_infos


def format_transaction_row(block, index):
    """Formata uma transação para exibição."""
    dt_raw = extract_field(block, 'DTPOSTED')
    dt_formatted = f"{dt_raw[6:8]}/{dt_raw[4:6]}/{dt_raw[0:4]}" if len(dt_raw) >= 8 else "---"
    
    amt = parse_amount(extract_field(block, 'TRNAMT'))
    name = extract_field(block, 'NAME')
    memo = extract_field(block, 'MEMO')
    desc = f"{name} {memo}".strip()[:60]
    
    return {
        'index': index,
        'data': dt_formatted,
        'valor': amt,
        'valor_fmt': format_amount(amt),
        'descricao': desc,
        'raw': block
    }


def build_filtered_ofx(original_text, statements, account_info, final_blocks, chosen_key):
    """
    Reconstrói arquivo OFX com apenas os blocos filtrados.
    """
    # Substitui no statement selecionado
    statement_text = account_info['statement']
    pattern = re.compile(r'(<STMTTRN>.*?</STMTTRN>)', re.DOTALL | re.IGNORECASE)
    matches = list(pattern.finditer(statement_text))
    
    if not matches:
        return original_text
    
    start_idx = matches[0].start()
    end_idx = matches[-1].end()
    before = statement_text[:start_idx]
    after = statement_text[end_idx:]
    
    new_inside = '\n'.join(final_blocks)
    if new_inside:
        new_inside = '\n' + new_inside + '\n'
    
    new_statement = before + new_inside + after
    new_statement = update_banktranlist_dates(new_statement, chosen_key)
    
    # Reconstrói documento inteiro
    output_before = original_text[:statements[0][1]]
    output_after = original_text[statements[-1][2]:]
    
    return output_before + new_statement + output_after


def update_banktranlist_dates(bank_content, chosen_key):
    """Atualiza DTSTART e DTEND para o mês selecionado."""
    if chosen_key is None:
        return bank_content
    
    year, month = chosen_key.split('-')
    start_date = f'{year}{month}01'
    last_day = calendar.monthrange(int(year), int(month))[1]
    end_date = f'{year}{month}{last_day:02d}'

    bank_content = re.sub(r'<DTSTART>\s*\d+', f'<DTSTART>{start_date}', bank_content, flags=re.IGNORECASE)
    bank_content = re.sub(r'<DTEND>\s*\d+', f'<DTEND>{end_date}', bank_content, flags=re.IGNORECASE)
    
    return bank_content
