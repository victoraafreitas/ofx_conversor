"""
Aplicação Streamlit para filtro de OFX - Interface moderna e intuitiva.
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
    page_title="OFX Filter Pro",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos
st.markdown("""
    <style>
    .header-title {
        text-align: center;
        color: #1f77b4;
        font-size: 2.5em;
        font-weight: bold;
        margin-bottom: 0.5em;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .metric-value {
        font-size: 1.8em;
        font-weight: bold;
        margin: 10px 0;
    }
    .metric-label {
        font-size: 0.9em;
        opacity: 0.9;
    }
    .success-box {
        background: #d4edda;
        border: 1px solid #c3e6cb;
        padding: 15px;
        border-radius: 5px;
        color: #155724;
    }
    .warning-box {
        background: #fff3cd;
        border: 1px solid #ffeaa7;
        padding: 15px;
        border-radius: 5px;
        color: #856404;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="header-title">📊 OFX Filter Pro</div>', unsafe_allow_html=True)
st.markdown("---")

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

# ===================== MAIN CONTENT ======================
else:
    st.info("👈 Faça o upload de um arquivo OFX para começar")
    st.stop()


# ===================== SEÇÃO DE VISUALIZAÇÃO ======================
st.header("📋 Transações do Período")

# Formata transações
transactions = [format_transaction_row(b, i+1) for i, b in enumerate(month_blocks)]
df_display = pd.DataFrame([
    {
        '#': t['index'],
        'Data': t['data'],
        'Valor': t['valor_fmt'],
        'Descrição': t['descricao'],
    }
    for t in transactions
])

# Sliders para intervalo
col1, col2 = st.columns(2)

with col1:
    st.subheader("4️⃣ Intervalo de Linhas")
    linha_inicial = st.slider(
        "Linha Inicial",
        min_value=1,
        max_value=len(transactions),
        value=1,
        key="linha_inicial"
    )

with col2:
    linha_final = st.slider(
        "Linha Final",
        min_value=max(1, linha_inicial),
        max_value=len(transactions),
        value=len(transactions),
        key="linha_final"
    )

# Valida intervalo
if linha_inicial > linha_final:
    linha_inicial = linha_final

# Filtra transações pelo intervalo
idx_inicio = linha_inicial - 1
idx_final = linha_final
transactions_filtradas = transactions[idx_inicio:idx_final]
final_blocks = [t['raw'] for t in transactions_filtradas]

# Exibe tabela de transações
st.dataframe(
    df_display.iloc[idx_inicio:idx_final].reset_index(drop=True),
    use_container_width=True,
    hide_index=True
)

# ===================== RESUMO FINANCEIRO ======================
st.markdown("---")

total_entrada = sum(t['valor'] for t in transactions_filtradas if t['valor'] >= 0)
total_saida = sum(t['valor'] for t in transactions_filtradas if t['valor'] < 0)
saldo_liquido = total_entrada + total_saida

# Cards de resumo
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Entradas</div>
        <div class="metric-value" style="color: #90EE90;">{format_amount(total_entrada)}</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Saídas</div>
        <div class="metric-value" style="color: #FFB6C6;">{format_amount(total_saida)}</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    cor_saldo = "#90EE90" if saldo_liquido >= 0 else "#FFB6C6"
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Saldo Líquido</div>
        <div class="metric-value" style="color: {cor_saldo};">{format_amount(saldo_liquido)}</div>
    </div>
    """, unsafe_allow_html=True)

# Info sobre seleção
st.markdown(f"""
<div class="success-box">
📊 <strong>Resumo da Seleção</strong><br>
• Linhas selecionadas: <strong>{len(transactions_filtradas)}</strong> de {len(transactions)}<br>
• Período: <strong>{selected_month.replace('-', '/')}</strong><br>
• Conta: <strong>{selected_account['label']}</strong>
</div>
""", unsafe_allow_html=True)

# ===================== DOWNLOAD ======================
st.markdown("---")
st.subheader("💾 Exportar Arquivo Filtrado")

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
    btn_download = st.button("⬇️ Baixar OFX Filtrado", use_container_width=True, type="primary")

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
            
            st.markdown(f"""
            <div class="success-box">
            ✨ <strong>Arquivo gerado com sucesso!</strong><br>
            • Transações: {len(final_blocks)}<br>
            • Total entradas: {format_amount(total_entrada)}<br>
            • Total saídas: {format_amount(total_saida)}<br>
            • Saldo: {format_amount(saldo_liquido)}
            </div>
            """, unsafe_allow_html=True)
            
        except Exception as e:
            st.error(f"❌ Erro ao processar arquivo: {str(e)}")

# ===================== RODAPÉ ======================
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #888; font-size: 0.9em; margin-top: 2em;">
    OFX Filter Pro v1.0 | Desenvolvido para Antigravity
    </div>
    """,
    unsafe_allow_html=True
)
