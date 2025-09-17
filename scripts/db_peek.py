# scripts/db_peek.py
import sqlite3
import os
import sys

DB_PATH = os.getenv("DB_PATH", "storage/bot.db")

def peek_table(table: str, limit: int = 5):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        rows = cur.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        if not rows:
            print(f"== {table} (last {limit}) ==\n(empty)\n")
            return
        print(f"== {table} (last {limit}) ==")
        for r in rows:
            print(dict(r))
        print()
    finally:
        conn.close()

if __name__ == "__main__":
    # можна передати таблиці як аргументи: python scripts/db_peek.py trades signals
    tables = sys.argv[1:] or ["trades", "signals"]
    for t in tables:
        peek_table(t, limit=5)
