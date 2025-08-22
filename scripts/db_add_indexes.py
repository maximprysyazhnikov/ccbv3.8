# scripts/db_add_indexes.py
import os, sqlite3

DB_PATH = os.getenv("DB_PATH") or "storage/bot.db"

DDL = [
    "CREATE INDEX IF NOT EXISTS idx_signals_user_time   ON signals(user_id, COALESCE(ts_closed, ts_created));",
    "CREATE INDEX IF NOT EXISTS idx_signals_status      ON signals(status);",
    "CREATE INDEX IF NOT EXISTS idx_signals_symbol_time ON signals(symbol, COALESCE(ts_closed, ts_created));",
]

with sqlite3.connect(DB_PATH, timeout=30) as c:
    cur = c.cursor()
    for sql in DDL:
        cur.execute(sql)
    c.commit()
print("OK: indexes ensured on", DB_PATH)
