# utils/openrouter.py
from __future__ import annotations
import os, json, time, random, itertools
from typing import Any, Dict, Iterable, List, Optional, Tuple
import httpx
from core_config import CFG

# ──────────────────────────────────────────────────────────────────────────────
# Defaults
# ──────────────────────────────────────────────────────────────────────────────

def _default_model() -> str:
    return (
        CFG.get("or_model")
        or os.getenv("OPENROUTER_MODEL")
        or "deepseek/deepseek-chat"
    )

def _default_base() -> str:
    return (
        CFG.get("or_base")
        or os.getenv("OPENROUTER_BASE")
        or os.getenv("OR_BASE")
        or "https://openrouter.ai/api/v1"
    )

def _default_timeout() -> float:
    try:
        return float(CFG.get("or_timeout") or os.getenv("OPENROUTER_TIMEOUT") or 30)
    except Exception:
        return 30.0

def _split_multi(s: Optional[str]) -> List[str]:
    if not s:
        return []
    return [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]

# slot tuple: (key, model, base, timeout)
def _normalize_slot(x: Any) -> Optional[Tuple[str, str, str, float]]:
    d_model = _default_model()
    d_base = _default_base()
    d_timeout = _default_timeout()

    if isinstance(x, dict):
        key = x.get("key") or x.get("api_key") or x.get("OPENROUTER_KEY")
        model = x.get("model") or d_model
        base = x.get("base") or d_base
        tout = float(x.get("timeout") or d_timeout)
        if key:
            return (str(key).strip(), str(model).strip(), str(base).strip(), float(tout))
        return None

    if isinstance(x, (list, tuple)) and x:
        key = x[0]
        model = x[1] if len(x) > 1 and x[1] else d_model
        base = x[2] if len(x) > 2 and x[2] else d_base
        tout = x[3] if len(x) > 3 and x[3] else d_timeout
        if key:
            return (str(key).strip(), str(model).strip(), str(base).strip(), float(tout))
        return None

    if isinstance(x, str):
        key = x.strip()
        if key:
            return (key, d_model, d_base, d_timeout)

    return None

def _dedup(slots: Iterable[Any]) -> List[Tuple[str, str, str, float]]:
    out: List[Tuple[str, str, str, float]] = []
    seen = set()
    for raw in slots or []:
        nm = _normalize_slot(raw)
        if not nm:
            continue
        sig = (nm[0], nm[1], nm[2], float(nm[3]))
        if sig not in seen:
            seen.add(sig)
            out.append(nm)
    return out

def _build_slots_from_env_and_cfg() -> List[Tuple[str, str, str, float]]:
    """
    Priority:
    1) CFG['or_slots'] = [{"key":..,"model":..,"base"?, "timeout"?}, ...]
    2) ENV: OR_SLOTS='[{"key":...,"model":...,"base":...,"timeout":...}, ...]'
    3) ENV: OPENROUTER_KEYS=key1,key2 ; OPENROUTER_MODEL=mdl1[,mdl2,...]
    """
    slots: List[Any] = []

    # 1) CFG.or_slots
    for s in (CFG.get("or_slots") or []):
        slots.append(s)

    # 2) OR_SLOTS JSON
    or_slots_env = os.getenv("OR_SLOTS")
    if or_slots_env:
        try:
            arr = json.loads(or_slots_env)
            if isinstance(arr, list):
                slots.extend(arr)
        except Exception:
            pass

    # 3) ENV fan-in KEYS/MODEL
    env_keys = _split_multi(os.getenv("OPENROUTER_KEYS") or os.getenv("OPENROUTER_KEY"))
    env_models = _split_multi(os.getenv("OPENROUTER_MODEL"))
    env_base = _default_base()
    env_timeout = _default_timeout()
    fallback_model = env_models[0] if env_models else _default_model()

    if env_keys:
        if env_models and len(env_models) >= len(env_keys):
            for k, m in zip(env_keys, env_models):
                slots.append({"key": k, "model": m, "base": env_base, "timeout": env_timeout})
        else:
            for k in env_keys:
                slots.append({"key": k, "model": fallback_model, "base": env_base, "timeout": env_timeout})

    return _dedup(slots)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _first_nonempty(*vals: Optional[str]) -> str:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def _extract_content(data: Any) -> str:
    """
    Універсальний екстрактор тексту з відповіді LLM/OpenRouter.
    Підтримувані варіанти:
      1) {"choices":[{"message":{"content":"..."}}, ...]}
      2) {"choices":{"message":{"content":"..."}}}
      3) {"message":{"content":"..."}}
      4) {"content":"..."}
      5) просто рядок
    Якщо нічого не знайшли — повертає "".
    """
    try:
        if isinstance(data, str):
            # це може бути готовий текст або JSON-рядок
            try:
                parsed = json.loads(data)
                data = parsed
            except Exception:
                return data.strip()

        if not isinstance(data, dict):
            return ""

        # 1) choices як масив
        ch = data.get("choices")
        if isinstance(ch, list) and ch:
            first = ch[0] or {}
            msg = first.get("message", first)
            if isinstance(msg, dict):
                txt = _first_nonempty(msg.get("content"))
                if txt:
                    return txt
            if isinstance(first, dict):
                txt = _first_nonempty(first.get("text"))
                if txt:
                    return txt
            if isinstance(first, str):
                return first.strip()

        # 2) choices як dict
        if isinstance(ch, dict):
            msg = ch.get("message", ch)
            if isinstance(msg, dict):
                txt = _first_nonempty(msg.get("content"))
                if txt:
                    return txt

        # 3) message на верхньому рівні
        msg = data.get("message")
        if isinstance(msg, dict):
            txt = _first_nonempty(msg.get("content"))
            if txt:
                return txt

        # 4) content на верхньому рівні
        txt = _first_nonempty(data.get("content"))
        if txt:
            return txt

        return ""
    except Exception:
        return ""

# ──────────────────────────────────────────────────────────────────────────────
# Public API (sync)
# ──────────────────────────────────────────────────────────────────────────────

def chat_completion(
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    messages: Optional[List[Dict[str, str]]] = None,
    timeout: Optional[float] = None,
    trial_slots: Optional[Iterable[Any]] = None,
    headers_extra: Optional[Dict[str, str]] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> str:
    """
    Синхронний клієнт OpenRouter з:
      • ротацією ключів/моделей (explicit → trial_slots → CFG/ENV);
      • ретраями на 402/429/5xx/timeout;
      • експоненціальним бекофом (0.5s → ×2 → ≤ 8s);
      • адаптивним зниженням max_tokens на 402.
    Повертає чистий текст відповіді (str). Якщо всі спроби вичерпані — RuntimeError.
    """
    base_default = _default_base()
    endpoint = (endpoint or base_default).rstrip("/")
    timeout_global = float(timeout or _default_timeout())

    # Керування вартістю
    dynamic_max = int(max_tokens or int(os.getenv("OR_MAX_TOKENS", "1024") or 1024))
    if dynamic_max < 128:
        dynamic_max = 128
    temp = float(temperature or float(os.getenv("OPENROUTER_TEMPERATURE", "0.2") or 0.2))

    # Кандидати слотів
    candidates: List[Tuple[str, str, str, float]] = []

    # (1) явний ключ/модель
    if api_key:
        candidates.append((
            api_key,
            (model or _default_model()),
            endpoint,
            timeout_global
        ))

    # (2) trial_slots
    for s in _dedup(trial_slots or []):
        key, mdl, base, tout = s
        candidates.append((key, (mdl or _default_model()), (base or endpoint), float(tout or timeout_global)))

    # (3) CFG/ENV
    for s in _build_slots_from_env_and_cfg():
        key, mdl, base, tout = s
        candidates.append((key, (mdl or _default_model()), (base or endpoint), float(tout or timeout_global)))

    # Фінальний список без дублів, збереження порядку
    slots = _dedup(candidates)
    if not slots:
        raise RuntimeError("OpenRouter: no API keys configured (slots empty)")

    # Заголовки
    base_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "HTTP-Referer": os.getenv("OR_REFERER", "https://github.com/maximprysyazhnikov/ccbv2"),
        "X-Title": os.getenv("OR_TITLE", "Crypto CAT Bot"),
    }
    if headers_extra:
        base_headers.update(headers_extra)

    # Заготовка payload
    base_payload = {
        "messages": messages or [],
        "temperature": temp,
        "max_tokens": dynamic_max,
    }

    # Randomized round-robin старт
    start_idx = random.randrange(len(slots)) if len(slots) > 1 else 0
    order = list(itertools.islice(itertools.cycle(range(len(slots))), start_idx, start_idx + len(slots)))

    # Параметри бекофа
    backoff0 = float(os.getenv("OR_BACKOFF_START", "0.5"))
    backoff_cap = float(os.getenv("OR_BACKOFF_CAP", "8.0"))

    last_err: Optional[str] = None

    # Два проходи: 1-й як є; 2-й — після потенційного урізання max_tokens на 402
    for pass_no in (1, 2):
        for idx in order:
            key, mdl, base, tout = slots[idx]
            headers = dict(base_headers)
            headers["Authorization"] = f"Bearer {key}"

            payload = dict(base_payload)
            payload["model"] = mdl
            payload["max_tokens"] = dynamic_max

            url = (base or endpoint).rstrip("/") + "/chat/completions"

            delay = backoff0

            # до 3 спроб на слот
            for attempt in range(1, 4):
                try:
                    with httpx.Client(timeout=float(tout or timeout_global)) as cli:
                        r = cli.post(url, headers=headers, content=json.dumps(payload))

                    # Статус-коди спершу
                    if r.status_code in (402, 429):
                        txt = (r.text or "")[:500]
                        last_err = f"{r.status_code} {txt}"

                        # 402 → часто «fewer max_tokens»/«max_tokens»; спробуємо урізати на 40% і перейти далі
                        if r.status_code == 402 and ("fewer max_tokens" in txt.lower() or "max_tokens" in txt.lower()):
                            if pass_no == 1:
                                dynamic_max = max(128, int(dynamic_max * 0.6))
                            time.sleep(min(delay, backoff_cap))
                            break  # наступний слот (у цьому проході)

                        # 429 → ліміт запитів; ретраїмо цей самий слот
                        if r.status_code == 429:
                            time.sleep(min(delay, backoff_cap))
                            delay = min(backoff_cap, delay * 2)
                            continue

                        # інші 402 → на наступний слот
                        time.sleep(min(delay, backoff_cap))
                        break

                    if 500 <= r.status_code < 600:
                        # тимчасова помилка сервера → ретраї на цьому ж слоті
                        last_err = f"{r.status_code} {r.text[:200]}"
                        time.sleep(min(delay, backoff_cap))
                        delay = min(backoff_cap, delay * 2)
                        continue

                    # інші 4xx → не ретраїмо, йдемо на інший слот
                    if 400 <= r.status_code < 500:
                        last_err = f"{r.status_code} {r.text[:200]}"
                        break

                    # 2xx → парсимо
                    data = r.json()

                    # Надійно витягнути текст
                    text = _extract_content(data)
                    if not text:
                        # спробуємо показати повідомлення про помилку з JSON
                        err = (data.get("error") or {}).get("message") or data.get("detail") or ""
                        if err:
                            last_err = err
                            break
                        last_err = "empty-content"
                        time.sleep(min(delay, backoff_cap))
                        delay = min(backoff_cap, delay * 2)
                        continue

                    return text

                except httpx.TimeoutException:
                    last_err = "timeout"
                    time.sleep(min(delay, backoff_cap))
                    delay = min(backoff_cap, delay * 2)
                    continue
                except Exception as e:
                    last_err = str(e)
                    # несподіване — одразу до наступного слоту
                    break

    raise RuntimeError(f"OpenRouter request failed with all keys. Last error: {last_err}")
