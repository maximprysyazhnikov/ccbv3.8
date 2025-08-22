from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes, Application, CommandHandler

from services.autopost import run_autopost_once
from utils.trading_db import pnl_summary

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_autopost_once(context.bot)
    await update.message.reply_text("✅ Scan complete.")

async def pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    days = 30
    if context.args:
        try:
            days = max(1, int(context.args[0]))
        except Exception:
            pass
    s = pnl_summary(uid, days)
    text = (f"📊 *PnL {days}d*\n"
            f"Trades: {s['trades']}\n"
            f"WIN/LOSS: {s['wins']}/{s['losses']}\n"
            f"Winrate: {s['winrate']:.1f}%\n"
            f"Avg RR: {s['avg_rr']:.2f}\n"
            f"Avg PnL: {s['avg_pnl_pct']:.2f}%")
    try:
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(text)

def register_handlers_extra(app: Application):
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("pnl", pnl))
