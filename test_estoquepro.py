#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes automatizados para EstoquePro (ESTOQ-CONTRO.py).
Usa banco SQLite in-memory para isolamento total.
"""

import csv
import io
import os
import sys
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import patch

# Importa o módulo principal
sys.path.insert(0, os.path.dirname(__file__))
import importlib
ESTOQUEPRO = importlib.import_module("ESTOQ-CONTRO")

# Aliases
DB = ESTOQUEPRO.DB
parse_decimal = ESTOQUEPRO.parse_decimal
init_db = ESTOQUEPRO.init_db
cadastrar_produto = ESTOQUEPRO.cadastrar_produto
listar_produtos = ESTOQUEPRO.listar_produtos
registrar_compra = ESTOQUEPRO.registrar_compra
registrar_venda = ESTOQUEPRO.registrar_venda
ajustar_estoque = ESTOQUEPRO.ajustar_estoque
inativar_produto = ESTOQUEPRO.inativar_produto
estoque_atual = ESTOQUEPRO.estoque_atual
relatorio_abaixo_minimo = ESTOQUEPRO.relatorio_abaixo_minimo
relatorio_estoque = ESTOQUEPRO.relatorio_estoque
exportar_csv = ESTOQUEPRO.exportar_csv


class MemDB:
    """Substituto do DB que usa :memory: para testes isolados."""
    def __init__(self):
        import sqlite3
        self.path = ':memory:'
        self._con = sqlite3.connect(':memory:')
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA foreign_keys = ON;")

    def connect(self):
        """Reutiliza a mesma conexão in-memory durante o teste."""
        return self._con

    def close(self):
        if self._con:
            self._con.close()
            self._con = None


# ======================
# Testes: parse_decimal
# ======================

class TestParseDecimal(unittest.TestCase):

    def test_inteiro(self):
        self.assertEqual(parse_decimal("100"), Decimal("100"))

    def test_virgula_decimal(self):
        self.assertEqual(parse_decimal("10,50"), Decimal("10.50"))

    def test_ponto_e_virgula_milhar(self):
        self.assertEqual(parse_decimal("1.500,00"), Decimal("1500.00"))

    def test_ponto_milhar_sem_virgula(self):
        """1.500 (com 3 dígitos após ponto) = 1500 (milhar)."""
        self.assertEqual(parse_decimal("1.500"), Decimal("1500"))

    def test_ponto_decimal_dois_digitos(self):
        """1.50 (com 2 dígitos após ponto) = 1.50 (decimal)."""
        self.assertEqual(parse_decimal("1.50"), Decimal("1.50"))

    def test_ponto_decimal_um_digito(self):
        self.assertEqual(parse_decimal("1.5"), Decimal("1.5"))

    def test_milhares_grandes(self):
        self.assertEqual(parse_decimal("12.500,75"), Decimal("12500.75"))

    def test_valor_zero(self):
        self.assertEqual(parse_decimal("0"), Decimal("0"))

    def test_valor_negativo_virgula(self):
        self.assertEqual(parse_decimal("-10,50"), Decimal("-10.50"))

    def test_espacos(self):
        self.assertEqual(parse_decimal("  25,00  "), Decimal("25.00"))

    def test_vazio_levanta_erro(self):
        with self.assertRaises(ValueError):
            parse_decimal("")

    def test_invalido_levanta_erro(self):
        with self.assertRaises(ValueError):
            parse_decimal("abc")


# =========================
# Testes: Cadastro + CRUD
# =========================

class TestCadastroProduto(unittest.TestCase):

    def setUp(self):
        self.db = MemDB()
        init_db(self.db)

    def tearDown(self):
        self.db.close()

    def _cadastrar_padrao(self):
        cadastrar_produto(
            db=self.db,
            sku="PROD001",
            nome="Parafuso Sextavado",
            categoria="Fixação",
            unidade="UN",
            estoque_minimo=Decimal("10"),
            preco_venda=Decimal("2.50"),
        )

    def test_cadastrar_produto_ok(self):
        self._cadastrar_padrao()
        con = self.db.connect()
        row = con.execute("SELECT * FROM produtos WHERE sku = 'PROD001'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["nome"], "Parafuso Sextavado")
        self.assertEqual(row["unidade"], "UN")
        self.assertEqual(row["ativo"], 1)

    def test_cadastrar_cria_categoria(self):
        self._cadastrar_padrao()
        con = self.db.connect()
        cat = con.execute("SELECT * FROM categorias WHERE nome = 'Fixação'").fetchone()
        self.assertIsNotNone(cat)

    def test_cadastrar_sku_duplicado_levanta_erro(self):
        self._cadastrar_padrao()
        with self.assertRaises(Exception):
            self._cadastrar_padrao()

    def test_listar_produtos(self):
        self._cadastrar_padrao()
        output = io.StringIO()
        with patch('sys.stdout', output):
            listar_produtos(self.db)
        text = output.getvalue()
        self.assertIn("PROD001", text)
        self.assertIn("Parafuso Sextavado", text)

    def test_inativar_produto(self):
        self._cadastrar_padrao()
        with patch('builtins.input', return_value='s'):
            inativar_produto(self.db, "PROD001")
        con = self.db.connect()
        row = con.execute("SELECT ativo FROM produtos WHERE sku = 'PROD001'").fetchone()
        self.assertEqual(row["ativo"], 0)

    def test_inativar_produto_cancelado(self):
        self._cadastrar_padrao()
        with patch('builtins.input', return_value='n'):
            inativar_produto(self.db, "PROD001")
        con = self.db.connect()
        row = con.execute("SELECT ativo FROM produtos WHERE sku = 'PROD001'").fetchone()
        self.assertEqual(row["ativo"], 1)  # não inativou


# ===================================
# Testes: Compra, Venda, Ajuste
# ===================================

class TestMovimentacoes(unittest.TestCase):

    def setUp(self):
        self.db = MemDB()
        init_db(self.db)
        cadastrar_produto(
            db=self.db,
            sku="MAT01",
            nome="Cimento CP-II",
            categoria="Material",
            unidade="SC",
            estoque_minimo=Decimal("5"),
            preco_venda=Decimal("35.00"),
        )

    def tearDown(self):
        self.db.close()

    def _saldo(self, sku="MAT01"):
        con = self.db.connect()
        p = con.execute("SELECT id FROM produtos WHERE sku = ?", (sku,)).fetchone()
        return estoque_atual(con, int(p["id"]))

    def test_compra_atualiza_saldo(self):
        registrar_compra(
            db=self.db, fornecedor="Fornecedor A",
            data="2024-01-15", sku="MAT01",
            quantidade=Decimal("20"), custo_unitario=Decimal("28.00"),
        )
        self.assertEqual(self._saldo(), Decimal("20"))

    def test_compra_custo_medio(self):
        registrar_compra(
            db=self.db, fornecedor=None,
            data="2024-01-15", sku="MAT01",
            quantidade=Decimal("10"), custo_unitario=Decimal("20.00"),
        )
        registrar_compra(
            db=self.db, fornecedor=None,
            data="2024-01-16", sku="MAT01",
            quantidade=Decimal("10"), custo_unitario=Decimal("30.00"),
        )
        con = self.db.connect()
        row = con.execute("SELECT custo_medio FROM produtos WHERE sku = 'MAT01'").fetchone()
        cm = Decimal(str(row["custo_medio"]))
        self.assertEqual(cm, Decimal("25"))  # (10*20 + 10*30) / 20

    def test_venda_reduz_saldo(self):
        registrar_compra(
            db=self.db, fornecedor=None,
            data="2024-01-15", sku="MAT01",
            quantidade=Decimal("10"), custo_unitario=Decimal("28.00"),
        )
        registrar_venda(
            db=self.db, cliente="Cliente X",
            data="2024-01-16", sku="MAT01",
            quantidade=Decimal("3"), preco_unitario=Decimal("35.00"),
        )
        self.assertEqual(self._saldo(), Decimal("7"))

    def test_venda_estoque_insuficiente(self):
        registrar_compra(
            db=self.db, fornecedor=None,
            data="2024-01-15", sku="MAT01",
            quantidade=Decimal("5"), custo_unitario=Decimal("28.00"),
        )
        with self.assertRaises(SystemExit):
            registrar_venda(
                db=self.db, cliente=None,
                data="2024-01-16", sku="MAT01",
                quantidade=Decimal("10"), preco_unitario=Decimal("35.00"),
            )

    def test_venda_usa_preco_cadastrado(self):
        registrar_compra(
            db=self.db, fornecedor=None,
            data="2024-01-15", sku="MAT01",
            quantidade=Decimal("10"), custo_unitario=Decimal("28.00"),
        )
        registrar_venda(
            db=self.db, cliente=None,
            data="2024-01-16", sku="MAT01",
            quantidade=Decimal("2"), preco_unitario=None,
        )
        con = self.db.connect()
        vi = con.execute("SELECT preco_unitario FROM vendas_itens ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(Decimal(str(vi["preco_unitario"])), Decimal("35.00"))

    def test_ajuste_positivo(self):
        ajustar_estoque(
            db=self.db, sku="MAT01",
            quantidade=Decimal("15"), motivo="INVENTARIO",
            custo_unitario=Decimal("30.00"),
        )
        self.assertEqual(self._saldo(), Decimal("15"))

    def test_ajuste_negativo(self):
        registrar_compra(
            db=self.db, fornecedor=None,
            data="2024-01-15", sku="MAT01",
            quantidade=Decimal("10"), custo_unitario=Decimal("28.00"),
        )
        ajustar_estoque(
            db=self.db, sku="MAT01",
            quantidade=Decimal("-3"), motivo="AVARIA",
        )
        self.assertEqual(self._saldo(), Decimal("7"))

    def test_ajuste_saldo_negativo_bloqueado(self):
        with self.assertRaises(SystemExit):
            ajustar_estoque(
                db=self.db, sku="MAT01",
                quantidade=Decimal("-5"), motivo="AVARIA",
            )


# ===================================
# Testes: Relatórios e Exportação
# ===================================

class TestRelatorios(unittest.TestCase):

    def setUp(self):
        self.db = MemDB()
        init_db(self.db)
        cadastrar_produto(
            db=self.db, sku="REL01", nome="Tijolo 6F",
            categoria="Alvenaria", unidade="UN",
            estoque_minimo=Decimal("100"), preco_venda=Decimal("1.20"),
        )

    def tearDown(self):
        self.db.close()

    def test_abaixo_minimo_detecta(self):
        # Saldo = 0, mínimo = 100 → deve aparecer
        output = io.StringIO()
        with patch('sys.stdout', output):
            relatorio_abaixo_minimo(self.db)
        self.assertIn("REL01", output.getvalue())

    def test_abaixo_minimo_ok(self):
        registrar_compra(
            db=self.db, fornecedor=None,
            data="2024-01-15", sku="REL01",
            quantidade=Decimal("200"), custo_unitario=Decimal("0.80"),
        )
        output = io.StringIO()
        with patch('sys.stdout', output):
            relatorio_abaixo_minimo(self.db)
        self.assertIn("Nenhum item abaixo do mínimo", output.getvalue())

    def test_relatorio_estoque(self):
        registrar_compra(
            db=self.db, fornecedor=None,
            data="2024-01-15", sku="REL01",
            quantidade=Decimal("50"), custo_unitario=Decimal("0.80"),
        )
        output = io.StringIO()
        with patch('sys.stdout', output):
            relatorio_estoque(self.db)
        text = output.getvalue()
        self.assertIn("REL01", text)
        self.assertIn("Valorização total", text)

    def test_exportar_csv(self):
        registrar_compra(
            db=self.db, fornecedor=None,
            data="2024-01-15", sku="REL01",
            quantidade=Decimal("50"), custo_unitario=Decimal("0.80"),
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            csv_path = f.name

        try:
            exportar_csv(self.db, csv_path)

            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=';')
                rows = list(reader)

            # Header + 1 data row
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][0], "sku")
            self.assertEqual(rows[1][0], "REL01")
            self.assertEqual(rows[1][6], "50")  # saldo
        finally:
            os.unlink(csv_path)


if __name__ == "__main__":
    unittest.main()
