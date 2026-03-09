import streamlit as st
from db import init_db
from reports import listar_produtos
from services import estoque_atual, recomputar_custo_medio

def main():
    st.set_page_config(page_title="EstoquePro", layout="wide")
    init_db()

    menu = ["Dashboard", "Cadastros", "Movimentações", "Relatórios", "Auditoria"]
    choice = st.sidebar.radio("Navegação", menu)

    if choice == "Dashboard":
        st.header("Dashboard & Alertas")
        df = listar_produtos()
        st.dataframe(df)

        # Exemplo: alertas
        alertas = df[df["estoque_minimo"] > 0]  # filtro simples
        st.write(f"Produtos com estoque mínimo definido: {len(alertas)}")

    elif choice == "Cadastros":
        st.header("Cadastros")
        st.write("Aqui você implementa formulários para produtos, categorias, fornecedores e clientes.")

    elif choice == "Movimentações":
        st.header("Movimentações")
        st.write("Aqui você implementa compra, venda e ajustes com ledger.")

    elif choice == "Relatórios":
        st.header("Relatórios")
        st.write("Aqui você implementa relatórios e exportação CSV.")

    elif choice == "Auditoria":
        st.header("Auditoria")
        st.write("Aqui você mostra logs de auditoria.")

if __name__ == "__main__":
    main()
