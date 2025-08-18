from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def _get_bool(name: str, default: int = 0) -> bool:
    return str(os.getenv(name, str(default))).strip().lower() in ("1", "true", "yes")

@dataclass(frozen=True)
class ORRoute:
    api_key: str
    model: str

@dataclass(frozen=True)
class CFGType:
    tg_token: str
    tg_chat_id: str
    bot_mode: str
    webhook_url: str
    port: int
    tz_name: str

    analyze_timeframe: str
    analyze_bars: int
    analyze_limit: int
    indicator_preset: str
    auto_push_min: int
    monitored_symbols: list[str]

    hybrid_source: str
    hybrid_catbot_enabled: bool
    hybrid_catbot_mode: str
    catbot_repo_url: str
    catbot_dir: str

    default_tf: str
    default_bars: int

    auto_top_enabled: bool
    auto_top_interval: int

    analyzer_endpoint: str

    per_symbol: dict[str, ORRoute]
    help_pool: list[ORRoute]
    fallback_enabled: bool
    fallback: ORRoute | None

    binance_key: str | None
    binance_secret: str | None

def _collect_per_symbol() -> dict[str, ORRoute]:
    pairs = {
        "BTCUSDT": ("ANALYZER_BTC_API_KEY", "ANALYZER_BTC_MODEL"),
        "ETHUSDT": ("ANALYZER_ETH_API_KEY", "ANALYZER_ETH_MODEL"),
        "BNBUSDT": ("ANALYZER_BNB_API_KEY", "ANALYZER_BNB_MODEL"),
        "SOLUSDT": ("ANALYZER_SOL_API_KEY", "ANALYZER_SOL_MODEL"),
        "XRPUSDT": ("ANALYZER_XRP_API_KEY", "ANALYZER_XRP_MODEL"),
        "RAYUSDT": ("ANALYZER_RAY_API_KEY", "ANALYZER_RAY_MODEL"),
        "SHELLUSDT": ("ANALYZER_SHELL_API_KEY", "ANALYZER_SHELL_MODEL"),
        "WEMIXUSDT": ("ANALYZER_WEMIX_API_KEY", "ANALYZER_WEMIX_MODEL"),
    }
    out = {}
    for sym, (k_key, k_model) in pairs.items():
        api_key = os.getenv(k_key, "").strip()
        model = os.getenv(k_model, "").strip()
        if api_key and model:
            out[sym] = ORRoute(api_key, model)
    return out

def _collect_help_pool(n: int = 8) -> list[ORRoute]:
    pool: list[ORRoute] = []
    for i in range(1, n + 1):
        k = os.getenv(f"HELP_API_KEY{i}", "").strip()
        m = os.getenv(f"HELP_API_KEY{i}_MODEL", "").strip()
        if k and m:
            pool.append(ORRoute(k, m))
    return pool

def _get_fallback() -> tuple[bool, ORRoute | None]:
    enabled = _get_bool("ANALYZER_FALLBACK_ENABLED", 0)
    if not enabled:
        return False, None
    fk = os.getenv("GLOBAL_ANALYZER_API_KEY", "").strip()
    fm = os.getenv("GLOBAL_ANALYZER_MODEL", "").strip()
    return True, (ORRoute(fk, fm) if fk and fm else None)

CFG = CFGType(
    tg_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
    tg_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
    bot_mode=os.getenv("BOT_MODE", "polling").strip(),
    webhook_url=os.getenv("WEBHOOK_URL", "").strip(),
    port=int(os.getenv("PORT", "8080")),
    tz_name=os.getenv("TZ_NAME", "Europe/Kyiv").strip(),

    analyze_timeframe=os.getenv("ANALYZE_TIMEFRAME", "5m").strip(),
    analyze_bars=int(os.getenv("ANALYZE_BARS", "100")),
    analyze_limit=int(os.getenv("ANALYZE_LIMIT", "150")),
    indicator_preset=os.getenv("INDICATOR_PRESET", "preset3").strip(),
    auto_push_min=int(os.getenv("AUTO_PUSH_MIN", "20")),
    monitored_symbols=[s.strip().upper() for s in os.getenv("MONITORED_SYMBOLS", "BTCUSDT").split(",") if s.strip()],

    hybrid_source=os.getenv("HYBRID_SOURCE", "v2").strip(),
    hybrid_catbot_enabled=_get_bool("HYBRID_CATBOT_ENABLED", 1),
    hybrid_catbot_mode=os.getenv("HYBRID_CATBOT_MODE", "preset3").strip(),
    catbot_repo_url=os.getenv("CATBOT_REPO_URL", "").strip(),
    catbot_dir=os.getenv("CATBOT_DIR", "external/crypto_cat_bot").strip(),

    default_tf=os.getenv("DEFAULT_TF", "15m").strip(),
    default_bars=int(os.getenv("DEFAULT_BARS", "200")),

    auto_top_enabled=_get_bool("AUTO_TOP_ENABLED", 1),
    auto_top_interval=int(os.getenv("AUTO_TOP_INTERVAL", "10")),

    analyzer_endpoint=os.getenv("ANALYZER_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions").strip(),

    per_symbol=_collect_per_symbol(),
    help_pool=_collect_help_pool(8),
    fallback_enabled=_get_bool("ANALYZER_FALLBACK_ENABLED", 1),
    fallback=_get_fallback()[1],

    binance_key=os.getenv("BINANCE_API_KEY", "").strip() or None,
    binance_secret=os.getenv("BINANCE_API_SECRET", "").strip() or None,
)

if not CFG.tg_token:
    raise ValueError("TELEGRAM_BOT_TOKEN is missing in .env")
