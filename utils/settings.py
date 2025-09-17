from __future__ import annotations
import os, sqlite3, time
from typing import Optional, Tuple, Dict
from utils.db import get_conn

_CACHE: Dict[str, Tuple[str, float]] = {}
_TTL = 10.0  # сек

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    now = time.time()
    v = _CACHE.get(key)
    if v and now - v[1] < _TTL:
        return v[0]
    with get_conn() as conn:
        cur = conn.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        if row and row[0] is not None:
            _CACHE[key] = (str(row[0]), now)
            return str(row[0])
    env = os.getenv(key.upper()) or os.getenv(key.lower())
    if env is not None:
        _CACHE[key] = (env, now)
        return env
    return default

def set_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings(key,value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()
    _CACHE.pop(key, None)
