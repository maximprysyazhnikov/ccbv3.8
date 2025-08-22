from __future__ import annotations
import time, threading
from typing import List, Dict

# твій існуючий реальний провайдер
from market_data.binance import fetch_ohlcv_raw  # очікується функція (symbol, timeframe, limit)->list[dict]

# простий процесний кеш
_CACHE: Dict[tuple, dict] = {}
_LOCK = threading.Lock()
TTL_SEC = 30  # однакові дані протягом 30с в усіх місцях (autopost,/ai,Analyze ALL)

def get_ohlcv(symbol: str, timeframe: str, limit: int = 200) -> List[dict]:
    key = (symbol.upper(), timeframe, int(limit))
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and (now - hit["ts"] <= TTL_SEC) and hit["data"]:
            return hit["data"]
    data = fetch_ohlcv_raw(symbol, timeframe, limit)  # твоя оригінальна реалізація
    with _LOCK:
        _CACHE[key] = {"ts": now, "data": data or []}
    return data or []

def snapshot_ts() -> int:
    """Єдиний штамп «ран-даних» для всіх розрахунків поточного батчу."""
    # Використаємо грубо поточну секунду: оскільки OHLCV кешується TTL, це буде узгоджено.
    return int(time.time())
