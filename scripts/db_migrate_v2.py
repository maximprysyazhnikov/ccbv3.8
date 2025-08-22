from __future__ import annotations
import os, sqlite3

DB = os.getenv("DB_PATH") or os.getenv("SQLITE_PATH") or os.getenv("DATABASE_PATH") or "storage/bot.db"

DDL = [
    # базова таблиця (якщо хтось розгорнув із мінімумом)
    """CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        source TEXT,
        symbol TEXT,
        timeframe TEXT,
        direction TEXT,
        entry REAL,
        stop REAL,
        tp REAL,
        rr REAL,
        status TEXT,
        ts_created INTEGER,
        ts_closed INTEGER,
        pnl_pct REAL,
        pnl_usd REAL,
        size_usd REAL,
        analysis_id TEXT,
        snapshot_ts INTEGER
    );""",

    # safe-ALTERs
    "ALTER TABLE signals ADD COLUMN entry REAL;",
    "ALTER TABLE signals ADD COLUMN stop REAL;",
    "ALTER TABLE signals ADD COLUMN tp REAL;",
    "ALTER TABLE signals ADD COLUMN rr REAL;",
    "ALTER TABLE signals ADD COLUMN size_usd REAL;",
    "ALTER TABLE signals ADD COLUMN analysis_id TEXT;",
    "ALTER TABLE signals ADD COLUMN snapshot_ts INTEGER;",
    "ALTER TABLE signals ADD COLUMN pnl_pct REAL;",
    "ALTER TABLE signals ADD COLUMN pnl_usd REAL;",
    "ALTER TABLE signals ADD COLUMN ts_closed INTEGER;",
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_signals_user_time ON signals(user_id, ts_created);",
    "CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status, ts_created);",
    "CREATE INDEX IF NOT EXISTS idx_signals_symbol_time ON signals(symbol, ts_created);",
]

def _run(cur, sql):
    try:
        cur.execute(sql)
    except sqlite3.OperationalError as e:
        # Ймовірно колонки вже є
        if "duplicate column name" in str(e).lower():
            return
        raise

def main():
    os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
    with sqlite3.connect(DB, timeout=30) as c:
        cur = c.cursor()
        for s in DDL:
            _run(cur, s)
        for s in INDEXES:
            cur.execute(s)
        c.commit()
    print(f"OK: migrated {DB}")

if __name__ == "__main__":
    main()
