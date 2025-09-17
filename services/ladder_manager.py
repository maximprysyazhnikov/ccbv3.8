from __future__ import annotations
import os, sqlite3, json
from typing import List, Tuple, Optional

DB_PATH = os.getenv("DB_PATH") or "storage/bot.db"

def _conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c

def plan_ladder_entries(direction: str, entry0: float, sl: float, atr: float, spacing_mode: str, spacing: float, n_buckets: int) -> List[Tuple[float, float]]:
    """Повертає список (price, rr_multiple) для N-1 додаткових відер."""
    out = []
    spacing_mode = (spacing_mode or "ATR").upper()
    for i in range(1, n_buckets):
        if spacing_mode == "ATR":
            delta = spacing * atr * i
            price = entry0 - delta if direction == "LONG" else entry0 + delta
        else:  # PERCENT
            k = spacing * i / 100.0
            price = entry0 * (1 - k) if direction == "LONG" else entry0 * (1 + k)
        out.append((float(price), float(i)))
    return out

def on_fill_leg(trade_id: int, price: float, qty: float):
    with _conn() as c:
        tr = c.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
        if not tr:
            return
        old_qty = float(tr["qty"] or 0.0) if "qty" in tr.keys() else 0.0
        old_avg = float(tr["avg_entry"] or tr["entry"])
        new_qty = old_qty + qty if old_qty else qty
        new_avg = (old_avg*old_qty + price*qty) / max(1e-9, new_qty)

        c.execute("UPDATE trades SET avg_entry=?, filled_buckets=COALESCE(filled_buckets,0)+1 WHERE id=?", (new_avg, trade_id))
        c.execute("INSERT INTO trade_legs(trade_id, side, qty, price, filled_at) VALUES (?,?,?,?,datetime('now'))", (trade_id, "BUY" if price<=new_avg else "SELL", qty, price))
