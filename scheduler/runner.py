# scheduler/runner.py
from __future__ import annotations
import os
from datetime import timedelta
from telegram.ext import Application

from core_config import CFG
from services.autopost import run_autopost_once
from services.signal_closer import check_and_close_signals

def _parse_interval_seconds() -> int:
    # Якщо лишили cron — зараз ігноруємо (JobQueue не підтримує crontab напряму)
    # Тому беремо інтервал AUTOPOST_INTERVAL_SEC (дефолт 300с)
    try:
        return int(CFG.get("autopost_interval_sec", int(os.getenv("AUTOPOST_INTERVAL_SEC", "300"))))
    except Exception:
        return 300

def start_autopost(application: Application) -> None:
    """
    Реєструє періодичні задачі у PTB JobQueue (всередині існуючого event loop):
      - autopost_scan: автопост сигналів (кожні N секунд)
      - signal_closer: перевірка TP/SL (кожні 120 секунд)
    """
    jq = application.job_queue

    # Автопост
    interval_s = _parse_interval_seconds()
    jq.run_repeating(
        lambda ctx: run_autopost_once(application.bot),
        interval=interval_s,
        first=5,            # старт через 5 сек після запуску бота
        name="autopost_scan",
    )

    # Закриття сигналів
    jq.run_repeating(
        lambda ctx: check_and_close_signals(),
        interval=120,
        first=15,
        name="signal_closer",
    )

    print(f"[jobqueue] ✅ scheduled: autopost_scan every {interval_s}s, signal_closer every 120s")
