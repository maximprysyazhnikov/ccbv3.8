# storage/migrate.py
from __future__ import annotations
import os, sqlite3

DB_PATH = os.getenv("DB_PATH", "storage/app.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS user_settings (
  user_id INTEGER PRIMARY KEY,
  timeframe     TEXT    DEFAULT '15m',
  autopost      INTEGER DEFAULT 0,
  autopost_tf   TEXT    DEFAULT '15m',
  autopost_rr   REAL    DEFAULT 1.5,
  rr_threshold  REAL    DEFAULT 1.5,
  model_key     TEXT    DEFAULT 'auto',
  locale        TEXT    DEFAULT 'uk'
);

CREATE TABLE IF NOT EXISTS signals (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER NOT NULL,
  symbol      TEXT    NOT NULL,
  tf          TEXT    NOT NULL,
  direction   TEXT    NOT NULL CHECK(direction IN('LONG','SHORT')),
  entry       REAL    NOT NULL,
  sl          REAL    NOT NULL,
  tp          REAL    NOT NULL,
  rr          REAL    NOT NULL,
  ts_created  INTEGER NOT NULL,
  ts_closed   INTEGER,
  status      TEXT    NOT NULL CHECK(status IN('OPEN','WIN','LOSS','SKIP')),
  pnl_pct     REAL
);
CREATE INDEX IF NOT EXISTS idx_signals_user_status ON signals(user_id,status);
CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(ts_created);

CREATE TABLE IF NOT EXISTS autopost_log (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id  INTEGER NOT NULL,
  symbol   TEXT    NOT NULL,
  tf       TEXT    NOT NULL,
  rr       REAL    NOT NULL,
  ts_sent  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_aplog_dedup ON autopost_log(user_id,symbol,tf,ts_sent);
"""

def migrate():
    con = sqlite3.connect(DB_PATH)
    try:
        con.executescript(DDL)
        con.commit()
        print(f"✅ migrated at {DB_PATH}")
    finally:
        con.close()

if __name__ == "__main__":
    migrate()
