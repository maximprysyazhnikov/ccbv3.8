# router/analyzer_router.py
from __future__ import annotations
import os, itertools, json
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple
from core_config import CFG

@dataclass
class Route:
    api_key: str
    model: str
    base: str
    timeout: int  # seconds

def _split_multi(s: Optional[str]) -> List[str]:
    if not s: return []
    return [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]

def _normalize_slot(x: Any, d_model: str, d_base: str, d_timeout: int) -> Optional[Tuple[str,str,str,int]]:
    if isinstance(x, dict):
        key = x.get("key") or x.get("api_key") or x.get("OPENROUTER_KEY")
        model = x.get("model") or d_model
        base  = x.get("base")  or d_base
        tout  = int(x.get("timeout") or d_timeout)
        if key and model and base:
            return (str(key).strip(), str(model).strip(), str(base).strip(), tout)
        return None
    if isinstance(x, (list, tuple)) and x:
        key   = x[0]
        model = x[1] if len(x) > 1 and x[1] else d_model
        base  = x[2] if len(x) > 2 and x[2] else d_base
        tout  = int(x[3] if len(x) > 3 and x[3] else d_timeout)
        if key and model and base:
            return (str(key).strip(), str(model).strip(), str(base).strip(), tout)
        return None
    if isinstance(x, str) and x.strip():
        return (x.strip(), d_model, d_base, d_timeout)
    return None

def _dedup(slots: List[Tuple[str,str,str,int]]) -> List[Tuple[str,str,str,int]]:
    out, seen = [], set()
    for k, m, b, t in slots:
        sig = (k, m, b, int(t))
        if sig not in seen:
            seen.add(sig); out.append((k, m, b, int(t)))
    return out

def _build_slots() -> List[Tuple[str,str,str,int]]:
    d_model   = (CFG.get("or_model")  or os.getenv("OPENROUTER_MODEL") or "deepseek/deepseek-chat")
    d_base    = (CFG.get("or_base")   or os.getenv("OPENROUTER_BASE")  or os.getenv("OR_BASE") or "https://openrouter.ai/api/v1")
    d_timeout = int(CFG.get("or_timeout") or os.getenv("OPENROUTER_TIMEOUT") or 30)

    raw: List[Any] = []
    # 1) з CFG
    raw.extend(CFG.get("or_slots") or [])
    # 2) з ENV (опційно, якщо хтось не користується CFG)
    env = os.getenv("OR_SLOTS")
    if env:
        try:
            arr = json.loads(env)
            if isinstance(arr, list):
                raw.extend(arr)
        except Exception:
            pass
    env_keys = _split_multi(os.getenv("OPENROUTER_KEYS") or os.getenv("OPENROUTER_KEY"))
    if env_keys:
        env_models = _split_multi(os.getenv("OPENROUTER_MODEL"))
        env_base   = (os.getenv("OPENROUTER_BASE") or os.getenv("OR_BASE") or d_base).strip()
        env_timeout = int(os.getenv("OPENROUTER_TIMEOUT") or d_timeout)
        if env_models and len(env_models) >= len(env_keys):
            raw.extend({"key": k, "model": m, "base": env_base, "timeout": env_timeout} for k, m in zip(env_keys, env_models))
        else:
            raw.extend({"key": k, "model": d_model, "base": env_base, "timeout": env_timeout} for k in env_keys)

    norm: List[Tuple[str,str,str,int]] = []
    for x in raw:
        nm = _normalize_slot(x, d_model, d_base, d_timeout)
        if nm: norm.append(nm)
    return _dedup(norm)

_SLOTS = _build_slots()
_RR = itertools.cycle(range(len(_SLOTS))) if _SLOTS else None

def pick_route(symbol: str, user_model_key: Optional[str] = None) -> Optional[Route]:
    """
    user_model_key:
      - 'auto'/'' → round-robin
      - інакше: шукаємо спочатку збіг по model, потім по key
    """
    if not _SLOTS:
        return None
    key = (user_model_key or "").strip().lower()
    if key and key != "auto":
        for k, m, b, t in _SLOTS:
            if m.lower() == key:
                return Route(api_key=k, model=m, base=b, timeout=int(t))
        for k, m, b, t in _SLOTS:
            if k.lower() == key:
                return Route(api_key=k, model=m, base=b, timeout=int(t))
    idx = next(_RR) if _RR else 0
    k, m, b, t = _SLOTS[idx]
    return Route(api_key=k, model=m, base=b, timeout=int(t))
