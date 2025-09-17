# telegram_bot/handlers_help.py
from telegram import Update
from telegram.ext import ContextTypes
from utils.texts import HELP_UA, GUIDE_SIGNAL_UA

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(HELP_UA)

async def cmd_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(GUIDE_SIGNAL_UA)

async def show_signal_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q:
        await q.answer()
        await q.message.reply_text(GUIDE_SIGNAL_UA)
