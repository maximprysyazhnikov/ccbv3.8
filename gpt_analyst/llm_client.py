# gpt_analyst/llm_client.py
from __future__ import annotations
import os, time, httpx
from typing import List, Dict, Optional

# локальна LLM (LM Studio / Ollama) — опціонально
LOCAL_BASE  = os.getenv("LOCAL_LLM_BASE", "http://127.0.0.1:1234/v1")
LOCAL_MODEL = os.getenv("LOCAL_LLM_MODEL", "meta-llama-3.1-8b-instruct")

RETRIES = int(os.getenv("LLM_RETRIES", "2"))
BACKOFF = float(os.getenv("LLM_BACKOFF", "1.5"))
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "256"))
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.6"))

def _headers_for_openrouter(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://local",
        "X-Title": "ccbv3-bot"
    }

def _post_chat(base: str, payload: Dict, headers: Dict, timeout: int) -> Dict:
    with httpx.Client(timeout=timeout) as cli:
        r = cli.post(f"{base}/chat/completions", json=payload, headers=headers)
        if r.status_code >= 400:
            raise RuntimeError(f"LLM HTTP {r.status_code}: {r.text[:200]}")
        return r.json()

def chat_with_route(route, messages: List[Dict[str,str]]) -> str:
    """
    route: object with {api_key, model, base, timeout}
    """
    if route:
        payload = {
            "model": route.model,
            "messages": messages,
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
            "top_p": 0.9,
        }
        headers = _headers_for_openrouter(route.api_key) if "openrouter.ai" in route.base else {}
        last_err = None
        for attempt in range(RETRIES + 1):
            try:
                data = _post_chat(route.base, payload, headers, route.timeout)
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                last_err = e
                time.sleep(BACKOFF * (attempt + 1))
        raise RuntimeError(f"LLM failed via route: {last_err}")

    # fallback → локальна LLM (якщо route=None)
    payload = {
        "model": LOCAL_MODEL,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "top_p": 0.9,
    }
    data = _post_chat(LOCAL_BASE, payload, {}, int(os.getenv("LLM_TIMEOUT", "45")))
    return data["choices"][0]["message"]["content"]
