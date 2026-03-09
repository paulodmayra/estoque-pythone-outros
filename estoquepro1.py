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
    col1.metric("Total Produtos", len(df))
    col2.metric("Baixo Estoque", len(df[df['quantidade'] < df['minimo']]))
    col3.metric("Valor Total", f"R$ {df['quantidade']*df['preco'].sum():,.2f}")

# ==================== CADASTRAR ====================
elif menu == "Cadastrar Produto":
    with st.form("cadastro"):
        nome = st.text_input("Nome do Produto")
        codigo = st.text_input("Código")
        qtd = st.number_input("Quantidade Inicial", min_value=0)
        minimo = st.number_input("Estoque Mínimo", min_value=0)
        preco = st.number_input("Preço Unitário", min_value=0.0)
        if st.form_submit_button("Cadastrar"):
            c.execute("INSERT INTO produtos (nome,codigo,quantidade,minimo,preco) VALUES (?,?,?,?,?)",
                      (nome, codigo, qtd, minimo, preco))
            conn.commit()
            st.success("✅ Produto cadastrado!")

# ==================== LISTAR ====================
elif menu == "Listar Produtos":
    df = pd.read_sql_query("SELECT * FROM produtos", conn)
    st.dataframe(df, use_container_width=True)

# ==================== COMPRA ====================
elif menu == "Compra":
    df = pd.read_sql_query("SELECT * FROM produtos", conn)
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

# ==================== VENDA ====================
elif menu == "Venda":
    df = pd.read_sql_query("SELECT * FROM produtos", conn)
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

# ==================== AJUSTE ====================
elif menu == "Ajuste":
    df = pd.read_sql_query("SELECT * FROM produtos", conn)
    produto = st.selectbox("Produto", df['nome'])
    nova_qtd = st.number_input("Nova Quantidade", min_value=0)
    if st.button("Ajustar"):
        idx = df[df['nome'] == produto].index[0]
        c.execute("UPDATE produtos SET quantidade=? WHERE id=?", (nova_qtd, df.loc[idx, 'id']))
        c.execute("INSERT INTO movimentos (data,tipo,produto,quantidade) VALUES (?,?,?,?)",
                  (datetime.now().strftime("%d/%m/%Y %H:%M"), "Ajuste", produto, nova_qtd))
        conn.commit()
        st.success("Estoque ajustado!")

# ==================== ABAIXO DO MÍNIMO ====================
elif menu == "Abaixo do Mínimo":
    df = pd.read_sql_query("SELECT * FROM produtos", conn)
    baixos = df[df['quantidade'] < df['minimo']]
    st.dataframe(baixos)

# ==================== MOVIMENTOS ====================
elif menu == "Movimentos":
    df = pd.read_sql_query("SELECT * FROM movimentos ORDER BY id DESC", conn)
    st.dataframe(df)

# ==================== EXPORTAR ====================
if st.sidebar.button("Exportar CSV"):
    df = pd.read_sql_query("SELECT * FROM produtos", conn)
    csv = df.to_csv(index=False).encode()
    st.download_button("Baixar CSV", csv, "estoque.csv", "text/csv")