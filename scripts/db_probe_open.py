# scripts/db_probe_open.py
import os, sqlite3, time
DB_PATH = os.getenv("DB_PATH") or "storage/bot.db"
now = int(time.time())

with sqlite3.connect(DB_PATH, timeout=30) as c:
    c.row_factory = sqlite3.Row
    cur = c.cursor()

    # 1) скільки відкриті за віковими кошиками
    for name, sec in [("≤6h", 6*3600), ("≤24h", 24*3600), ("≤3d", 3*86400), (">3d", 10**9)]:
        cur.execute("""
            SELECT COUNT(*) FROM signals
            WHERE status='OPEN' AND (? - ts_created) BETWEEN 0 AND ?
        """, (now, sec))
        print(f"OPEN {name}:", cur.fetchone()[0])

    # 2) чи є в них entry/stop/tp/rr
    cur.execute("""
        SELECT
          SUM(CASE WHEN entry IS NULL OR stop IS NULL OR tp IS NULL THEN 1 ELSE 0 END) AS miss_levels,
          SUM(CASE WHEN rr IS NULL OR rr<=0 THEN 1 ELSE 0 END) AS bad_rr
        FROM signals WHERE status='OPEN'
    """)
    r = cur.fetchone()
    print("OPEN missing levels:", r["miss_levels"], "| bad_rr:", r["bad_rr"])

    # 3) топ символів з OPEN
    cur.execute("""
        SELECT symbol, COUNT(*) AS n
        FROM signals
        WHERE status='OPEN'
        GROUP BY symbol
        ORDER BY n DESC LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"OPEN {row['symbol']}: {row['n']}")
