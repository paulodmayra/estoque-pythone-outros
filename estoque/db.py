import sqlite3
import datetime

DB_PATH = "estoquepro.db"

SCHEMA_SQL = """
-- (Cole aqui o schema SQL completo que você já tem no CLI)
CREATE TABLE IF NOT EXISTS categorias (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL UNIQUE
);
-- (adicione todas as outras tabelas conforme seu schema)
"""

def connect():
    con = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON;")
    return con

def init_db():
    with connect() as con:
        con.executescript(SCHEMA_SQL)
        con.commit()

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
