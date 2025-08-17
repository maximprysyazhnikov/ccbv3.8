import requests
from core_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

def send_alert(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[sender] Missing TELEGRAM_* env; skip send")
        return
    requests.post(f"{API}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": text})
