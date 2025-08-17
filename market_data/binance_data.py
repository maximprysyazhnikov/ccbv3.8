import requests
import pandas as pd

BINANCE_BASE = "https://api.binance.com"

def get_ohlcv(symbol: str, interval: str = "1m", limit: int = 150) -> pd.DataFrame:
    url = f"{BINANCE_BASE}/api/v3/klines"
    r = requests.get(url, params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=15)
    r.raise_for_status()
    raw = r.json()
    cols = [
        "open_time","open","high","low","close","volume",
        "close_time","qav","trades","tbbav","tbqav","ignore"
    ]
    df = pd.DataFrame(raw, columns=cols)
    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.rename(columns={"open_time":"timestamp"})
    return df[["timestamp","open","high","low","close","volume"]].copy()

def get_24h_ticker() -> list:
    url = f"{BINANCE_BASE}/api/v3/ticker/24hr"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()

def get_latest_price(symbol: str) -> float:
    url = f"{BINANCE_BASE}/api/v3/ticker/price"
    r = requests.get(url, params={"symbol": symbol}, timeout=10)
    r.raise_for_status()
    return float(r.json()["price"])
