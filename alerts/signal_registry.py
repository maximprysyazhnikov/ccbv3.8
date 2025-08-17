# alerts/signal_registry.py
from __future__ import annotations
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any

from core_config import (
    ALERT_MIN_COOLDOWN_MIN, ALERT_CONSUME_PCT, ALERT_INVALIDATE_PCT,
    ALERT_MAX_AGE_MIN, REARM_RSI_GAP, REARM_REQUIRE_MACD_REFLIP,
    OPTIONAL_HARD_REISSUE_MIN
)

STATE_PATH = Path("alerts/state.json")

@dataclass
class SignalState:
    symbol: str
    tf: str
    direction: str   # LONG/SHORT
    entry: float
    ts_iso: str      # UTC ISO
    status: str      # ACTIVE|CONSUMED|INVALIDATED|EXPIRED
    why: str = ""
    cooldown_until_iso: Optional[str] = None
    # для re-arm:
    last_rsi: Optional[float] = None
    last_macd_delta: Optional[float] = None
    # опц. дані валідності
    valid_for_min: Optional[int] = None
    valid_until_iso: Optional[str] = None

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _load() -> Dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def _save(obj: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def _key(symbol: str, tf: str) -> str:
    return f"{symbol.upper()}::{tf}"

def _pct_move_long(entry: float, price: float) -> float:
    return (price - entry) / entry * 100.0

def _pct_move_short(entry: float, price: float) -> float:
    return (entry - price) / entry * 100.0

def _adverse_long(entry: float, price: float) -> float:
    return (entry - price) / entry * 100.0

def _adverse_short(entry: float, price: float) -> float:
    return (price - entry) / entry * 100.0

def _macd_sign(x: Optional[float]) -> int:
    try:
        if x is None or not math.isfinite(float(x)): return 0
        v = float(x)
        return 1 if v > 1e-12 else (-1 if v < -1e-12 else 0)
    except Exception:
        return 0

def get_state(symbol: str, tf: str) -> Optional[SignalState]:
    data = _load()
    node = data.get(_key(symbol, tf))
    if not node:
        return None
    try:
        return SignalState(**node)
    except Exception:
        return None

def set_state(st: SignalState) -> None:
    data = _load()
    data[_key(st.symbol, st.tf)] = asdict(st)
    _save(data)

def clear_state(symbol: str, tf: str) -> None:
    data = _load()
    data.pop(_key(symbol, tf), None)
    _save(data)

def should_emit_signal(
    *,
    symbol: str,
    tf: str,
    direction: str,          # LONG/SHORT
    entry: float,
    price_now: float,
    rsi: Optional[float],
    macd_delta: Optional[float],
) -> tuple[bool, str]:
    now = _now_utc()
    st = get_state(symbol, tf)

    if not st:
        return True, "no_previous_signal"

    # cooldown?
    if st.cooldown_until_iso:
        try:
            cu = datetime.fromisoformat(st.cooldown_until_iso)
            if now < cu:
                return False, f"cooldown_until {st.cooldown_until_iso}"
        except Exception:
            pass

    # valid_until?
    if st.valid_until_iso:
        try:
            vu = datetime.fromisoformat(st.valid_until_iso)
            if now > vu:
                st.status = "EXPIRED"
                st.why = "validity_expired"
                set_state(st)
                return False, "expired"
        except Exception:
            pass

    # age guard
    try:
        ts = datetime.fromisoformat(st.ts_iso)
        age_min = (now - ts).total_seconds() / 60.0
        if age_min >= ALERT_MAX_AGE_MIN:
            st.status = "EXPIRED"
            st.why = f"age>={ALERT_MAX_AGE_MIN}m"
            set_state(st)
            return False, "expired"
    except Exception:
        pass

    # активний існуючий?
    if st.status == "ACTIVE":
        if st.direction.upper() == "LONG":
            move = _pct_move_long(st.entry, price_now)
            adverse = _adverse_long(st.entry, price_now)
        else:
            move = _pct_move_short(st.entry, price_now)
            adverse = _adverse_short(st.entry, price_now)

        if math.isfinite(move) and move >= ALERT_CONSUME_PCT:
            st.status = "CONSUMED"
            st.why = f"move≥{ALERT_CONSUME_PCT}%"
            st.cooldown_until_iso = (now + timedelta(minutes=ALERT_MIN_COOLDOWN_MIN)).isoformat()
            set_state(st)
            return False, "consumed"

        if math.isfinite(adverse) and adverse >= ALERT_INVALIDATE_PCT:
            st.status = "INVALIDATED"
            st.why = f"adverse≥{ALERT_INVALIDATE_PCT}%"
            st.cooldown_until_iso = (now + timedelta(minutes=ALERT_MIN_COOLDOWN_MIN)).isoformat()
            set_state(st)
            return False, "invalidated"

        return False, "active_exists"

    # re-arm умови
    need_rsi = REARM_RSI_GAP
    need_macd = (REARM_REQUIRE_MACD_REFLIP == 1)

    rsi_ok = True
    if st.last_rsi is not None and rsi is not None and math.isfinite(rsi):
        if st.direction.upper() == "LONG":
            rsi_ok = (rsi <= st.last_rsi - need_rsi) or (rsi >= st.last_rsi + need_rsi)
        else:
            rsi_ok = (rsi >= st.last_rsi + need_rsi) or (rsi <= st.last_rsi - need_rsi)

    macd_ok = True
    if need_macd and st.last_macd_delta is not None and macd_delta is not None:
        macd_ok = _macd_sign(macd_delta) != _macd_sign(st.last_macd_delta)

    # дуже давній сигнал? — дозволимо форс‑повтор
    try:
        ts = datetime.fromisoformat(st.ts_iso)
        age_min = (now - ts).total_seconds() / 60.0
        if OPTIONAL_HARD_REISSUE_MIN > 0 and age_min >= OPTIONAL_HARD_REISSUE_MIN:
            rsi_ok = True
            macd_ok = True
    except Exception:
        pass

    if not rsi_ok or not macd_ok:
        return False, f"rearm_needed rsi_ok={rsi_ok} macd_ok={macd_ok}"

    return True, "rearm_passed"

def register_emit(
    *,
    symbol: str,
    tf: str,
    direction: str,
    entry: float,
    rsi: Optional[float],
    macd_delta: Optional[float],
    valid_for_min: Optional[int] = None,
) -> None:
    now = _now_utc()
    valid_until_iso = None
    if valid_for_min and valid_for_min > 0:
        valid_until_iso = (now + timedelta(minutes=int(valid_for_min))).isoformat()

    st = SignalState(
        symbol=symbol.upper(),
        tf=tf,
        direction=direction.upper(),
        entry=float(entry),
        ts_iso=now.isoformat(),
        status="ACTIVE",
        why="ai_decision",
        cooldown_until_iso=(now + timedelta(minutes=ALERT_MIN_COOLDOWN_MIN)).isoformat(),
        last_rsi=(float(rsi) if rsi is not None and math.isfinite(float(rsi)) else None),
        last_macd_delta=(float(macd_delta) if macd_delta is not None and math.isfinite(float(macd_delta)) else None),
        valid_for_min=(int(valid_for_min) if valid_for_min else None),
        valid_until_iso=valid_until_iso
    )
    set_state(st)

def observe_price_progress(
    *,
    symbol: str,
    tf: str,
    price_now: float
) -> Optional[str]:
    st = get_state(symbol, tf)
    if not st or st.status != "ACTIVE":
        return None

    if st.direction.upper() == "LONG":
        move = _pct_move_long(st.entry, price_now)
        adverse = _adverse_long(st.entry, price_now)
    else:
        move = _pct_move_short(st.entry, price_now)
        adverse = _adverse_short(st.entry, price_now)

    now = _now_utc()
    if math.isfinite(move) and move >= ALERT_CONSUME_PCT:
        st.status = "CONSUMED"; st.why = f"move≥{ALERT_CONSUME_PCT}%"
        st.cooldown_until_iso = (now + timedelta(minutes=ALERT_MIN_COOLDOWN_MIN)).isoformat()
        set_state(st); return "CONSUMED"
    if math.isfinite(adverse) and adverse >= ALERT_INVALIDATE_PCT:
        st.status = "INVALIDATED"; st.why = f"adverse≥{ALERT_INVALIDATE_PCT}%"
        st.cooldown_until_iso = (now + timedelta(minutes=ALERT_MIN_COOLDOWN_MIN)).isoformat()
        set_state(st); return "INVALIDATED"

    # validity timeout
    if st.valid_until_iso:
        try:
            vu = datetime.fromisoformat(st.valid_until_iso)
            if now > vu:
                st.status = "EXPIRED"; st.why = "validity_expired"
                set_state(st); return "EXPIRED"
        except Exception:
            pass
    return None
