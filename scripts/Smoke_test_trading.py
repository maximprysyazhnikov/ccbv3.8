# scripts/smoke_test_trading.py
from __future__ import annotations
import argparse
import sqlite3
import sys
import time
from datetime import datetime, timedelta

DB_PATH = "storage/bot.db"

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def check_schema():
    conn = _conn()
    print("== schema check ==")
    for t in ("settings","trades","signals"):
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(t,)
        ).fetchone()
        print(f"- {t}: {'OK' if row else 'NOT FOUND'}")
    conn.close()

def get_setting(key: str, default: str|None=None) -> str|None:
    conn = _conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return (row["value"] if row else default)

def set_setting(key: str, value: str):
    conn = _conn()
    conn.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit(); conn.close()

def show_settings():
    conn = _conn()
    print("== settings ==")
    for r in conn.execute("SELECT key,value FROM settings ORDER BY key"):
        print(f"- {r['key']}={r['value']}")
    conn.close()

def open_dummy_trade(symbol="BTCUSDT", timeframe="15m", direction="LONG",
                     entry=60000.0, sl=59400.0, tp=61200.0, rr=2.0) -> int|None:
    """
    Створює запис у trades, імітуючи open_trade_from_signal().
    Не потребує імпорту сервісів — працює напряму з БД.
    """
    conn = _conn()
    # Переконаймося, що таблиця існує (міграція вже мала це зробити)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS trades (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      signal_id INTEGER,
      symbol TEXT,
      timeframe TEXT,
      direction TEXT CHECK(direction IN ('LONG','SHORT')),
      entry REAL,
      sl REAL,
      tp REAL,
      opened_at TEXT,
      closed_at TEXT,
      close_price REAL,
      close_reason TEXT,
      size_usd REAL DEFAULT 100.0,
      fees_bps INTEGER DEFAULT 10,
      pnl_usd REAL,
      pnl_pct REAL,
      rr_planned REAL,
      rr_realized REAL,
      status TEXT CHECK(status IN ('OPEN','WIN','LOSS','CLOSED'))
    );
    """)
    now = datetime.utcnow().isoformat(timespec="seconds")
    conn.execute(
        """INSERT INTO trades(signal_id, symbol, timeframe, direction, entry, sl, tp,
                              opened_at, status, rr_planned, size_usd, fees_bps)
           VALUES(?,?,?,?,?,?,?,?, 'OPEN', ?, 100.0, 10)""",
        (int(time.time()), symbol, timeframe, direction, float(entry), float(sl), float(tp),
         now, float(rr))
    )
    tid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit(); conn.close()
    return int(tid)

def list_recent_trades(limit=5):
    conn = _conn()
    rows = conn.execute("""
      SELECT id, symbol, timeframe, direction, entry, sl, tp, status, close_reason,
             pnl_usd, rr_planned, rr_realized, opened_at, closed_at
      FROM trades ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    print("== recent trades ==")
    if not rows:
        print("(empty)")
        return
    for r in rows:
        print(f"#{r['id']} {r['symbol']} {r['timeframe']} {r['direction']} "
              f"entry={r['entry']} sl={r['sl']} tp={r['tp']} "
              f"status={r['status']} reason={r['close_reason']} "
              f"pnl={r['pnl_usd']} rr={r['rr_realized']} "
              f"opened={r['opened_at']} closed={r['closed_at']}")

def neutral_close_latest(price: float):
    """
    Емуляція CLOSE на NEUTRAL: закриваємо останню OPEN-угоду за переданою ціною.
    """
    conn = _conn()
    row = conn.execute("SELECT * FROM trades WHERE status='OPEN' ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        print("no OPEN trades to close"); return
    now = datetime.utcnow().isoformat(timespec="seconds")
    # спрощений розрахунок pnl/rr
    direction = row["direction"]
    entry = float(row["entry"])
    fees = (row["fees_bps"] or 10) / 10000.0
    size = float(row["size_usd"] or 100.0)
    pnl = 0.0
    if direction == "LONG":
        pnl = size * ((price - entry) / entry) - size * fees
        rr_real = (price - entry) / max(1e-9, (entry - float(row["sl"])))
    else:
        pnl = size * ((entry - price) / entry) - size * fees
        rr_real = (entry - price) / max(1e-9, (float(row["sl"]) - entry))

    conn.execute("""UPDATE trades
                    SET status='CLOSED', close_reason='NEUTRAL_CLOSE',
                        closed_at=?, close_price=?, pnl_usd=?, rr_realized=?
                    WHERE id=?""",
                 (now, float(price), float(pnl), float(rr_real), row["id"]))
    conn.commit(); conn.close()
    print(f"closed trade #{row['id']} at price={price} (NEUTRAL_CLOSE)")

def neutral_trail_latest(price: float, atr: float):
    """
    Емуляція TRAIL на NEUTRAL: підтягнути SL (0.5*ATR, не гірше entry і не гірше старого SL).
    """
    conn = _conn()
    row = conn.execute("SELECT * FROM trades WHERE status='OPEN' ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        print("no OPEN trades to trail"); return
    direction = row["direction"]
    entry = float(row["entry"]); sl = float(row["sl"])
    if direction == "LONG":
        new_sl = max(sl, max(entry, price - 0.5*atr))
    else:
        new_sl = min(sl, min(entry, price + 0.5*atr))
    conn.execute("UPDATE trades SET sl=? WHERE id=?", (float(new_sl), row["id"]))
    conn.commit(); conn.close()
    print(f"trailed trade #{row['id']} sl -> {new_sl}")

def kpis_last_24h():
    """
    Прості KPI за 24h: winrate, pnl_usd, trades, avg_rr, rr3_usd100.
    """
    conn = _conn()
    since = (datetime.utcnow() - timedelta(hours=24)).isoformat(timespec="seconds")
    rows = conn.execute("""
      SELECT status, rr_planned, rr_realized, pnl_usd
      FROM trades
      WHERE opened_at >= ?
    """, (since,)).fetchall()
    conn.close()
    if not rows:
        return {"winrate": 0.0, "pnl_usd": 0.0, "trades": 0, "avg_rr": 0.0, "rr3_usd100": 0.0}
    wins = sum(1 for r in rows if (r["status"] in ("WIN","CLOSED") and (r["pnl_usd"] or 0) > 0))
    trades = len(rows)
    pnl = sum(float(r["pnl_usd"] or 0) for r in rows)
    avg_rr = 0.0
    rr_vals = [float(r["rr_realized"] or 0) for r in rows if r["rr_realized"] is not None]
    if rr_vals:
        avg_rr = sum(rr_vals) / max(1, len(rr_vals))
    rr3 = [float(r["pnl_usd"] or 0) for r in rows if (r["rr_planned"] or 0) >= 3.0]
    rr3_usd100 = sum(rr3) if rr3 else 0.0
    winrate = round(100.0 * wins / max(1, trades), 2)
    return {"winrate": winrate, "pnl_usd": round(pnl, 2), "trades": trades,
            "avg_rr": round(avg_rr, 2), "rr3_usd100": round(rr3_usd100, 2)}

def print_kpis():
    k = kpis_last_24h()
    print("== KPI (24h) ==")
    print(f"- Winrate: {k['winrate']}%")
    print(f"- PnL: {k['pnl_usd']}$")
    print(f"- Trades: {k['trades']}")
    print(f"- Avg RR: {k['avg_rr']}")
    print(f"- $100 on RR≥3: {k['rr3_usd100']}$")

def main():
    p = argparse.ArgumentParser(description="ccbv3 trading smoke test")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("schema", help="перевірити наявність таблиць settings/trades/signals")
    sub.add_parser("settings", help="показати всі settings")

    sp_set = sub.add_parser("set-mode", help="встановити neutral_mode (CLOSE|TRAIL|IGNORE)")
    sp_set.add_argument("mode", choices=["CLOSE","TRAIL","IGNORE"])

    sp_open = sub.add_parser("open", help="відкрити тестову угоду")
    sp_open.add_argument("--symbol", default="BTCUSDT")
    sp_open.add_argument("--tf", default="15m")
    sp_open.add_argument("--dir", choices=["LONG","SHORT"], default="LONG")
    sp_open.add_argument("--entry", type=float, default=60000.0)
    sp_open.add_argument("--sl", type=float, default=59400.0)
    sp_open.add_argument("--tp", type=float, default=61200.0)
    sp_open.add_argument("--rr", type=float, default=2.0)

    sp_neu_c = sub.add_parser("neutral-close", help="закрити останню OPEN угоду по ціні (NEUTRAL_CLOSE)")
    sp_neu_c.add_argument("price", type=float)

    sp_neu_t = sub.add_parser("neutral-trail", help="підтягнути SL останньої OPEN (TRAIL) за ціною та ATR")
    sp_neu_t.add_argument("price", type=float)
    sp_neu_t.add_argument("--atr", type=float, default=150.0)

    sub.add_parser("trades", help="показати останні 5 угод")
    sub.add_parser("kpi", help="показати KPI за 24h")

    sp_watch = sub.add_parser("watch", help="періодично показувати KPI/останню угоду")
    sp_watch.add_argument("--interval", type=int, default=15)

    args = p.parse_args()

    if args.cmd == "schema":
        check_schema(); return
    if args.cmd == "settings":
        show_settings(); return
    if args.cmd == "set-mode":
        set_setting("neutral_mode", args.mode)
        print("neutral_mode set ->", args.mode)
        show_settings(); return
    if args.cmd == "open":
        tid = open_dummy_trade(args.symbol, args.tf, args.dir, args.entry, args.sl, args.tp, args.rr)
        print("opened trade id:", tid)
        list_recent_trades(); return
    if args.cmd == "neutral-close":
        neutral_close_latest(args.price); list_recent_trades(); print_kpis(); return
    if args.cmd == "neutral-trail":
        neutral_trail_latest(args.price, args.atr); list_recent_trades(); return
    if args.cmd == "trades":
        list_recent_trades(); return
    if args.cmd == "kpi":
        print_kpis(); return
    if args.cmd == "watch":
        try:
            while True:
                list_recent_trades(limit=1)
                print_kpis()
                print(f"(refresh in {args.interval}s) ----")
                time.sleep(max(1, args.interval))
        except KeyboardInterrupt:
            print("\nbye"); return

    p.print_help()

if __name__ == "__main__":
    main()
