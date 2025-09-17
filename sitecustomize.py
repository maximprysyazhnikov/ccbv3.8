# sitecustomize.py
# ─────────────────────────────────────────────────────────────────────────────
# Ранній контроль LLM через .env:
#   Пріоритети:
#     1) LLM_FORCE=1            → примусово УВІМКНЕНО (ігнорує все інше)
#     2) LLM_DISABLED=1         → примусово ВИМКНЕНО
#     3) AUTOPOST_LLM_ENABLED   → треба "true/1/on"
#        і одночасно OPENROUTER_DISABLE → має бути "false/0/off"
#
# Якщо DISABLED=True — блокуємо будь-які httpx-запити до openrouter.ai,
# повертаючи порожню "безпечну" відповідь (204 + choices[0].message.content="").
# ─────────────────────────────────────────────────────────────────────────────
import os, sys, logging
from functools import wraps
from importlib.abc import MetaPathFinder, Loader
from importlib.machinery import PathFinder

# Підтягнемо .env РАНО (до імпорту основного коду), якщо доступний python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except Exception:
    pass

log = logging.getLogger("llm_guard")

def _env_true(v):  return str(v).lower() in ("1","true","yes","on")
def _env_false(v): return str(v).lower() in ("0","false","no","off")
def _get(name, default=None): return os.getenv(name, default)

# ── Базові прапорці з .env/ОС
AUTOPOST_LLM_ENABLED = _get("AUTOPOST_LLM_ENABLED", "false")   # має бути true, щоб дозволити
OPENROUTER_DISABLE   = _get("OPENROUTER_DISABLE",   "1")       # має бути 0/false, щоб дозволити
LLM_DISABLED_ENV     = _get("LLM_DISABLED",         "0")       # явне вимкнення
LLM_FORCE_ENV        = _get("LLM_FORCE",            "0")       # явне увімкнення

# ── Базове рішення (за бізнес-правилом: потрібно ДВІ умови для дозволу)
# дозволено ТІЛЬКИ якщо: AUTOPOST_LLM_ENABLED==true  І  OPENROUTER_DISABLE==false
_enabled_by_policy = _env_true(AUTOPOST_LLM_ENABLED) and _env_false(OPENROUTER_DISABLE)
DISABLED = not _enabled_by_policy

# ── Пріоритети перекриття
if _env_true(LLM_DISABLED_ENV):
    DISABLED = True
if _env_true(LLM_FORCE_ENV):
    DISABLED = False

def _as_str(url) -> str:
    try:
        return str(url)
    except Exception:
        return ""

def _is_openrouter(url) -> bool:
    return "openrouter.ai" in _as_str(url)

def _fake_response(httpx, url, method="POST"):
    # Повертаємо коректний httpx.Response із JSON-тілом, щоб .json()/raise_for_status() працювали
    req = httpx.Request(method, _as_str(url))
    return httpx.Response(
        204,  # No Content
        request=req,
        headers={"Content-Type": "application/json"},
        content=b'{"choices":[{"message":{"content":""}}]}'
    )

def _patch_httpx(httpx):
    # module-level: post / request
    if hasattr(httpx, "post"):
        _orig = httpx.post
        @wraps(_orig)
        def _guard(url, *a, **kw):
            if _is_openrouter(url):
                log.warning("LLM blocked: %s", _as_str(url))
                return _fake_response(httpx, url, "POST")
            return _orig(url, *a, **kw)
        httpx.post = _guard

    if hasattr(httpx, "request"):
        _orig = httpx.request
        @wraps(_orig)
        def _guard(method, url, *a, **kw):
            if _is_openrouter(url):
                log.warning("LLM blocked: %s %s", method, _as_str(url))
                return _fake_response(httpx, url, method)
            return _orig(method, url, *a, **kw)
        httpx.request = _guard

    # Client
    if hasattr(httpx, "Client"):
        _Cpost, _Creq = httpx.Client.post, httpx.Client.request
        @wraps(_Cpost)
        def _guard_cpost(self, url, *a, **kw):
            if _is_openrouter(url):
                log.warning("LLM blocked (client): %s", _as_str(url))
                return _fake_response(httpx, url, "POST")
            return _Cpost(self, url, *a, **kw)
        @wraps(_Creq)
        def _guard_creq(self, method, url, *a, **kw):
            if _is_openrouter(url):
                log.warning("LLM blocked (client): %s %s", method, _as_str(url))
                return _fake_response(httpx, url, method)
            return _Creq(self, method, url, *a, **kw)
        httpx.Client.post, httpx.Client.request = _guard_cpost, _guard_creq

    # AsyncClient
    if hasattr(httpx, "AsyncClient"):
        _Apost, _Areq = httpx.AsyncClient.post, httpx.AsyncClient.request
        @wraps(_Apost)
        async def _guard_apost(self, url, *a, **kw):
            if _is_openrouter(url):
                log.warning("LLM blocked (async): %s", _as_str(url))
                return _fake_response(httpx, url, "POST")
            return await _Apost(self, url, *a, **kw)
        @wraps(_Areq)
        async def _guard_areq(self, method, url, *a, **kw):
            if _is_openrouter(url):
                log.warning("LLM blocked (async): %s %s", method, _as_str(url))
                return _fake_response(httpx, url, method)
            return await _Areq(self, method, url, *a, **kw)
        httpx.AsyncClient.post, httpx.AsyncClient.request = _guard_apost, _guard_areq

# ── Активуємо патч тільки коли DISABLED=True
if DISABLED and "httpx" in sys.modules:
    try:
        _patch_httpx(sys.modules["httpx"])
        log.warning("sitecustomize: LLM DISABLED (httpx patched: pre-import)")
    except Exception as e:
        log.warning("sitecustomize: pre-import patch failed: %s", e)

if DISABLED:
    class _HttpxFinder(MetaPathFinder):
        _reentry = False
        def find_spec(self, fullname, path, target=None):
            if fullname != "httpx" or self._reentry:
                return None
            self._reentry = True
            try:
                spec = PathFinder.find_spec(fullname, path)
            finally:
                self._reentry = False
            if not spec or not spec.loader:
                return None
            orig_loader = spec.loader
            class _Loader(Loader):
                def create_module(self, spec_):
                    if hasattr(orig_loader, "create_module"):
                        return orig_loader.create_module(spec_)
                    return None
                def exec_module(self, module):
                    orig_loader.exec_module(module)
                    try:
                        _patch_httpx(module)
                        log.warning("sitecustomize: LLM DISABLED (httpx patched on import)")
                    except Exception as e:
                        log.warning("sitecustomize: import patch failed: %s", e)
            spec.loader = _Loader()
            return spec
    sys.meta_path.insert(0, _HttpxFinder())
else:
    # Для наочності у консолі
    try:
        print("sitecustomize: LLM ENABLED (policy/env allows outbound OpenRouter)")
    except Exception:
        pass
