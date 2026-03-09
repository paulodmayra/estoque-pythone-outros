import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

st.set_page_config(page_title="ESTOQUE PRO", layout="wide")
st.title("📦 ESTOQUE PRO - Controle Completo")

# Banco de dados
conn = sqlite3.connect('estoque.db')
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS produtos 
             (id INTEGER PRIMARY KEY, nome TEXT, codigo TEXT, quantidade INTEGER, minimo INTEGER, preco REAL)''')
c.execute('''CREATE TABLE IF NOT EXISTS movimentos 
             (id INTEGER PRIMARY KEY, data TEXT, tipo TEXT, produto TEXT, quantidade INTEGER)''')
conn.commit()

# ==================== MENU ====================
menu = st.sidebar.selectbox("Escolha uma opção", [
    "Dashboard", "Cadastrar Produto", "Listar Produtos", 
    "Compra", "Venda", "Ajuste", "Abaixo do Mínimo", "Movimentos"
])

# ==================== DASHBOARD ====================
if menu == "Dashboard":
    df = pd.read_sql_query("SELECT * FROM produtos", conn)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Produtos", len(df))
    
    baixos = len(df[df['quantidade'] < df['minimo']]) if not df.empty else 0
    col2.metric("Baixo Estoque", baixos)
    
    # CORREÇÃO AQUI:
    valor_total = (df['quantidade'] * df['preco']).sum() if not df.empty else 0
    col3.metric("Valor Total em Estoque", f"R$ {valor_total:,.2f}")

# ==================== CADASTRAR ====================

elif menu == "Cadastrar Produto":
    st.header("Cadastrar Novo Produto")
    
    with st.form(key="cadastro_form", clear_on_submit=True):   # ← chave importante
        nome = st.text_input("Nome do Produto", key="nome")
        codigo = st.text_input("Código", key="codigo")
        qtd = st.number_input("Quantidade Inicial", min_value=0, value=0, key="qtd")
        minimo = st.number_input("Estoque Mínimo", min_value=0, value=0, key="minimo")
        preco = st.number_input("Preço Unitário", min_value=0.0, value=0.0, format="%.2f", key="preco")
        
        if st.form_submit_button("Cadastrar Produto"):
            if nome.strip() and codigo.strip():
                c.execute("INSERT INTO produtos (nome, codigo, quantidade, minimo, preco) VALUES (?, ?, ?, ?, ?)",
                          (nome, codigo, qtd, minimo, preco))
                conn.commit()
                st.success(f"✅ Produto '{nome}' cadastrado com sucesso!")
                st.rerun()          # ← Isso limpa todos os campos
            else:
                st.error("Nome e Código são obrigatórios!")



# ==================== LISTAR ====================
elif menu == "Listar Produtos":
    df = pd.read_sql_query("SELECT * FROM produtos", conn)
    st.dataframe(df, use_container_width=True)

# ==================== COMPRA ====================
elif menu == "Compra":
    df = pd.read_sql_query("SELECT * FROM produtos", conn)
    if not df.empty:
        produto = st.selectbox("Produto", df['nome'])
        qtd = st.number_input("Quantidade", min_value=1)
        if st.button("Confirmar Compra"):
            idx = df[df['nome'] == produto].index[0]
            nova_qtd = df.loc[idx, 'quantidade'] + qtd
            c.execute("UPDATE produtos SET quantidade=? WHERE id=?", (nova_qtd, df.loc[idx, 'id']))
            c.execute("INSERT INTO movimentos (data,tipo,produto,quantidade) VALUES (?,?,?,?)",
                      (datetime.now().strftime("%d/%m/%Y %H:%M"), "Compra", produto, qtd))
            conn.commit()
            st.success("Compra registrada!")
    else:
        st.warning("Cadastre produtos primeiro!")

# ==================== VENDA ====================
elif menu == "Venda":
    df = pd.read_sql_query("SELECT * FROM produtos", conn)
    if not df.empty:
        produto = st.selectbox("Produto", df['nome'])
        qtd = st.number_input("Quantidade", min_value=1)
        if st.button("Confirmar Venda"):
            idx = df[df['nome'] == produto].index[0]
            if df.loc[idx, 'quantidade'] >= qtd:
                nova_qtd = df.loc[idx, 'quantidade'] - qtd
                c.execute("UPDATE produtos SET quantidade=? WHERE id=?", (nova_qtd, df.loc[idx, 'id']))
                c.execute("INSERT INTO movimentos (data,tipo,produto,quantidade) VALUES (?,?,?,?)",
                          (datetime.now().strftime("%d/%m/%Y %H:%M"), "Venda", produto, -qtd))
                conn.commit()
                st.success("Venda registrada!")
            else:
                st.error("Estoque insuficiente!")
    else:
        st.warning("Cadastre produtos primeiro!")

# ==================== AJUSTE ====================
elif menu == "Ajuste":
    df = pd.read_sql_query("SELECT * FROM produtos", conn)
    if not df.empty:
        produto = st.selectbox("Produto", df['nome'])
        nova_qtd = st.number_input("Nova Quantidade", min_value=0)
        if st.button("Ajustar"):
            idx = df[df['nome'] == produto].index[0]
            c.execute("UPDATE produtos SET quantidade=? WHERE id=?", (nova_qtd, df.loc[idx, 'id']))
            c.execute("INSERT INTO movimentos (data,tipo,produto,quantidade) VALUES (?,?,?,?)",
                      (datetime.now().strftime("%d/%m/%Y %H:%M"), "Ajuste", produto, nova_qtd))
            conn.commit()
            st.success("Estoque ajustado!")
    else:
        st.warning("Cadastre produtos primeiro!")

# ==================== ABAIXO DO MÍNIMO ====================
elif menu == "Abaixo do Mínimo":
    df = pd.read_sql_query("SELECT * FROM produtos", conn)
    baixos = df[df['quantidade'] < df['minimo']] if not df.empty else pd.DataFrame()
    st.dataframe(baixos, use_container_width=True)

# ==================== MOVIMENTOS ====================
elif menu == "Movimentos":
    df_mov = pd.read_sql_query("SELECT * FROM movimentos ORDER BY id DESC", conn)
    st.dataframe(df_mov, use_container_width=True)

# ==================== EXPORTAR ====================
if st.sidebar.button("Exportar CSV"):
    df = pd.read_sql_query("SELECT * FROM produtos", conn)
    csv = df.to_csv(index=False).encode()
    st.download_button("Baixar CSV", csv, "estoque.csv", "text/csv")