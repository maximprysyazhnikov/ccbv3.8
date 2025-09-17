# services/pnl.py
from __future__ import annotations

def calc_rr_realized(entry: float, sl: float, close_price: float, direction: str) -> float | None:
    risk = abs(entry - sl)
    if not risk:
        return None
    move = (close_price - entry) if direction.upper() == "LONG" else (entry - close_price)
    return move / risk

def calc_pnl_usd(entry: float, sl: float, close_price: float, direction: str,
                 size_usd: float, fees_bps: float | int = 0) -> tuple[float | None, float | None]:
    rr = calc_rr_realized(entry, sl, close_price, direction)
    if rr is None or not entry:
        return (rr, None)
    risk_pct = abs(entry - sl) / entry
    risk_usd = (size_usd or 0.0) * risk_pct
    fees = (float(fees_bps or 0) / 10000.0) * (size_usd or 0.0)   # якщо треба 2 сторони — помнож на 2
    pnl = rr * risk_usd - fees
    return (rr, pnl)
