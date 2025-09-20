from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import os
import inspect

# вмикає TTL-кеш для get_setting
import utils.settings_cached  # noqa: F401

from datetime import time as dtime
from zoneinfo import ZoneInfo
from utils.db_migrate import migrate_if_needed
migrate_if_needed()
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import (
    Application,
    AIORateLimiter,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters as tg_filters,
)

import sitecustomize  # noqa: F401  # LLM-guard

from core_config import CFG
from services.autopost import mark_autopost_sent, run_autopost_once
from services.daily_tracker import daily_tracker_job
from services.kpi import kpi_summary
from services.winrate_tracker import winrate_job
from services.autopost_bridge import handle_autopost_message

from telegram_bot.handlers import register_handlers  # ваш catch-all "^panel:"
from telegram_bot.handlers_addons import register_extra  # /daily_now, /winrate_now, panel:neutral/kpi
from telegram_bot import panel_neutral  # ⚙️ Neutral і 📊 KPI
from telegram_bot.handlers_help import cmd_help, cmd_guide, show_signal_guide

# ───────────────────────────────────────────────
# optional integrations (best-effort imports)
# ───────────────────────────────────────────────
_close_fn = None
try:
    from services.signal_closer import check_and_close_neutral as _close_fn
except Exception:
    try:
        from services.signal_closer import close_signals_once as _close_fn
    except Exception:
        _close_fn = None

try:
    from services.position_manager import manage_open_positions as _pm_fn
except Exception:
    _pm_fn = None

try:
    from services.signal_sync import sync_signals_once
except Exception:
    sync_signals_once = None

try:
    from alerts.push_alerts import run_alerts_once as _alerts_fn
except Exception:
    _alerts_fn = None

# ───────────────────────────────────────────────
# globals & logging
# ───────────────────────────────────────────────
TZ = ZoneInfo(os.getenv("TZ_NAME", "Europe/Kyiv"))

log = logging.getLogger("app")
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
)
logging.getLogger("llm_guard").setLevel(logging.ERROR)


# ───────────────────────────────────────────────
# helpers: universal maybe-async runner
# ───────────────────────────────────────────────
async def _run_maybe_async(fn, /, *args, **kwargs):
    """
    Виконує fn як async (await), або як sync у thread; якщо sync-функція повернула корутину — теж await.
    """
    if fn is None:
        return None
    try:
        if inspect.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)
        res = await asyncio.to_thread(fn, *args, **kwargs)
        if asyncio.iscoroutine(res):
            return await res
        return res
    except Exception:
        log.warning("runner failed for %s", getattr(fn, "__name__", fn), exc_info=True)
        return None


# ───────────────────────────────────────────────
# /kpi helpers ✨
# ───────────────────────────────────────────────
def _parse_kpi_args(args: list[str]) -> tuple[str, int]:
    """Підтримує /kpi, /kpi 3, /kpi trades 7, /kpi signals 14, /kpi 14 trades."""
    table = "trades"
    days = 7
    if not args:
        return table, days

    if len(args) == 1:
        if args[0].isdigit():
            days = int(args[0])
        else:
            a = args[0].lower()
            table = "signals" if a.startswith("sig") else "trades"
        return table, max(1, days)

    a, b = args[0], args[1]
    a_is_num, b_is_num = a.isdigit(), b.isdigit()
    if a_is_num and not b_is_num:
        days = int(a)
        table = "signals" if b.lower().startswith("sig") else "trades"
    elif b_is_num and not a_is_num:
        table = "signals" if a.lower().startswith("sig") else "trades"
        days = int(b)
    else:
        if a_is_num:
            days = int(a)
        if b.lower().startswith("sig"):
            table = "signals"

    return table, max(1, days)


def _kpi_keyboard(table: str, days: int) -> InlineKeyboardMarkup:
    """Інлайн-клавіатура: пресети днів і перемикач таблиці."""
    other_table = "signals" if table == "trades" else "trades"
    presets = [3, 7, 14, 30]
    rows = [
        [InlineKeyboardButton(f"{d}d", callback_data=f"kpi:{table}:{d}") for d in presets],
        [InlineKeyboardButton(
            f"Switch → {other_table}", callback_data=f"kpi:{other_table}:{days}"
        )],
    ]
    return InlineKeyboardMarkup(rows)


def _append_pnl_bars(report_text: str) -> str:
    """Парсить табличку KPI та додає компактний ASCII-bar по PnL наприкінці."""
    lines = report_text.splitlines()
    rows: list[tuple[str, float]] = []
    in_rows = False

    for ln in lines:
        if not in_rows and "Symbol" in ln and "PnL" in ln:
            in_rows = True
            continue
        if in_rows:
            if ln.strip().startswith("TOTAL"):
                break
            if set(ln.strip()) <= {"─", "—", " ", "─"} or not ln.strip():
                continue
            parts = ln.split()
            if len(parts) < 2:
                continue
            symbol = parts[0]
            pnl = None
            for tok in reversed(parts):
                tok2 = tok.replace(",", "")
                try:
                    pnl = float(tok2)
                    break
                except ValueError:
                    continue
            if pnl is None:
                continue
            rows.append((symbol, pnl))

    nonzero = [(s, p) for s, p in rows if abs(p) > 1e-12]
    if not nonzero:
        return report_text + "\n\nPnL bars: всі значення 0.00"

    max_abs = max(abs(p) for _, p in nonzero) or 1.0

    def mk_bar(v: float) -> str:
        width = max(1, int(round(10 * abs(v) / max_abs)))
        bar = "#" * width
        return f"+{bar}" if v > 0 else f"-{bar}"

    nonzero.sort(key=lambda x: abs(x[1]), reverse=True)
    lines_bars = []
    for s, p in nonzero[:8]:
        sign = "+" if p >= 0 else "-"
        lines_bars.append(f"{s:<8} | {mk_bar(p):<12} | {sign}{abs(p):.2f}")

    return report_text + "\n\nPnL bars:\n" + "\n".join(lines_bars)


def _same_markup(a, b) -> bool:
    """Безпечно порівнює InlineKeyboardMarkup (або None) через dict-подання."""
    try:
        if a is None and b is None:
            return True
        if (a is None) != (b is None):
            return False
        return a.to_dict() == b.to_dict()
    except Exception:
        return False


# ───────────────────────────────────────────────
# /kpi command & callback ✨
# ───────────────────────────────────────────────
async def kpi_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /kpi [table] [days] — показує KPI та додає ASCII-bars по PnL."""
    table, days = _parse_kpi_args(context.args or [])
    try:
        text = kpi_summary(days=days, table=table)
    except Exception as e:
        text = f"❌ KPI error: {e}"
    text = _append_pnl_bars(text)
    await update.effective_chat.send_message(text, reply_markup=_kpi_keyboard(table, days))


async def kpi_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Інлайн-кнопки KPI: kpi:<table>:<days>."""
    q = update.callback_query
    await q.answer()

    try:
        _, table, days_str = (q.data or "").split(":")
        days = int(days_str)
    except Exception:
        table, days = "trades", 7

    try:
        text = kpi_summary(days=days, table=table)
    except Exception as e:
        text = f"❌ KPI error: {e}"

    text = _append_pnl_bars(text)
    new_markup = _kpi_keyboard(table, days)

    old_text = q.message.text if q.message else None
    old_markup = q.message.reply_markup if q.message else None
    if old_text == text and _same_markup(old_markup, new_markup):
        await q.answer("Вже оновлено ✅", show_alert=False)
        return

    await q.edit_message_text(text=text, reply_markup=new_markup)


# ───────────────────────────────────────────────
# Error handler
# ───────────────────────────────────────────────
async def on_error(update: object, context) -> None:
    if isinstance(context.error, asyncio.CancelledError):
        log.info("Task was cancelled (graceful): %s", context.error)
        return
    try:
        uid = getattr(getattr(update, "effective_user", None), "id", None)
        chat = getattr(getattr(update, "effective_chat", None), "id", None)
        log.exception(
            "Unhandled error (user=%s chat=%s): %s", uid, chat, context.error
        )
    except Exception:
        log.exception("Unhandled error while processing update", exc_info=context.error)


# ───────────────────────────────────────────────
# Jobs
# ───────────────────────────────────────────────
async def autopost_scan(context) -> None:
    """Автопост: збирає сигнали, шле у TG, маркує sent та мостить у trades."""
    try:
        # універсально виконуємо run_autopост_once (async або sync)
        msgs = await _run_maybe_async(run_autopost_once, context.application)
        if not msgs:
            return

        default_chat = CFG.get("CHAT_ID") or CFG.get("TELEGRAM_CHAT_ID")
        sent = 0
        seen: set[tuple[int | None, str]] = set()

        for m in msgs:
            if isinstance(m, str):
                text = m
                chat_id = default_chat
                parse_mode = constants.ParseMode.HTML
                btns = None
            else:
                text = (m.get("text", "") or "") if isinstance(m, dict) else ""
                chat_id = (m.get("chat_id") if isinstance(m, dict) else None) or default_chat
                parse_mode = (m.get("parse_mode") if isinstance(m, dict) else None) or constants.ParseMode.HTML
                btns = m.get("buttons") if isinstance(m, dict) else None

            if not text or not chat_id:
                continue

            sig = (int(chat_id) if chat_id is not None else None, text)
            if sig in seen:
                continue
            seen.add(sig)

            reply_markup = None
            if btns:
                rows = []
                for row in btns:
                    r = []
                    for b in row:
                        if b.get("type") == "url":
                            r.append(
                                InlineKeyboardButton(
                                    b.get("text", "Link"), url=b.get("url", "")
                                )
                            )
                        else:
                            data = (b.get("data") or "")[:64]
                            r.append(
                                InlineKeyboardButton(
                                    b.get("text", "…"), callback_data=data
                                )
                            )
                    if r:
                        rows.append(r)
                if rows:
                    reply_markup = InlineKeyboardMarkup(rows)

            # 1) Надіслати в TG
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    disable_web_page_preview=True,
                    reply_markup=reply_markup,
                )
                sent += 1
            except Exception as e:
                log.warning("autopost send fail: %s", e)

            # 2) Позначити «надіслано»
            try:
                if isinstance(m, dict):
                    mark_autopost_sent(
                        symbol=m.get("symbol"),
                        timeframe=m.get("timeframe"),
                        rr=m.get("rr"),
                    )
            except Exception as e:
                log.warning("autopost_log mark_sent fail: %s", e)

            # 3) Міст у trades
            try:
                if isinstance(m, dict):
                    tid = handle_autopost_message(m)
                    if tid:
                        log.info("[autopост_scan] opened trade id=%s from message", tid)
            except Exception as e:
                log.warning("autopost_bridge failed: %s", e)

        log.info("autopost scan done (sent=%d)", sent)

    except Exception:
        log.warning("autopost_scan failed", exc_info=True)


async def signal_closer_job(context) -> None:
    """Періодичне закриття/NEUTRAL-обробка."""
    try:
        await _run_maybe_async(_close_fn)
    except Exception as e:
        log.warning("signal_closer failed: %s", e)


async def position_manager_job(context) -> None:
    """Partial TP / move SL to BE / легкий трейл."""
    try:
        updated = await _run_maybe_async(_pm_fn)
        if updated:
            log.info("position_manager: updated %d positions", updated)
    except Exception as e:
        log.warning("position_manager failed: %s", e)


async def daily_pnl_job(context) -> None:
    """Щоденний P&L о 23:59."""
    try:
        await _run_maybe_async(daily_tracker_job, context.bot)
    except Exception as e:
        log.warning("daily_pnl_job failed: %s", e)


async def winrate_daily_job(context) -> None:
    """Winrate за 7 днів о 00:05."""
    try:
        await _run_maybe_async(winrate_job, context.bot, 7)
    except Exception as e:
        log.warning("winrate_daily_job failed: %s", e)


async def signal_sync_job(context) -> None:
    """Синхронізація сигналів із джерел (якщо доступна)."""
    if sync_signals_once is None or str(os.getenv("SIGNAL_SYNC_ENABLED", "true")).lower() != "true":
        return
    try:
        await _run_maybe_async(sync_signals_once)
    except Exception as e:
        log.warning("signal_sync: %s", e)


async def alerts_job(context) -> None:
    """Risk alerts job."""
    try:
        await _run_maybe_async(_alerts_fn, context.bot)
    except Exception as e:
        log.warning("risk_alerts failed: %s", e)


# ───────────────────────────────────────────────
# App bootstrap
# ───────────────────────────────────────────────
def build_app():
    if not CFG.get("tg_token"):
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing in .env")

    app = (
        Application.builder().token(CFG["tg_token"]).rate_limiter(AIORateLimiter()).build()
    )

    # ✨ /kpi + callback
    app.add_handler(CommandHandler("kpi", kpi_cmd))
    app.add_handler(CallbackQueryHandler(kpi_cb, pattern=r"^kpi:(trades|signals):\d+$"))

    # ✨ /help, /guide і callback для гайду
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("guide", cmd_guide))
    app.add_handler(CallbackQueryHandler(show_signal_guide, pattern=r"^guide:signal$"))

    # 1) Спочатку — специфічні хендлери
    panel_neutral.register(app)
    register_extra(app)

    # 2) Потім — універсальні/інші
    register_handlers(app)

    # ───────────────────────────────────────────────
    # ОЧИСНИК дублікатів /ai і MessageHandler з командними фільтрами
    # Залишається тільки наш cmd_ai; інші /ai — видаляються.
    # Також прибираємо generic MessageHandler-и, що ловлять командні апдейти.
    # ───────────────────────────────────────────────
    try:
        # 1) Прибрати всі інші CommandHandler('/ai'), окрім нашого cmd_ai
        for grp, handlers in list((app.handlers or {}).items()):
            keep: list = []
            for h in handlers:
                if isinstance(h, CommandHandler):
                    cmds = set(getattr(h, "commands", set()))
                    if "ai" in cmds and getattr(h.callback, "__name__", "") != "cmd_ai":
                        log.info(
                            "[handlers] removing duplicate CommandHandler /ai from %s",
                            getattr(h.callback, "__qualname__", h.callback),
                        )
                        continue
                keep.append(h)
            app.handlers[grp] = keep

        # 2) Прибрати MessageHandler-и, що ловлять будь-які команди (щоб не підхоплювали /ai)
        for grp, handlers in list((app.handlers or {}).items()):
            keep2: list = []
            for h in handlers:
                if isinstance(h, MessageHandler):
                    f = getattr(h, "filters", None)
                    try:
                        if f is not None and (
                            f == tg_filters.COMMAND or (hasattr(f, "__str__") and "COMMAND" in str(f))
                        ):
                            log.info(
                                "[handlers] removing generic MessageHandler COMMAND from %s",
                                getattr(h.callback, "__qualname__", h.callback),
                            )
                            continue
                    except Exception:
                        # Безпечний пропуск на випадок нестандартних фільтрів
                        pass
                keep2.append(h)
            app.handlers[grp] = keep2
    except Exception:
        log.warning("handlers cleanup failed", exc_info=True)

    # error handler
    app.add_error_handler(on_error)

    # ── Планування робіт
    app.job_queue.run_repeating(
        autopost_scan, interval=300, first=10, name="autopost_scan"
    )

    interval_closer = int(CFG.get("signal_closer_interval_sec", 120))
    interval_pm = int(CFG.get("position_manager_interval_sec", 60))
    interval_sync = int(CFG.get("signal_sync_interval_sec", 60))
    alerts_interval = int(CFG.get("alerts_interval_sec", 300))

    if _close_fn:
        app.job_queue.run_repeating(
            signal_closer_job, interval=interval_closer, first=15, name="signal_closer"
        )
    if _pm_fn:
        app.job_queue.run_repeating(
            position_manager_job, interval=interval_pm, first=20, name="position_manager"
        )

    app.job_queue.run_daily(
        daily_pnl_job, time=dtime(hour=23, minute=59, tzinfo=TZ), name="daily_pnl_job"
    )
    app.job_queue.run_daily(
        winrate_daily_job, time=dtime(hour=0, minute=5, tzinfo=TZ), name="winrate_job"
    )

    signal_sync_enabled = str(os.getenv("SIGNAL_SYNC_ENABLED", "true")).lower() == "true"
    if sync_signals_once and signal_sync_enabled:
        app.job_queue.run_repeating(
            signal_sync_job, interval=interval_sync, first=30, name="signal_sync"
        )

    if _alerts_fn:
        app.job_queue.run_repeating(
            alerts_job, interval=alerts_interval, first=45, name="risk_alerts"
        )

    tz_key = getattr(TZ, "key", "Europe/Kyiv")
    log.info(
        (
            "[jobqueue] ✅ scheduled: autopost 300s, signal_closer %ss%s; "
            "position_manager %ss%s; daily_pnl 23:59; winrate 00:05; "
            "signal_sync %ss%s; risk_alerts %ss%s (TZ=%s)"
        ),
        interval_closer,
        "" if _close_fn else " (off)",
        interval_pm,
        "" if _pm_fn else " (off)",
        interval_sync,
        "" if (sync_signals_once and signal_sync_enabled) else " (off)",
        alerts_interval,
        "" if _alerts_fn else " (off)",
        tz_key,
    )
    return app


def main() -> None:
    # авто-міграції (один раз на старт)
    try:
        from utils.db_migrate import migrate_if_needed
        migrate_if_needed()
    except Exception as e:
        log.warning("migrate_if_needed skipped: %s", e)

    app = build_app()
    mode = str(CFG.get("bot_mode", "polling")).lower()

    if mode == "webhook" and CFG.get("webhook_url"):
        url = CFG["webhook_url"].rstrip("/") + "/" + CFG["tg_token"]
        port = int(CFG.get("port", 8080))
        log.info("Starting bot (webhook) on port %s …", port)
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=CFG["tg_token"],
            webhook_url=url,
            drop_pending_updates=True,
        )
    else:
        log.info("Starting bot (polling)…")
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )

        # після graceful shutdown/рестарту — гарантуємо індекси
        from utils.db import get_conn
        try:
            from utils.db_migrate import ensure_indexes_and_triggers
            with get_conn() as conn:
                ensure_indexes_and_triggers(conn)
        except Exception as e:
            log.warning("ensure_indexes_and_triggers skipped: %s", e)


if __name__ == "__main__":
    main()
