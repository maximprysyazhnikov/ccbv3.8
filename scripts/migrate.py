from __future__ import annotations
import os, sqlite3, sys

DB_PATH = os.getenv("DB_PATH") or "storage/bot.db"

def table_exists(c, name: str) -> bool:
    row = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (name,)).fetchone()
    return bool(row)

def column_exists(c, table: str, column: str) -> bool:
    rows = c.execute(f"PRAGMA table_info({table});").fetchall()
    return any(r[1] == column for r in rows)  # (cid, name, type, ...)

def add_column_if_missing(c, table: str, column: str, ddl: str):
    if table_exists(c, table) and not column_exists(c, table, column):
        c.execute(f"ALTER TABLE {table} ADD COLUMN {ddl};")

def ensure_settings(c):
    c.execute("""
      CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
      );
    """)

def ensure_indexes(c):
    for tbl, col in (("signals","closed_at"),("signals","status"),("signals","symbol"),
                     ("trades","closed_at"),("trades","status"),("trades","symbol")):
        if table_exists(c, tbl):
            c.execute(f"CREATE INDEX IF NOT EXISTS ix_{tbl}_{col} ON {tbl}({col});")

def migrate_telemetry(c):
    for tbl in ("trades","signals"):
        if not table_exists(c, tbl):
            continue
        add_column_if_missing(c, tbl, "reason_close",   "reason_close TEXT")
        add_column_if_missing(c, tbl, "trend_ok",       "trend_ok INTEGER")
        add_column_if_missing(c, tbl, "atr_entry",      "atr_entry REAL")
        add_column_if_missing(c, tbl, "ema50",          "ema50 REAL")
        add_column_if_missing(c, tbl, "ema200",         "ema200 REAL")
        add_column_if_missing(c, tbl, "rr_target",      "rr_target REAL")
        add_column_if_missing(c, tbl, "entry_sl_dist",  "entry_sl_dist REAL")
    # flags лише для trades
    if table_exists(c, "trades"):
        add_column_if_missing(c, "trades", "partial_50_done", "partial_50_done INTEGER")
        add_column_if_missing(c, "trades", "be_done",         "be_done INTEGER")

def migrate_laddering(c):
    if table_exists(c, "trades"):
        c.execute("""
          CREATE TABLE IF NOT EXISTS trade_legs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER NOT NULL,
            side TEXT NOT NULL,
            qty REAL NOT NULL,
            price REAL NOT NULL,
            filled_at TEXT,
            FOREIGN KEY(trade_id) REFERENCES trades(id)
          );
        """)
        add_column_if_missing(c, "trades", "avg_entry",       "avg_entry REAL")
        add_column_if_missing(c, "trades", "filled_buckets",  "filled_buckets INTEGER")
        add_column_if_missing(c, "trades", "target_rrs_json", "target_rrs_json TEXT")

def main():
    if not os.path.exists(DB_PATH):
        print(f"[migrate] ❌ DB not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)
    with sqlite3.connect(DB_PATH) as c:
        ensure_settings(c)
        ensure_indexes(c)
        migrate_telemetry(c)
        migrate_laddering(c)
    print("[migrate] OK")

if __name__ == "__main__":
    main()
