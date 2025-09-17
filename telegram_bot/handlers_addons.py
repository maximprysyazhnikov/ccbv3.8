# telegram_bot/handlers_addons.py
from __future__ import annotations
from telegram.ext import Application, CallbackQueryHandler
from telegram_bot import panel_neutral  # /neutral, /kpi і їх callback-и
from services.daily_tracker import compute_daily_summary

async def cmd_daily_now(update, context):
    try:
        text = compute_daily_summary()  # без аргументів!
        await update.effective_chat.send_message(text)
    except Exception as e:
        await update.effective_chat.send_message(f"⚠️ daily_now error: {e}")

def register_extra(app: Application):
    # Кнопки з /panel → ті самі екрани, що й /neutral та /kpi
    app.add_handler(CallbackQueryHandler(panel_neutral.cmd_neutral, pattern=r"^panel:neutral$"))
    app.add_handler(CallbackQueryHandler(panel_neutral.cmd_kpi,     pattern=r"^panel:kpi$"))
    # Кнопки вибору режиму на екрані Neutral (CLOSE/TRAIL/IGNORE)
    app.add_handler(CallbackQueryHandler(panel_neutral.cb_neutral,  pattern=r"^neutral_mode:"))
