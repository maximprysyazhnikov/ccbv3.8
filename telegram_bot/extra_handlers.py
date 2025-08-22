from __future__ import annotations
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from services.autopost import run_autopost_once

log = logging.getLogger("tg.extra")

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("⏳ Запускаю автоскан один раз…")
        app = context.application
        # виконуємо блокуючу функцію у треді
        await asyncio.to_thread(run_autopost_once, app)
        await update.message.reply_text("✅ Autopost scan завершено")
    except Exception as e:
        log.exception("/scan failed")
        await update.message.reply_text(f"⚠️ scan error: {e}")

def register_handlers_extra(app: Application):
    app.add_handler(CommandHandler("scan", scan_cmd))
