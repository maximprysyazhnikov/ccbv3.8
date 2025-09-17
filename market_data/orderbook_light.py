# market_data/orderbook_light.py
from __future__ import annotations
import time
from typing import Dict, Any, Optional, Tuple, List
import httpx
from core_config import CFG

_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}

def _now() -> float: return time.time()
def _ttl_key(symbol: str) -> str: return f"ob:{symbol.upper()}"

async def _fetch_binance_depth(symbol: str, limit: int) -> Dict[str, Any]:
    url = "https://api.binance.com/api/v3/depth"
    params = {"symbol": symbol.upper(), "limit": limit}
    async with httpx.AsyncClient(timeout=5.0) as cli:
        r = await cli.get(url, params=params)
        r.raise_for_status()
        return r.json()

def _to_usd_levels(levels: List[List[str]]) -> List[Tuple[float, float, float]]:
    out = []
    for p_str, q_str in levels:
        try:
            p = float(p_str); q = float(q_str)
            out.append((p, q, p*q))  # (price, qty, vol_usd)
        except Exception:
            continue
    return out

def _nearest_wall(levels: List[Tuple[float,float,float]], price: float, direction: str,
                  vol_threshold: float, near_pct: float) -> Optional[Dict[str, Any]]:
    best = None
    for p, q, v in levels:
        if direction == "bid" and p >= price:   # шукаємо нижче
            continue
        if direction == "ask" and p <= price:   # шукаємо вище
            continue
        dist_pct = (p - price)/price * 100.0
        if abs(dist_pct) > near_pct:
            continue
        if v >= vol_threshold:
            cand = {"price": p, "qty": q, "vol_usd": v, "dist_pct": dist_pct}
            if best is None or abs(cand["dist_pct"]) < abs(best["dist_pct"]):
                best = cand
    if best:
        best["vol_str"] = f"{best['vol_usd']/1e6:.1f}M"
        sign = "↓" if best["dist_pct"]<0 else "↑"
        best["dist_str"] = f"{abs(best['dist_pct']):.2f}%{sign}"
    return best

def _imbalance(bids: List[Tuple[float,float,float]], asks: List[Tuple[float,float,float]],
               price: float, window_pct: float = 0.5) -> float:
    lo = price*(1 - window_pct/100.0)
    hi = price*(1 + window_pct/100.0)
    bid_sum = sum(v for p,_,v in bids if lo <= p <= price)
    ask_sum = sum(v for p,_,v in asks if price <= p <= hi)
    if ask_sum <= 1e-9: return 9.99
    return bid_sum / ask_sum

async def get_orderbook_metrics(symbol: str) -> Optional[Dict[str, Any]]:
    if not CFG.get("orderbook_enabled", True):
        return None
    key = _ttl_key(symbol)
    ttl = float(CFG.get("orderbook_ttl_sec", 20))
    now = _now()
    cached = _CACHE.get(key)
    if cached and (now - cached[0] <= ttl):
        return cached[1]
    try:
        depth = await _fetch_binance_depth(symbol, int(CFG.get("orderbook_levels", 50)))
        bids = _to_usd_levels(depth.get("bids", []))
        asks = _to_usd_levels(depth.get("asks", []))
        if not bids or not asks:
            return None
        best_bid = max(bids, key=lambda x: x[0])[0]
        best_ask = min(asks, key=lambda x: x[0])[0]
        mid = (best_bid + best_ask)/2.0
        support = _nearest_wall(bids, mid, "bid",
                                float(CFG.get("wall_usdt_threshold", 2_000_000)),
                                float(CFG.get("wall_near_pct", 1.0)))
        resistance = _nearest_wall(asks, mid, "ask",
                                   float(CFG.get("wall_usdt_threshold", 2_000_000)),
                                   float(CFG.get("wall_near_pct", 1.0)))
        imbal = _imbalance(bids, asks, mid, window_pct=0.5)
        data = {"mid": mid, "imbalance": imbal, "support_wall": support, "resistance_wall": resistance}
        _CACHE[key] = (now, data)
        return data
    except Exception:
        return None
