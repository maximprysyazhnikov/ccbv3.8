# telegram_bot/panel.py
from __future__ import annotations
from typing import List
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram_bot import panel_neutral
from core_config import CFG
from utils.user_settings import get_user_settings, set_user_settings, ensure_user_row

TF_OPTIONS: List[str] = ["5m", "15m", "1h", "4h", "1d"]
AP_RR_OPTIONS: List[float] = [1.0, 1.5, 2.0, 3.0]
LOCALE_OPTIONS: List[str] = ["uk", "en"]

def _bool_emoji(v: int | bool | None) -> str:
    return "✅ ON" if bool(v or 0) else "❌ OFF"

def _mark(value: str, current: str) -> str:
    return f"✅ {value}" if str(value) == str(current) else value

def _model_options() -> List[str]:
    models: List[str] = []
    try:
        for s in (CFG.get("or_slots") or []):
            m = s.get("model")
            if m and m not in models:
                models.append(m)
    except Exception:
        pass
    if not models:
        models = [CFG.get("or_model") or "deepseek/deepseek-chat"]
    return ["auto"] + models

def panel_keyboard(user_id: int) -> InlineKeyboardMarkup:
    ensure_user_row(user_id)
    us = get_user_settings(user_id) or {}

    timeframe = us.get("timeframe") or CFG.get("analyze_timeframe", "15m")
    autopost  = int(us.get("autopost") or 0)
    ap_tf     = us.get("autopost_tf") or timeframe
    ap_rr     = float(us.get("autopost_rr") or 1.5)
    model_key = (us.get("model_key") or "auto")
    locale    = (us.get("locale") or CFG.get("default_locale","uk")).lower()

    daily_tracker   = int(us.get("daily_tracker") or 0)
    winrate_tracker = int(us.get("winrate_tracker") or 0)

    rows: list[list[InlineKeyboardButton]] = []

    # Autopost ON/OFF
    rows.append([
        InlineKeyboardButton(
            f"Autopost: {_bool_emoji(autopost)}",
            callback_data=f"panel:toggle_autopost:{1 if not autopost else 0}"
        )
    ])

    rows.append([
        InlineKeyboardButton("⚙️ Neutral", callback_data="panel:neutral"),
        InlineKeyboardButton("📊 KPI", callback_data="panel:kpi"),
    ])
    keyboard = InlineKeyboardMarkup(rows)

    # Timeframe
    rows.append([InlineKeyboardButton(_mark(tf, timeframe), callback_data=f"panel:set_tf:{tf}") for tf in TF_OPTIONS])

    # Autopost TF
    rows.append([InlineKeyboardButton(_mark(tf, ap_tf), callback_data=f"panel:set_ap_tf:{tf}") for tf in TF_OPTIONS])

    # Autopost RR threshold
    rows.append([
        InlineKeyboardButton(
            _mark(f"AP RR {r:.1f}", f"AP RR {ap_rr:.1f}"),
            callback_data=f"panel:set_ap_rr:{r}"
        ) for r in AP_RR_OPTIONS
    ])

    # Models (групами по 4)
    m_row: list[InlineKeyboardButton] = []
    for m in _model_options():
        cap = m if m != model_key else f"✅ {m}"
        m_row.append(InlineKeyboardButton(cap, callback_data=f"panel:set_model:{m}"))
        if len(m_row) == 4:
            rows.append(m_row); m_row = []
    if m_row: rows.append(m_row)

    # Locale
    rows.append([
        InlineKeyboardButton(loc.upper() if loc != locale else f"✅ {loc.upper()}",
                             callback_data=f"panel:set_locale:{loc}")
        for loc in LOCALE_OPTIONS
    ])

    # Daily / Winrate (вказуємо цільове значення прямо у callback_data)
    rows.append([
        InlineKeyboardButton(
            f"Daily: {_bool_emoji(daily_tracker)}",
            callback_data=f"panel:toggle_daily:{0 if daily_tracker else 1}"
        ),
        InlineKeyboardButton(
            f"Winrate: {_bool_emoji(winrate_tracker)}",
            callback_data=f"panel:toggle_winrate:{0 if winrate_tracker else 1}"
        ),
    ])

    rows.append([InlineKeyboardButton("ℹ️ Help", callback_data="panel:help:")])
    return InlineKeyboardMarkup(rows)

def apply_panel_action(user_id: int, action: str, value: str) -> None:
    ensure_user_row(user_id)

    if action == "toggle_autopost":
        try: v = int(value)
        except: v = 0
        set_user_settings(user_id, autopost=v)

    elif action == "set_tf" and value:
        set_user_settings(user_id, timeframe=value)

    elif action == "set_ap_tf" and value:
        set_user_settings(user_id, autopost_tf=value)

    elif action == "set_ap_rr":
        try: rr = float(value)
        except: rr = 1.5
        set_user_settings(user_id, autopost_rr=rr)

    elif action == "set_model":
        mk = (value or "auto").strip()
        if mk: set_user_settings(user_id, model_key=mk)

    elif action == "set_locale":
        loc = (value or "").strip().lower()
        if loc in LOCALE_OPTIONS: set_user_settings(user_id, locale=loc)

    elif action == "toggle_daily":
        try: newv = int(value)
        except: newv = 0 if (get_user_settings(user_id).get("daily_tracker") or 0) else 1
        set_user_settings(user_id, daily_tracker=newv)

    elif action == "toggle_winrate":
        try: newv = int(value)
        except: newv = 0 if (get_user_settings(user_id).get("winrate_tracker") or 0) else 1
        set_user_settings(user_id, winrate_tracker=newv)

    elif action == "help":
        pass
