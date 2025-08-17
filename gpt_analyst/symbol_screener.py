from __future__ import annotations
import pandas as pd, math
from typing import List
from core_config import UNIVERSE_MIN_QVOL_USD
from market_data.binance_data import get_24h_ticker, get_ohlcv
from signal_tools.ta_calc import get_ta_indicators

def _score(last) -> float:
    price = float(last.get("close", 0) or 0)
    rsi = float(last.get("rsi", 50) or 50)
    macd = float(last.get("macd", 0) or 0) - float(last.get("macd_signal", 0) or 0)
    sma7 = float(last.get("sma_7", price) or price)
    sma25 = float(last.get("sma_25", price) or price)
    atr = float(last.get("atr_14", 0) or 0)
    atr_pct = (atr / price * 100) if price else 0.0

    trend = 1.0 if sma7 > sma25 else -1.0 if sma7 < sma25 else 0.0
    mom = max(-1.0, min(1.0, (rsi - 50.0) / 20.0))
    macd_s = max(-1.0, min(1.0, macd * 5.0))
    vola = max(0.0, min(1.0, atr_pct / 1.0))
    return 0.9 * trend + 0.7 * macd_s + 0.6 * mom + 0.3 * vola

def get_top_symbols(n: int = 20) -> List[str]:
    # Universe filter by USDT pairs & quote volume in USD >= threshold
    tick = [t for t in get_24h_ticker() if t.get("symbol","").endswith("USDT")]
    universe = []
    for t in tick:
        try:
            q = float(t.get("quoteVolume") or 0.0)
            if q >= UNIVERSE_MIN_QVOL_USD:
                universe.append(t["symbol"])
        except Exception:
            continue
    # Rank by our TA score on 1m
    ranks = []
    for s in universe:
        try:
            df = get_ohlcv(s, "1m", 150)
            if df.empty: 
                continue
            inds = get_ta_indicators(df)
            last = inds.iloc[-1]
            ranks.append((s, abs(_score(last))))
        except Exception:
            continue
    ranks.sort(key=lambda x: x[1], reverse=True)
    return [s for s,_ in ranks[:n]]
