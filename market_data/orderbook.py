# market_data/orderbook.py
from __future__ import annotations
import requests, time
from typing import Dict

BINANCE_BASE = "https://api.binance.com"

def _get(path: str, params: dict | None = None, retries: int = 2, timeout: int = 10):
    url = f"{BINANCE_BASE}{path}"
    last = None
    for i in range(retries + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                time.sleep(0.5 + 0.5*i)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(0.3 + 0.3*i)
    raise RuntimeError(f"orderbook fetch failed: {last}")

def get_orderbook_stats(symbol: str, limit: int = 50) -> Dict[str, float]:
    symbol = (symbol or "").upper().strip()
    if symbol.endswith(":USDT"):
        symbol = symbol.replace(":USDT", "USDT")
    ob = _get("/api/v3/depth", {"symbol": symbol, "limit": min(max(int(limit), 5), 1000)})

    def _best(lst, side: str):
        if not lst: return (float("nan"), float("nan"))
        # [price, qty] як строки
        p = float(lst[0][0]); q = float(lst[0][1])
        return p, q

    bids = ob.get("bids", [])  # найвища ціна
    asks = ob.get("asks", [])  # найнижча ціна

    best_bid, bid_qty = _best(bids, "bid")
    best_ask, ask_qty = _best(asks, "ask")
    if not (best_bid == best_bid and best_ask == best_ask):  # NaN check
        return {"mid": float("nan"), "spread_bps": float("nan"),
                "imbalance_pct": float("nan"), "nearest_bid_wall": float("nan"),
                "nearest_ask_wall": float("nan")}
    mid = (best_bid + best_ask) / 2.0
    spread_bps = (best_ask - best_bid) / mid * 10_000 if mid > 0 else float("nan")
    # найпростіша “стінка” — найбільший обсяг серед перших N
    nb = max((float(q) for _, q in bids[:limit]), default=float("nan"))
    na = max((float(q) for _, q in asks[:limit]), default=float("nan"))
    total_b = sum(float(q) for _, q in bids[:limit]) or 1.0
    total_a = sum(float(q) for _, q in asks[:limit]) or 1.0
    imbalance = (total_b - total_a) / (total_b + total_a) * 100.0

    return {
        "mid": mid,
        "spread_bps": spread_bps,
        "imbalance_pct": imbalance,
        "nearest_bid_wall": nb,
        "nearest_ask_wall": na,
    }
