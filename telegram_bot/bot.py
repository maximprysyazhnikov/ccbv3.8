from __future__ import annotations
import logging
from typing import Optional
from telegram.ext import Application

from core_config import CFG
from telegram_bot.handlers import register_handlers
from telegram_bot.extra_handlers import register_handlers_extra
from scheduler.runner import start_autopost

log = logging.getLogger("tg.bot")

async def on_error(update, context):
    log.exception("Unhandled error", exc_info=context.error)
    try:
        chat = update.effective_chat if update else None
        if chat:
            await chat.send_message("⚠️ Виникла помилка, спробуйте ще раз пізніше.")
    except Exception:
        pass

def run_app(webhook_url: Optional[str] = None, listen: str = "0.0.0.0", port: int = 8080):
    app = Application.builder().token(CFG["tg_token"]).build()
    register_handlers_extra(app)
    register_handlers(app)
    start_autopost(app)
    app.add_error_handler(on_error)

    mode = CFG.get("bot_mode", "polling")
    if mode == "webhook" and webhook_url:
        app.run_webhook(
            listen=listen, port=port, url_path="",
            webhook_url=webhook_url, drop_pending_updates=True,
        )
    else:
        app.run_polling(drop_pending_updates=True)
