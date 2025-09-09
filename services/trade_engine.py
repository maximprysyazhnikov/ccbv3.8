import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

DB_PATH = os.getenv("DB_PATH", "storage/bot.db")

def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def get_setting(key: str, default: str) -> str:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return (row["value"] if row else default)

def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value;",
            (key, value),
        )

def _get_open_trade(conn, symbol: str, timeframe: str):
    return conn.execute(
        "SELECT * FROM trades WHERE symbol=? AND timeframe=? AND status='OPEN' "
        "ORDER BY opened_at DESC LIMIT 1",
        (symbol, timeframe),
    ).fetchone()

def _rr(entry: float, sl: float, tp: float):
    try:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk <= 0:
            return None
        return reward / risk
    except Exception:
        return None

def _round(x: float) -> float:
    return float(f"{x:.6f}")

def open_trade_from_signal(signal: Dict) -> Optional[int]:
    """
    Idempotent open - only if no OPEN trade exists for (symbol,timeframe).
    Expected keys in `signal` (best effort):
      - id (signal_id) | symbol | timeframe | direction ('LONG'/'SHORT')
      - entry | sl | tp | rr (optional)
    """
    symbol = signal.get("symbol")
    timeframe = signal.get("timeframe") or signal.get("tf") or "1h"
    direction = (signal.get("direction") or "").upper()
    if direction not in ("LONG", "SHORT"):
        return None

    entry = float(signal.get("entry"))
    sl = float(signal.get("sl"))
    tp = float(signal.get("tp"))
    rr_planned = signal.get("rr")
    if rr_planned is None:
        rr_planned = _rr(entry, sl, tp)

    signal_id = signal.get("id")
    size_usd = float(get_setting("sim_usd_per_trade", "100"))
    fees_bps = int(get_setting("fees_bps", "10"))

    with _connect() as conn:
        if _get_open_trade(conn, symbol, timeframe):
            return None
        cur = conn.execute(
            "INSERT INTO trades(signal_id,symbol,timeframe,direction,entry,sl,tp,opened_at,"
            "size_usd,fees_bps,rr_planned,status) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                signal_id, symbol, timeframe, direction,
                _round(entry), _round(sl), _round(tp),
                _now_iso(), size_usd, fees_bps, rr_planned, "OPEN",
            ),
        )
        return cur.lastrowid

def _close_pnl(direction: str, entry: float, close: float, size_usd: float, fees_bps: int) -> Tuple[float, float]:
    qty = size_usd / entry  # simulated quantity
    gross = (close - entry) * qty if direction == "LONG" else (entry - close) * qty
    # round-trip fees on notional (open+close): approx 2 legs * bps
    notional = qty * entry + qty * close
    fees = (fees_bps / 10000.0) * notional
    pnl_usd = gross - fees
    pnl_pct = (pnl_usd / size_usd) * 100.0
    return (_round(pnl_usd), _round(pnl_pct))

def close_trade(symbol: str, timeframe: str, price: float, reason: str, win_loss_hint: Optional[str] = None) -> Optional[int]:
    with _connect() as conn:
        tr = _get_open_trade(conn, symbol, timeframe)
        if not tr:
            return None
        pnl_usd, pnl_pct = _close_pnl(tr["direction"], float(tr["entry"]), float(price), float(tr["size_usd"]), int(tr["fees_bps"]))
        rr_realized = None
        if tr["sl"] is not None and float(tr["sl"]) != float(tr["entry"]):
            rr_realized = abs(float(price) - float(tr["entry"])) / abs(float(tr["entry"]) - float(tr["sl"]))
        status = win_loss_hint if win_loss_hint in ("WIN", "LOSS") else ("WIN" if pnl_usd > 0 else "LOSS")
        conn.execute(
            "UPDATE trades SET closed_at=?, close_price=?, close_reason=?, pnl_usd=?, pnl_pct=?, rr_realized=?, status=? "
            "WHERE id=?",
            (_now_iso(), _round(price), reason, pnl_usd, pnl_pct, rr_realized, status, tr["id"]),
        )
        return tr["id"]

def evaluate_open_trades(price_map: Optional[dict] = None) -> int:
    """
    Evaluates TP/SL hits for OPEN trades using provided price_map:
        { (symbol, timeframe): last_price }
    Returns number of closed trades.
    If no price_map supplied, it's a no-op (safe for schedulers).
    """
    if not price_map:
        return 0
    closed = 0
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM trades WHERE status='OPEN'").fetchall()
        for tr in rows:
            key = (tr["symbol"], tr["timeframe"])
            price = price_map.get(key)
            if price is None:
                continue
            entry, sl, tp = float(tr["entry"]), float(tr["sl"]), float(tr["tp"])
            if tr["direction"] == "LONG":
                if price >= tp:
                    close_trade(tr["symbol"], tr["timeframe"], price, "TP", win_loss_hint="WIN")
                    closed += 1
                elif price <= sl:
                    close_trade(tr["symbol"], tr["timeframe"], price, "SL", win_loss_hint="LOSS")
                    closed += 1
            else:  # SHORT
                if price <= tp:
                    close_trade(tr["symbol"], tr["timeframe"], price, "TP", win_loss_hint="WIN")
                    closed += 1
                elif price >= sl:
                    close_trade(tr["symbol"], tr["timeframe"], price, "SL", win_loss_hint="LOSS")
                    closed += 1
    return closed

def handle_neutral_transition(symbol: str, timeframe: str, price: float, atr: Optional[float], mode: Optional[str] = None) -> Optional[str]:
    """
    Applies Neutral policy to OPEN trade if present.
    mode: CLOSE | TRAIL | IGNORE (defaults to settings.neutral_mode)
    Returns action string or None.
    """
    mode = (mode or get_setting("neutral_mode", "TRAIL")).upper()
    with _connect() as conn:
        tr = _get_open_trade(conn, symbol, timeframe)
        if not tr:
            return None
        if mode == "IGNORE":
            return "IGNORED"
        if mode == "CLOSE":
            close_trade(symbol, timeframe, price, "NEUTRAL_CLOSE")
            return "CLOSED"
        # TRAIL mode
        entry = float(tr["entry"])
        sl = float(tr["sl"])
        # Fallback ATR if missing
        if atr is None or atr <= 0:
            atr = 0.005 * price  # 0.5% fallback band
        if tr["direction"] == "LONG":
            new_sl = max(sl, max(entry, price - 0.5 * atr))
            if new_sl > sl:
                conn.execute("UPDATE trades SET sl=? WHERE id=?", (_round(new_sl), tr["id"]))
                return f"TRAIL_SL→{_round(new_sl)}"
        else:
            new_sl = min(sl, min(entry, price + 0.5 * atr))
            if new_sl < sl:
                conn.execute("UPDATE trades SET sl=? WHERE id=?", (_round(new_sl), tr["id"]))
                return f"TRAIL_SL→{_round(new_sl)}"
        return "TRAIL_NOCHANGE"
