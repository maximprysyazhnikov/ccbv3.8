# utils/signals_db.py
from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List

DB_PATH = Path("storage") / "bot.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            tf TEXT NOT NULL,
            direction TEXT NOT NULL,  -- LONG/SHORT
            entry REAL NOT NULL,
            sl REAL NOT NULL,
            tp REAL NOT NULL,
            rr REAL,
            ts_created INTEGER NOT NULL,
            ts_closed INTEGER,
            status TEXT NOT NULL,     -- OPEN/WIN/LOSS/SKIP
            pnl_pct REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS autopost_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            tf TEXT NOT NULL,
            rr REAL,
            ts_sent INTEGER NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_apl_user_sym_tf ON autopost_log(user_id, symbol, tf, ts_sent)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sig_user_status ON signals(user_id, status)")
    return conn

def insert_signal_open(user_id: int, symbol: str, tf: str, direction: str,
                       entry: float, sl: float, tp: float, rr: Optional[float],
                       ts_created: int) -> int:
    with _conn() as c:
        cur = c.execute("""
            INSERT INTO signals(user_id, symbol, tf, direction, entry, sl, tp, rr, ts_created, status)
            VALUES(?,?,?,?,?,?,?,?,?,?)
        """, (user_id, symbol, tf, direction, float(entry), float(sl), float(tp), rr, ts_created, "OPEN"))
        return int(cur.lastrowid)

def update_signal_close(signal_id: int, status: str, ts_closed: int, pnl_pct: float) -> None:
    with _conn() as c:
        c.execute("""
            UPDATE signals
            SET status=?, ts_closed=?, pnl_pct=?
            WHERE id=?
        """, (status, ts_closed, pnl_pct, signal_id))

def add_autopost_log(user_id: int, symbol: str, tf: str, rr: float, ts_sent: int) -> None:
    with _conn() as c:
        c.execute("""
            INSERT INTO autopost_log(user_id, symbol, tf, rr, ts_sent)
            VALUES(?,?,?,?,?)
        """, (user_id, symbol, tf, rr, ts_sent))

def has_recent_autopost(user_id: int, symbol: str, tf: str, since_ts: int) -> bool:
    with _conn() as c:
        row = c.execute("""
            SELECT 1 FROM autopost_log
            WHERE user_id=? AND symbol=? AND tf=? AND ts_sent>=?
            LIMIT 1
        """, (user_id, symbol, tf, since_ts)).fetchone()
        return bool(row)

def open_signals_for_user(user_id: int) -> List[Dict[str, Any]]:
    with _conn() as c:
        rows = c.execute("""
            SELECT * FROM signals WHERE user_id=? AND status='OPEN'
        """, (user_id,)).fetchall()
        return [dict(r) for r in rows]
