# telegram_bot/handlers.py
from __future__ import annotations
import asyncio, time, math, logging, json, re
from typing import Tuple, Optional, Dict, List
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from core_config import (
    MONITORED_SYMBOLS,
    ANALYZE_TIMEFRAME, ANALYZE_LIMIT,  # лишаємо (ліміт свічок для фетчу)
    TZ_NAME,
    OPENROUTER_API_KEY, OPENROUTER_MODEL,
    LOCAL_LLM_MODEL,
    # ⬇️ додано
    ANALYZE_BARS,          # скільки останніх барів беремо в контекст LLM
    COMPACT_MODE,          # компактний/повний режим промпта
)

# Дані/TA
from market_data.binance_data import get_ohlcv, get_latest_price
from signal_tools.ta_calc import get_ta_indicators

# Інше
from utils.report_saver import save_report
from gpt_analyst.symbol_screener import get_top_symbols
from gpt_analyst.llm_client import chat

# ── Сумісний імпорт аналізатора ──────────────────────────────────────────────
_run_full_analysis = None
_analyze_symbol = None
try:
    # Новий варіант
    from gpt_analyst.full_analyzer import run_full_analysis as _run_full_analysis
except Exception:
    pass
try:
    # Старий варіант
    from gpt_analyst.full_analyzer import analyze_symbol as _analyze_symbol
except Exception:
    pass

log = logging.getLogger("tg.handlers")


# ──────────────────────────────────────────────────────────────────────────────
# UI / Клавіатура
# ──────────────────────────────────────────────────────────────────────────────
def get_keyboard():
    return ReplyKeyboardMarkup(
        [["/top", "/analyze", "/ai"], ["/news", "/ping", "/help", "/guide"]],  # /ai — головний аналітик
        resize_keyboard=True
    )


# ──────────────────────────────────────────────────────────────────────────────
# Хелпери
# ──────────────────────────────────────────────────────────────────────────────
def _current_ai_model() -> str:
    try:
        if (OPENROUTER_API_KEY or "").strip():
            return str(OPENROUTER_MODEL or "").strip() or "unknown"
        return str(LOCAL_LLM_MODEL or "").strip() or "unknown"
    except Exception:
        return "unknown"

def _tf_minutes(tf: str) -> int:
    t = (tf or "").strip().lower()
    if t.endswith("m"): return int(t[:-1])
    if t.endswith("h"): return int(t[:-1]) * 60
    if t.endswith("d"): return int(t[:-1]) * 60 * 24
    return 15

_VALID_DIR_WORDS = {"LONG", "SHORT", "NEUTRAL"}

def _looks_like_symbol(s: str) -> bool:
    s = (s or "").strip().upper()
    if not (2 <= len(s) <= 20): return False
    if not all(c.isalnum() for c in s): return False
    for q in ("USDT", "FDUSD", "USDC", "BUSD", "BTC", "ETH", "EUR", "TRY"):
        if s.endswith(q):
            return True
    return False

def _pick_default_symbol() -> str:
    try:
        for x in MONITORED_SYMBOLS:
            x = (x or "").strip().upper()
            if _looks_like_symbol(x):
                return x
    except Exception:
        pass
    return "BTCUSDT"

def _parse_ai_json(txt: str) -> dict:
    try:
        t = txt.strip()
        if t.startswith("```"):
            t = t.strip("` \n")
            t = t.replace("json\n", "", 1).replace("\njson", "").strip("` \n")
        data = json.loads(t)
        out = {
            "direction": str(data.get("direction", "")).upper(),
            "entry": float(data.get("entry", "nan")),
            "stop": float(data.get("stop", "nan")),
            "tp": float(data.get("tp", "nan")),
            "confidence": float(data.get("confidence", 0.0)),
            "holding_time_hours": float(data.get("holding_time_hours", 0.0)),
            "holding_time": str(data.get("holding_time", "")).strip(),
            "rationale": str(data.get("rationale", "")).strip(),
        }
        return out
    except Exception:
        dir_m = re.search(r"\b(LONG|SHORT|NEUTRAL)\b", txt, re.I)
        def num(key_regex):
            m = re.search(key_regex + r"\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", txt, re.I)
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
        if any(math.isnan(x) for x in [entry, stop, tp]):
            return "-"
        if direction == "LONG":
            risk = entry - stop
            reward = tp - entry
        elif direction == "SHORT":
            risk = stop - entry
            reward = entry - tp
        else:
            return "-"
        if risk <= 0 or reward <= 0:
            return "-"
        return f"{reward/risk:.2f}"
    except Exception:
        return "-"


# ──────────────────────────────────────────────────────────────────────────────
# Сервісні
# ──────────────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привіт! Я трейд-бот. Команди нижче.", reply_markup=get_keyboard())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команди:\n"
        "/top — топ-20 монет за скором (весь Binance), швидкий дайджест\n"
        f"/analyze — повний аналіз по MONITORED_SYMBOLS (TF={ANALYZE_TIMEFRAME})\n"
        "/ai <SYMBOL> [TF] — розгорнутий AI-план (entry/SL/TP, RR, час утримання)\n"
        "/news — заголовки з крипто-RSS\n"
        "/ping — діагностика\n"
        "/guide — як читати AI-план\n\n"
        f"Активна AI-модель: {_current_ai_model()}"
    )

async def guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Як читати AI-план*\n\n"
        f"Використання: `/ai BTCUSDT` — аналізує ринкові дані на TF={ANALYZE_TIMEFRAME} і повертає план.\n\n"
        "📌 *Поля:*\n"
        "- *Direction* – LONG/SHORT/NEUTRAL (напрям ідеї)\n"
        "- *Confidence* – впевненість (0–1)\n"
        "- *RR* – ризик/прибуток (>1.5 добре, 2.0+ краще)\n"
        "- *Entry / SL / TP* – рівні входу/стопу/тейку\n"
        "- *Recommended hold* – скільки тримати позицію та дедлайн у твоєму time zone\n"
        "- *— пояснення —* – коротка логіка рішення\n\n"
        "💡 *Поради:*\n"
        "• Якщо RR < 1.5 — краще пошукати кращу точку входу.\n"
        "• Дивись на EMA50/EMA200 (тренд) та ADX (сила тренду).\n"
        "• RSI/StochRSI — для фільтрації імпульсів.\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🏓 pong all ok | AI model: {_current_ai_model()}")


# ──────────────────────────────────────────────────────────────────────────────
# NEWS (опційно)
# ──────────────────────────────────────────────────────────────────────────────
async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        from market_data.news import get_latest_news
        items = get_latest_news(limit=8)
        if not items:
            await update.message.reply_text("📰 Немає свіжих заголовків зараз.")
            return
        lines = ["📰 Останні заголовки:\n"]
        for it in items:
            lines.append(f"• {it['title']} — {it['link']}")
        text = "\n".join(lines)
        await update.message.reply_text(text[:4000])
    except Exception as e:
        log.exception("/news failed")
        await update.message.reply_text(f"⚠️ news error: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# /top — Топ-20 по всьому Binance (паралельно + кеш)
# ──────────────────────────────────────────────────────────────────────────────
_TOP_CACHE: Dict[str, object] = {"text": "", "ts": 0.0, "busy": False}
TOP_TTL_SEC = 120
MAX_CONCURRENCY = 12
DETAIL_POOL_SIZE = 60

def _bias_from_row(row) -> str:
    try:
        rsi = float(row.get("rsi"))
        macd_d = float(row.get("macd")) - float(row.get("macd_signal"))
        sma7 = float(row.get("sma_7"))
        sma25 = float(row.get("sma_25"))
    except Exception:
        return "NEUTRAL"
    if sma7 > sma25 and macd_d > 0 and rsi >= 52: return "LONG"
    if sma7 < sma25 and macd_d < 0 and rsi <= 48: return "SHORT"
    return "NEUTRAL"

def _fmt_line(symbol: str, bias: str, price: float, rsi: float, macd_delta: float, atr_pct: Optional[float]) -> str:
    dot = "🟢" if bias == "LONG" else "🔴" if bias == "SHORT" else "⚪️"
    atr_txt = "-" if (atr_pct is None or (isinstance(atr_pct, float) and math.isnan(atr_pct))) else f"{atr_pct:.3f}%"
    return f"{dot} {bias} {symbol}  | P={price:.4f}  | RSI={rsi:.1f}  | MACDΔ={macd_delta:.4f}  | ATR%={atr_txt}"

async def _detail_one(symbol: str) -> Optional[Tuple[str, str, float, float, float, Optional[float]]]:
    try:
        def _work():
            df = get_ohlcv(symbol, ANALYZE_TIMEFRAME, ANALYZE_LIMIT)
            if df is None or df.empty:
                return None
            inds = get_ta_indicators(df)
            last = inds.iloc[-1]
            price = float(last.get("close", 0.0))
            rsi = float(last.get("rsi", 50.0))
            macd_d = float(last.get("macd", 0.0)) - float(last.get("macd_signal", 0.0))
            atr = float(last.get("atr_14", 0.0))
            atr_pct = (atr / price * 100) if price else None
            bias = _bias_from_row(last)
            return (symbol, bias, price, rsi, macd_d, atr_pct)
        return await asyncio.to_thread(_work)
    except Exception:
        return None

async def _build_top_text() -> str:
    candidates = get_top_symbols(DETAIL_POOL_SIZE) or []
    if not candidates:
        return f"🏆 Топ-20 монет за скором (TF={ANALYZE_TIMEFRAME})\n⚠️ Немає даних для відбору."

    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    async def _guarded(sym):
        async with sem:
            return await _detail_one(sym)

    tasks = [asyncio.create_task(_guarded(s)) for s in candidates]
    results = [r for r in await asyncio.gather(*tasks) if r]

    def strength(row):
        _, bias, _, rsi, macd_d, atr_pct = row
        score = 0.0
        if bias == "LONG":
            score += 2.0 + max(0.0, min(1.0, (rsi - 50.0) / 20.0)) + max(0.0, min(1.0, macd_d)) * 0.5
        elif bias == "SHORT":
            score += 2.0 + max(0.0, min(1.0, (50.0 - rsi) / 20.0)) + max(0.0, min(1.0, -macd_d)) * 0.5
        else:
            score += 1.0
        if atr_pct and not math.isnan(atr_pct):
            score += min(1.0, atr_pct / 1.0) * 0.1
        return score

    results.sort(key=strength, reverse=True)
    top20 = results[:20]

    header = (
        f"🏆 Топ-20 монет за скором (TF={ANALYZE_TIMEFRAME})\n"
        "📊 Колонки:\n"
        "P — остання ціна (4 знаки)\n"
        "RSI — RSI(14), 0.1\n"
        "MACDΔ — MACD − Signal, 4 знаки\n"
        "ATR% — ATR(14) / Price * 100, 3 знаки\n"
        "Time — Europe/Kyiv (час не дублюємо в рядках)\n"
    )
    body = "\n".join(_fmt_line(*r) for r in top20)
    return (header + "\n" + body)[:4000]

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = time.time()
    if (_TOP_CACHE["text"] and (now - float(_TOP_CACHE["ts"]) <= TOP_TTL_SEC)):
        await update.message.reply_text(_TOP_CACHE["text"])
        return

    await update.message.reply_text(f"⏳ Рахую топ по всьому Binance (TF={ANALYZE_TIMEFRAME})… Зачекай кілька секунд…")

    if _TOP_CACHE["busy"]:
        for _ in range(30):
            await asyncio.sleep(0.5)
            if (_TOP_CACHE["text"] and (time.time() - float(_TOP_CACHE["ts"]) <= TOP_TTL_SEC)):
                await update.message.reply_text(_TOP_CACHE["text"])
                return
        await update.message.reply_text("⌛️ Дані ще готуються — надішлю як тільки будуть готові.")
        return

    async def _compute_and_send(chat_id: int):
        try:
            _TOP_CACHE["busy"] = True
            text = await _build_top_text()
            _TOP_CACHE["text"] = text
            _TOP_CACHE["ts"] = time.time()
            await context.bot.send_message(chat_id=chat_id, text=text)
        except Exception as e:
            log.exception("top build failed")
            await context.bot.send_message(chat_id=chat_id, text=f"⚠️ top build error: {e}")
        finally:
            _TOP_CACHE["busy"] = False

    asyncio.create_task(_compute_and_send(update.effective_chat.id))


# ──────────────────────────────────────────────────────────────────────────────
# /analyze — повний аналіз по MONITORED_SYMBOLS (підтримка двох API)
# ──────────────────────────────────────────────────────────────────────────────
async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"⏳ Аналізую на TF={ANALYZE_TIMEFRAME}… Зачекай кілька секунд…")
    for s in MONITORED_SYMBOLS:
        try:
            text_out = None
            if _run_full_analysis:
                # очікувані сигнатури: (symbol, timeframe) або (symbol,)
                try:
                    res = _run_full_analysis(s, ANALYZE_TIMEFRAME)
                except TypeError:
                    res = _run_full_analysis(s)
                text_out = "\n".join(res) if isinstance(res, (list, tuple)) else str(res)
            elif _analyze_symbol:
                res = _analyze_symbol(s)
                text_out = str(res)
            else:
                text_out = "⚠️ Немає ні run_full_analysis, ні analyze_symbol у gpt_analyst.full_analyzer."

            if text_out:
                save_report(s, text_out)
                await update.message.reply_text(text_out[:4000], parse_mode="Markdown")
        except Exception as e:
            log.exception("analyze %s failed", s)
            await update.message.reply_text(f"⚠️ analyze {s} error: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# /ai — розгорнутий план (TA-контекст: EMA/MACD/RSI/ATR/OBV/MFI/ADX/CCI/Pivots)
# ──────────────────────────────────────────────────────────────────────────────
AI_SYSTEM = (
    "You are a concise crypto trading assistant. "
    "Return STRICT JSON only (no prose) with keys exactly: "
    '{"direction":"LONG|SHORT|NEUTRAL","entry":number,"stop":number,"tp":number,'
    '"confidence":0..1,"holding_time_hours":number,"holding_time":"string",'
    '"rationale":"2-3 sentences"} '
    "Use only the provided trend/momentum/volatility/strength/volume/pivots data. "
    "Prefer ~1:3 risk-reward when reasonable."
)

async def ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    raw = (args[0] if args else "").strip().upper()
    timeframe = (args[1] if len(args) > 1 else ANALYZE_TIMEFRAME).strip()

    if not raw:
        symbol = _pick_default_symbol()
    elif raw in _VALID_DIR_WORDS:
        await update.message.reply_text("ℹ️ Це схоже на *напрям*, а не символ. Приклад: `/ai BTCUSDT`.")
        return
    elif not _looks_like_symbol(raw):
        await update.message.reply_text("⚠️ Невірний символ. Приклад: `/ai BTCUSDT`.")
        return
    else:
        symbol = raw

    await update.message.reply_text(
        f"⏳ Рахую індикатори для {symbol} (TF={timeframe}, bars={ANALYZE_BARS}, mode={'COMPACT' if COMPACT_MODE else 'FULL'})…"
    )

    try:
        # 1) Дані ринку (свічки + індикатори)
        def _work():
            # Фетчимо з запасом по ANALYZE_LIMIT, але LLM-контексту дамо ANALYZE_BARS
            df = get_ohlcv(symbol, timeframe, ANALYZE_LIMIT)
            inds = get_ta_indicators(df)
            last = inds.iloc[-1]
            price = float(last.get("close", float("nan")))
            return inds, last, price
        inds, last, price = await asyncio.to_thread(_work)

        # 2) Вікно для LLM: останні ANALYZE_BARS
        win = inds.tail(ANALYZE_BARS).copy()
        block: List[str] = []
        block.append(f"SYMBOL: {symbol}")
        block.append(f"TF: {timeframe}")
        block.append(f"PRICE_LAST: {price:.6f}")

        if COMPACT_MODE:
            # Стисле резюме ключових фіч
            ema50 = float(last.get('ema_50', last.get('EMA50', float('nan'))))
            ema200 = float(last.get('ema_200', last.get('EMA200', float('nan'))))
            rsi_avg = float(win['rsi'].mean()) if 'rsi' in win.columns else float('nan')
            macd = float(last.get('macd', last.get('MACD', float('nan'))))
            atr_avg = float(win['atr_14'].mean()) if 'atr_14' in win.columns else (float(win['ATR'].mean()) if 'ATR' in win.columns else float('nan'))
            adx = float(last.get('adx', last.get('ADX', float('nan'))))

            block += [
                f"EMA50_last: {ema50:.6f}",
                f"EMA200_last: {ema200:.6f}",
                f"RSI_avg_{ANALYZE_BARS}: {rsi_avg:.4f}",
                f"MACD_last: {macd:.6f}",
                f"ATR_avg_{ANALYZE_BARS}: {atr_avg:.6f}",
                f"ADX_last: {adx:.4f}",
            ]
        else:
            # Повний блок: основні індикатори + кілька осциляторів/півотів
            # Тренд
            block.append(f"EMA50_last: {float(last.get('ema_50', last.get('EMA50', float('nan')))):.6f}")
            block.append(f"EMA200_last: {float(last.get('ema_200', last.get('EMA200', float('nan')))):.6f}")

            # MACD/Signal
            block.append(f"MACD_last: {float(last.get('macd', last.get('MACD', float('nan')))):.6f}")
            block.append(f"MACD_SIGNAL_last: {float(last.get('macd_signal', last.get('MACD_SIGNAL', float('nan')))):.6f}")

            # RSI / StochRSI середнє/останнє
            rsi_col = 'rsi' if 'rsi' in win.columns else ('RSI' if 'RSI' in win.columns else None)
            rsi_avg = float(win[rsi_col].mean()) if rsi_col else float('nan')
            block.append(f"RSI_avg_{ANALYZE_BARS}: {rsi_avg:.4f}")
            block.append(f"StochRSI_K_last: {float(last.get('stochrsi_k', last.get('STOCHRSI_K', float('nan')))):.4f}")
            block.append(f"StochRSI_D_last: {float(last.get('stochrsi_d', last.get('STOCHRSI_D', float('nan')))):.4f}")

            # Волатильність
            atr_col = 'atr_14' if 'atr_14' in win.columns else ('ATR' if 'ATR' in win.columns else None)
            atr_avg = float(win[atr_col].mean()) if atr_col else float('nan')
            pctb = float(last.get('pct_b', last.get('PCTB', float('nan'))))
            block.append(f"ATR_avg_{ANALYZE_BARS}: {atr_avg:.6f}")
            block.append(f"BB_pctB_last: {pctb:.4f}")

            # Обʼєм/сила
            if 'obv' in last or 'OBV' in last:
                block.append(f"OBV_last: {float(last.get('obv', last.get('OBV', 0.0))):.0f}")
            if 'mfi' in last or 'MFI' in last:
                block.append(f"MFI_last: {float(last.get('mfi', last.get('MFI', float('nan')))):.4f}")
            block.append(f"ADX_last: {float(last.get('adx', last.get('ADX', float('nan')))):.4f}")
            block.append(f"CCI_last: {float(last.get('cci', last.get('CCI', float('nan')))):.4f}")

            # Півоти (звичайні + Fib, якщо є)
            for key in ["pivot", "r1", "s1", "r2", "s2", "r3", "s3",
                        "fib_pivot", "fib_r1", "fib_s1", "fib_r2", "fib_s2", "fib_r3", "fib_s3"]:
                if key in last.index:
                    try:
                        block.append(f"{key.upper()}: {float(last.get(key, float('nan'))):.6f}")
                    except Exception:
                        pass

        market_block = "\n".join(block)

        # 3) Prompt для ШІ
        prompt = (
            f"{market_block}\n\n"
            "Decide if there is a trade now. Return STRICT JSON only (no prose) with keys exactly:\n"
            '{"direction":"LONG|SHORT|NEUTRAL","entry":number,"stop":number,"tp":number,'
            '"confidence":0..1,"holding_time_hours":number,"holding_time":"string","rationale":"2-3 sentences"}.\n'
            "Use trend (EMAs), momentum (MACD/RSI/StochRSI), volatility (ATR/BB), strength (ADX/CCI), volume (OBV/MFI), and Pivots."
        )
        raw = chat([{"role":"system","content":AI_SYSTEM},{"role":"user","content":prompt}])
        plan = _parse_ai_json(raw)

        # 4) Нормалізація + holding time
        direction = (plan.get("direction") or "").upper()
        entry = float(plan.get("entry", math.nan))
        stop = float(plan.get("stop", math.nan))
        tp   = float(plan.get("tp", math.nan))
        conf = float(plan.get("confidence", 0.0))

        # RR-фільтр: якщо < 1.5 — скіпаємо
        rr_text = _rr(direction, entry, stop, tp)
        try:
            if rr_text != "-" and float(rr_text) < 1.5:
                await update.message.reply_text("⚠️ Слабкий сигнал (RR < 1.5) — скіп.")
                return
        except Exception:
            pass  # якщо rr не розпарсився — не блокуємо, але покажемо як "-"

        # Обчислення holding time
        hold_source = "AI"
        hold_h = float(plan.get("holding_time_hours", 0.0))
        if hold_h <= 0.0:
            hold_source = "heuristic"
            # оцінимо швидкість за ATR% (беремо середнє по вікну)
            try:
                atr_col = 'atr_14' if 'atr_14' in win.columns else ('ATR' if 'ATR' in win.columns else None)
                atr_avg = float(win[atr_col].mean()) if atr_col else 0.0
                atr_pct = (atr_avg / float(price) * 100.0) if price and atr_avg == atr_avg else 0.0
            except Exception:
                atr_pct = 0.0
            base_hours = max(1, _tf_minutes(timeframe) / 15 * 2)
            if atr_pct >= 2.0:   speed_adj = 0.5
            elif atr_pct >= 1.0: speed_adj = 0.75
            elif atr_pct <= 0.2: speed_adj = 1.5
            else:                speed_adj = 1.0
            hold_h = float(int(round(base_hours * speed_adj)))

        if direction == "NEUTRAL":
            entry = stop = tp = float("nan")

        # 5) Вивід із TZ_NAME + час генерації
        tz = ZoneInfo(TZ_NAME)
        now_local = datetime.now(tz)
        hold_until_local = now_local + timedelta(hours=hold_h) if hold_h > 0 else None
        hold_line = (
            f"Recommended hold: {int(round(hold_h))} h ({hold_source})"
            + (f" (до {hold_until_local.strftime('%Y-%m-%d %H:%M %Z')} / {TZ_NAME})" if hold_until_local else "")
        )
        stamp_line = f"Generated: {now_local.strftime('%Y-%m-%d %H:%M %Z')}"

        reply = (
            f"🤖 AI план для {symbol} (TF={timeframe})\n"
            f"Модель: {_current_ai_model()}\n"
            f"{stamp_line}\n"
            f"Direction: {direction or '-'}   | Confidence: {conf:.2f}   | RR: {rr_text}\n"
            f"Entry: {_fmt_or_dash(entry)}    | SL: {_fmt_or_dash(stop)}   | TP: {_fmt_or_dash(tp)}\n"
            f"{hold_line}\n"
            "— пояснення —\n"
            f"{plan.get('rationale','—')}"
        )
        await update.message.reply_text(reply)

    except Exception as e:
        log.exception("/ai failed")
        await update.message.reply_text(f"⚠️ ai error: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Callback stub (на майбутнє)
# ──────────────────────────────────────────────────────────────────────────────
async def on_cb_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer("Soon™")
    except Exception:
        pass
