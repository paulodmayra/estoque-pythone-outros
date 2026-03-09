from db import connect
import pandas as pd

def listar_produtos():
    with connect() as con:
        df = pd.read_sql_query(
            """
            SELECT p.sku, p.nome, c.nome as categoria, p.unidade, p.estoque_minimo,
                   p.preco_venda, p.custo_medio, p.ativo
            FROM produtos p
            LEFT JOIN categorias c ON c.id = p.categoria_id
            WHERE p.ativo = 1
            ORDER BY p.nome
            """, con)
        return df

def export_csv(df, filename="export.csv"):
    df.to_csv(filename, index=False)
