import requests, json
from typing import List, Dict
from core_config import (OPENROUTER_API_KEY, OPENROUTER_BASE, OPENROUTER_MODEL,
                         LOCAL_LLM_BASE, LOCAL_LLM_MODEL, LOCAL_LLM_TIMEOUT, OPENROUTER_TIMEOUT)

def _chat_http(base: str, model: str, messages, timeout: int, headers=None):
    url = f"{base}/chat/completions"
    payload = {"model": model, "messages": messages, "max_tokens": 256, "temperature": 0.6, "top_p": 0.9}
    r = requests.post(url, json=payload, headers=headers or {}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]

def chat(messages: List[Dict[str,str]]) -> str:
    if OPENROUTER_API_KEY:
        try:
            return _chat_http(OPENROUTER_BASE, OPENROUTER_MODEL, messages, OPENROUTER_TIMEOUT,
                              headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                                       "HTTP-Referer": "https://local", "X-Title": "trader-bot"})
        except Exception:
            pass
    # fallback to local
    return _chat_http(LOCAL_LLM_BASE, LOCAL_LLM_MODEL, messages, LOCAL_LLM_TIMEOUT)
