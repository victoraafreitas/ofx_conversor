"""
Aplicação Streamlit para filtro de OFX.
Execute com: streamlit run streamlit_app.py
"""

import streamlit as st
import pandas as pd
import os
from io import BytesIO
import re
from datetime import datetime
import locale

from ofx_utils import (
    extract_field, parse_amount, format_amount,
    process_ofx_file, format_transaction_row,
    build_filtered_ofx, extract_statement_blocks
)

st.set_page_config(
    page_title="Filtro OFX",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS para métricas com background
st.markdown("""
    <style>
    .metric-entrada {
        background-color: #e8f5e9;
        padding: 20px;
        border-radius: 8px;
        text-align: center;
    }
    .metric-saida {
        background-color: #ffebee;
        padding: 20px;
        border-radius: 8px;
        text-align: center;
    }
    .metric-neutro {
        background-color: #f5f5f5;
        padding: 20px;
        border-radius: 8px;
        text-align: center;
    }
    .metric-label {
        font-size: 0.85em;
        color: #666;
        margin-bottom: 8px;
    }
    .metric-valor {
        font-size: 1.5em;
        font-weight: 600;
        color: #1a1a1a;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📊 Filtro OFX")

# ===================== UPLOAD ======================
uploaded_file = st.file_uploader("Selecione o arquivo OFX", type=['ofx', 'txt'])

if not uploaded_file:
    st.info("👆 Faça o upload de um arquivo OFX para começar")
    st.stop()

ofx_content = uploaded_file.read().decode('utf-8', errors='ignore')

# Processa arquivo
accounts = process_ofx_file(ofx_content)

if not accounts:
    st.error("❌ Nenhuma transação encontrada no arquivo OFX")
    st.stop()

# ===================== SELEÇÃO DE CONTA ======================
account_labels = [acc['label'] for acc in accounts]
selected_account_idx = st.selectbox(
    "Conta",
    range(len(accounts)),
    format_func=lambda i: account_labels[i],
    key="select_conta"
)
selected_account = accounts[selected_account_idx]

# ===================== SELEÇÃO DE MÊS ======================
months = sorted([k for k in selected_account['month_map'].keys() if k is not None], reverse=True)
if None in selected_account['month_map']:
    months.append(None)

month_labels = [
    (m.replace('-', '/') if m else 'Sem data')
    for m in months
]
selected_month_idx = st.selectbox(
    "Mês",
    range(len(months)),
    format_func=lambda i: month_labels[i],
    key="select_mes"
)
selected_month = months[selected_month_idx]

# Obter transações do mês
month_blocks = selected_account['month_map'][selected_month]

# ===================== PERÍODO DE EXTRAÇÃO ======================
st.divider()

# Inicializa session state
if 'linha_inicial' not in st.session_state:
    st.session_state.linha_inicial = 1
if 'linha_final' not in st.session_state:
    st.session_state.linha_final = len(month_blocks)

# Funções de validação em tempo real
def validar_inicial():
    valor = st.session_state.input_inicial
    # Filtra apenas dígitos
    valor_limpo = ''.join(filter(str.isdigit, valor))
    # Se vazio, usa padrão
    if not valor_limpo:
        st.session_state.input_inicial = str(st.session_state.linha_inicial)
    else:
        # Limita ao intervalo válido
        valor_int = int(valor_limpo)
        valor_int = max(1, min(valor_int, len(month_blocks)))
        st.session_state.input_inicial = str(valor_int)
        st.session_state.linha_inicial = valor_int

def validar_final():
    valor = st.session_state.input_final
    # Filtra apenas dígitos
    valor_limpo = ''.join(filter(str.isdigit, valor))
    # Se vazio, usa padrão
    if not valor_limpo:
        st.session_state.input_final = str(st.session_state.linha_final)
    else:
        # Limita ao intervalo válido
        valor_int = int(valor_limpo)
        valor_int = max(1, min(valor_int, len(month_blocks)))
        st.session_state.input_final = str(valor_int)
        st.session_state.linha_final = valor_int

st.subheader("Período de Extração")

col1, col2 = st.columns(2)

with col1:
    st.text_input(
        "ID Inicial",
        value=str(st.session_state.linha_inicial),
        on_change=validar_inicial,
        key="input_inicial"
    )

with col2:
    st.text_input(
        "ID Final",
        value=str(st.session_state.linha_final),
        on_change=validar_final,
        key="input_final"
    )

# Valida intervalo de IDs
if st.session_state.linha_inicial > st.session_state.linha_final:
    st.session_state.linha_inicial, st.session_state.linha_final = st.session_state.linha_final, st.session_state.linha_inicial

# Usa valores do session_state
linha_inicial = st.session_state.linha_inicial
linha_final = st.session_state.linha_final

# Filtra transações
idx_inicio = linha_inicial - 1
idx_final = linha_final
transactions = [format_transaction_row(b, i+1) for i, b in enumerate(month_blocks)]
transactions_filtradas = transactions[idx_inicio:idx_final]

# Filtro por Data - Calcula intervalo do OFX
st.subheader("Filtro por Data (Opcional)")

# Extrai datas mínima e máxima das transações
datas_transacoes = []
for t in transactions_filtradas:
    try:
        dia, mes, ano = map(int, t['data'].split('/'))
        data_obj = datetime(ano, mes, dia).date()
        datas_transacoes.append(data_obj)
    except:
        pass

if datas_transacoes:
    data_min = min(datas_transacoes)
    data_max = max(datas_transacoes)
else:
    data_min = None
    data_max = None

col1, col2 = st.columns(2)

with col1:
    data_inicial = st.date_input(
        "Data Inicial",
        value=None,
        min_value=data_min,
        max_value=data_max,
        format="DD/MM/YYYY",
        key="data_inicial"
    )

with col2:
    data_final = st.date_input(
        "Data Final",
        value=None,
        min_value=data_min,
        max_value=data_max,
        format="DD/MM/YYYY",
        key="data_final"
    )

# Aplica filtro de data se selecionadas
if data_inicial or data_final:
    transactions_por_data = []
    for t in transactions_filtradas:
        # Converte data da transação (formato DD/MM/YYYY) para objeto date
        try:
            dia, mes, ano = map(int, t['data'].split('/'))
            data_tx = pd.to_datetime(f"{ano}-{mes:02d}-{dia:02d}").date()
            
            # Verifica se está dentro do intervalo
            dentro = True
            if data_inicial and data_tx < data_inicial:
                dentro = False
            if data_final and data_tx > data_final:
                dentro = False
            
            if dentro:
                transactions_por_data.append(t)
        except:
            pass
    
    transactions_filtradas = transactions_por_data

final_blocks = [t['raw'] for t in transactions_filtradas]

# ===================== RESUMO FINANCEIRO ======================
st.divider()

total_entrada = sum(t['valor'] for t in transactions_filtradas if t['valor'] >= 0)
total_saida = sum(t['valor'] for t in transactions_filtradas if t['valor'] < 0)
saldo_liquido = total_entrada + total_saida
num_transacoes = len(transactions_filtradas)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="metric-entrada">
        <div class="metric-label">Entradas</div>
        <div class="metric-valor">{format_amount(total_entrada)}</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-saida">
        <div class="metric-label">Saídas</div>
        <div class="metric-valor">{format_amount(total_saida)}</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-neutro">
        <div class="metric-label">Saldo Líquido</div>
        <div class="metric-valor">{format_amount(saldo_liquido)}</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="metric-neutro">
        <div class="metric-label">Transações</div>
        <div class="metric-valor">{num_transacoes}</div>
    </div>
    """, unsafe_allow_html=True)

# ===================== TABELA DE TRANSAÇÕES ======================
st.divider()
st.subheader("Movimentações")

df_display = pd.DataFrame([
    {
        'ID': t['index'],
        'Data': t['data'],
        'Valor': t['valor_fmt'],
        'Descrição': t['descricao'],
    }
    for t in transactions_filtradas
])

st.dataframe(
    df_display,
    use_container_width=True,
    hide_index=True,
    height=400
)

# ===================== DOWNLOAD ======================
st.divider()
st.subheader("Exportar")

nome_saida = st.text_input(
    "Nome do arquivo (sem extensão)",
    value=f"filtrado_{selected_account['acctid']}_{selected_month.replace('-', '')}",
    key="nome_arquivo"
)

if st.button("Baixar OFX", type="primary", use_container_width=True, key="btn_download"):
    if len(final_blocks) == 0:
        st.error("Nenhuma transação selecionada")
    else:
        try:
            statements = extract_statement_blocks(ofx_content)
            new_ofx_content = build_filtered_ofx(
                ofx_content,
                statements,
                selected_account,
                final_blocks,
                selected_month
            )
            
            ofx_bytes = new_ofx_content.encode('utf-8')
            
            st.download_button(
                label="Clique aqui para baixar",
                data=ofx_bytes,
                file_name=f"{nome_saida}.ofx",
                mime="text/plain",
                use_container_width=True,
                key="download_ofx"
            )
            
            st.success(f"Arquivo gerado com {len(final_blocks)} transações")
            
        except Exception as e:
            st.error(f"Erro: {str(e)}")
