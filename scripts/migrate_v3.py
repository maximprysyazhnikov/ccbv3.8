import os, sqlite3

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "users.db")
SQL_PATH = os.path.join(os.path.dirname(__file__), "migrate_v3.sql")

def ensure_dir():
    os.makedirs(DB_DIR, exist_ok=True)

def run_sql():
    with open(SQL_PATH, "r", encoding="utf-8") as f:
        sql = f.read()
    con = sqlite3.connect(DB_PATH)
    con.executescript(sql)
    con.commit()
    con.close()

def alter_missing_columns():
    con = sqlite3.connect(DB_PATH)
    con.execute("CREATE TABLE IF NOT EXISTS user_settings (user_id INTEGER PRIMARY KEY)")
    need = {
        "timeframe": "TEXT DEFAULT '15m'",
        "autopost": "INTEGER DEFAULT 0",
        "autopost_tf": "TEXT DEFAULT '15m'",
        "autopost_rr": "REAL DEFAULT 1.5",
        "rr_threshold": "REAL DEFAULT 1.5",
        "model_key": "TEXT DEFAULT 'auto'",
        "locale": "TEXT DEFAULT 'uk'",
    }
    cur = con.execute("PRAGMA table_info(user_settings)")
    cols = {r[1] for r in cur.fetchall()}
    for c, ddl in need.items():
        if c not in cols:
            con.execute(f"ALTER TABLE user_settings ADD COLUMN {c} {ddl}")
    con.commit()
    con.close()

if __name__ == "__main__":
    ensure_dir()
    run_sql()
    alter_missing_columns()
    print("✅ migrate_v3 done")
