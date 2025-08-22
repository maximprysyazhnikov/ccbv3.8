import os, sqlite3, time, random
DB = os.getenv("DB_PATH") or os.getenv("SQLITE_PATH") or os.getenv("DATABASE_PATH") or "data/app.db"
os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
conn = sqlite3.connect(DB); cur = conn.cursor()

# таблиці (мінімум полів, яких вистачить сервісам)
cur.execute("""CREATE TABLE IF NOT EXISTS user_settings(
  user_id INTEGER PRIMARY KEY,
  timeframe TEXT, autopost INTEGER, autopost_tf TEXT, autopost_rr REAL,
  model_key TEXT, locale TEXT,
  daily_tracker INTEGER DEFAULT 1, daily_rr REAL DEFAULT 3.0,
  winrate_tracker INTEGER DEFAULT 1, rr_threshold REAL DEFAULT 1.5
)""")
cur.execute("""CREATE TABLE IF NOT EXISTS signals(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER, symbol TEXT, tf TEXT, direction TEXT,
  entry REAL, sl REAL, tp REAL, rr REAL,
  status TEXT, pnl_pct REAL,
  ts_created INTEGER, ts_closed INTEGER
)""")

uid = int(os.getenv("TEST_UID", "1468793208"))  # підстав свій user id
cur.execute("INSERT OR IGNORE INTO user_settings(user_id, timeframe, locale, daily_tracker, winrate_tracker, daily_rr, rr_threshold) VALUES(?,?,?,?,?,?,?)",
            (uid, "15m", "uk", 1, 1, 3.0, 1.5))

now = int(time.time()); day0 = now - (now % 86400)
rows = [
    # сьогодні: 2 WIN RR>=3, 1 LOSS RR>=3
    (uid,"BTCUSDT","15m","LONG", 60000, 59000, 63000, 3.0, "WIN",  +5.0, day0+3600, day0+7200),
    (uid,"ETHUSDT","15m","SHORT",3500,  3600,  3300,  3.0, "WIN",  +5.8, day0+8000, day0+11000),
    (uid,"ADAUSDT","15m","LONG", 0.40,  0.37,  0.52,  4.0, "LOSS", -7.5, day0+12000, day0+15000),
    # вчора: для winrate
    (uid,"SOLUSDT","1h","LONG", 150.0, 140.0, 180.0, 3.0, "WIN", +10.0, day0-40000, day0-38000),
]
cur.executemany("""INSERT INTO signals(user_id,symbol,tf,direction,entry,sl,tp,rr,status,pnl_pct,ts_created,ts_closed)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
conn.commit(); conn.close()
print("✅ Seeded.")
