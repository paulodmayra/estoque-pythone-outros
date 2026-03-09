#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EstoquePro — Controle de Estoque (CLI) com SQLite
- Cadastro: produtos, categorias, fornecedores, clientes
- Movimentações: compra (entrada), venda (saída), ajuste (+/-)
- Estoque atual por somatório do ledger (tabela movimentos)
- Alertas: abaixo do estoque mínimo
- Relatórios: saldo, valorização (custo médio simples), movimentação por período
- Exportação CSV
- Auditoria básica (log)

Requisitos: Python 3.10+
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sqlite3
import sys
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Iterable, Any


DB_DEFAULT = "estoquepro.db"


# ---------------------------
# Utilidades
# ---------------------------

def money(x: Decimal) -> str:
    q = x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"R$ {q}".replace(".", ",")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def parse_decimal(s: str) -> Decimal:
    # aceita "10,50" e "10.50"
    s = s.strip().replace(".", "").replace(",", ".") if "," in s else s.strip()
    return Decimal(s)


def today_iso_date() -> str:
    return dt.date.today().isoformat()


@dataclass(frozen=True)
class DB:
    path: str = DB_DEFAULT

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON;")
        return con


# ---------------------------
# Schema e migração
# ---------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS categorias (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS fornecedores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL UNIQUE,
  documento TEXT,
  telefone TEXT,
  email TEXT
);

CREATE TABLE IF NOT EXISTS clientes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL UNIQUE,
  documento TEXT,
  telefone TEXT,
  email TEXT
);

CREATE TABLE IF NOT EXISTS produtos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sku TEXT NOT NULL UNIQUE,
  nome TEXT NOT NULL,
  categoria_id INTEGER,
  unidade TEXT NOT NULL DEFAULT 'UN',
  ativo INTEGER NOT NULL DEFAULT 1,
  estoque_minimo NUMERIC NOT NULL DEFAULT 0,
  preco_venda NUMERIC NOT NULL DEFAULT 0,
  custo_medio NUMERIC NOT NULL DEFAULT 0,
  criado_em TEXT NOT NULL,
  atualizado_em TEXT NOT NULL,
  FOREIGN KEY (categoria_id) REFERENCES categorias(id)
);

-- Ledger de movimentações: entrada (+), saída (-), ajuste (+/-)
CREATE TABLE IF NOT EXISTS movimentos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  produto_id INTEGER NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('ENTRADA','SAIDA','AJUSTE')),
  quantidade NUMERIC NOT NULL,
  custo_unitario NUMERIC,         -- relevante para entradas/ajustes+
  preco_unitario NUMERIC,         -- relevante para saídas
  ref_tipo TEXT,                  -- COMPRA, VENDA, INVENTARIO, AVARIA etc.
  ref_id INTEGER,                 -- id de compras/vendas (opcional)
  observacao TEXT,
  criado_em TEXT NOT NULL,
  FOREIGN KEY (produto_id) REFERENCES produtos(id)
);

CREATE TABLE IF NOT EXISTS compras (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fornecedor_id INTEGER,
  data TEXT NOT NULL,
  total NUMERIC NOT NULL DEFAULT 0,
  criado_em TEXT NOT NULL,
  FOREIGN KEY (fornecedor_id) REFERENCES fornecedores(id)
);

CREATE TABLE IF NOT EXISTS compras_itens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  compra_id INTEGER NOT NULL,
  produto_id INTEGER NOT NULL,
  quantidade NUMERIC NOT NULL,
  custo_unitario NUMERIC NOT NULL,
  subtotal NUMERIC NOT NULL,
  FOREIGN KEY (compra_id) REFERENCES compras(id) ON DELETE CASCADE,
  FOREIGN KEY (produto_id) REFERENCES produtos(id)
);

CREATE TABLE IF NOT EXISTS vendas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cliente_id INTEGER,
  data TEXT NOT NULL,
  total NUMERIC NOT NULL DEFAULT 0,
  criado_em TEXT NOT NULL,
  FOREIGN KEY (cliente_id) REFERENCES clientes(id)
);

CREATE TABLE IF NOT EXISTS vendas_itens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  venda_id INTEGER NOT NULL,
  produto_id INTEGER NOT NULL,
  quantidade NUMERIC NOT NULL,
  preco_unitario NUMERIC NOT NULL,
  subtotal NUMERIC NOT NULL,
  FOREIGN KEY (venda_id) REFERENCES vendas(id) ON DELETE CASCADE,
  FOREIGN KEY (produto_id) REFERENCES produtos(id)
);

CREATE TABLE IF NOT EXISTS auditoria (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  acao TEXT NOT NULL,
  detalhe TEXT,
  criado_em TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mov_prod_data ON movimentos(produto_id, criado_em);
CREATE INDEX IF NOT EXISTS idx_prod_sku ON produtos(sku);
"""


def init_db(db: DB) -> None:
    with db.connect() as con:
        con.executescript(SCHEMA_SQL)
        log(con, "INIT_DB", f"Banco inicializado em {db.path}")


def log(con: sqlite3.Connection, acao: str, detalhe: str = "") -> None:
    con.execute(
        "INSERT INTO auditoria (acao, detalhe, criado_em) VALUES (?,?,?)",
        (acao, detalhe, now_iso()),
    )


# ---------------------------
# Queries de estoque
# ---------------------------

def get_produto_by_sku(con: sqlite3.Connection, sku: str) -> sqlite3.Row:
    row = con.execute("SELECT * FROM produtos WHERE sku = ? AND ativo = 1", (sku,)).fetchone()
    if not row:
        raise SystemExit(f"Produto não encontrado/ativo: SKU={sku}")
    return row


def estoque_atual(con: sqlite3.Connection, produto_id: int) -> Decimal:
    row = con.execute(
        "SELECT COALESCE(SUM(quantidade), 0) AS saldo FROM movimentos WHERE produto_id = ?",
        (produto_id,),
    ).fetchone()
    return Decimal(str(row["saldo"] or 0))


def recomputar_custo_medio(con: sqlite3.Connection, produto_id: int) -> None:
    """
    Custo médio simples baseado em entradas (quantidade > 0) com custo_unitario.
    Ajustes positivos com custo_unitario também entram.
    """
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
        q = Decimal(str(r["quantidade"]))
        c = Decimal(str(r["custo_unitario"]))
        total_q += q
        total_v += q * c

    custo_medio = (total_v / total_q) if total_q > 0 else Decimal("0")
    con.execute(
        "UPDATE produtos SET custo_medio = ?, atualizado_em = ? WHERE id = ?",
        (str(custo_medio), now_iso(), produto_id),
    )


# ---------------------------
# Cadastros
# ---------------------------

def upsert_categoria(con: sqlite3.Connection, nome: str) -> int:
    nome = nome.strip()
    if not nome:
        raise SystemExit("Categoria inválida.")
    con.execute("INSERT OR IGNORE INTO categorias (nome) VALUES (?)", (nome,))
    row = con.execute("SELECT id FROM categorias WHERE nome = ?", (nome,)).fetchone()
    return int(row["id"])


def cadastrar_produto(
    db: DB,
    sku: str,
    nome: str,
    categoria: Optional[str],
    unidade: str,
    estoque_minimo: Decimal,
    preco_venda: Decimal
) -> None:
    sku = sku.strip().upper()
    nome = nome.strip()
    unidade = (unidade or "UN").strip().upper()

    if not sku or not nome:
        raise SystemExit("SKU e nome são obrigatórios.")

    with db.connect() as con:
        cat_id = upsert_categoria(con, categoria) if categoria else None
        ts = now_iso()
        con.execute(
            """
            INSERT INTO produtos (sku, nome, categoria_id, unidade, estoque_minimo, preco_venda, custo_medio, criado_em, atualizado_em)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (sku, nome, cat_id, unidade, str(estoque_minimo), str(preco_venda), "0", ts, ts),
        )
        log(con, "CAD_PRODUTO", f"{sku} - {nome}")
        print(f"OK: Produto cadastrado: {sku} — {nome}")


def listar_produtos(db: DB, incluir_inativos: bool = False) -> None:
    with db.connect() as con:
        where = "" if incluir_inativos else "WHERE p.ativo = 1"
        rows = con.execute(
            f"""
            SELECT p.sku, p.nome, c.nome as categoria, p.unidade, p.estoque_minimo, p.preco_venda, p.custo_medio, p.ativo
            FROM produtos p
            LEFT JOIN categorias c ON c.id = p.categoria_id
            {where}
            ORDER BY p.nome
            """
        ).fetchall()

        print("SKU | Nome | Categoria | UN | Min | Preço | Custo Médio | Ativo | Saldo")
        for r in rows:
            prod = con.execute("SELECT id FROM produtos WHERE sku = ?", (r["sku"],)).fetchone()
            saldo = estoque_atual(con, int(prod["id"]))
            print(
                f'{r["sku"]} | {r["nome"]} | {r["categoria"] or "-"} | {r["unidade"]} | {r["estoque_minimo"]} | '
                f'{r["preco_venda"]} | {r["custo_medio"]} | {r["ativo"]} | {saldo}'
            )


def inativar_produto(db: DB, sku: str) -> None:
    with db.connect() as con:
        p = get_produto_by_sku(con, sku.strip().upper())
        con.execute("UPDATE produtos SET ativo = 0, atualizado_em = ? WHERE id = ?", (now_iso(), p["id"]))
        log(con, "INATIVA_PRODUTO", sku)
        print(f"OK: Produto inativado: {sku}")


# ---------------------------
# Movimentações
# ---------------------------

def registrar_compra(
    db: DB,
    fornecedor: Optional[str],
    data: str,
    sku: str,
    quantidade: Decimal,
    custo_unitario: Decimal,
    observacao: str = ""
) -> None:
    if quantidade <= 0:
        raise SystemExit("Quantidade deve ser > 0.")
    if custo_unitario < 0:
        raise SystemExit("Custo unitário inválido.")

    with db.connect() as con:
        fornecedor_id = None
        if fornecedor:
            nomef = fornecedor.strip()
            con.execute("INSERT OR IGNORE INTO fornecedores (nome) VALUES (?)", (nomef,))
            fornecedor_id = con.execute("SELECT id FROM fornecedores WHERE nome = ?", (nomef,)).fetchone()["id"]

        p = get_produto_by_sku(con, sku.strip().upper())

        ts = now_iso()
        cur = con.execute(
            "INSERT INTO compras (fornecedor_id, data, total, criado_em) VALUES (?,?,?,?)",
            (fornecedor_id, data, "0", ts),
        )
        compra_id = cur.lastrowid

        subtotal = quantidade * custo_unitario
        con.execute(
            """
            INSERT INTO compras_itens (compra_id, produto_id, quantidade, custo_unitario, subtotal)
            VALUES (?,?,?,?,?)
            """,
            (compra_id, p["id"], str(quantidade), str(custo_unitario), str(subtotal)),
        )

        con.execute("UPDATE compras SET total = ? WHERE id = ?", (str(subtotal), compra_id))

        con.execute(
            """
            INSERT INTO movimentos (produto_id, tipo, quantidade, custo_unitario, ref_tipo, ref_id, observacao, criado_em)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (p["id"], "ENTRADA", str(quantidade), str(custo_unitario), "COMPRA", compra_id, observacao, ts),
        )

        recomputar_custo_medio(con, int(p["id"]))
        log(con, "COMPRA", f"compra_id={compra_id} sku={p['sku']} qtd={quantidade} custo={custo_unitario}")
        saldo = estoque_atual(con, int(p["id"]))
        print(f"OK: Entrada registrada. Saldo atual ({p['sku']}): {saldo}")


def registrar_venda(
    db: DB,
    cliente: Optional[str],
    data: str,
    sku: str,
    quantidade: Decimal,
    preco_unitario: Optional[Decimal],
    observacao: str = ""
) -> None:
    if quantidade <= 0:
        raise SystemExit("Quantidade deve ser > 0.")

    with db.connect() as con:
        cliente_id = None
        if cliente:
            nomec = cliente.strip()
            con.execute("INSERT OR IGNORE INTO clientes (nome) VALUES (?)", (nomec,))
            cliente_id = con.execute("SELECT id FROM clientes WHERE nome = ?", (nomec,)).fetchone()["id"]

        p = get_produto_by_sku(con, sku.strip().upper())
        saldo = estoque_atual(con, int(p["id"]))
        if saldo - quantidade < 0:
            raise SystemExit(f"Estoque insuficiente. Saldo={saldo} tentando sair={quantidade}")

        pu = preco_unitario if preco_unitario is not None else Decimal(str(p["preco_venda"]))
        if pu < 0:
            raise SystemExit("Preço unitário inválido.")

        ts = now_iso()
        cur = con.execute(
            "INSERT INTO vendas (cliente_id, data, total, criado_em) VALUES (?,?,?,?)",
            (cliente_id, data, "0", ts),
        )
        venda_id = cur.lastrowid

        subtotal = quantidade * pu
        con.execute(
            """
            INSERT INTO vendas_itens (venda_id, produto_id, quantidade, preco_unitario, subtotal)
            VALUES (?,?,?,?,?)
            """,
            (venda_id, p["id"], str(quantidade), str(pu), str(subtotal)),
        )
        con.execute("UPDATE vendas SET total = ? WHERE id = ?", (str(subtotal), venda_id))

        con.execute(
            """
            INSERT INTO movimentos (produto_id, tipo, quantidade, preco_unitario, ref_tipo, ref_id, observacao, criado_em)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (p["id"], "SAIDA", str(-quantidade), str(pu), "VENDA", venda_id, observacao, ts),
        )

        log(con, "VENDA", f"venda_id={venda_id} sku={p['sku']} qtd={quantidade} preco={pu}")
        saldo2 = estoque_atual(con, int(p["id"]))
        print(f"OK: Saída registrada. Saldo atual ({p['sku']}): {saldo2}")


def ajustar_estoque(
    db: DB,
    sku: str,
    quantidade: Decimal,
    motivo: str,
    custo_unitario: Optional[Decimal] = None,
    observacao: str = ""
) -> None:
    if quantidade == 0:
        raise SystemExit("Quantidade do ajuste não pode ser 0.")
    motivo = (motivo or "AJUSTE").strip().upper()

    with db.connect() as con:
        p = get_produto_by_sku(con, sku.strip().upper())
        saldo = estoque_atual(con, int(p["id"]))
        if saldo + quantidade < 0:
            raise SystemExit(f"Ajuste resultaria em saldo negativo. Saldo={saldo} ajuste={quantidade}")

        ts = now_iso()
        con.execute(
            """
            INSERT INTO movimentos (produto_id, tipo, quantidade, custo_unitario, ref_tipo, observacao, criado_em)
            VALUES (?,?,?,?,?,?,?)
            """,
            (p["id"], "AJUSTE", str(quantidade), str(custo_unitario) if custo_unitario is not None else None, motivo, observacao, ts),
        )
        recomputar_custo_medio(con, int(p["id"]))
        log(con, "AJUSTE", f"sku={p['sku']} qtd={quantidade} motivo={motivo}")

        saldo2 = estoque_atual(con, int(p["id"]))
        print(f"OK: Ajuste registrado. Saldo atual ({p['sku']}): {saldo2}")


# ---------------------------
# Relatórios
# ---------------------------

def relatorio_abaixo_minimo(db: DB) -> None:
    with db.connect() as con:
        rows = con.execute(
            """
            SELECT id, sku, nome, estoque_minimo, custo_medio
            FROM produtos
            WHERE ativo = 1
            ORDER BY nome
            """
        ).fetchall()

        print("Abaixo do mínimo:")
        found = False
        for r in rows:
            saldo = estoque_atual(con, int(r["id"]))
            minimo = Decimal(str(r["estoque_minimo"]))
            if saldo < minimo:
                found = True
                print(f'- {r["sku"]} | {r["nome"]}: saldo={saldo} min={minimo}')
        if not found:
            print("Nenhum item abaixo do mínimo.")


def relatorio_estoque(db: DB) -> None:
    with db.connect() as con:
        rows = con.execute(
            """
            SELECT p.id, p.sku, p.nome, p.unidade, p.custo_medio, p.preco_venda, p.estoque_minimo
            FROM produtos p
            WHERE p.ativo = 1
            ORDER BY p.nome
            """
        ).fetchall()

        total_val = Decimal("0")
        print("SKU | Nome | Saldo | UN | Custo Médio | Valorização | Preço")
        for r in rows:
            saldo = estoque_atual(con, int(r["id"]))
            cm = Decimal(str(r["custo_medio"]))
            val = saldo * cm
            total_val += val
            print(f'{r["sku"]} | {r["nome"]} | {saldo} | {r["unidade"]} | {cm} | {val} | {r["preco_venda"]}')

        print(f"\nValorização total (custo médio): {money(total_val)}")


def relatorio_movimentos(db: DB, inicio: str, fim: str) -> None:
    with db.connect() as con:
        rows = con.execute(
            """
            SELECT m.criado_em, p.sku, p.nome, m.tipo, m.quantidade, m.custo_unitario, m.preco_unitario, m.ref_tipo, m.ref_id, m.observacao
            FROM movimentos m
            JOIN produtos p ON p.id = m.produto_id
            WHERE date(m.criado_em) BETWEEN date(?) AND date(?)
            ORDER BY m.criado_em DESC
            """,
            (inicio, fim),
        ).fetchall()

        print(f"Movimentos de {inicio} até {fim}:")
        for r in rows:
            print(
                f'{r["criado_em"]} | {r["sku"]} | {r["tipo"]} | qtd={r["quantidade"]} | '
                f'custo={r["custo_unitario"]} | preco={r["preco_unitario"]} | ref={r["ref_tipo"]}:{r["ref_id"]} | {r["observacao"] or ""}'
            )


def exportar_csv(db: DB, arquivo: str) -> None:
    with db.connect() as con:
        rows = con.execute(
            """
            SELECT p.id, p.sku, p.nome, p.unidade, p.estoque_minimo, p.preco_venda, p.custo_medio
            FROM produtos p
            WHERE p.ativo = 1
            ORDER BY p.nome
            """
        ).fetchall()

        with open(arquivo, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["sku", "nome", "unidade", "estoque_minimo", "preco_venda", "custo_medio", "saldo"])
            for r in rows:
                saldo = estoque_atual(con, int(r["id"]))
                w.writerow([r["sku"], r["nome"], r["unidade"], r["estoque_minimo"], r["preco_venda"], r["custo_medio"], str(saldo)])

        print(f"OK: Exportado para {arquivo}")


# ---------------------------
# CLI
# ---------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="estoquepro", description="Controle de estoque (CLI) com SQLite")
    p.add_argument("--db", default=DB_DEFAULT, help="Caminho do arquivo SQLite (padrão: estoquepro.db)")

    sp = p.add_subparsers(dest="cmd", required=True)

    sp.add_parser("init", help="Inicializa o banco de dados")

    cad = sp.add_parser("cadastrar-produto", help="Cadastra um produto")
    cad.add_argument("--sku", required=True)
    cad.add_argument("--nome", required=True)
    cad.add_argument("--categoria")
    cad.add_argument("--unidade", default="UN")
    cad.add_argument("--min", default="0")
    cad.add_argument("--preco", default="0")

    lp = sp.add_parser("listar-produtos", help="Lista produtos")
    lp.add_argument("--inativos", action="store_true")

    ina = sp.add_parser("inativar-produto", help="Inativa produto")
    ina.add_argument("--sku", required=True)

    compra = sp.add_parser("compra", help="Registra compra (entrada)")
    compra.add_argument("--fornecedor")
    compra.add_argument("--data", default=today_iso_date())
    compra.add_argument("--sku", required=True)
    compra.add_argument("--qtd", required=True)
    compra.add_argument("--custo", required=True)
    compra.add_argument("--obs", default="")

    venda = sp.add_parser("venda", help="Registra venda (saída)")
    venda.add_argument("--cliente")
    venda.add_argument("--data", default=today_iso_date())
    venda.add_argument("--sku", required=True)
    venda.add_argument("--qtd", required=True)
    venda.add_argument("--preco")  # opcional
    venda.add_argument("--obs", default="")

    aj = sp.add_parser("ajuste", help="Ajuste de estoque (+/-)")
    aj.add_argument("--sku", required=True)
    aj.add_argument("--qtd", required=True, help="Ex.: 5 para +5, -2 para -2")
    aj.add_argument("--motivo", default="INVENTARIO")
    aj.add_argument("--custo")  # opcional (para ajustes positivos)
    aj.add_argument("--obs", default="")

    rmin = sp.add_parser("abaixo-minimo", help="Lista produtos abaixo do mínimo")
    rest = sp.add_parser("relatorio-estoque", help="Relatório de estoque + valorização")
    rmov = sp.add_parser("movimentos", help="Relatório de movimentos por período")
    rmov.add_argument("--inicio", required=True, help="YYYY-MM-DD")
    rmov.add_argument("--fim", required=True, help="YYYY-MM-DD")

    exp = sp.add_parser("exportar-csv", help="Exporta produtos + saldo para CSV")
    exp.add_argument("--arquivo", default="estoque.csv")

    return p


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    if argv is None and len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    
    args = parser.parse_args(argv)

    db = DB(args.db)

    if args.cmd == "init":
        init_db(db)
        print("OK: Banco pronto.")
        return

    # garante que o banco existe / schema aplicado
    init_db(db)

    if args.cmd == "cadastrar-produto":
        cadastrar_produto(
            db=db,
            sku=args.sku,
            nome=args.nome,
            categoria=args.categoria,
            unidade=args.unidade,
            estoque_minimo=parse_decimal(args.min),
            preco_venda=parse_decimal(args.preco),
        )
        return

    if args.cmd == "listar-produtos":
        listar_produtos(db, incluir_inativos=args.inativos)
        return

    if args.cmd == "inativar-produto":
        inativar_produto(db, args.sku)
        return

    if args.cmd == "compra":
        registrar_compra(
            db=db,
            fornecedor=args.fornecedor,
            data=args.data,
            sku=args.sku,
            quantidade=parse_decimal(args.qtd),
            custo_unitario=parse_decimal(args.custo),
            observacao=args.obs,
        )
        return

    if args.cmd == "venda":
        pu = parse_decimal(args.preco) if args.preco is not None else None
        registrar_venda(
            db=db,
            cliente=args.cliente,
            data=args.data,
            sku=args.sku,
            quantidade=parse_decimal(args.qtd),
            preco_unitario=pu,
            observacao=args.obs,
        )
        return

    if args.cmd == "ajuste":
        cu = parse_decimal(args.custo) if args.custo is not None else None
        ajustar_estoque(
            db=db,
            sku=args.sku,
            quantidade=parse_decimal(args.qtd),
            motivo=args.motivo,
            custo_unitario=cu,
            observacao=args.obs,
        )
        return

    if args.cmd == "abaixo-minimo":
        relatorio_abaixo_minimo(db)
        return

    if args.cmd == "relatorio-estoque":
        relatorio_estoque(db)
        return

    if args.cmd == "movimentos":
        relatorio_movimentos(db, args.inicio, args.fim)
        return

    if args.cmd == "exportar-csv":
        exportar_csv(db, args.arquivo)
        return


if __name__ == "__main__":
    main()
