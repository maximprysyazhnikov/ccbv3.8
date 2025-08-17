# telegram_bot/bot.py
from __future__ import annotations
import logging, os, sys

# щоб імпортувати пакет від кореня проекту
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from core_config import TELEGRAM_BOT_TOKEN
from telegram_bot.handlers import (
    start, help_cmd, ping, analyze, top, ai, news, guide, on_cb_detail
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("tg.bot")

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Команди
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("analyze", analyze))
    app.add_handler(CommandHandler("ai", ai))
    app.add_handler(CommandHandler("news", news))      # опційно
    app.add_handler(CommandHandler("guide", guide))    # ← НОВЕ: інструкція

    # Callback‑кнопки (на майбутнє)
    app.add_handler(CallbackQueryHandler(on_cb_detail, pattern=r"^detail:"))

    log.info("🤖 Running bot…")
    # Якщо десь уже крутиться APScheduler — тут нічого додатково не запускаємо.
    app.run_polling(close_loop=False, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    main()
