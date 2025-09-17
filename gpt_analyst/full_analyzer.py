# gpt_analyst/full_analyzer.py
from __future__ import annotations

import re
from typing import Optional, Tuple

from core_config import CFG
from router.analyzer_router import pick_route

# OpenRouter клієнт (реальний або запасний)
try:
    from utils.openrouter import chat_completion
except Exception:  # pragma: no cover
    from utils.openrouter_client import chat_completion  # type: ignore


def _make_ta_block(symbol: str, timeframe: str) -> str:
    """
    Повертає Markdown-блок з індикаторами.
    Спочатку пробуємо utils.ta_formatter.format_ta_report.
    """
    # 1) красивий Markdown-пресет
    try:
        from utils.ta_formatter import format_ta_report

        md = format_ta_report(symbol, timeframe, CFG.get("analyze_limit", 150))
        return md if isinstance(md, str) and md.strip() else "_No indicators_"
    except Exception:
        pass

    # 2) fallback: спрощений набір
    try:
        from gpt_analyst.ta_engine import get_ta_indicators  # optional

        data = get_ta_indicators(
            symbol=symbol, timeframe=timeframe, limit=CFG.get("analyze_limit", 150)
        )
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
    "entry": re.compile(r"\bENTRY\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", re.I),
    "sl": re.compile(r"\bS(?:TOP(?:-|\s*)LOSS|L)\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", re.I),
    "tp": re.compile(r"\bT(?:AKE(?:-|\s*)PROFIT|P)\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", re.I),
    "rr": re.compile(r"\bRR\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", re.I),
}


def _calc_rr_block(symbol: str, tf: str, *, entry=None, sl=None, tp=None) -> str:
    """
    Backward-compatible shim.
    Якщо реальна RR-логіка буде в іншому модулі (наприклад, analyzer_core чи services.autopost),
    можна прокинути сюди імпорт і повернути сформатований блок.
    Поки що повертаємо порожній блок, щоб не ламати /ai.
    """
    try:
        # Якщо захочеш — підключи реальний розрахунок:
        # from services.autopost import compute_rr_metrics
        # if entry is not None and sl is not None:
        #     m = compute_rr_metrics(float(entry), float(sl), float(tp) if tp is not None else None)
        #     rr = m.get("rr_target")
        #     if rr is not None:
        #         return f"🎯 RR(target): {rr:.2f}"
        return ""  # тимчасово без RR, але без креша
    except Exception:
        return ""


def _parse_fields(text: str) -> dict:
    t = (text or "").replace("\u00a0", " ")
    out = {"direction": "-", "entry": "-", "sl": "-", "tp": "-", "rr": "-"}
    # direction: якщо є і LONG і SHORT — залишимо «-»
    ds = {m.group(1).upper() for m in re.finditer(_PLAN_RX["direction"], t)}
    if len(ds) == 1:
        out["direction"] = next(iter(ds))
    for k in ("entry", "sl", "tp", "rr"):
        m = _PLAN_RX[k].search(t)
        if m:
            out[k] = f"{float(m.group(1)):.4f}"
    return out


def _normalize_locale(loc: str) -> str:
    """
    Перетворює 'uk'/'ua'/'en' у дволітерний код для підказки LLM.
    Повертає рядок для вставки у system-prompt.
    """
    if not loc:
        return "UK"
    u = loc.strip().lower()
    if u in ("uk", "ua", "uk-UA".lower()):
        return "UK"
    return "EN"


def run_full_analysis(
    symbol: str,
    tf: str,
    route: Optional[str] = None,  # параметр збережено для сумісності API
    locale: str = "uk",
    **_: object,
) -> Tuple[str, str]:
    """
    Генерує короткий план + окремо Markdown з індикаторами.
    Повертає (plan_text_plain, indicators_markdown).
    """
    loc_cfg = CFG.get("default_locale", "uk")
    loc_norm = _normalize_locale(locale or loc_cfg)

    indicators_md = _make_ta_block(symbol, tf)
    rr_block = _calc_rr_block(symbol, tf)

    system = f"You are a concise crypto trading assistant. Respond in {loc_norm}."
    user = (
        f"Symbol: {symbol}\n"
        f"Timeframe: {tf}\n\n"
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
    if rr_block:
        user += f"\nRR helper:\n{rr_block}\n"

    # Вибір маршруту LLM: без undefined змінних і без перезапису параметра route
    chosen_route = pick_route(symbol)

    resp = chat_completion(
        endpoint=(
            chosen_route.base
            if chosen_route and getattr(chosen_route, "base", None)
            else CFG.get("or_base")
        ),
        api_key=(chosen_route.api_key if chosen_route else None),
        model=(chosen_route.model if chosen_route else None),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        timeout=(chosen_route.timeout if chosen_route else CFG.get("or_timeout", 30)),
    ) or ""

    # витягуємо ключові числа, щоб гарантовано були у плані
    parsed = _parse_fields(resp)
    header = (
        f"{symbol} [{tf}] → {parsed['direction']}\n"
        f"Entry: {parsed['entry']} | SL: {parsed['sl']} | TP: {parsed['tp']}\n"
        f"RR: {parsed['rr']}\n"
    )

    # план без Markdown, щоб безпечніше відправляти
    body = resp.strip()
    plan_plain = header + (("\n" + body) if body else "")
    return plan_plain, indicators_md
