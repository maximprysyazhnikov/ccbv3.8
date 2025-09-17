from __future__ import annotations
import re
import logging
import sqlite3
import math
from typing import Optional, Dict, List

from core_config import CFG

log = logging.getLogger("autopost_bridge")
DB_PATH = CFG.get("db_path", "storage/bot.db")

# Якщо маєш локальні свічки — використаємо для закриття REVERSED по ринку
try:
    from market_data.candles import get_ohlcv  # get_ohlcv(symbol, timeframe, n) -> list[{"close": ...}]
except Exception:
    get_ohlcv = None

# ──────────────────────────────────────────────────────────────────────────────
# Parsers for autopost text
# Example:
# 🤖 Autopost plan ETHUSDT [1h]
# Dir: LONG | RR≈2.4211
# Entry: 4588.0000 | SL: 4550.0000 | TP: 4680.0000
# ──────────────────────────────────────────────────────────────────────────────
_RE_HEADER = re.compile(r"Autopost plan\s+([A-Z0-9]+)\s+\[([^\]]+)\]", re.I)
_RE_DIR_RR = re.compile(r"Dir:\s*(LONG|SHORT)\s*\|\s*RR[≈~=]\s*([0-9.]+)", re.I)
_RE_LVLS   = re.compile(r"Entry:\s*([0-9.]+)\s*\|\s*SL:\s*([0-9.]+)\s*\|\s*TP:\s*([0-9.]+)", re.I)

def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def _parse(text: str) -> Optional[Dict]:
    body = text or ""
    m1 = _RE_HEADER.search(body)
    m2 = _RE_DIR_RR.search(body)
    m3 = _RE_LVLS.search(body)
    if not (m1 and m2 and m3):
        return None
    symbol, timeframe = m1.group(1).upper(), m1.group(2)
    direction, rr = m2.group(1).upper(), float(m2.group(2))
    entry, sl, tp = float(m3.group(1)), float(m3.group(2)), float(m3.group(3))
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,   # 'LONG' або 'SHORT'
        "rr": rr,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "source": "autopost",
    }

def _last_price(symbol: str, timeframe: str) -> Optional[float]:
    if get_ohlcv is None:
        return None
    try:
        bars = get_ohlcv(symbol, timeframe, 2)
        if not bars:
            return None
        return float(bars[-1]["close"])
    except Exception:
        return None

def _pnl_rr(direction: str, entry: float, sl: float, close_price: float, size_usd: float, fees_bps: int) -> tuple[float, float]:
    denom = abs(entry - sl) if sl is not None else 0.0
    rr_real = (abs(close_price - entry) / denom) if denom > 0 else 0.0
    if direction == "LONG":
        pnl_usd = size_usd * ((close_price - entry) / entry)
    else:
        pnl_usd = size_usd * ((entry - close_price) / entry)
    pnl_usd -= size_usd * (fees_bps / 10000.0) * 2.0
    return float(pnl_usd), float(rr_real)

def _has_open_trade(cur: sqlite3.Cursor, symbol: str, timeframe: str) -> bool:
    row = cur.execute(
        "SELECT 1 FROM trades WHERE symbol=? AND timeframe=? AND status='OPEN' LIMIT 1",
        (symbol, timeframe),
    ).fetchone()
    return bool(row)

def _find_open_trades(cur: sqlite3.Cursor, symbol: str, timeframe: str) -> List[sqlite3.Row]:
    return cur.execute(
        "SELECT * FROM trades WHERE symbol=? AND timeframe=? AND status='OPEN' ORDER BY id",
        (symbol, timeframe),
    ).fetchall()

def _close_trade(cur: sqlite3.Cursor, trade: sqlite3.Row, reason: str, at_price: Optional[float]):
    price = float(at_price if at_price is not None else trade["entry"])
    pnl, rr_real = _pnl_rr(
        direction=trade["direction"].upper(),
        entry=float(trade["entry"]),
        sl=float(trade["sl"]),
        close_price=price,
        size_usd=float(trade["size_usd"] or 100.0),
        fees_bps=int(trade["fees_bps"] or 10),
    )
    cur.execute(
        "UPDATE trades SET status='CLOSED', closed_at=datetime('now'), close_reason=?, pnl_usd=?, rr_realized=? WHERE id=?",
        (reason, pnl_usd, rr_real, trade_id),
    )

    if trade["signal_id"]:
        cur.execute("UPDATE signals SET status='CLOSED', closed_at=datetime('now') WHERE id=? AND status='OPEN'",
                    (int(trade["signal_id"]),))

def _insert_signal(cur: sqlite3.Cursor, plan: Dict, user_id: int) -> int:
    cur.execute(
        """
        INSERT INTO signals(user_id, symbol, timeframe, direction, entry, sl, tp, rr, source, status, opened_at)
        VALUES(?,?,?,?,?,?,?,?,?,'OPEN',datetime('now'))
        """,
        (
            int(user_id),
            plan["symbol"], plan["timeframe"], plan["direction"],
            float(plan["entry"]), float(plan["sl"]), float(plan["tp"]),
            float(plan["rr"]),
            plan.get("source","autopost"),
        ),
    )
    return int(cur.lastrowid)

def _insert_trade(cur: sqlite3.Cursor, plan: Dict, signal_id: Optional[int]) -> int:
    size_usd = float(CFG.get("sim_usd_per_trade", 100))
    fees_bps = int(CFG.get("fees_bps", 10))
    rr_planned = float(plan.get("rr") or 0.0)
    cur.execute(
        """
        INSERT INTO trades(
            signal_id, symbol, timeframe, direction, entry, sl, tp,
            opened_at, status, close_reason, size_usd, fees_bps, rr_planned
        )
        VALUES(?,?,?,?,?,?,?,datetime('now'),'OPEN',NULL,?,?,?)
        """,
        (
            signal_id,
            plan["symbol"], plan["timeframe"], plan["direction"],
            float(plan["entry"]), float(plan["sl"]), float(plan["tp"]),
            size_usd, fees_bps, rr_planned,
        ),
    )
    return int(cur.lastrowid)

def handle_autopost_message(msg: Dict) -> Optional[int]:
    """
    Приймає дикт з автопоста (msg['text'], msg.get('meta', {})):
      - парсить план;
      - перевіряє RR-поріг (user_rr у meta або CFG.autopost_rr_min, деф.1.5);
      - якщо вже є OPEN з тим самим напрямом — скіпає;
      - якщо вже є OPEN з протилежним напрямом — СПОЧАТКУ закриває їх (REVERSED) за останньою ціною (або entry), потім відкриває нову;
      - створює рядки у signals та trades; повертає trade_id.
    """
    text = (msg or {}).get("text") or ""
    plan = _parse(text)
    if not plan:
        return None

    meta = msg.get("meta") if isinstance(msg.get("meta"), dict) else {}
    user_rr = None
    try:
        if "user_rr" in meta:
            user_rr = float(meta["user_rr"])
    except Exception:
        user_rr = None
    rr_thr = user_rr
    if rr_thr is None:
        try:
            rr_thr = float(CFG.get("autopost_rr_min", 1.5))
        except Exception:
            rr_thr = 1.5

    if float(plan["rr"]) < rr_thr:
        log.info("autopost_bridge: skip %s [%s]: rr=%.2f < thr=%.2f",
                 plan["symbol"], plan["timeframe"], plan["rr"], rr_thr)
        return None

    user_id = 0
    try:
        user_id = int(meta.get("user_id", 0))
    except Exception:
        user_id = 0

    with _conn() as c:
        cur = c.cursor()

        # Якщо є відкриті — перевіряємо напрям
        open_rows = _find_open_trades(cur, plan["symbol"], plan["timeframe"])
        if open_rows:
            same_dir = [r for r in open_rows if (r["direction"] or "").upper() == plan["direction"].upper()]
            opp_dir  = [r for r in open_rows if (r["direction"] or "").upper() != plan["direction"].upper()]

            if same_dir and not opp_dir:
                log.info("autopost_bridge: already OPEN same dir %s [%s], skip",
                         plan["symbol"], plan["timeframe"])
                return None

            # Закриваємо протилежні перед відкриттям нової
            if opp_dir:
                last = _last_price(plan["symbol"], plan["timeframe"])
                for tr in opp_dir:
                    _close_trade(cur, tr, reason="REVERSED", at_price=last)

        # Тепер створюємо сигнал і трейд
        sig_id = _insert_signal(cur, plan, user_id=user_id)
        trade_id = _insert_trade(cur, plan, signal_id=sig_id)
        c.commit()

    log.info("autopost_bridge: OPEN trade#%s %s [%s] %s @%.4f SL=%.4f TP=%.4f (RR≈%.2f) sig#%s",
             trade_id, plan["symbol"], plan["timeframe"], plan["direction"],
             plan["entry"], plan["sl"], plan["tp"], plan["rr"], sig_id)
    return trade_id
