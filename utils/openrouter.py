from __future__ import annotations
import time
import requests

def chat_completion(endpoint: str, api_key: str, model: str, messages: list[dict], timeout: int = 30, max_retries: int = 2):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/maximprysyazhnikov/crypto_cat_bot",
        "X-Title": "Crypto CAT Bot",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 900
    }
    for attempt in range(max_retries + 1):
        try:
            r = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
            r.raise_for_status()
            j = r.json()
            return j["choices"][0]["message"]["content"]
        except Exception:
            if attempt >= max_retries:
                raise
            time.sleep(1 + attempt * 0.5)
