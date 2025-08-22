# utils/db_migrate.py
from __future__ import annotations
import os, sqlite3

DB_PATH = os.getenv("DB_PATH") or os.path.join("storage", "bot.db")

DDL_USER_SETTINGS = """
CREATE TABLE IF NOT EXISTS user_settings (
  user_id       INTEGER PRIMARY KEY,
  timeframe     TEXT    DEFAULT '15m',
  autopost      INTEGER DEFAULT 0,
  autopost_tf   TEXT    DEFAULT '15m',
  autopost_rr   REAL    DEFAULT 1.5,
  rr_threshold  REAL    DEFAULT 1.5,
  model_key     TEXT    DEFAULT 'auto',
  locale        TEXT    DEFAULT 'uk',
  daily_tracker INTEGER DEFAULT 0,
  winrate_tracker INTEGER DEFAULT 0
);
"""

DDL_SIGNALS = """
CREATE TABLE IF NOT EXISTS signals (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL,
  symbol     TEXT    NOT NULL,
  tf         TEXT    NOT NULL,
  direction  TEXT    CHECK(direction IN ('LONG','SHORT')) NOT NULL,
  entry      REAL    NOT NULL,
  sl         REAL    NOT NULL,
  tp         REAL    NOT NULL,
  rr         REAL    NOT NULL,
  ts_created INTEGER NOT NULL,
  ts_closed  INTEGER,
  status     TEXT    CHECK(status IN ('OPEN','WIN','LOSS','SKIP')) NOT NULL,
  pnl_pct    REAL
);
"""

DDL_AUTOPOST_LOG = """
CREATE TABLE IF NOT EXISTS autopost_log (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id  INTEGER NOT NULL,
  symbol   TEXT    NOT NULL,
  tf       TEXT    NOT NULL,
  rr       REAL    NOT NULL,
  ts_sent  INTEGER NOT NULL
);
"""

# idempotent ALTERs — безпечно запускати багато разів
ALTERS_USER_SETTINGS = [
    ("autopost_tf",   "TEXT",    "15m"),
    ("autopost_rr",   "REAL",    "1.5"),
    ("rr_threshold",  "REAL",    "1.5"),
    ("model_key",     "TEXT",    "'auto'"),
    ("locale",        "TEXT",    "'uk'"),
    ("daily_tracker", "INTEGER", "0"),
    ("winrate_tracker","INTEGER","0"),
]

INDEXES = [
    ("CREATE INDEX IF NOT EXISTS idx_signals_user_open ON signals(user_id, status)",),
    ("CREATE INDEX IF NOT EXISTS idx_aplog_dedup ON autopost_log(user_id, symbol, tf, ts_sent)",),
]

def column_exists(cur: sqlite3.Cursor, table: str, col: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == col for row in cur.fetchall())

def migrate(db_path: str = DB_PATH) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()

        # Базові таблиці
        c.execute(DDL_USER_SETTINGS)
        c.execute(DDL_SIGNALS)
        c.execute(DDL_AUTOPOST_LOG)

        # Додати відсутні колонки user_settings
        for col, typ, default in ALTERS_USER_SETTINGS:
            if not column_exists(c, "user_settings", col):
                c.execute(f"ALTER TABLE user_settings ADD COLUMN {col} {typ} DEFAULT {default}")

        # Індекси
        for (ddl,) in INDEXES:
            c.execute(ddl)

        conn.commit()
    print(f"[migrate] OK → {db_path}")

if __name__ == "__main__":
    migrate()
