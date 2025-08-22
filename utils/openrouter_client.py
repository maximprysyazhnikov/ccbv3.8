# utils/openrouter_client.py
from __future__ import annotations
import os
import asyncio
import aiohttp
from typing import Dict, Any, Tuple, List

from core_config import CFG

BASE = (CFG.get("or_base") or os.getenv("OPENROUTER_BASE") or "https://openrouter.ai/api/v1").rstrip("/")
TIMEOUT = float(CFG.get("or_timeout") or os.getenv("OPENROUTER_TIMEOUT") or 30)
# Підтримка словникового формату слотів з CFG["or_slots"]
def _normalize_slots(slots_cfg) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for s in (slots_cfg or []):
        if isinstance(s, dict):
            key = s.get("key") or s.get("api_key")
            model = s.get("model") or CFG.get("or_model") or "deepseek/deepseek-chat"
            if key:
                out.append((str(key).strip(), str(model).strip()))
        elif isinstance(s, (list, tuple)) and s:
            key = s[0]
            model = s[1] if len(s) > 1 and s[1] else (CFG.get("or_model") or "deepseek/deepseek-chat")
            if key:
                out.append((str(key).strip(), str(model).strip()))
        elif isinstance(s, str) and s.strip():
            out.append((s.strip(), CFG.get("or_model") or "deepseek/deepseek-chat"))
    return out

SLOTS: List[Tuple[str, str]] = _normalize_slots(CFG.get("or_slots"))

class OpenRouterClient:
    def __init__(self) -> None:
        if not SLOTS:
            raise RuntimeError("OpenRouter slots are empty")
        self._i = 0  # round-robin

        # бекоф
        self._backoff_start = float(os.getenv("OR_BACKOFF_START", "0.5"))
        self._backoff_cap = float(os.getenv("OR_BACKOFF_CAP", "8.0"))

        # керування вартістю
        try:
            self._max_tokens = int(os.getenv("OR_MAX_TOKENS", "1024"))
        except Exception:
            self._max_tokens = 1024
        if self._max_tokens < 128:
            self._max_tokens = 128

        try:
            self._temperature = float(os.getenv("OPENROUTER_TEMPERATURE", "0.2"))
        except Exception:
            self._temperature = 0.2

    def _pick_slot(self) -> Tuple[str, str]:
        slot = SLOTS[self._i % len(SLOTS)]
        self._i += 1
        return slot

    async def chat(self, messages: list[dict], model: str | None = None) -> Dict[str, Any]:
        """
        Async клієнт з ретраями/бекофом/зменшенням max_tokens аналогічно sync-версії.
        Повертає сирий JSON (щоб за потреби дістати usage, choices тощо).
        """
        last_err = None

        # два проходи: 2-й — із зменшеними max_tokens, якщо був 402 із натяком
        reduce_tokens_next_pass = False

        for pass_no in (1, 2):
            if pass_no == 2 and reduce_tokens_next_pass:
                self._max_tokens = max(128, int(self._max_tokens * 0.6))

            # одне коло по слотах у round‑robin
            for _ in range(len(SLOTS)):
                key, default_model = self._pick_slot()
                mdl = model or default_model

                headers = {
                    "Authorization": f"Bearer {key}",
                    "HTTP-Referer": "https://github.com/maximprysyazhnikov/ccbv2",
                    "X-Title": "Crypto CAT Bot v3",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
                payload = {"model": mdl, "messages": messages, "max_tokens": self._max_tokens, "temperature": self._temperature}

                delay = self._backoff_start
                # до 3 спроб на слот
                for attempt in range(1, 4):
                    try:
                        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
                        async with aiohttp.ClientSession(timeout=timeout) as s:
                            async with s.post(f"{BASE}/chat/completions", json=payload, headers=headers) as r:
                                if r.status in (402, 429):
                                    txt = await r.text()
                                    last_err = f"{r.status} {txt[:500]}"

                                    if r.status == 402 and ("fewer max_tokens" in txt.lower() or "max_tokens" in txt.lower()):
                                        # на наступному проході зменшимо
                                        if pass_no == 1:
                                            reduce_tokens_next_pass = True
                                        await asyncio.sleep(min(delay, self._backoff_cap))
                                        break  # до наступного слоту

                                    if r.status == 429:
                                        await asyncio.sleep(min(delay, self._backoff_cap))
                                        delay = min(self._backoff_cap, delay * 2)
                                        continue  # ще раз цей же слот

                                    # інші 402 → наступний слот
                                    await asyncio.sleep(min(delay, self._backoff_cap))
                                    break

                                if 500 <= r.status < 600:
                                    last_err = f"{r.status} server error"
                                    await asyncio.sleep(min(delay, self._backoff_cap))
                                    delay = min(self._backoff_cap, delay * 2)
                                    continue  # ще раз цей же слот

                                if 400 <= r.status < 500:
                                    # інші 4xx — не ретраїмо на цьому ж слоті
                                    txt = await r.text()
                                    last_err = f"{r.status} {txt[:200]}"
                                    break

                                # 2xx
                                r.raise_for_status()
                                return await r.json()

                    except asyncio.TimeoutError:
                        last_err = "timeout"
                        await asyncio.sleep(min(delay, self._backoff_cap))
                        delay = min(self._backoff_cap, delay * 2)
                        continue
                    except Exception as e:
                        last_err = str(e)
                        break  # інший слот

        raise RuntimeError(f"OpenRouter async request failed with all keys. Last error: {last_err}")
