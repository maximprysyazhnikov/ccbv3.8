from __future__ import annotations
import os, sqlite3, time, math, logging
from typing import List
from market_data.candles import get_ohlcv
from services.signals_repo import close_signal

log = logging.getLogger("signal_closer")

DB = os.getenv("DB_PATH") or os.getenv("SQLITE_PATH") or os.getenv("DATABASE_PATH") or "storage/bot.db"

def _conn():
    import os
    os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
    c = sqlite3.connect(DB, timeout=30); c.row_factory = sqlite3.Row
    return c

def _pnl_pct(direction: str, entry: float, stop: float, tp: float, last: float) -> tuple[str, float]:
    """
    Визначаємо що торкнулося першим (на спрощенні):
    - якщо LONG і last >= tp => WIN (tp)
    - якщо LONG і last <= stop => LOSS (sl)
    - SHORT симетрично
    Повертає (status, pnl_pct)
    """
    if any(x is None or (isinstance(x,float) and (math.isnan(x) or math.isinf(x))) for x in (entry, stop, tp)):
        return ("OPEN", 0.0)

    if direction == "LONG":
        if last >= tp:
            return ("WIN", (tp/entry - 1.0) * 100.0)
        if last <= stop:
            return ("LOSS", (stop/entry - 1.0) * 100.0)
    elif direction == "SHORT":
        if last <= tp:
            return ("WIN", (entry/tp - 1.0) * 100.0)
        if last >= stop:
            return ("LOSS", (entry/stop - 1.0) * 100.0)
    return ("OPEN", 0.0)

def run_once():
    # беремо відкриті сигнали
    with _conn() as c:
        cur = c.cursor()
        cur.execute("""
            SELECT id, symbol, timeframe, direction, entry, stop, tp, size_usd
            FROM signals
            WHERE status='OPEN'
        """)
        rows = cur.fetchall()

    for r in rows:
        sym = r["symbol"]; tf = r["timeframe"]
        data = get_ohlcv(sym, tf, 2)
        if not data:
            continue
        last = float(data[-1]["close"])
        status, pnl = _pnl_pct(r["direction"], r["entry"], r["stop"], r["tp"], last)
        if status in ("WIN","LOSS"):
            try:
                close_signal(r["id"], status=status, pnl_pct=float(pnl), size_usd=float(r["size_usd"] or 100.0))
            except Exception as e:
                log.warning("close failed %s: %s", r["id"], e)
