# main.py
from __future__ import annotations
import asyncio
import logging
import os
from datetime import time as dtime

from telegram.ext import Application, AIORateLimiter

from core_config import CFG
from telegram_bot.handlers import register_handlers
from services.daily_tracker import daily_tracker_job
from services.winrate_tracker import winrate_job

# optional imports (можуть бути відсутні)
try:
    from services.autopost import run_autopost_once  # синхронна функція, повертає список повідомлень
except Exception:
    run_autopost_once = None

try:
    # синхронна функція без аргументів; якщо немає — пропускаємо job
    from services.signal_closer import close_signals_once
except Exception:
    close_signals_once = None

from zoneinfo import ZoneInfo
TZ = ZoneInfo(os.getenv("TZ_NAME", "Europe/Kyiv"))

log = logging.getLogger("app")
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s"
)

# ──────────────────────────────────────────────────────────────────────────────
# Error handler
# ──────────────────────────────────────────────────────────────────────────────
async def on_error(update, context):
    log.exception("Unhandled error while processing update", exc_info=context.error)

# ──────────────────────────────────────────────────────────────────────────────
# Async wrappers for jobs (PTB JobQueue очікує async)
# ──────────────────────────────────────────────────────────────────────────────
async def autopost_scan(context):
    """
    Запускає автопост: розрахунок у треді, відправка тут (async).
    run_autopост_once() має повертати список повідомлень [{"chat_id", "text", ...}, ...]
    """
    if run_autopost_once is None:
        log.warning("autopost_scan skipped: services.autopost.run_autopost_once not available")
        return
    try:
        msgs = await asyncio.to_thread(run_autopost_once, context.application)
        sent = 0
        for m in msgs or []:
            try:
                await context.bot.send_message(
                    m.get("chat_id"),
                    m.get("text", ""),
                    parse_mode=m.get("parse_mode"),
                    disable_web_page_preview=m.get("disable_web_page_preview", True),
                )
                sent += 1
            except Exception as e:
                log.warning("autopost send fail: %s", e)
        log.info("autopost scan done (sent=%d)", sent)
    except Exception as e:
        log.exception("autopost_scan failed: %s", e)

async def signal_closer_job(context):
    """Періодичне закриття сигналів, якщо модуль доступний."""
    if close_signals_once is None:
        return
    try:
        await asyncio.to_thread(close_signals_once)
    except Exception as e:
        log.warning("signal_closer failed: %s", e)

async def daily_pnl_job(context):
    """Щоденний P&L о 23:59 локального часу."""
    try:
        # daily_tracker_job очікує bot як аргумент
        await asyncio.to_thread(daily_tracker_job, context.bot)
    except Exception as e:
        log.warning("daily_pnl_job failed: %s", e)

async def winrate_daily_job(context):
    """Winrate за останні 7 днів щодня о 00:05 локального часу."""
    try:
        await asyncio.to_thread(winrate_job, context.bot, 7)
    except Exception as e:
        log.warning("winrate_daily_job failed: %s", e)

# ──────────────────────────────────────────────────────────────────────────────
# App bootstrap
# ──────────────────────────────────────────────────────────────────────────────
def build_app():
    if not CFG.get("tg_token"):
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing in .env")

    app = (
        Application.builder()
        .token(CFG["tg_token"])
        .rate_limiter(AIORateLimiter())
        .build()
    )

    # хендлери
    register_handlers(app)

    # error handler
    app.add_error_handler(on_error)

    # jobs (intervals з .env/CFG)
    interval_autopost = int(CFG.get("autopost_interval_sec", 300))  # 5 хв за замовчуванням
    interval_closer = int(CFG.get("signal_closer_interval_sec", 120))

    # автопост скан (якщо модуль доступний — він все одно перевіряється в самій функції)
    app.job_queue.run_repeating(
        autopost_scan,
        interval=interval_autopost,
        first=5,
        name="autopost_scan",
    )

    # періодичне закриття сигналів (плануємо завжди; всередині є guard)
    app.job_queue.run_repeating(
        signal_closer_job,
        interval=interval_closer,
        first=15,
        name="signal_closer",
    )

    # денний P&L — 23:59 локального часу
    app.job_queue.run_daily(
        daily_pnl_job,
        time=dtime(hour=23, minute=59, tzinfo=TZ),
        name="daily_pnl_job",
    )

    # winrate — 00:05 локального часу
    app.job_queue.run_daily(
        winrate_daily_job,
        time=dtime(hour=0, minute=5, tzinfo=TZ),
        name="winrate_job",
    )

    log.info("[jobqueue] ✅ scheduled: autopost_scan every %ss, signal_closer every %ss; daily_pnl 23:59; winrate 00:05 (TZ=%s)",
             interval_autopost, interval_closer, TZ.key if hasattr(TZ, "key") else "Europe/Kyiv")
    return app

def main():
    # (опц.) міграції БД якщо використовуєш utils/db_migrate.py у імпорті
    try:
        from utils.db_migrate import migrate_if_needed
        migrate_if_needed()
    except Exception:
        pass

    app = build_app()

    mode = str(CFG.get("bot_mode", "polling")).lower()
    if mode == "webhook" and CFG.get("webhook_url"):
        # webhook mode
        url = CFG["webhook_url"].rstrip("/") + "/" + CFG["tg_token"]
        port = int(CFG.get("port", 8080))
        log.info("Starting bot (webhook) on port %s …", port)
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=CFG["tg_token"],
            webhook_url=url,
        )
    else:
        # polling mode
        log.info("Starting bot (polling)…")
        app.run_polling()

if __name__ == "__main__":
    main()
