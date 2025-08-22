# market_data/binance.py
from __future__ import annotations
import logging
import time
from typing import List, Dict, Any
import requests

log = logging.getLogger("binance_http")

BASE_URL = "https://api.binance.com"  # spot API

# Дозволені таймфрейми (мапа 1:1 з Binance)
INTERVAL_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "8h": "8h", "12h": "12h",
    "1d": "1d", "3d": "3d", "1w": "1w", "1M": "1M",
}

def _http_get(url: str, params: Dict[str, Any], retries: int = 3, backoff: float = 0.6):
    """Простий GET з ретраями на 429/5xx."""
    for i in range(retries):
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
        # ліміти/тимчасові помилки — ретрай
        if r.status_code in (429, 418) or 500 <= r.status_code < 600:
            wait = backoff * (2 ** i)
            log.warning("Binance GET %s failed (%s). Retry in %.2fs", url, r.status_code, wait)
            time.sleep(wait)
            continue
        # інші коди — піднімаємо
        r.raise_for_status()
    # якщо всі ретраї вмерли — остання відповідь
    r.raise_for_status()

def fetch_ohlcv_raw(symbol: str, timeframe: str, limit: int = 500) -> List[Dict[str, Any]]:
    """
    Повертає список барів у форматі:
    [
      {"ts": <unix_seconds>, "open": float, "high": float, "low": float, "close": float, "volume": float},
      ...
    ]
    """
    tf = timeframe.strip()
    if tf not in INTERVAL_MAP:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    lim = max(1, min(int(limit or 500), 1000))  # Binance максимум 1000
    url = f"{BASE_URL}/api/v3/klines"
    params = {
        "symbol": symbol.upper(),
        "interval": INTERVAL_MAP[tf],
        "limit": lim,
    }

    data = _http_get(url, params)
    out: List[Dict[str, Any]] = []
    # Відповідь: [openTime, open, high, low, close, volume, closeTime, ...]
    for row in data:
        try:
            out.append({
                "ts": int(row[0] // 1000),               # ms → s
                "open": float(row[1]),
                "high": float(row[2]),
                "low":  float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            })
        except Exception as e:
            log.warning("Bad kline row for %s %s: %s (%s)", symbol, timeframe, row, e)
    return out
