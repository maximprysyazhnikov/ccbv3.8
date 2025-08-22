# gpt_analyst/full_analyzer.py
from __future__ import annotations
import re
from typing import Optional, Tuple

from core_config import CFG
from router.analyzer_router import pick_route

# OpenRouter клієнт (реальний або запасний)
try:
    from utils.openrouter import chat_completion
except Exception:
    from utils.openrouter_client import chat_completion  # type: ignore

def _make_ta_block(symbol: str, timeframe: str) -> str:
    """
    Повертає Markdown‑блок з індикаторами.
    Спочатку пробуємо utils.ta_formatter.format_ta_report.
    """
    # 1) красивий Markdown‑пресет
    try:
        from utils.ta_formatter import format_ta_report
        md = format_ta_report(symbol, timeframe, CFG.get("analyze_limit", 150))
        return md if isinstance(md, str) and md.strip() else "_No indicators_"
    except Exception:
        pass

    # 2) fallback: спрощений набір
    try:
        from gpt_analyst.ta_engine import get_ta_indicators  # optional
        data = get_ta_indicators(symbol=symbol, timeframe=timeframe, limit=CFG.get("analyze_limit", 150))
        lines = [f"*{symbol}* (TF={timeframe}) — Indicators", ""]
        for k, v in data.items():
            try:
                lines.append(f"- {k}: `{float(v):.4f}`")
            except Exception:
                lines.append(f"- {k}: `{v}`")
        return "\n".join(lines)
    except Exception:
        return f"*{symbol}* (TF={timeframe}) — _indicators unavailable_"

_PLAN_RX = {
    "direction": re.compile(r"\b(LONG|SHORT)\b", re.I),
    "entry":     re.compile(r"\bENTRY\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", re.I),
    "sl":        re.compile(r"\bS(?:TOP(?:-|\s*)LOSS|L)\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", re.I),
    "tp":        re.compile(r"\bT(?:AKE(?:-|\s*)PROFIT|P)\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", re.I),
    "rr":        re.compile(r"\bRR\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", re.I),
}

def _parse_fields(text: str) -> dict:
    t = (text or "").replace("\u00a0"," ")
    out = {"direction": "-", "entry": "-", "sl": "-", "tp": "-", "rr": "-"}
    # direction: якщо є і LONG і SHORT — залишимо «-»
    ds = set(m.group(1).upper() for m in re.finditer(_PLAN_RX["direction"], t))
    if len(ds) == 1:
        out["direction"] = next(iter(ds))
    for k in ("entry","sl","tp","rr"):
        m = _PLAN_RX[k].search(t)
        if m:
            out[k] = f"{float(m.group(1)):.4f}"
    return out

def run_full_analysis(symbol: str, timeframe: str, *,
                      locale: Optional[str] = None,
                      user_model_key: Optional[str] = None) -> Tuple[str, str]:
    """
    Генерує короткий план + окремо Markdown з індикаторами.
    Повертає (plan_text_plain, indicators_markdown).
    """
    loc = (locale or CFG.get("default_locale","uk")).strip().upper()
    if loc not in ("UK", "UA", "EN"):
        loc = "UK"

    indicators_md = _make_ta_block(symbol, timeframe)

    system = f"You are a concise crypto trading assistant. Respond in {loc}."
    user = (
        f"Symbol: {symbol}\n"
        f"Timeframe: {timeframe}\n\n"
        "Based on the technical indicators (see below), decide if a trade is present now.\n"
        "Return a *short* plan containing the fields on their own lines:\n"
        "Direction: LONG|SHORT\n"
        "Entry: <number>\n"
        "SL: <number>\n"
        "TP: <number>\n"
        "RR: <number>\n"
        "One or two sentences of rationale are OK after that.\n\n"
        "Indicators:\n"
        f"{indicators_md}\n"
    )

    route = pick_route(symbol, user_model_key=user_model_key)
    resp = chat_completion(
        endpoint=(route.base if route and getattr(route, "base", None) else CFG.get("or_base")),
        api_key=(route.api_key if route else None),
        model=(route.model if route else None),
        messages=[{"role":"system","content":system},{"role":"user","content":user}],
        timeout=(route.timeout if route else CFG.get("or_timeout", 30)),
    ) or ""

    # витягуємо ключові числа, щоб гарантовано були у плані
    parsed = _parse_fields(resp)
    header = (
        f"{symbol} [{timeframe}] → {parsed['direction']}\n"
        f"Entry: {parsed['entry']} | SL: {parsed['sl']} | TP: {parsed['tp']}\n"
        f"RR: {parsed['rr']}\n"
    )
    # план без Markdown, щоб безпечніше відправляти
    plan_plain = header + ("\n" + resp.strip() if resp.strip() else "")
    return plan_plain, indicators_md
