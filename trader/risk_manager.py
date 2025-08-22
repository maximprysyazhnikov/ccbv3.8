from __future__ import annotations

def fixed_fraction(balance: float, risk_pct: float, entry: float, sl: float) -> float:
    risk = balance * (risk_pct / 100.0)
    stop = abs(entry - sl)
    if stop <= 0:
        return 0.0
    qty = risk / stop
    return max(qty, 0.0)
