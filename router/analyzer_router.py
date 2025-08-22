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
            return (str(key).strip(), str(model).strip(), str(base).strip(), int(tout))
        return None
    if isinstance(x, (list, tuple)):
        if not x: return None
        key   = x[0]
        model = x[1] if len(x) > 1 and x[1] else d_model
        base  = x[2] if len(x) > 2 and x[2] else d_base
        tout  = x[3] if len(x) > 3 and x[3] else d_timeout
        if key and model and base:
            return (str(key).strip(), str(model).strip(), str(base).strip(), int(tout))
        return None
    if isinstance(x, str) and x.strip():
        return (x.strip(), d_model, d_base, d_timeout)
    return None

def _dedup(slots: List[Tuple[str,str,str,int]]) -> List[Tuple[str,str,str,int]]:
    out, seen = [], set()
    for k, m, b, t in slots:
        sig = (k, m, b, int(t))
        if sig not in seen:
            seen.add(sig); out.append(sig)
    return out

def _build_slots() -> List[Tuple[str,str,str,int]]:
    d_model   = (CFG.get("or_model") or os.getenv("OPENROUTER_MODEL") or "deepseek/deepseek-chat")
    d_base    = (CFG.get("or_base")  or os.getenv("OPENROUTER_BASE") or os.getenv("OR_BASE") or "https://openrouter.ai/api/v1")
    d_timeout = int(CFG.get("or_timeout") or os.getenv("OPENROUTER_TIMEOUT") or 30)

    raw: List[Any] = []
    # 1) з CFG
    raw.extend(CFG.get("or_slots") or [])

    # 2) з ENV (опціонально)
    env_keys   = _split_multi(os.getenv("OPENROUTER_KEYS") or os.getenv("OPENROUTER_KEY"))
    env_models = _split_multi(os.getenv("OPENROUTER_MODEL"))
    env_base   = (os.getenv("OPENROUTER_BASE") or os.getenv("OR_BASE") or d_base).strip()
    env_timeout = int(os.getenv("OPENROUTER_TIMEOUT") or d_timeout)

    if env_keys:
        if env_models and len(env_models) >= len(env_keys):
            for k, m in zip(env_keys, env_models):
                raw.append({"key": k, "model": m, "base": env_base, "timeout": env_timeout})
        else:
            for k in env_keys:
                raw.append({"key": k, "model": d_model, "base": env_base, "timeout": env_timeout})

    norm: List[Tuple[str,str,str,int]] = []
    for r in raw:
        n = _normalize_slot(r, d_model, d_base, d_timeout)
        if n: norm.append(n)
    return _dedup(norm)

_SLOTS: List[Tuple[str,str,str,int]] = _build_slots()
_cycle = itertools.cycle(range(len(_SLOTS))) if _SLOTS else None

def get_all_slots_count() -> int:
    return len(_SLOTS)

def pick_route(symbol: str, user_model_key: Optional[str] = None) -> Optional[Route]:
    if not _SLOTS:
        return None
    key = (user_model_key or "").strip().lower()
    if key and key != "auto":
        # спершу шукаємо співпадіння по model, далі по key
        for k, m, b, t in _SLOTS:
            if m.lower() == key:
                return Route(k, m, b, int(t))
        for k, m, b, t in _SLOTS:
            if k.lower() == key:
                return Route(k, m, b, int(t))
    # round-robin
    idx = next(_cycle) if _cycle else 0
    k, m, b, t = _SLOTS[idx]
    return Route(k, m, b, int(t))
