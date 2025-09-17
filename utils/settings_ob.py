# utils/settings_ob.py
from __future__ import annotations
import os
from utils.db import get_conn
from core_config import CFG

_KEY = "orderbook_enabled"

def is_ob_enabled() -> bool:
    """DB > ENV > CFG default"""
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (_KEY,)).fetchone()
            if row and str(row[0]).strip():
                v = str(row[0]).strip().lower()
                return v in ("1","true","yes","on")
    except Exception:
        pass
    env = os.getenv("ORDERBOOK_ENABLED")
    if env is not None:
        return env.lower() in ("1","true","yes","on")
    return bool(CFG.get("orderbook_enabled", True))

def set_ob_enabled(flag: bool) -> None:
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (_KEY, "true" if flag else "false"),
            )
            conn.commit()
    except Exception:
        pass
