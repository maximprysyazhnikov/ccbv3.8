# telegram_bot/handlers_addons.py
from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes, Application, CommandHandler
from services.daily_tracker import daily_now
from services.winrate_tracker import winrate_now

async def cmd_daily_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await daily_now(context.bot, update.effective_chat.id)

async def cmd_winrate_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = int(context.args[0]) if context.args else 7
    await winrate_now(context.bot, update.effective_chat.id, days)

def register_extra(app: Application):
    app.add_handler(CommandHandler("daily_now", cmd_daily_now))
    app.add_handler(CommandHandler("winrate_now", cmd_winrate_now))
