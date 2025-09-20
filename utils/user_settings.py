# utils/user_settings.py
from __future__ import annotations
import sqlite3
import logging
from typing import Any, Dict
from utils.db import get_conn  # єдиний шлях до БД

log = logging.getLogger("user_settings")

# ──────────────────────────────────────────────
# schema bootstrap (ідемпотентно) + МІГРАЦІЯ UNIQUE(user_id)
# ──────────────────────────────────────────────
def _ensure_schema() -> None:
    with get_conn() as c:
        cur = c.cursor()

        # 1) Базова таблиця (для нових БД одразу з UNIQUE)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS user_settings(
          id              INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id         INTEGER NOT NULL UNIQUE,
          timeframe       TEXT    DEFAULT '15m',
          autopost        INTEGER DEFAULT 0,
          autopost_tf     TEXT    DEFAULT '15m',
          autopost_rr     REAL    DEFAULT 1.5,
          rr_threshold    REAL    DEFAULT 1.5,
          model_key       TEXT    DEFAULT 'auto',
          locale          TEXT    DEFAULT 'uk',
          daily_tracker   INTEGER DEFAULT 0,
          daily_rr        REAL    DEFAULT 3.0,
          winrate_tracker INTEGER DEFAULT 0
        )
        """)

        # 2) Ідемпотентно додаємо відсутні колонки (для старих БД)
        cur.execute("PRAGMA table_info(user_settings)")
        have_cols = {r[1] for r in cur.fetchall()}
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
            if col not in have_cols:
                try:
                    cur.execute(ddl)
                except sqlite3.OperationalError:
                    pass

        # 3) Гарантуємо унікальність user_id для старих таблиць:
        #    - якщо індексу нема → створимо,
        #    - але перед цим приберемо дублікати user_id (залишимо запис із найбільшим id)
        cur.execute("PRAGMA index_list(user_settings)")
        idx_names = {r[1] for r in cur.fetchall()}
        if "idx_user_settings_user_id" not in idx_names:
            try:
                # приберемо дублі, якщо вони є
                cur.executescript("""
                DELETE FROM user_settings
                WHERE id IN (
                    SELECT id FROM (
                        SELECT id,
                               ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY id DESC) AS rn
                        FROM user_settings
                    ) t
                    WHERE t.rn > 1
                );
                """)
            except sqlite3.OperationalError:
                # старі SQLite без window-функцій: fallback через self-join
                cur.executescript("""
                DELETE FROM user_settings
                WHERE id IN (
                    SELECT u1.id
                    FROM user_settings u1
                    JOIN user_settings u2
                      ON u1.user_id = u2.user_id AND u1.id < u2.id
                );
                """)

            # створюємо унікальний індекс (ідеально для ON CONFLICT(user_id))
            try:
                cur.execute("CREATE UNIQUE INDEX idx_user_settings_user_id ON user_settings(user_id)")
            except sqlite3.OperationalError:
                pass

        c.commit()

_ensure_schema()

# ──────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────
def ensure_user_row(user_id: int) -> None:
    """Гарантує якірний рядок для user_id (щоб UPDATE завжди мав що оновлювати)."""
    with get_conn() as c:
        # INSERT OR IGNORE працює як з унікальним індексом, так і без нього (на випадок дуже старої БД)
        c.execute("INSERT OR IGNORE INTO user_settings(user_id) VALUES (?)", (user_id,))
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
        cur = c.execute(f"UPDATE user_settings SET {', '.join(cols)} WHERE user_id=?", vals)
        c.commit()
        log.info("set_user_settings uid=%s updated=%s data=%s", user_id, cur.rowcount, kwargs)

# (опційно) для швидкого дебагу:
def _debug_dump() -> None:
    with get_conn() as c:
        rows = c.execute("SELECT user_id, autopost, autopost_rr, rr_threshold FROM user_settings").fetchall()
        log.info("[debug_dump] %s", rows)
