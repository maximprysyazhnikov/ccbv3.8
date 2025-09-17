# utils/settings_cached.py
from __future__ import annotations
import os, time, threading

# намагаємося взяти оригінальну функцію
try:
    import utils.settings as _S
    _raw_get = _S.get_setting
except Exception:
    _S = None
    def _raw_get(key: str, default=None):
        return os.getenv(key, default if default is not None else "")

_TTL = float(os.getenv("SETTINGS_CACHE_TTL_SEC", "30") or 30)
_LOCK = threading.RLock()
_CACHE: dict[str, tuple[float, str | None]] = {}

def _now() -> float:
    return time.monotonic()

def get_setting(key: str, default=None):
    """Кешований get_setting із TTL (секунди)."""
    k = str(key)
    now = _now()
    with _LOCK:
        item = _CACHE.get(k)
        if item:
            ts, val = item
            if (now - ts) <= _TTL:
                return val
        # miss або прострочено — читаємо сире значення
        val = _raw_get(k, default)
        _CACHE[k] = (now, val)
        return val

def clear_settings_cache():
    with _LOCK:
        _CACHE.clear()

# авто-монкіпатч оригінального модуля, якщо він є
if _S is not None:
    try:
        _S.get_setting = get_setting  # type: ignore
    except Exception:
        pass
