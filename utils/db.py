# utils/db.py
from __future__ import annotations
import os
import sqlite3
import contextlib

def _resolve_db_path() -> str:
    # 1) читаємо кожного разу з env, щоб не було проблем із порядком імпортів
    p = os.environ.get("DB_PATH", "/data/bot.db")
    # 2) якщо шлях відносний — створимо базову теку
    base = os.path.dirname(p) or "."
    os.makedirs(base, exist_ok=True)  # не впаде, якщо /data вже примонтовано
    return p

@contextlib.contextmanager
def get_conn():
    db_path = _resolve_db_path()
    # timeout/PRAGMAs підлаштовуй під себе
    con = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    try:
        yield con
    finally:
        try:
            con.close()
        except Exception:
            pass
