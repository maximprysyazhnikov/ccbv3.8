# telegram_bot/panel_neutral.py
from __future__ import annotations

import os
import sqlite3
import logging
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from services.daily_tracker import compute_kpis  # повертає ГОТОВИЙ ТЕКСТ

log = logging.getLogger("panel_neutral")

DB_PATH = (
    os.getenv("DB_PATH")
    or os.getenv("SQLITE_PATH")
    or os.getenv("DATABASE_PATH")
    or "storage/bot.db"
)

# ───────────────────────────────────────────────
# DB helpers
# ───────────────────────────────────────────────
def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c

def _ensure_settings_table(cur: sqlite3.Cursor) -> None:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings(
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)

def _get_setting(key: str, default: str) -> str:
    try:
        with _conn() as c:
            cur = c.cursor()
            _ensure_settings_table(cur)
            cur.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = cur.fetchone()
            if row and row[0] is not None:
                return str(row[0])
    except Exception as e:
        log.debug("get_setting(%s) failed: %s", key, e)
    # .env fallback
    v = os.getenv(key.upper())
    return v if v is not None else default

def _set_setting(key: str, value: str) -> None:
    with _conn() as c:
        cur = c.cursor()
        _ensure_settings_table(cur)
        cur.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        c.commit()

# ───────────────────────────────────────────────
# UI helpers
# ───────────────────────────────────────────────
_ALLOWED = ("CLOSE", "TRAIL", "IGNORE")

def _neutral_keyboard(current: str) -> InlineKeyboardMarkup:
    def mark(opt: str) -> str:
        return ("✅ " if opt.upper() == current.upper() else "   ") + opt
    rows = [
        [
            InlineKeyboardButton(mark("CLOSE"), callback_data="neutral_mode:CLOSE"),
            InlineKeyboardButton(mark("TRAIL"), callback_data="neutral_mode:TRAIL"),
            InlineKeyboardButton(mark("IGNORE"), callback_data="neutral_mode:IGNORE"),
        ]
    ]
    return InlineKeyboardMarkup(rows)

def _neutral_text(current: str) -> str:
    return (
        "⚙️ Neutral mode\n\n"
        "Що робити, коли напрям сигналу стає NEUTRAL?\n"
        "• CLOSE — закривати позицію й фіксувати причину 'neutral'.\n"
        "• TRAIL — підтягувати SL до BE (або -0.25R), не закриваючи.\n"
        "• IGNORE — нічого не робити (не рекомендовано).\n\n"
        f"Поточне значення: *{current}*"
    )

# ───────────────────────────────────────────────
# Handlers
# ───────────────────────────────────────────────
async def cmd_neutral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = _get_setting("neutral_mode", "TRAIL").upper()
    if mode not in _ALLOWED:
        mode = "TRAIL"
    await update.effective_chat.send_message(
        _neutral_text(mode),
        reply_markup=_neutral_keyboard(mode),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )

async def cb_neutral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data:
        return
    await q.answer()
    try:
        _, val = q.data.split(":", 1)
        val_up = val.strip().upper()
        if val_up not in _ALLOWED:
            await q.edit_message_text("⚠️ Невідоме значення neutral_mode")
            return
        _set_setting("neutral_mode", val_up)
        await q.edit_message_text(
            _neutral_text(val_up),
            reply_markup=_neutral_keyboard(val_up),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    except Exception as e:
        log.warning("cb_neutral failed: %s", e)
        try:
            await q.edit_message_text(f"⚠️ Помилка: {e}")
        except Exception:
            pass

async def cmd_kpi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Показує KPI (останній період і RR-бакет беруться з settings/.env).
    compute_kpis() повертає вже готовий текст → просто відсилаємо.
    """
    try:
        text = compute_kpis()
    except Exception as e:
        text = f"⚠️ KPI error: {e}"
    await update.effective_chat.send_message(
        text,
        disable_web_page_preview=True,
    )

# ───────────────────────────────────────────────
# Registration
# ───────────────────────────────────────────────
def register(app: Application) -> None:
    """
    Реєструємо лише /neutral, /kpi і обробник neutral_mode:*
    (кнопки panel:* додаються в handlers_addons.py, щоб не дублювати відповіді)
    """
    app.add_handler(CommandHandler("neutral", cmd_neutral))
    app.add_handler(CommandHandler("kpi", cmd_kpi))
    app.add_handler(CallbackQueryHandler(cb_neutral, pattern=r"^neutral_mode:"))
