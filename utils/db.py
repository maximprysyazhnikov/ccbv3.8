from __future__ import annotations
import os, sqlite3
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "storage/bot.db")

@contextmanager
def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        yield con
    finally:
        con.close()
