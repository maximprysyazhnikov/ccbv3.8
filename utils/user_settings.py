# utils/user_settings.py
from __future__ import annotations
import sqlite3
from typing import Any, Dict
from utils.db import get_conn  # ← ЄДИНИЙ шлях до БД

# ──────────────────────────────────────────────
# schema bootstrap (ідемпотентно)
# ──────────────────────────────────────────────
def _ensure_schema() -> None:
    with get_conn() as c:
        cur = c.cursor()
        # Колонкова схема (один рядок на user_id)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS user_settings(
          id             INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id        INTEGER NOT NULL UNIQUE,
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
        # Додаємо відсутні колонки (мʼяко)
        cur.execute("PRAGMA table_info(user_settings)")
        have = {r[1] for r in cur.fetchall()}
        add_cols = {
            "timeframe":       "ALTER TABLE user_settings ADD COLUMN timeframe TEXT DEFAULT '15m'",
            "autopost":        "ALTER TABLE user_settings ADD COLUMN autopost INTEGER DEFAULT 0",
            "autopost_tf":     "ALTER TABLE user_settings ADD COLUMN autopost_tf TEXT DEFAULT '15m'",
            "autopost_rr":     "ALTER TABLE user_settings ADD COLUMN autopost_rr REAL DEFAULT 1.5",
            "rr_threshold":    "ALTER TABLE user_settings ADD COLUMN rr_threshold REAL DEFAULT 1.5",
            "model_key":       "ALTER TABLE user_settings ADD COLUMN model_key TEXT DEFAULT 'auto'",
            "locale":          "ALTER TABLE user_settings ADD COLUMN locale TEXT DEFAULT 'uk'",
            "daily_tracker":   "ALTER TABLE user_settings ADD COLUMN daily_tracker INTEGER DEFAULT 0",
            "daily_rr":        "ALTER TABLE user_settings ADD COLUMN daily_rr REAL DEFAULT 3.0",
            "winrate_tracker": "ALTER TABLE user_settings ADD COLUMN winrate_tracker INTEGER DEFAULT 0",
        }
        for col, ddl in add_cols.items():
            if col not in have:
                try:
                    cur.execute(ddl)
                except sqlite3.OperationalError:
                    pass
        c.commit()

_ensure_schema()

# ──────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────
def ensure_user_row(user_id: int) -> None:
    with get_conn() as c:
        c.execute("""
            INSERT INTO user_settings(user_id) VALUES (?)
            ON CONFLICT(user_id) DO NOTHING
        """, (user_id,))
        c.commit()

def get_user_settings(user_id: int) -> Dict[str, Any]:
    ensure_user_row(user_id)
    with get_conn() as c:
        cur = c.execute("""
            SELECT user_id, timeframe, autopost, autopost_tf, autopost_rr,
                   rr_threshold, model_key, locale, daily_tracker, daily_rr, winrate_tracker
            FROM user_settings WHERE user_id=?
        """, (user_id,))
        row = cur.fetchone()
        if not row:
            return {}
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))

def set_user_settings(user_id: int, **kwargs: Any) -> None:
    """
    Гнучкий апдейт полів user_settings.
    Приклад: set_user_settings(123, autopost_rr=2.0, autopost=1)
    """
    if not kwargs:
        return
    ensure_user_row(user_id)
    cols = [f"{k}=?" for k in kwargs.keys()]
    vals = list(kwargs.values()) + [user_id]
    with get_conn() as c:
        c.execute(f"UPDATE user_settings SET {', '.join(cols)} WHERE user_id=?", vals)
        c.commit()
