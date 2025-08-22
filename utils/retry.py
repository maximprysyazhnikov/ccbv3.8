# utils/retry.py
from __future__ import annotations
import time, random, logging
import httpx

log = logging.getLogger("openrouter")

RETRIABLE_STATUS = {402, 429, 500, 502, 503, 504}

def _should_retry(resp: httpx.Response | None) -> bool:
    if resp is None:
        return True
    return resp.status_code in RETRIABLE_STATUS

def _sleep_backoff(attempt: int, *, base: float = 1.0, cap: float = 30.0, jitter: float = 0.1) -> None:
    # delay = min(cap, base * 2^(attempt-1)) з «джитером» ±10%
    delay = min(cap, base * (2 ** (attempt - 1)))
    delay += random.uniform(-jitter * delay, jitter * delay)
    time.sleep(max(0.0, delay))

def request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    json: dict | None = None,
    timeout: float = 30.0,
    max_retries: int = 6,
    base_delay: float = 1.0,
    cap_delay: float = 30.0,
) -> httpx.Response:
    """
    Виконує HTTP-запит із ретраями для 402/429/5xx з експоненц. бекофом.
    Повертає останню відповідь (навіть якщо вона не 200), якщо спроби вичерпано.
    Кидає помилку лише при мережевому ексепшені без відповіді.
    """
    resp: httpx.Response | None = None
    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = httpx.request(method, url, headers=headers, json=json, timeout=timeout)
            if not _should_retry(resp):
                return resp

            log.warning("OpenRouter %s -> %s; retry %d/%d",
                        url, resp.status_code, attempt, max_retries)

        except httpx.HTTPError as e:
            last_exc = e
            log.warning("OpenRouter network error: %s; retry %d/%d", e, attempt, max_retries)

        # якщо ще є спроби — спимо
        if attempt < max_retries:
            _sleep_backoff(attempt, base=base_delay, cap=cap_delay)

    # якщо є відповідь — повертаємо, хай обробник кине змістовну помилку з body
    if resp is not None:
        return resp
    # інакше мережевий ексепшн
    raise last_exc if last_exc else RuntimeError("HTTP request failed without response")
