# storage/seed_demo.py
from __future__ import annotations
import os, sqlite3, time
DB_PATH = os.getenv("DB_PATH", "storage/app.db")

def seed(uid: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    now = int(time.time())
    cur.execute("INSERT OR IGNORE INTO user_settings(user_id,autopost,locale) VALUES(?,0,'uk')", (uid,))
    rows = [
        # id, user_id, symbol, tf, direction, entry, sl, tp, rr, ts_created, ts_closed, status, pnl_pct
        (uid, "BTCUSDT", "15m", "LONG", 100.0, 95.0, 109.0, 1.80, now-3600*20, now-3600*18, "WIN", 9.0),
        (uid, "ETHUSDT", "15m", "SHORT",  50.0, 55.0,  47.0, 0.60, now-3600*10, now-3600* 9, "LOSS", -10.0),
        (uid, "SOLUSDT", "1h",  "LONG",  10.0,  9.5,  11.5, 3.00, now-3600*30, now-3600*28, "WIN", 15.0),
    ]
    for (u,sym,tf,dir,entry,sl,tp,rr,tc,td,st,pnl) in rows:
        cur.execute(
            "INSERT INTO signals(user_id,symbol,tf,direction,entry,sl,tp,rr,ts_created,ts_closed,status,pnl_pct) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (u,sym,tf,dir,entry,sl,tp,rr,tc,td,st,pnl)
        )
    con.commit(); con.close(); print("✅ demo rows inserted")

if __name__ == "__main__":
    seed(uid=int(os.getenv("SEED_UID","1468793208")))
