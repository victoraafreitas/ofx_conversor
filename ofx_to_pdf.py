"""
Converte um arquivo OFX para PDF sem alterar os dados originais.
Uso:
  python ofx_to_pdf.py caminho/para/seu.arquivo.ofx

No Colab, faça upload do arquivo quando solicitado.
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
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak
    from reportlab.lib.units import mm
except ImportError as e:
    raise ImportError(
        'reportlab não encontrado. Instale com: pip install reportlab'
    ) from e


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
    dtstart = extract_field(statement, 'DTSTART')
    dtend = extract_field(statement, 'DTEND')
    return {
        'ACCTID': acctid,
        'BANKID': bankid,
        'ACCTTYPE': accttype,
        'CURDEF': curdef,
        'DTSTART': dtstart,
        'DTEND': dtend,
    }


def extract_stmttrn_blocks(statement):
    pattern = re.compile(r'<STMTTRN>(.*?)</STMTTRN>', re.DOTALL | re.IGNORECASE)
    return ['<STMTTRN>' + m + '</STMTTRN>' for m in pattern.findall(statement)]


def parse_transaction(block):
    return {
        'TRNTYPE': extract_field(block, 'TRNTYPE'),
        'DTPOSTED': extract_field(block, 'DTPOSTED'),
        'TRNAMT': extract_field(block, 'TRNAMT'),
        'FITID': extract_field(block, 'FITID'),
        'CHECKNUM': extract_field(block, 'CHECKNUM'),
        'NAME': extract_field(block, 'NAME'),
        'MEMO': extract_field(block, 'MEMO'),
    }


def format_date(dtposted):
    if not dtposted:
        return ''
    dt = dtposted.strip()
    if len(dt) >= 8 and dt[:8].isdigit():
        return f'{dt[0:4]}-{dt[4:6]}-{dt[6:8]}'
    return dt


def create_paragraph(text, style):
    safe_text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return Paragraph(safe_text, style)


def build_pdf(output_path, file_name, statements):
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading2']
    normal_style = styles['BodyText']
    normal_style.leading = 12

    doc = SimpleDocTemplate(output_path, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm)
    elements = []

    elements.append(create_paragraph(f'OFX → PDF: {file_name}', title_style))
    elements.append(Spacer(1, 8))

    for si, statement in enumerate(statements, start=1):
        info = parse_statement_info(statement)
        header_text = f'Conta {si}: {info.get("ACCTID") or "sem conta"}'
        if info.get('ACCTTYPE'):
            header_text += f' ({info["ACCTTYPE"]})'
        if info.get('BANKID'):
            header_text += f' - Banco {info["BANKID"]}'
        if info.get('CURDEF'):
            header_text += f' - Moeda {info["CURDEF"]}'
        elements.append(create_paragraph(header_text, heading_style))
        metadata = []
        for key in ['DTSTART', 'DTEND', 'ACCTID', 'BANKID', 'ACCTTYPE', 'CURDEF']:
            value = info.get(key)
            if value:
                metadata.append(f'<b>{key}</b>: {value}')
        if metadata:
            elements.append(create_paragraph(' | '.join(metadata), normal_style))
            elements.append(Spacer(1, 6))

        tx_blocks = extract_stmttrn_blocks(statement)
        transactions = [parse_transaction(block) for block in tx_blocks]
        if not transactions:
            elements.append(create_paragraph('Nenhuma transação encontrada nesta conta.', normal_style))
            elements.append(PageBreak())
            continue

        table_data = [['#', 'Data', 'Tipo', 'Valor', 'FITID', 'CHECKNUM', 'Nome', 'Memo']]
        for idx, tx in enumerate(transactions, start=1):
            row = [
                str(idx),
                format_date(tx['DTPOSTED']),
                tx['TRNTYPE'],
                tx['TRNAMT'],
                tx['FITID'],
                tx['CHECKNUM'],
                tx['NAME'],
                tx['MEMO'],
            ]
            table_data.append([create_paragraph(str(cell or ''), normal_style) for cell in row])

        col_widths = [12 * mm, 22 * mm, 18 * mm, 22 * mm, 22 * mm, 18 * mm, 40 * mm, 30 * mm]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.25, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (3, 1), (3, -1), 'RIGHT'),
            ('ALIGN', (1, 1), (2, -1), 'CENTER'),
            ('WORDWRAP', (0, 0), (-1, -1), 'ON'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(table)
        if si < len(statements):
            elements.append(PageBreak())

    doc.build(elements)


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
    if not statements:
        raise SystemExit('Nenhuma declaração OFX encontrada.')

    out_name = os.path.splitext(name)[0] + '.pdf'
    output_path = os.path.join(os.getcwd(), out_name)
    build_pdf(output_path, name, statements)
    print(f'PDF gerado: {output_path}')

    if _IN_COLAB:
        try:
            files.download(output_path)
        except Exception:
            print('Falha ao iniciar download automático. Baixe manualmente do diretório do runtime.')


if __name__ == '__main__':
    main()
