from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from services.trade_engine import get_setting, set_setting
from services.daily_tracker import compute_kpis

def _neutral_keyboard(current: str) -> InlineKeyboardMarkup:
    cur = (current or "TRAIL").upper()
    def btn(label: str) -> InlineKeyboardButton:
        mark = "✅ " if cur == label else ""
        return InlineKeyboardButton(f"{mark}{label}", callback_data=f"neutral_mode:{label}")
    row = [btn("CLOSE"), btn("TRAIL"), btn("IGNORE")]
    return InlineKeyboardMarkup([row])

async def cmd_neutral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = get_setting("neutral_mode", "TRAIL").upper()
    await update.message.reply_text(
        f"Neutral mode: *{mode}*\n\n"
        "CLOSE → close trade on NEUTRAL\n"
        "TRAIL → trail SL on NEUTRAL\n"
        "IGNORE → do nothing",
        reply_markup=_neutral_keyboard(mode),
        parse_mode="Markdown",
    )

async def cb_neutral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, mode = q.data.split(":", 1)
    set_setting("neutral_mode", mode.upper())
    await q.edit_message_text(
        f"Neutral mode set to *{mode}*",
        parse_mode="Markdown",
        reply_markup=_neutral_keyboard(mode),
    )

def _kpi_text(k: dict) -> str:
    return (
        "📊 *KPIs (last 24h)*\n"
        f"- Winrate: *{k['winrate']}%*\n"
        f"- PnL: *{k['pnl_usd']}$*\n"
        f"- Trades: *{k['trades']}*\n"
        f"- Avg RR: *{k['avg_rr']}*\n"
        f"- $100 on RR≥3: *{k['rr3_usd100']}$*\n"
    )

async def cmd_kpi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    k = compute_kpis(hours=24)
    await update.message.reply_text(_kpi_text(k), parse_mode="Markdown")

def register(app: Application):
    app.add_handler(CommandHandler("neutral", cmd_neutral))
    app.add_handler(CallbackQueryHandler(cb_neutral, pattern=r"^neutral_mode:"))
    app.add_handler(CommandHandler("kpi", cmd_kpi))
