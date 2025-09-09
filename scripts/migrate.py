import os
import sqlite3
from pathlib import Path

DB_PATH = os.getenv("DB_PATH", "storage/bot.db")
SQL_FILE = Path("migrations/00XX_trades_and_settings.sql")

def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def _table_has_column(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info({table});")
    return any(row[1] == column for row in cur.fetchall())

def _apply_sql(conn, path: Path):
    with path.open("r", encoding="utf-8") as f:
        conn.executescript(f.read())

def _ensure_signals_last_direction(conn):
    if not _table_has_column(conn, "signals", "last_direction"):
        conn.execute("ALTER TABLE signals ADD COLUMN last_direction TEXT;")

def _seed_settings(conn):
    defaults = {
        "neutral_mode": os.getenv("NEUTRAL_MODE", "TRAIL").upper(),
        "sim_usd_per_trade": os.getenv("SIM_USD_PER_TRADE", "100"),
        "fees_bps": os.getenv("FEES_BPS", "10"),
    }
    for k, v in defaults.items():
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value;",
            (k, str(v)),
        )

def main():
    conn = _connect()
    try:
        conn.execute("BEGIN;")
        _apply_sql(conn, SQL_FILE)
        _ensure_signals_last_direction(conn)
        _seed_settings(conn)
        conn.commit()
        print("[migrate] OK →", DB_PATH)
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
