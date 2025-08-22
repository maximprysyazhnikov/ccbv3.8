# gpt_decider/decider.py
from __future__ import annotations
import re
from typing import Optional, Dict, Any

RR_RX = re.compile(r"\bRR\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", re.I)
CONF_RXES = [
    re.compile(r"\bconfidence\b\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*%", re.I),  # 75%
    re.compile(r"\bconfidence\b\s*[:=]\s*0*\.?([0-9]+(?:\.[0-9]+)?)\b", re.I),  # 0.75 або 0.8
]
DIR_RX = re.compile(r"\b(LONG|SHORT|NO[_\s-]?TRADE|NEUTRAL)\b", re.I)
ENTRY_RX = re.compile(r"\b(?:entry|price)\b\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", re.I)
STOP_RX  = re.compile(r"\b(?:stop(?:-|\s*)loss|sl)\b\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", re.I)
TP_RX    = re.compile(r"\b(?:take(?:-|\s*)profit|tp)\b\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", re.I)

def _to_float(s: Optional[str]) -> Optional[float]:
    if s is None: return None
    try: return float(s)
    except Exception: return None

def _extract_rr(md: str) -> Optional[float]:
    m = RR_RX.search(md)
    return _to_float(m.group(1)) if m else None

def _extract_conf(md: str) -> Optional[float]:
    for rx in CONF_RXES:
        m = rx.search(md)
        if m:
            v = _to_float(m.group(1))
            if v is None:
                continue
            # якщо формат був 0.75 — переводимо в %
            return v if rx.pattern.endswith("%") else (v*100.0 if v <= 1.0 else v)
    return None

def _extract_dir(md: str) -> Optional[str]:
    m = DIR_RX.search(md)
    if not m: return None
    d = m.group(1).upper().replace("_", "").replace("-", "")
    if d == "NOTRADE": d = "NO_TRADE"
    return d

def _extract_levels(md: str) -> Dict[str, Optional[float]]:
    e = ENTRY_RX.search(md); s = STOP_RX.search(md); t = TP_RX.search(md)
    return {
        "entry": _to_float(e.group(1)) if e else None,
        "stop":  _to_float(s.group(1)) if s else None,
        "tp":    _to_float(t.group(1)) if t else None,
    }

def decide_from_markdown(md: str, rr_threshold: float = 1.5, conf_threshold: int = 75) -> Dict[str, Any]:
    """
    Парсить MD/текст плану й каже, чи проходить фільтри.
    Повертає dict:
      {
        "ok": bool,
        "rr": float|None,
        "confidence_pct": float|None,
        "direction": "LONG|SHORT|NO_TRADE|NEUTRAL|None",
        "entry": float|None, "stop": float|None, "tp": float|None,
        "reason": str
      }
    """
    md = md or ""
    rr = _extract_rr(md)
    conf = _extract_conf(md)
    direction = _extract_dir(md)
    lvls = _extract_levels(md)

    reasons = []
    ok = True

    if rr is None:
        ok = False
        reasons.append("RR не знайдено")
    elif rr < rr_threshold:
        ok = False
        reasons.append(f"RR<{rr_threshold}")

    if conf is None:
        reasons.append("Confidence не знайдено")
    elif conf < conf_threshold:
        ok = False
        reasons.append(f"Conf<{conf_threshold}%")

    if direction in ("NO_TRADE", None):
        ok = False
        reasons.append("direction=NO_TRADE або відсутній")

    return {
        "ok": ok,
        "rr": rr,
        "confidence_pct": conf,
        "direction": direction,
        "entry": lvls["entry"],
        "stop": lvls["stop"],
        "tp": lvls["tp"],
        "reason": "; ".join(reasons) if reasons else "ok",
    }
