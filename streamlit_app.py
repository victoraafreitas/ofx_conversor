"""
Aplicação Streamlit para filtro de OFX - Interface limpa e profissional.
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
    initial_sidebar_state="expanded"
)

# Estilos minimalistas
st.markdown("""
    <style>
    .header-title {
        color: #1a1a1a;
        font-size: 2em;
        font-weight: 600;
        margin-bottom: 1em;
    }
    .metrics-row {
        display: flex;
        gap: 20px;
        margin: 20px 0;
    }
    .metric-box {
        flex: 1;
        padding: 20px;
        background: #f8f9fa;
        border-left: 4px solid #1f77b4;
        border-radius: 4px;
    }
    .metric-label {
        font-size: 0.85em;
        color: #666;
        margin-bottom: 8px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-value {
        font-size: 1.8em;
        font-weight: 600;
        color: #1a1a1a;
    }
    .value-positive {
        color: #28a745;
    }
    .value-negative {
        color: #dc3545;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="header-title">📊 Filtro OFX</div>', unsafe_allow_html=True)

# ===================== SIDEBAR: Upload e Seleção ======================
with st.sidebar:
    st.header("⚙️ Configurações")
    
    # Upload
    st.subheader("1️⃣ Arquivo OFX")
    uploaded_file = st.file_uploader("Selecione um arquivo OFX", type=['ofx', 'txt'])
    
    if uploaded_file:
        ofx_content = uploaded_file.read().decode('utf-8', errors='ignore')
        
        # Processa arquivo
        accounts = process_ofx_file(ofx_content)
        
        if not accounts:
            st.error("❌ Nenhuma transação encontrada no arquivo OFX")
            st.stop()
        
        # Seleção de Conta
        st.subheader("2️⃣ Conta")
        account_labels = [acc['label'] for acc in accounts]
        selected_account_idx = st.selectbox(
            "Selecione a conta",
            range(len(accounts)),
            format_func=lambda i: account_labels[i]
        )
        selected_account = accounts[selected_account_idx]
        
        # Seleção de Mês
        st.subheader("3️⃣ Mês")
        months = sorted([k for k in selected_account['month_map'].keys() if k is not None], reverse=True)
        if None in selected_account['month_map']:
            months.append(None)
        
        month_labels = [
            (m.replace('-', '/') if m else 'Sem data')
            for m in months
        ]
        selected_month_idx = st.selectbox(
            "Selecione o mês",
            range(len(months)),
            format_func=lambda i: month_labels[i]
        )
        selected_month = months[selected_month_idx]
        
        # Obter transações do mês
        month_blocks = selected_account['month_map'][selected_month]
        st.success(f"✅ {len(month_blocks)} transações carregadas")
    else:
        st.info("👈 Faça o upload de um arquivo OFX para começar")
        st.stop()

# ===================== MAIN CONTENT ======================


# ===================== RESUMO FINANCEIRO ======================
# Formata transações
transactions = [format_transaction_row(b, i+1) for i, b in enumerate(month_blocks)]

# Sliders para intervalo de linhas
st.subheader("Período de Extração")
col1, col2 = st.columns(2)

with col1:
    linha_inicial = st.number_input(
        "ID Inicial",
        min_value=1,
        max_value=len(transactions),
        value=1,
        key="linha_inicial"
    )

with col2:
    linha_final = st.number_input(
        "ID Final",
        min_value=1,
        max_value=len(transactions),
        value=len(transactions),
        key="linha_final"
    )

# Sliders para ajuste fino
col1, col2 = st.columns(2)

with col1:
    linha_inicial = st.slider(
        "Arraste para ajustar inicial",
        min_value=1,
        max_value=len(transactions),
        value=int(linha_inicial),
        key="slider_inicial"
    )

with col2:
    linha_final = st.slider(
        "Arraste para ajustar final",
        min_value=1,
        max_value=len(transactions),
        value=int(linha_final),
        key="slider_final"
    )

# Valida intervalo
if linha_inicial > linha_final:
    linha_inicial, linha_final = linha_final, linha_inicial

# Filtra transações pelo intervalo
idx_inicio = linha_inicial - 1
idx_final = linha_final
transactions_filtradas = transactions[idx_inicio:idx_final]
final_blocks = [t['raw'] for t in transactions_filtradas]

# Calcula resumo
total_entrada = sum(t['valor'] for t in transactions_filtradas if t['valor'] >= 0)
total_saida = sum(t['valor'] for t in transactions_filtradas if t['valor'] < 0)
saldo_liquido = total_entrada + total_saida

# Exibe métricas em linha
st.markdown(f"""
<div class="metrics-row">
    <div class="metric-box">
        <div class="metric-label">Entradas</div>
        <div class="metric-value value-positive">{format_amount(total_entrada)}</div>
    </div>
    <div class="metric-box">
        <div class="metric-label">Saídas</div>
        <div class="metric-value value-negative">{format_amount(total_saida)}</div>
    </div>
    <div class="metric-box">
        <div class="metric-label">Saldo Líquido</div>
        <div class="metric-value" style="color: {'#28a745' if saldo_liquido >= 0 else '#dc3545'};">{format_amount(saldo_liquido)}</div>
    </div>
    <div class="metric-box">
        <div class="metric-label">Transações</div>
        <div class="metric-value">{len(transactions_filtradas)}</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ===================== TABELA DE TRANSAÇÕES ======================
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
st.markdown("---")
st.subheader("💾 Exportar Arquivo")

col1, col2 = st.columns([3, 1])

with col1:
    nome_saida = st.text_input(
        "Nome do arquivo (sem extensão)",
        value=f"filtrado_{selected_account['acctid']}_{selected_month.replace('-', '')}",
        help="O arquivo será salvo com extensão .ofx"
    )

with col2:
    st.write("")  # Espaço
    st.write("")
    btn_download = st.button("⬇️ Baixar", use_container_width=True, type="primary")

if btn_download:
    if len(final_blocks) == 0:
        st.error("❌ Nenhuma transação selecionada")
    else:
        try:
            # Reconstrói OFX com transações filtradas
            statements = extract_statement_blocks(ofx_content)
            new_ofx_content = build_filtered_ofx(
                ofx_content,
                statements,
                selected_account,
                final_blocks,
                selected_month
            )
            
            # Prepara download
            ofx_bytes = new_ofx_content.encode('utf-8')
            
            st.download_button(
                label="✅ Clique aqui para baixar",
                data=ofx_bytes,
                file_name=f"{nome_saida}.ofx",
                mime="text/plain",
                use_container_width=True
            )
            
            st.success(f"✨ Arquivo gerado com sucesso! {len(final_blocks)} transações")
            
        except Exception as e:
            st.error(f"❌ Erro ao processar arquivo: {str(e)}")
