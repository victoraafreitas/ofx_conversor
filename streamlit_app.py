"""
Aplicação Streamlit para filtro de OFX.
Execute com: streamlit run streamlit_app.py
"""

import streamlit as st
import pandas as pd
import os
from io import BytesIO
import re

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
    format_func=lambda i: account_labels[i]
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
    format_func=lambda i: month_labels[i]
)
selected_month = months[selected_month_idx]

# Obter transações do mês
month_blocks = selected_account['month_map'][selected_month]

# ===================== PERÍODO DE EXTRAÇÃO ======================
st.divider()

# Inicializa session state para sincronização
if 'linha_inicial' not in st.session_state:
    st.session_state.linha_inicial = 1
if 'linha_final' not in st.session_state:
    st.session_state.linha_final = len(month_blocks)

st.subheader("Período de Extração")

col1, col2 = st.columns(2)

with col1:
    entrada_inicial = st.number_input(
        "ID Inicial",
        min_value=1,
        max_value=len(month_blocks),
        value=st.session_state.linha_inicial,
        key="input_inicial"
    )
    st.session_state.linha_inicial = entrada_inicial

with col2:
    entrada_final = st.number_input(
        "ID Final",
        min_value=1,
        max_value=len(month_blocks),
        value=st.session_state.linha_final,
        key="input_final"
    )
    st.session_state.linha_final = entrada_final

col1, col2 = st.columns(2)

with col1:
    slider_inicial = st.slider(
        "Arrastar inicial",
        min_value=1,
        max_value=len(month_blocks),
        value=st.session_state.linha_inicial,
        key="slider_inicial",
        label_visibility="collapsed"
    )
    st.session_state.linha_inicial = slider_inicial

with col2:
    slider_final = st.slider(
        "Arrastar final",
        min_value=1,
        max_value=len(month_blocks),
        value=st.session_state.linha_final,
        key="slider_final",
        label_visibility="collapsed"
    )
    st.session_state.linha_final = slider_final

# Valida intervalo
linha_inicial = st.session_state.linha_inicial
linha_final = st.session_state.linha_final

if linha_inicial > linha_final:
    linha_inicial, linha_final = linha_final, linha_inicial
    st.session_state.linha_inicial = linha_inicial
    st.session_state.linha_final = linha_final

# Filtra transações
idx_inicio = linha_inicial - 1
idx_final = linha_final
transactions = [format_transaction_row(b, i+1) for i, b in enumerate(month_blocks)]
transactions_filtradas = transactions[idx_inicio:idx_final]
final_blocks = [t['raw'] for t in transactions_filtradas]

# ===================== RESUMO FINANCEIRO ======================
st.divider()

total_entrada = sum(t['valor'] for t in transactions_filtradas if t['valor'] >= 0)
total_saida = sum(t['valor'] for t in transactions_filtradas if t['valor'] < 0)
saldo_liquido = total_entrada + total_saida

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Entradas", format_amount(total_entrada))

with col2:
    st.metric("Saídas", format_amount(total_saida))

with col3:
    st.metric("Saldo", format_amount(saldo_liquido))

with col4:
    st.metric("Transações", len(transactions_filtradas))

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
)

if st.button("Baixar OFX", type="primary", use_container_width=True):
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
                use_container_width=True
            )
            
            st.success(f"Arquivo gerado com {len(final_blocks)} transações")
            
        except Exception as e:
            st.error(f"Erro: {str(e)}")
