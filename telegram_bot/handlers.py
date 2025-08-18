# telegram_bot/handlers.py
from __future__ import annotations
import asyncio, math, logging, json, re
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, Application, CommandHandler, CallbackQueryHandler

from core_config import CFG
from router.analyzer_router import pick_route
from utils.openrouter import chat_completion
from utils.formatting import save_report
from utils.ta_formatter import format_ta_report
from gpt_analyst.full_analyzer import run_full_analysis
from gpt_decider.decider import decide_from_markdown
from market_data.candles import get_ohlcv
from market_data.binance_rank import get_all_usdt_24h, get_top_by_quote_volume_usdt
from utils.news_fetcher import get_latest_news

log = logging.getLogger("tg.handlers")

# ──────────────────────────────────────────────────────────────────────────────
# universal send (менш вибагливий: без прев’ю, можна без parse_mode)
# ──────────────────────────────────────────────────────────────────────────────
async def _send(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, *, parse_mode: Optional[str]=None, reply_markup=None):
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is None and update.callback_query and update.callback_query.message:
        chat_id = update.callback_query.message.chat_id
    if chat_id is None and update.message:
        chat_id = update.message.chat_id
    if chat_id is None:
        return
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )

# ──────────────────────────────────────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────────────────────────────────────
def get_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["/top", "/analyze", "/ai"],
            ["/req", "/news", "/ping"],
            ["/help", "/guide"],
        ],
        resize_keyboard=True
    )

# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────
_VALID_DIR_WORDS = {"LONG", "SHORT", "NEUTRAL"}

def _current_ai_model() -> str:
    try:
        probe = (CFG.monitored_symbols[0] if CFG.monitored_symbols else "BTCUSDT").upper()
        route = pick_route(probe)
        return route.model if route else "unknown"
    except Exception:
        return "unknown"

def _looks_like_symbol(s: str) -> bool:
    s = (s or "").strip().upper()
    if not (2 <= len(s) <= 20): return False
    if not all(c.isalnum() for c in s): return False
    for q in ("USDT", "FDUSD", "USDC", "BUSD", "BTC", "ETH", "EUR", "TRY"):
        if s.endswith(q): return True
    return False

def _pick_default_symbol() -> str:
    try:
        for x in CFG.monitored_symbols:
            x = (x or "").strip().upper()
            if _looks_like_symbol(x): return x
    except Exception:
        pass
    return "BTCUSDT"

def _parse_ai_json(txt: str) -> dict:
    try:
        t = txt.strip()
        if t.startswith("```"):
            t = t.strip("` \n").replace("json\n","",1).replace("\njson","").strip("` \n")
        data = json.loads(t)
        return {
            "direction": str(data.get("direction","")).upper(),
            "entry": float(data.get("entry","nan")),
            "stop": float(data.get("stop","nan")),
            "tp": float(data.get("tp","nan")),
            "confidence": float(data.get("confidence",0.0)),
            "holding_time_hours": float(data.get("holding_time_hours",0.0)),
            "holding_time": str(data.get("holding_time","")).strip(),
            "rationale": str(data.get("rationale","")).strip(),
        }
    except Exception:
        dir_m = re.search(r"\b(LONG|SHORT|NEUTRAL)\b", txt, re.I)
        def num(rx):
            m = re.search(rx + r"\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", txt, re.I)
            return float(m.group(1)) if m else float("nan")
        return {
            "direction": dir_m.group(1).upper() if dir_m else "NEUTRAL",
            "entry": num(r"(?:entry|price)"),
            "stop": num(r"(?:stop(?:-|\s*)loss|sl)"),
            "tp":   num(r"(?:take(?:-|\s*)profit|tp)"),
            "confidence": 0.5,
            "holding_time_hours": 0.0,
            "holding_time": "",
            "rationale": txt.strip()
        }

def _fmt_or_dash(v):
    try:
        return f"{float(v):.2f}"
    except Exception:
        return "-"

def _rr(direction: str, entry: float, stop: float, tp: float) -> str:
    try:
        if any(math.isnan(x) for x in [entry,stop,tp]): return "-"
        if direction == "LONG":
            risk = entry - stop; reward = tp - entry
        elif direction == "SHORT":
            risk = stop - entry; reward = entry - tp
        else:
            return "-"
        if risk <= 0 or reward <= 0: return "-"
        return f"{reward/risk:.2f}"
    except Exception:
        return "-"

def _chunk(lst: List[str], n: int) -> List[List[str]]:
    return [lst[i:i+n] for i in range(0, len(lst), n)]

# ──────────────────────────────────────────────────────────────────────────────
# service
# ──────────────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send(update, context, "👋 Привіт! Я трейд-бот. Команди нижче.", reply_markup=get_keyboard())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🆘 *Довідка*\n\n"
        "Доступні команди:\n"
        "• `/top` — Топ-20 USDT пар (режими: *Volume* / *Gainers*). Натисни на монету → меню дій (*🤖 AI* або *🔗 Залежність BTC/ETH*).\n"
        f"• `/analyze` — Повний аналіз по `MONITORED_SYMBOLS` (TF={CFG.analyze_timeframe}), зі збереженням звітів.\n"
        "• `/ai <SYMBOL> [TF]` — Короткий AI-план (Entry/SL/TP, RR, утримання) + індикатори з нашого пресета.\n"
        "• `/req <SYMBOL> [TF]` — Залежність монети від BTC/ETH (ρ, β, Δ Ratio) з AI-коментарем (якщо ключ заданий).\n"
        "• `/news [запит]` — Останні заголовки (швидко, без форматування). Приклади: `/news`, `/news gold`, `/news btc`.\n"
        "• `/ping` — Перевірка стану.\n"
        "• `/guide` — Як читати AI-план та метрики.\n\n"
        f"🧠 Активна AI-модель: `{_current_ai_model()}`\n"
        f"⏱ Часовий пояс: `{getattr(CFG, 'tz_name', 'UTC')}`"
    )
    await _send(update, context, text, parse_mode="Markdown")

async def guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Гайд: як користуватись ботом*\n\n"
        "1) **/top** — Топ-20 USDT пар, перемикай *Volume/Gainers*, тисни на символ → *🤖 AI* або *🔗 Залежність*.\n\n"
        "2) **/ai <SYMBOL> [TF]** — Direction, Confidence(0–1), RR, Entry/SL/TP, утримання + 12 індикаторів.\n"
        "   Порада: якщо RR < 1.5 — краще дочекатись кращої точки входу.\n\n"
        "3) **/req <SYMBOL> [TF]** — ρ(30/90), β, Δ Ratio(30) до BTC/ETH + короткий коментар.\n\n"
        f"4) **/analyze** — повний звіт по `MONITORED_SYMBOLS` на TF={CFG.analyze_timeframe}."
    )
    await _send(update, context, text, parse_mode="Markdown")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send(update, context, f"🏓 pong all ok | AI model: {_current_ai_model()}")

# ──────────────────────────────────────────────────────────────────────────────
# /news — спрощений, швидкий, без Markdown/HTML
# ──────────────────────────────────────────────────────────────────────────────
async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        query = " ".join(args).strip() if args else None
        # Швидкий режим: менше елементів
        items = get_latest_news(query=query, max_items=8, lang=getattr(CFG, "news_lang", "uk"))
        if not items:
            await _send(update, context, "📰 Немає свіжих заголовків зараз.")
            return
        lines = ["📰 Останні заголовки:"]
        for it in items:
            # Жодного форматування Markdown/HTML — лише plain text
            title = it.get("title") or ""
            link = it.get("link") or ""
            src  = it.get("source") or ""
            if src:
                lines.append(f"• {title} — {src}\n  {link}")
            else:
                lines.append(f"• {title}\n  {link}")
        msg = "\n".join(lines)
        await _send(update, context, msg[:4000])  # parse_mode=None
    except Exception as e:
        log.exception("/news failed")
        await _send(update, context, f"⚠️ news error: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# /top — Volume / Gainers + «меню монети»
# ──────────────────────────────────────────────────────────────────────────────
TOP_MODE_VOLUME = "volume"
TOP_MODE_GAINERS = "gainers"

def _build_top_text(rows: List[dict]) -> Tuple[str, List[str]]:
    def fmt_vol(usdt: float) -> str:
        a = abs(usdt)
        if a >= 1_000_000_000: return f"{usdt/1_000_000_000:.2f}B"
        if a >= 1_000_000:     return f"{usdt/1_000_000:.1f}M"
        if a >= 1_000:         return f"{usdt/1_000:.1f}K"
        return f"{usdt:.0f}"

    lines, symbols = [], []
    lines.append("_Symbol | Price | 24h% | QuoteVol_\n")
    for i, r in enumerate(rows, 1):
        sym = r["symbol"]; symbols.append(sym)
        price = r["lastPrice"]; chg = r["priceChangePercent"]; vol = r["quoteVolume"]
        emoji = "🟢" if chg >= 0 else "🔴"
        lines.append(f"{i:>2}. `{sym}` | `{price:,.6f}` | {emoji} `{chg:+.2f}%` | `{fmt_vol(vol)}`")
    return "\n".join(lines), symbols

def _top_mode_buttons(active: str) -> list[list[InlineKeyboardButton]]:
    vol = InlineKeyboardButton(("✅ Volume" if active==TOP_MODE_VOLUME else "Volume"), callback_data="topmode:volume")
    gai = InlineKeyboardButton(("✅ Gainers" if active==TOP_MODE_GAINERS else "Gainers"), callback_data="topmode:gainers")
    return [[vol, gai]]

async def _send_top(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str):
    if mode == TOP_MODE_GAINERS:
        all_rows = await asyncio.to_thread(get_all_usdt_24h)
        all_rows.sort(key=lambda x: x["priceChangePercent"], reverse=True)
        rows = all_rows[:20]
        header = "🏆 *Топ-20 USDT пар — Gainers (24h %)*\n"
    else:
        rows = await asyncio.to_thread(get_top_by_quote_volume_usdt, 20)
        header = "🏆 *Топ-20 USDT пар — Volume (24h QuoteVol)*\n"

    text_body, symbols = _build_top_text(rows)

    sym_rows = []
    for chunk in _chunk(symbols, 4):
        sym_rows.append([InlineKeyboardButton(text=s, callback_data=f"sym:{s}") for s in chunk])

    kb = InlineKeyboardMarkup(sym_rows + _top_mode_buttons(mode))
    await _send(update, context, (header + text_body)[:4000], parse_mode="Markdown", reply_markup=kb)

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = TOP_MODE_GAINERS if (context.args and context.args[0].lower().startswith("gain")) else TOP_MODE_VOLUME
    await _send_top(update, context, mode)

# ──────────────────────────────────────────────────────────────────────────────
# «меню монети»
# ──────────────────────────────────────────────────────────────────────────────
async def on_cb_sym(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = (q.data or "")
    if not data.startswith("sym:"): return
    sym = data.split(":",1)[1].upper()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🤖 AI {sym}", callback_data=f"ai:{sym}")],
        [InlineKeyboardButton(f"🔗 Залежність BTC/ETH {sym}", callback_data=f"dep:{sym}")],
    ])
    await _send(update, context, f"Вибери дію для `{sym}`:", parse_mode="Markdown", reply_markup=kb)

async def on_cb_topmode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = (q.data or "")
    if not data.startswith("topmode:"): return
    mode = data.split(":",1)[1]
    if mode not in (TOP_MODE_VOLUME, TOP_MODE_GAINERS):
        mode = TOP_MODE_VOLUME
    await _send_top(update, context, mode)

# ──────────────────────────────────────────────────────────────────────────────
# /analyze — повний аналіз + індикатори
# ──────────────────────────────────────────────────────────────────────────────
async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send(update, context, f"⏳ Аналізую на TF={CFG.analyze_timeframe}…")
    for s in CFG.monitored_symbols:
        try:
            lines = await asyncio.to_thread(run_full_analysis, s, CFG.analyze_timeframe, CFG.default_bars)
            save_report(s, lines)
            ta_block = format_ta_report(s, CFG.analyze_timeframe, CFG.analyze_limit)
            reply_text = "\n".join(lines) + "\n\n📊 Indicators:\n" + ta_block
            await _send(update, context, reply_text[:4000], parse_mode="Markdown")
        except Exception as e:
            log.exception("analyze %s failed", s)
            await _send(update, context, f"⚠️ analyze {s} error: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# /ai — план + RR-фільтр + індикатори
# ──────────────────────────────────────────────────────────────────────────────
AI_SYSTEM = (
    "You are a concise crypto trading assistant. "
    "Return STRICT JSON only (no prose) with keys exactly: "
    '{"direction":"LONG|SHORT|NEUTRAL","entry":number,"stop":number,"tp":number,'
    '"confidence":0..1,"holding_time_hours":number,"holding_time":"string",'
    '"rationale":"2-3 sentences"} '
    "Use trend/momentum/volatility/strength/volume/pivots data. "
    "Prefer ~1:3 risk-reward when reasonable."
)
CONF_RR_MIN = 1.5

async def ai(update: Update, context: ContextTypes.DEFAULT_TYPE, *, symbol_arg: Optional[str] = None, timeframe_arg: Optional[str] = None):
    args = context.args or []
    raw = symbol_arg or (args[0] if args else "")
    raw = raw.strip().upper()
    timeframe = (timeframe_arg or (args[1] if len(args) > 1 else CFG.analyze_timeframe)).strip()

    if not raw:
        symbol = _pick_default_symbol()
    elif raw in _VALID_DIR_WORDS:
        await _send(update, context, "ℹ️ Це схоже на напрям, а не символ. Приклад: `/ai BTCUSDT`.")
        return
    elif not _looks_like_symbol(raw):
        await _send(update, context, "⚠️ Невірний символ. Приклад: `/ai BTCUSDT`.")
        return
    else:
        symbol = raw

    await _send(update, context, f"⏳ Рахую індикатори для {symbol} (TF={timeframe})…")

    try:
        data = get_ohlcv(symbol, timeframe, CFG.analyze_limit)
        last_close = data[-1]["close"] if data else float("nan")

        block = [
            f"SYMBOL: {symbol}",
            f"TF: {timeframe}",
            f"PRICE_LAST: {last_close:.6f}",
            f"BARS: {min(len(data), CFG.analyze_limit)}",
        ]
        route = pick_route(symbol)
        if not route:
            await _send(update, context, f"❌ Немає доступного API-роутингу для {symbol}")
            return

        prompt = (
            "\n".join(block) + "\n\n"
            "Decide if there is a trade now. Return STRICT JSON only (no prose) with keys exactly:\n"
            '{"direction":"LONG|SHORT|NEUTRAL","entry":number,"stop":number,"tp":number,'
            '"confidence":0..1,"holding_time_hours":number,"holding_time":"string","rationale":"2-3 sentences"}.\n'
            "Use trend, momentum (MACD/RSI), volatility (ATR/BB), strength (ADX/CCI), volume (OBV/MFI), and Pivots (assume computed)."
        )

        raw_resp = chat_completion(
            endpoint=CFG.analyzer_endpoint,
            api_key=route.api_key,
            model=route.model,
            messages=[{"role":"system","content":AI_SYSTEM},{"role":"user","content":prompt}],
            timeout=25
        )
        plan = _parse_ai_json(raw_resp)

        direction = (plan.get("direction") or "").upper()
        entry = float(plan.get("entry", math.nan))
        stop = float(plan.get("stop", math.nan))
        tp   = float(plan.get("tp", math.nan))
        conf = float(plan.get("confidence", 0.0))

        rr_text = _rr(direction, entry, stop, tp)
        try:
            if rr_text != "-" and float(rr_text) < CONF_RR_MIN:
                await _send(update, context, f"⚠️ Слабкий сигнал (RR < {CONF_RR_MIN}) — скіп.")
                return
        except Exception:
            pass

        tz = ZoneInfo(CFG.tz_name)
        now_local = datetime.now(tz)
        hold_h = float(plan.get("holding_time_hours", 0.0))
        hold_until_local = now_local + timedelta(hours=hold_h) if hold_h > 0 else None
        hold_line = (
            f"Recommended hold: {int(round(hold_h))} h"
            + (f" (до {hold_until_local.strftime('%Y-%m-%d %H:%M %Z')} / {CFG.tz_name})" if hold_until_local else "")
        )
        stamp_line = f"Generated: {now_local.strftime('%Y-%m-%d %H:%M %Z')}"

        reply = (
            f"🤖 *AI Trade Plan* for {symbol} (TF={timeframe})\n"
            f"📌 Model: {_current_ai_model()}\n"
            f"🕒 {stamp_line}\n\n"
            f"➡️ *Direction*: `{direction or '-'}`\n"
            f"📊 *Confidence*: `{conf:.2%}`\n"
            f"⚖️ *RR*: `{rr_text}`\n"
            f"💰 *Entry*: `{_fmt_or_dash(entry)}`\n"
            f"🛑 *Stop*: `{_fmt_or_dash(stop)}`\n"
            f"🎯 *Take*: `{_fmt_or_dash(tp)}`\n"
            f"⏳ {hold_line}\n\n"
            f"🧾 *Reasoning*:\n{plan.get('rationale','—')}\n\n"
            "📈 *Indicators (preset)*:\n"
            f"{format_ta_report(symbol, timeframe, CFG.analyze_limit)}"
        )
        await _send(update, context, reply, parse_mode="Markdown")

    except Exception as e:
        log.exception("/ai failed")
        await _send(update, context, f"⚠️ ai error: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# ЗАЛЕЖНІСТЬ BTC/ETH → <SYMBOL>  (швидший фолбек; AI тільки якщо ключ заданий)
# ──────────────────────────────────────────────────────────────────────────────
def _pct(series: List[float]) -> List[float]:
    out = []
    for i in range(1, len(series)):
        prev = series[i-1] or 0.0
        out.append(0.0 if prev == 0 else (series[i]-series[i-1]) / prev)
    return out

def _corr(a: List[float], b: List[float]) -> float:
    import statistics as st
    n = min(len(a), len(b))
    if n < 3: return float("nan")
    a, b = a[:n], b[:n]
    try:
        ma, mb = st.mean(a), st.mean(b)
        cov = sum((x-ma)*(y-mb) for x,y in zip(a,b)) / (n-1)
        va = sum((x-ma)**2 for x in a) / (n-1)
        vb = sum((y-mb)**2 for y in b) / (n-1)
        if va <= 0 or vb <= 0: return float("nan")
        return cov / (va**0.5 * vb**0.5)
    except Exception:
        return float("nan")

def _beta(dep: List[float], indep: List[float]) -> float:
    import statistics as st
    n = min(len(dep), len(indep))
    if n < 3: return float("nan")
    dep, indep = dep[:n], indep[:n]
    md, mi = st.mean(dep), st.mean(indep)
    cov = sum((x-md)*(y-mi) for x,y in zip(dep,indep)) / (n-1)
    var_i = sum((y-mi)**2 for y in indep) / (n-1)
    if var_i <= 0: return float("nan")
    return cov / var_i

DEP_SYSTEM = (
    "You are a quantitative crypto assistant. "
    "Given correlations, betas and ratio changes for a symbol vs BTC/ETH, "
    "return exactly 3 short Ukrainian bullets (max 18 words each), no extra text."
)

def _heuristic_dep_bullets(symbol: str, corr_btc_30, corr_eth_30, corr_btc_90, corr_eth_90, beta_btc, beta_eth, rbtc, reth) -> str:
    tips = []
    hi = lambda x: (isinstance(x, (int,float)) and x==x and x>=0.6)
    lo = lambda x: (isinstance(x, (int,float)) and x==x and x<0.3)
    if hi(corr_btc_30) or hi(corr_eth_30):
        tips.append(f"{symbol}: висока короткострокова кореляція з лідерами — рух синхронний, ризик системний.")
    if hi(beta_btc) or hi(beta_eth):
        tips.append(f"{symbol}: β>1 — амплітуда більша за лідера, підсилює тренд й ризик.")
    if lo(corr_btc_90) and lo(corr_eth_90):
        tips.append(f"{symbol}: низька довгострокова кореляція — власні драйвери, диверсифікаційний ефект.")
    if isinstance(rbtc,(int,float)) and rbtc==rbtc:
        tips.append(f"{symbol}: відносно BTC за 30 барів {rbtc*100:+.2f}% — оцінка сили/слабкості.")
    if isinstance(reth,(int,float)) and reth==reth:
        tips.append(f"{symbol}: відносно ETH за 30 барів {reth*100:+.2f}% — підтверджено другим лідером.")
    if not tips:
        tips = [f"{symbol}: звʼязок із BTC/ETH помірний; корисні фільтри тренду (EMA/ADX) та обʼєм."]
    return "\n".join("- " + t for t in tips[:3])

async def _dependency_report(symbol: str, timeframe: str, limit: int = 300) -> str:
    t_data = get_ohlcv(symbol, timeframe, limit)
    b_data = get_ohlcv("BTCUSDT", timeframe, limit)
    e_data = get_ohlcv("ETHUSDT", timeframe, limit)
    if not t_data or not b_data or not e_data:
        return "_No data to compute dependency_"

    t_close = [x["close"] for x in t_data]
    b_close = [x["close"] for x in b_data]
    e_close = [x["close"] for x in e_data]

    t_ret = _pct(t_close); b_ret = _pct(b_close); e_ret = _pct(e_close)

    win30 = 30 if len(t_ret) >= 30 else len(t_ret)
    win90 = 90 if len(t_ret) >= 90 else len(t_ret)

    corr_btc_30 = _corr(t_ret[-win30:], b_ret[-win30:])
    corr_eth_30 = _corr(t_ret[-win30:], e_ret[-win30:])
    corr_btc_90 = _corr(t_ret[-win90:], b_ret[-win90:])
    corr_eth_90 = _corr(t_ret[-win90:], e_ret[-win90:])

    beta_btc = _beta(t_ret[-win90:], b_ret[-win90:])
    beta_eth = _beta(t_ret[-win90:], e_ret[-win90:])

    ratio_btc_change = (t_close[-1] / b_close[-1]) / (t_close[-win30] / b_close[-win30]) - 1 if win30>=2 else float("nan")
    ratio_eth_change = (t_close[-1] / e_close[-1]) / (t_close[-win30] / e_close[-win30]) - 1 if win30>=2 else float("nan")

    # AI-коментар: викликаємо лише якщо є ключ+модель
    ai_text = None
    api_key_1 = getattr(CFG, "help_api_key8", None) or getattr(CFG, "HELP_API_KEY8", None)
    model_1   = getattr(CFG, "help_api_key8_model", None) or getattr(CFG, "HELP_API_KEY8_MODEL", None)

    if api_key_1 and model_1:
        hints = (
            f"SYMBOL={symbol}\nTF={timeframe}\n"
            f"corr_btc_30={corr_btc_30:.3f}\ncorr_eth_30={corr_eth_30:.3f}\n"
            f"corr_btc_90={corr_btc_90:.3f}\ncorr_eth_90={corr_eth_90:.3f}\n"
            f"beta_btc={beta_btc:.3f}\nbeta_eth={beta_eth:.3f}\n"
            f"ratio_btc_change_30={ratio_btc_change:.3f}\n"
            f"ratio_eth_change_30={ratio_eth_change:.3f}\n"
            "Return exactly 3 short bullets."
        )
        try:
            ai_text = chat_completion(
                endpoint=CFG.analyzer_endpoint,
                api_key=api_key_1,
                model=model_1,
                messages=[{"role":"system","content":DEP_SYSTEM},
                          {"role":"user","content":hints}],
                timeout=18
            )
        except Exception:
            ai_text = None

    if not ai_text:
        ai_text = _heuristic_dep_bullets(
            symbol, corr_btc_30, corr_eth_30, corr_btc_90, corr_eth_90, beta_btc, beta_eth,
            ratio_btc_change, ratio_eth_change
        )

    def fmt(x, d=3):
        try: return f"{float(x):.{d}f}"
        except: return "-"

    md = []
    md.append(f"🔗 *Залежність BTC/ETH для* `{symbol}` *(TF={timeframe})*")
    md.append("")
    md.append(f"- ρ BTC (30/90): `{fmt(corr_btc_30)}` / `{fmt(corr_btc_90)}`")
    md.append(f"- ρ ETH (30/90): `{fmt(corr_eth_30)}` / `{fmt(corr_eth_90)}`")
    md.append(f"- β до BTC/ETH: `{fmt(beta_btc)}` / `{fmt(beta_eth)}`")
    md.append(f"- Δ Ratio vs BTC (30): `{fmt(ratio_btc_change*100,2)}%`")
    md.append(f"- Δ Ratio vs ETH (30): `{fmt(ratio_eth_change*100,2)}%`")
    md.append("")
    md.append("🧠 *Коментар*:")
    md.append((ai_text or "-").strip()[:1200])
    return "\n".join(md)

async def on_cb_dep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = (q.data or "")
    if not data.startswith("dep:"): return
    sym = data.split(":",1)[1].upper()
    await _send(update, context, f"⏳ Рахую залежність BTC/ETH для {sym}…")
    try:
        report = await _dependency_report(sym, CFG.analyze_timeframe, limit=300)
        await _send(update, context, report, parse_mode="Markdown")
    except Exception as e:
        log.exception("dep failed")
        await _send(update, context, f"⚠️ dep error: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# CALLBACK: ai:<SYM>
# ──────────────────────────────────────────────────────────────────────────────
async def on_cb_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        q = update.callback_query
        await q.answer()
        data = (q.data or "")
        if not data.startswith("ai:"): return
        symbol = data.split(":",1)[1].strip().upper()
        await ai(update, context, symbol_arg=symbol, timeframe_arg=CFG.analyze_timeframe)
    except Exception as e:
        log.exception("on_cb_ai failed")
        await _send(update, context, f"⚠️ callback error: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# /req — залежність як окрема команда
# ──────────────────────────────────────────────────────────────────────────────
async def req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    symbol = (args[0] if args else _pick_default_symbol()).upper()
    tf = (args[1] if len(args) > 1 else CFG.analyze_timeframe)
    if not _looks_like_symbol(symbol):
        await _send(update, context, "⚠️ Невірний символ. Приклад: `/req ADAUSDT 1h`")
        return
    await _send(update, context, f"⏳ Рахую залежність BTC/ETH для {symbol}…")
    try:
        report = await _dependency_report(symbol, tf, limit=300)
        await _send(update, context, report, parse_mode="Markdown")
    except Exception as e:
        log.exception("/req failed")
        await _send(update, context, f"⚠️ req error: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# register
# ──────────────────────────────────────────────────────────────────────────────
def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("guide", guide))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("analyze", analyze))
    app.add_handler(CommandHandler("ai", ai))
    app.add_handler(CommandHandler("req", req))
    app.add_handler(CommandHandler("news", news))

    app.add_handler(CallbackQueryHandler(on_cb_sym,     pattern=r"^sym:[A-Z0-9]+$"))
    app.add_handler(CallbackQueryHandler(on_cb_ai,      pattern=r"^ai:[A-Z0-9]+$"))
    app.add_handler(CallbackQueryHandler(on_cb_dep,     pattern=r"^dep:[A-Z0-9]+$"))
    app.add_handler(CallbackQueryHandler(on_cb_topmode, pattern=r"^topmode:(volume|gainers)$"))
