from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager

# Визначаємо шлях до БД
DB_PATH = os.getenv("DB_PATH")
if not DB_PATH:
    # Railway монтує volume у /data
    DB_PATH = "/data/bot.db"


@contextmanager
def get_conn() -> sqlite3.Connection:
    """
    Повертає SQLite-зʼєднання з БД у /data/bot.db (Railway).
    Автоматично створює директорію, якщо її немає.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        yield con
    finally:
        con.close()
