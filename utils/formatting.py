# utils/formatting.py
from __future__ import annotations
from typing import Any, Dict, Optional
from datetime import datetime



def format_stats(stats: dict, rr_threshold: float, days: int) -> str:
    return (
        f"📊 Win-Rate за {days} днів (RR ≥ {rr_threshold}):\n"
        f"- Сигналів: {stats['count']}\n"
        f"- Win-Rate: {stats['winrate']:.2f}%\n"
        f"- Середній RR: {stats['avg_rr']:.2f}"
    )

def _fmt_num(v: Any, digits_small: int = 4) -> str:
    """Форматує число охайно: великі ціни з 2 знаками, дрібні з 4."""
    try:
        f = float(v)
        if f != f:  # NaN
            return "-"
        if abs(f) >= 1000:
            return f"{f:,.2f}".replace(",", " ")
        return f"{f:.{digits_small}f}"
    except Exception:
        return "-"

def _fmt_pct01(x: Any) -> str:
    """0..1 → 0..100%"""
    try:
        f = float(x)
        if f <= 1.0:
            f *= 100.0
        return f"{f:.2f}%"
    except Exception:
        return "-"

def _fmt_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return "-"
    return dt.strftime("%Y-%m-%d %H:%M")

def build_trade_plan_message(
    *,
    symbol: str,
    timeframe: str,
    model_name: str,
    generated_local: datetime,
    tz_name: str,
    direction: str,
    confidence01: Any,
    rr_text: str,
    entry: Any,
    stop: Any,
    take: Any,
    hold_until_local: Optional[datetime] = None,
    rationale_text: str = "",
) -> str:
    """
    Рендерить повідомлення у стилі:

    🤖 AI Trade Plan for BTCUSDT (TF=15m)
    Model: deepseek/deepseek-chat
    Generated: 2025-08-20 19:31 EEST

    Direction: LONG
    Confidence: 70.00%
    RR: 2.57
    Entry: 114210.00
    Stop:  113837.67
    Take:  115168.35
    Recommended hold: 6 h (до 2025-08-21 01:31 EEST / Europe/Kyiv)

    Reasoning:
    <пара речень>
    """
    lines = []
    lines.append(f"🤖 AI Trade Plan for {symbol} (TF={timeframe})")
    lines.append(f"Model: {model_name}")
    lines.append(f"Generated: {_fmt_dt(generated_local)} {generated_local.tzname() or ''}".strip())
    lines.append("")
    lines.append(f"Direction: {direction or '-'}")
    lines.append(f"Confidence: {_fmt_pct01(confidence01)}")
    lines.append(f"RR: {rr_text}")
    lines.append(f"Entry: {_fmt_num(entry)}")
    lines.append(f"Stop:  {_fmt_num(stop)}")
    lines.append(f"Take:  {_fmt_num(take)}")

    # hold
    if hold_until_local:
        lines.append(f"Recommended hold: "
                     f"{'-' if not hold_until_local else ''}"
                     f"{'' if not hold_until_local else f'(до {_fmt_dt(hold_until_local)} {hold_until_local.tzname()} / {tz_name})'}")
    else:
        # якщо модель дала години — їх можна підставляти поза цим форматером, але лишимо рядок для консистентності
        lines.append("Recommended hold: -")

    lines.append("")
    lines.append("Reasoning:")
    lines.append((rationale_text or "—").strip())
    return "\n".join(lines)
