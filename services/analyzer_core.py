from __future__ import annotations
import math, uuid, time
from typing import Optional, Tuple, Dict, Any
from zoneinfo import ZoneInfo

from core_config import CFG
from market_data.candles import get_ohlcv, snapshot_ts
from utils.ta_formatter import format_ta_report
from router.analyzer_router import pick_route
from utils.openrouter import chat_completion

# ---- парсер ----
def _rr(direction: str, entry: float, stop: float, tp: float) -> Optional[float]:
    try:
        if any(math.isnan(x) for x in (entry, stop, tp)): return None
        if direction == "LONG":
            risk = entry - stop; reward = tp - entry
        elif direction == "SHORT":
            risk = stop - entry; reward = entry - tp
        else:
            return None
        if risk <= 0 or reward <= 0: return None
        return reward / risk
    except Exception:
        return None

def _strip_md(s: str) -> str:
    import re
    s = re.sub(r"[*_`]", "", s or "")
    return " ".join(s.split())

def _parse_ai_json(txt: str) -> Dict[str, Any]:
    import json, re
    t = (txt or "").strip()
    if t.startswith("```"):
        t = t.strip("` \n")
        t = re.sub(r"^json\s*", "", t, flags=re.I).strip("` \n")
    try:
        d = json.loads(t)
        return {
            "direction": str(d.get("direction","")).upper(),
            "entry": float(d.get("entry","nan")),
            "stop": float(d.get("stop","nan")),
            "tp": float(d.get("tp","nan")),
            "confidence": float(d.get("confidence",0.0)),
            "holding_time_hours": float(d.get("holding_time_hours",0.0)),
            "rationale": str(d.get("rationale","")).strip()
        }
    except Exception:
        # fallback: простий витяг
        import re, math
        dir_m = re.search(r"\b(LONG|SHORT|NEUTRAL)\b", txt or "", re.I)
        def num(rx):
            m = re.search(rx + r"\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", txt or "", re.I)
            return float(m.group(1)) if m else float("nan")
        return {
            "direction": dir_m.group(1).upper() if dir_m else "NEUTRAL",
            "entry": num(r"(?:entry|price)"),
            "stop":  num(r"(?:stop(?:-|\s*)loss|sl)"),
            "tp":    num(r"(?:take(?:-|\s*)profit|tp)"),
            "confidence": 0.5,
            "holding_time_hours": 0.0,
            "rationale": (txt or "").strip(),
        }

# ---- публічний API ----
def generate_trade_plan(symbol: str, timeframe: str, *, user_model_key: Optional[str], locale: str) -> Tuple[Dict[str,Any], str]:
    """
    Повертає (plan_dict, indicators_md). НІЧОГО НЕ ПИШЕ В БД.
    """
    data = get_ohlcv(symbol, timeframe, CFG.get("analyze_limit", 150))
    last_close = data[-1]["close"] if data else float("nan")

    ta_md = format_ta_report(symbol, timeframe, CFG.get("analyze_limit", 150))
    ta_raw = _strip_md(ta_md)

    route = pick_route(symbol, user_model_key=(user_model_key or "auto"))
    system = (
        "You are a concise crypto trading assistant. "
        "Return STRICT JSON only with keys exactly: "
        '{"direction":"LONG|SHORT|NEUTRAL","entry":number,"stop":number,"tp":number,'
        '"confidence":0..1,"holding_time_hours":number,"rationale":"2-3 sentences"}'
    )
    user = (
        f"SYMBOL: {symbol}\nTF: {timeframe}\nLAST_PRICE: {last_close}\n\n"
        f"INDICATORS_PRESET:\n{ta_raw}\n\n"
        "Decide if there is a trade now and return STRICT JSON."
    )

    raw = chat_completion(
        endpoint=CFG.get("or_base"),
        api_key=route.api_key if route else None,
        model=route.model if route else None,
        messages=[{"role":"system","content":system},{"role":"user","content":user}],
        timeout=route.timeout if route else CFG.get("or_timeout", 30),
        max_tokens=256,
        temperature=0.2,
    )
    plan = _parse_ai_json(raw)
    # enrich
    plan["direction"] = (plan.get("direction") or "NEUTRAL").upper()
    plan["rr"] = _rr(plan["direction"], float(plan.get("entry", math.nan)), float(plan.get("stop", math.nan)), float(plan.get("tp", math.nan)))
    return plan, ta_md
