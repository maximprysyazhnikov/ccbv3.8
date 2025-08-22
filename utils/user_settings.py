# utils/user_settings.py
from __future__ import annotations
import os
import sqlite3
from typing import Any, Dict

# Один шлях до БД для всього проєкту
DB_PATH = (
    os.getenv("DB_PATH")
    or os.getenv("SQLITE_PATH")
    or os.getenv("DATABASE_PATH")
    or "storage/bot.db"
)


try:
    from utils.db_migrate import migrate as _migrate_db
    _migrate_db()  # гарантує наявність колонок/таблиць
except Exception:
    pass

def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def _ensure_schema() -> None:
    with _conn() as c:
        cur = c.cursor()
        # Базова таблиця налаштувань
        cur.execute("""
        CREATE TABLE IF NOT EXISTS user_settings(
          user_id        INTEGER PRIMARY KEY,
          timeframe      TEXT    DEFAULT '15m',
          autopost       INTEGER DEFAULT 0,
          autopost_tf    TEXT    DEFAULT '15m',
          autopost_rr    REAL    DEFAULT 1.5,
          rr_threshold   REAL    DEFAULT 1.5,
          model_key      TEXT    DEFAULT 'auto',
          locale         TEXT    DEFAULT 'uk',
          daily_tracker  INTEGER DEFAULT 0,
          daily_rr       REAL    DEFAULT 3.0,
          winrate_tracker INTEGER DEFAULT 0
        )
        """)
        # Ідемпотентно додаємо відсутні колонки (на випадок старої БД)
        cur.execute("PRAGMA table_info(user_settings)")
        have = {r[1] for r in cur.fetchall()}
        add_cols = {
            "daily_tracker":   "ALTER TABLE user_settings ADD COLUMN daily_tracker INTEGER DEFAULT 0",
            "daily_rr":        "ALTER TABLE user_settings ADD COLUMN daily_rr REAL DEFAULT 3.0",
            "winrate_tracker": "ALTER TABLE user_settings ADD COLUMN winrate_tracker INTEGER DEFAULT 0",
            "rr_threshold":    "ALTER TABLE user_settings ADD COLUMN rr_threshold REAL DEFAULT 1.5",
        }
        for col, ddl in add_cols.items():
            if col not in have:
                try: cur.execute(ddl)
                except sqlite3.OperationalError: pass
        c.commit()

_ensure_schema()

def ensure_user_row(user_id: int) -> None:
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO user_settings(user_id) VALUES(?)", (user_id,))
        c.commit()

def get_user_settings(user_id: int) -> Dict[str, Any]:
    with _conn() as c:
        cur = c.execute("SELECT * FROM user_settings WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else {}

def set_user_settings(user_id: int, **kwargs: Any) -> None:
    """
    Гнучкий апдейт будь‑яких полів user_settings.
    Приклад: set_user_settings(123, daily_tracker=1, daily_rr=2.5)
    """
    if not kwargs:
        return
    ensure_user_row(user_id)
    cols = [f"{k}=?" for k in kwargs.keys()]
    vals = list(kwargs.values()) + [user_id]
    with _conn() as c:
        c.execute(f"UPDATE user_settings SET {', '.join(cols)} WHERE user_id=?", vals)
        c.commit()
