from __future__ import annotations
import requests
from typing import Any, List, Dict

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"

def get_ohlcv(symbol: str, timeframe: str, limit: int = 100) -> List[Dict[str, Any]]:
    params = {"symbol": symbol.upper(), "interval": timeframe, "limit": min(max(int(limit), 5), 1000)}
    r = requests.get(BINANCE_KLINES, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    out = []
    for k in data:
        out.append({
            "ts": k[0],
            "open": float(k[1]),
            "high": float(k[2]),
            "low":  float(k[3]),
            "close":float(k[4]),
            "volume":float(k[5]),
        })
    return out
