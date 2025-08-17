import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core_config import TELEGRAM_CHAT_ID, SCREENER_EVERY_MIN, LOCAL_SCANNER_MIN
from scheduler.screener_job import run_once as global_top20_run_once
from scheduler.local_top5_job import run_local_top5  # async

def start_autopost(application):
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(global_top20_run_once, "interval", minutes=int(SCREENER_EVERY_MIN), id="global_top20",
                      coalesce=True, max_instances=1, misfire_grace_time=60)
    scheduler.add_job(run_local_top5, "interval", minutes=int(LOCAL_SCANNER_MIN), id="local_top5",
                      args=[application.bot, TELEGRAM_CHAT_ID], coalesce=True, max_instances=1, misfire_grace_time=60)
    scheduler.start()
    print(f"[scheduler] ✅ APScheduler: глобальний={SCREENER_EVERY_MIN} хв, локальний={LOCAL_SCANNER_MIN} хв")
