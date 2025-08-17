# utils/screener_cache.py
from __future__ import annotations
from typing import List, Dict, Any
import time

_CACHE: Dict[str, Any] = {
    "rows": [],      # список словників: {"symbol", "score", "bias", "price", "rsi", "macd_d", "atr_pct", "ts"}
    "ts": 0.0,       # unix time останнього оновлення
}

def set_rows(rows: List[Dict[str, Any]]) -> None:
    _CACHE["rows"] = rows or []
    _CACHE["ts"] = time.time()

def get_rows() -> List[Dict[str, Any]]:
    return list(_CACHE.get("rows") or [])

def is_fresh(max_age_sec: int = 300) -> bool:
    return (time.time() - float(_CACHE.get("ts") or 0)) <= max_age_sec
