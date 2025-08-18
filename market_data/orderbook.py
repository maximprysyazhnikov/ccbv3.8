from __future__ import annotations
import requests
from typing import Any, Dict, List, Tuple

BINANCE_DEPTH = "https://api.binance.com/api/v3/depth"


def get_orderbook_summary(symbol: str, limit: int = 50) -> Dict[str, Any]:
    params = {"symbol": symbol.upper(), "limit": min(max(limit, 5), 5000)}
    r = requests.get(BINANCE_DEPTH, params=params, timeout=10)
    r.raise_for_status()
    j = r.json()

    bids: List[Tuple[float, float]] = [(float(p), float(q)) for p, q in j.get("bids", [])]
    asks: List[Tuple[float, float]] = [(float(p), float(q)) for p, q in j.get("asks", [])]

    top_bid = bids[0][0] if bids else None
    top_ask = asks[0][0] if asks else None

    def wall(levels):
        return max(levels[:limit], key=lambda x: x[1])[0] if levels else None

    bid_wall = wall(bids)
    ask_wall = wall(asks)

    bid_vol = sum(q for _, q in bids[:limit])
    ask_vol = sum(q for _, q in asks[:limit])

    if bid_vol > ask_vol * 1.2:
        imbalance = "BUY_DOMINANT"
    elif ask_vol > bid_vol * 1.2:
        imbalance = "SELL_DOMINANT"
    else:
        imbalance = "BALANCED"

    return {
        "top_bid": top_bid,
        "top_ask": top_ask,
        "bid_wall": bid_wall,
        "ask_wall": ask_wall,
        "imbalance": imbalance,
        "bid_vol_topN": bid_vol,
        "ask_vol_topN": ask_vol,
    }
