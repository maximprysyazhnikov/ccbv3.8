from __future__ import annotations
import time
from core_config import CFG
from gpt_analyst.full_analyzer import run_full_analysis
from gpt_decider.decider import decide_from_markdown
from telegram import Bot

def run_auto_top():
    bot = Bot(CFG.tg_token)
    tf, bars = CFG.default_tf, CFG.default_bars
    while True:
        if CFG.auto_top_enabled:
            results = []
            for s in CFG.monitored_symbols:
                lines = run_full_analysis(s, tf, bars)
                d = decide_from_markdown(lines)
                if d["push"]:
                    results.append((s, d["direction"], d["confidence"]))
            if results:
                results.sort(key=lambda x: x[2], reverse=True)
                top_txt = "\n".join([f"{i+1}. {s} — {dir_} ({conf}%)" for i, (s, dir_, conf) in enumerate(results)])
                bot.send_message(chat_id=CFG.tg_chat_id, text="🏆 АвтоТОП:\n" + top_txt)
        time.sleep(CFG.auto_top_interval * 60)

if __name__ == "__main__":
    run_auto_top()
