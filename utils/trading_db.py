from __future__ import annotations
import os, sqlite3, time
from typing import Dict, Any, List

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "users.db")

def _conn():
    os.makedirs(DB_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
    CREATE TABLE IF NOT EXISTS signals (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      symbol TEXT NOT NULL,
      tf TEXT NOT NULL,
      direction TEXT CHECK(direction IN ('LONG','SHORT')) NOT NULL,
      entry REAL NOT NULL,
      sl REAL NOT NULL,
      tp REAL NOT NULL,
      rr REAL NOT NULL,
      ts_created INTEGER NOT NULL,
      ts_closed INTEGER,
      status TEXT CHECK(status IN ('OPEN','WIN','LOSS','SKIP')) NOT NULL,
      pnl_pct REAL
    )""")
    con.execute("""
    CREATE TABLE IF NOT EXISTS autopost_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      symbol TEXT NOT NULL,
      tf TEXT NOT NULL,
      rr REAL NOT NULL,
      ts_sent INTEGER NOT NULL
    )""")
    con.commit()
    return con

def record_signal_open(user_id: int, symbol: str, tf: str, direction: str,
                       entry: float, sl: float, tp: float, rr: float) -> int:
    con = _conn()
    cur = con.execute("""INSERT INTO signals(user_id,symbol,tf,direction,entry,sl,tp,rr,ts_created,status)
                         VALUES (?,?,?,?,?,?,?,?,?, 'OPEN')""",
                      (user_id, symbol, tf, direction, float(entry), float(sl), float(tp), float(rr), int(time.time())))
    con.commit()
    rid = cur.lastrowid
    con.close()
    return rid

def recent_autopost_exists(user_id: int, symbol: str, tf: str, cooldown_secs: int) -> bool:
    con = _conn()
    since = int(time.time()) - int(cooldown_secs)
    cur = con.execute("""SELECT 1 FROM autopost_log
                         WHERE user_id=? AND symbol=? AND tf=? AND ts_sent>=? LIMIT 1""",
                      (user_id, symbol, tf, since))
    row = cur.fetchone()
    con.close()
    return bool(row)

def log_autopost(user_id: int, symbol: str, tf: str, rr: float) -> None:
    con = _conn()
    con.execute("INSERT INTO autopost_log(user_id,symbol,tf,rr,ts_sent) VALUES (?,?,?,?,?)",
                (user_id, symbol, tf, float(rr), int(time.time())))
    con.commit()
    con.close()

def get_open_signals() -> List[Dict[str, Any]]:
    con = _conn()
    cur = con.execute("""SELECT id,user_id,symbol,tf,direction,entry,sl,tp,rr,ts_created
                         FROM signals WHERE status='OPEN'""")
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    con.close()
    return rows

def close_signal(sig_id: int, status: str, pnl_pct: float) -> None:
    con = _conn()
    con.execute("UPDATE signals SET status=?, pnl_pct=?, ts_closed=? WHERE id=?",
                (status, float(pnl_pct), int(time.time()), sig_id))
    con.commit()
    con.close()

def pnl_summary(user_id: int, days: int = 30) -> Dict[str, Any]:
    con = _conn()
    since = int(time.time()) - int(days)*86400
    cur = con.execute("""
        SELECT
          SUM(CASE WHEN status='WIN'  THEN 1 ELSE 0 END),
          SUM(CASE WHEN status='LOSS' THEN 1 ELSE 0 END),
          AVG(rr),
          AVG(COALESCE(pnl_pct,0))
        FROM signals
        WHERE user_id=? AND status IN ('WIN','LOSS') AND ts_created>=?
    """, (user_id, since))
    wins, losses, avg_rr, avg_pnl = cur.fetchone() or (0,0,None,None)
    total = (wins or 0) + (losses or 0)
    winrate = (100.0 * (wins or 0) / total) if total else 0.0
    con.close()
    return {
        "wins": int(wins or 0),
        "losses": int(losses or 0),
        "trades": int(total),
        "winrate": float(winrate),
        "avg_rr": float(avg_rr or 0.0),
        "avg_pnl_pct": float(avg_pnl or 0.0),
    }
