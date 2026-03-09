from db import connect, now_iso
from decimal import Decimal

def estoque_atual(produto_id: int) -> Decimal:
    with connect() as con:
        row = con.execute(
            "SELECT COALESCE(SUM(quantidade), 0) AS saldo FROM movimentos WHERE produto_id = ?",
            (produto_id,)
        ).fetchone()
        return Decimal(row["saldo"] or 0)

def recomputar_custo_medio(produto_id: int) -> None:
    with connect() as con:
        rows = con.execute(
            """
            SELECT quantidade, custo_unitario
            FROM movimentos
            WHERE produto_id = ?
              AND quantidade > 0
              AND custo_unitario IS NOT NULL
            """,
            (produto_id,),
        ).fetchall()

        total_q = Decimal("0")
        total_v = Decimal("0")
        for r in rows:
            q = Decimal(r["quantidade"])
            c = Decimal(r["custo_unitario"])
            total_q += q
            total_v += q * c

        custo_medio = (total_v / total_q) if total_q > 0 else Decimal("0")
        con.execute(
            "UPDATE produtos SET custo_medio = ?, atualizado_em = ? WHERE id = ?",
            (str(custo_medio), now_iso(), produto_id),
        )
        con.commit()
