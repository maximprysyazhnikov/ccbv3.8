# utils/pretty_md.py
from __future__ import annotations
from typing import Iterable, Optional, Dict, Any
import math

_DIR_EMOJI = {"LONG": "🟢", "SHORT": "🔻", "NEUTRAL": "⚪️", "NO_TRADE": "⚪️"}

def _fmt_num(x: Any, digits: int = 2, dash: str = "-") -> str:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return dash
        return f"{v:,.{digits}f}".replace(",", " ")  # тонкий пробіл як розділювач
    except Exception:
        return dash

def _rr(direction: str, entry: float, stop: float, tp: float) -> str:
    try:
        if any(math.isnan(float(z)) for z in (entry, stop, tp)):
            return "-"
        if direction == "LONG":
            risk = entry - stop
            reward = tp - entry
        elif direction == "SHORT":
            risk = stop - entry
            reward = entry - tp
        else:
            return "-"
        if risk <= 0 or reward <= 0:
            return "-"
        return f"{reward/risk:.2f}"
    except Exception:
        return "-"

def render_trade_brief(
    symbol: str,
    *,
    direction: str,
    confidence: float | int | str,
    entry: float | str | None,
    stop: float | str | None,
    take: float | str | None,
    bullets: Iterable[str] = (),
    notes: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    show_rr: bool = True,
    confidence_as_percent: bool = True,
) -> str:
    """
    Універсальний Markdown-рендер трейд-звіту:
    - symbol: 'BTCUSDT'
    - direction: 'LONG' | 'SHORT' | 'NEUTRAL' | 'NO_TRADE'
    - confidence: 0..1 або 0..100 (визначиться автоматично)
    - entry/stop/take: float/str
    - bullets: список пунктів пояснення
    - notes: довільний текст після 'Notes'
    - meta: {'tf': '15m', 'price_last': 12345.67, ...} — буде додано у шапку (необов'язково)
    """

    meta = meta or {}
    sym = symbol.upper().strip()
    dir_u = str(direction or "").upper().strip()
    emoji = _DIR_EMOJI.get(dir_u, "⚪️")

    # нормалізація confidence
    try:
        c = float(confidence) if isinstance(confidence, (int, float, str)) else 0.0
        # якщо це 0..1 — зробимо %
        if confidence_as_percent and c <= 1.0001:
            c *= 100.0
    except Exception:
        c = 0.0

    # RR
    try:
        e = float(entry)
        s = float(stop)
        t = float(take)
    except Exception:
        e = s = t = float("nan")
    rr_txt = _rr(dir_u, e, s, t) if show_rr else "-"

    # Шапка
    header_lines = [f"## 📊 {sym} — Trade Brief"]
    if meta.get("tf"):
        header_lines[0] = f"## 📊 {sym} — Trade Brief *(TF={meta['tf']})*"

    # Setup
    setup_lines = [
        "### 🎯 Setup",
        f"- **Direction**: {emoji} {dir_u or '-'}",
        f"- **Confidence**: **{_fmt_num(c, 0)}%**",
        f"- **Entry**: `{_fmt_num(entry, 2)}`",
        f"- **Stop**: `{_fmt_num(stop, 2)}`",
        f"- **Take**: `{_fmt_num(take, 2)}`",
    ]
    if show_rr:
        setup_lines.append(f"- **R/R**: **{rr_txt}**")

    # Reasoning
    reason_lines = ["", "---", "", "### 📝 Reasoning"]
    for b in bullets or []:
        b = str(b).strip()
        if not b:
            continue
        # якщо пункт уже містить емодзі або жирні теги — не чіпаємо
        if b[0] in {"📉","📈","🏦","📰","📊","⚖️","🧭","🧪","🧱","🧠","⚙️","💬","🔥","🚨"} or "**" in b:
            reason_lines.append(f"- {b}")
        else:
            reason_lines.append(f"- {b}")

    # Notes
    notes_lines = []
    if notes:
        notes_lines = ["", "---", "", "### ⚠️ Notes", str(notes).strip()]

    # Опціональний блок meta (лаконічно)
    meta_lines = []
    if meta:
        kv = []
        tf = meta.get("tf")
        price_last = meta.get("price_last")
        if tf: kv.append(f"TF=`{tf}`")
        if price_last is not None: kv.append(f"Last=`{_fmt_num(price_last, 2)}`")
        if kv:
            meta_lines = ["", f"> " + " • ".join(kv)]

    return "\n".join(header_lines + [""] + setup_lines + reason_lines + notes_lines + meta_lines) + "\n"
