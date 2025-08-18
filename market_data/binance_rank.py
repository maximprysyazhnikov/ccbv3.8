# market_data/binance_rank.py
from __future__ import annotations
import requests
from typing import List, Dict

TICKER_24H = "https://api.binance.com/api/v3/ticker/24hr"

_EXCLUDE_SUFFIXES = ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT", "HEDGEUSDT")
_EXCLUDE_PREFIXES = ("LD", )
_STABLE_STABLE = {"BUSDUSDT","USDCUSDT","TUSDUSDT","FDUSDUSDT","EURUSDT","TRYUSDT"}

def _is_spot_usdt_symbol(sym: str) -> bool:
    if not sym.endswith("USDT"): return False
    if sym in _STABLE_STABLE: return False
    if any(sym.endswith(suf) for suf in _EXCLUDE_SUFFIXES): return False
    if any(sym.startswith(pfx) for pfx in _EXCLUDE_PREFIXES): return False
    return True

def get_all_usdt_24h() -> List[Dict]:
    """Всі спотові USDT-пари з 24h даними (lastPrice, priceChangePercent, quoteVolume)."""
    r = requests.get(TICKER_24H, timeout=15)
    r.raise_for_status()
    data = r.json()
    out = []
    for it in data:
        sym = it.get("symbol","")
        if not _is_spot_usdt_symbol(sym):
            continue
        try:
            out.append({
                "symbol": sym,
                "lastPrice": float(it.get("lastPrice","0")),
                "priceChangePercent": float(it.get("priceChangePercent","0")),
                "quoteVolume": float(it.get("quoteVolume","0")),
            })
        except Exception:
            continue
    return out

def get_top_by_quote_volume_usdt(n: int = 20) -> List[Dict]:
    rows = get_all_usdt_24h()
    rows.sort(key=lambda x: x["quoteVolume"], reverse=True)
    return rows[:max(1,int(n))]
