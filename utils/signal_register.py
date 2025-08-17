# utils/signal_register.py
from __future__ import annotations
import time
from typing import Dict, Any, Tuple, List

from core_config import (
    ALERT_MIN_COOLDOWN_MIN,   # мін. час між сигналами тієї ж пари/TF
    ALERT_MAX_AGE_MIN,        # коли вважати запис застарілим і прибрати
)

# In‑memory реєстр сигналів.
# Ключ: (symbol, timeframe)
# Значення: {
#   'plan': { direction, entry, stop, tp, confidence, holding_time_hours, rationale },
#   'ts': float (unix epoch),
#   'status': 'ACTIVE'|'CONSUMED'|'INVALIDATED'|'EXPIRED'
# }
_signal_store: Dict[Tuple[str, str], Dict[str, Any]] = {}

def _age_min(ts: float) -> float:
    return max(0.0, (time.time() - float(ts)) / 60.0)

def check_signal_status(symbol: str, tf: str, plan: dict) -> dict:
    """
    Чи можна показати/створити новий сигнал зараз?
    - cooldown після попереднього сигналу
    - дубль напряму підряд (шум)
    """
    cleanup_expired_signals()

    key = (symbol.upper(), tf)
    if key in _signal_store:
        last = _signal_store[key]
        age = _age_min(last.get("ts", time.time()))
        if age < ALERT_MIN_COOLDOWN_MIN:
            return {"allow": False, "reason": f"cooldown {ALERT_MIN_COOLDOWN_MIN}m"}
        try:
            if str(last["plan"].get("direction","")).upper() == str(plan.get("direction","")).upper():
                return {"allow": False, "reason": "duplicate direction"}
        except Exception:
            pass
    return {"allow": True}

def register_signal(symbol: str, tf: str, plan: dict) -> None:
    """
    Реєструє (або перезаписує) активний сигнал для пари/TF.
    Зберігає всю AI-аналітику та поточний час.
    """
    _signal_store[(symbol.upper(), tf)] = {
        "plan": {
            "direction": (str(plan.get("direction","")).upper() or "NEUTRAL"),
            "entry": float(plan.get("entry", float("nan"))),
            "stop": float(plan.get("stop", float("nan"))),
            "tp": float(plan.get("tp", float("nan"))),
            "confidence": float(plan.get("confidence", 0.0)),
            "holding_time_hours": float(plan.get("holding_time_hours", 0.0)),
            "rationale": str(plan.get("rationale","")).strip(),
        },
        "ts": time.time(),
        "status": "ACTIVE",
    }

def update_signal_status(symbol: str, tf: str, status: str) -> None:
    key = (symbol.upper(), tf)
    if key in _signal_store:
        _signal_store[key]["status"] = status

def get_active_signals() -> List[Tuple[str, str, Dict[str, Any]]]:
    out: List[Tuple[str, str, Dict[str, Any]]] = []
    for (sym, tf), data in _signal_store.items():
        if data.get("status") == "ACTIVE":
            out.append((sym, tf, data))
    out.sort(key=lambda x: x[2].get("ts", 0.0), reverse=True)
    return out

def cleanup_expired_signals() -> None:
    """
    Прибираємо дуже старі записи з пам'яті.
    """
    to_del = []
    now = time.time()
    for key, data in _signal_store.items():
        if _age_min(data.get("ts", now)) > ALERT_MAX_AGE_MIN:
            to_del.append(key)
    for k in to_del:
        _signal_store.pop(k, None)

PIVOT_EPS = 0.005  # 0.5% від pivot

ALERT_RULES += [
    {"when": "NEAR_FIB_PIVOT", "expr": lambda r: "FIB_PIVOT" in r and abs(r["CLOSE"] - r["FIB_PIVOT"]) / r["FIB_PIVOT"] < PIVOT_EPS},
    {"when": "NEAR_FIB_R1",    "expr": lambda r: "FIB_R1" in r    and abs(r["CLOSE"] - r["FIB_R1"])    / r["FIB_PIVOT"] < PIVOT_EPS},
    {"when": "NEAR_FIB_S1",    "expr": lambda r: "FIB_S1" in r    and abs(r["CLOSE"] - r["FIB_S1"])    / r["FIB_PIVOT"] < PIVOT_EPS},
]
