# telegram_bot/bot.py
from __future__ import annotations
import logging, os
from typing import Optional

from telegram.ext import Application
from core_config import CFG
from telegram_bot.handlers import register_handlers

log = logging.getLogger("tg.bot")

# ---- error handler (глобальний) ---------------------------------------------
async def on_error(update, context):
    log.exception("Unhandled error", exc_info=context.error)
    try:
        chat = update.effective_chat if update else None
        if chat:
            await context.bot.send_message(chat.id, "⚠️ Виникла помилка. Уже чиню.")
    except Exception:
        pass

# ---- побудова застосунку ----------------------------------------------------
def _build_app(token: Optional[str] = None) -> Application:
    token = token or getattr(CFG, "telegram_bot_token", None) or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in CFG or ENV")

    app = Application.builder().token(token).build()
    register_handlers(app)
    app.add_error_handler(on_error)
    return app

# ---- запуск (синхронний, без asyncio.run) -----------------------------------
def run():
    """
    Підтримує два режими:
      - polling (локалка)
      - webhook (прод)
    """
    app = _build_app()

    mode = (getattr(CFG, "bot_mode", None) or os.getenv("BOT_MODE") or "polling").lower()
    tz = getattr(CFG, "tz_name", "UTC")
    log.info("Starting bot in %s mode (TZ=%s)", mode, tz)

    if mode == "webhook":
        webhook_url = getattr(CFG, "webhook_url", None) or os.getenv("WEBHOOK_URL")
        port = int(getattr(CFG, "port", 8080) or os.getenv("PORT") or 8080)
        listen = "0.0.0.0"

        if not webhook_url:
            raise RuntimeError("WEBHOOK_URL must be set for webhook mode")

        # PTB 21: синхронний блокуючий виклик
        app.run_webhook(
            listen=listen,
            port=port,
            url_path="",
            webhook_url=webhook_url,
            allowed_updates=None,
            drop_pending_updates=True,
        )
    else:
        # PTB 21: синхронний блокуючий виклик
        app.run_polling(
            allowed_updates=None,
            drop_pending_updates=True,
        )
