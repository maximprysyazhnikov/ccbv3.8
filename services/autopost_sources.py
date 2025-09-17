# services/autopost_sources.py
from __future__ import annotations
import json
import os
from typing import Any, Dict, List
from urllib.request import urlopen

import math
import pandas as pd
from utils.settings import get_setting

BINANCE_URL = "https://api.binance.com/api/v3/klines"

# ── helpers: settings/env ─────────────────────────────────────────────────────
def _gs(key: str, default: str = "") -> str:
    """get_setting → ENV (UPPER) → default"""
    v = get_setting(key, None)
    if v in (None, ""):
        v = os.getenv(key.upper(), "")
    return v if v not in (None, "") else default

def _gs_float(key: str, default: float) -> float:
    try:
        return float(_gs(key, str(default)) or default)
    except Exception:
        return default

def _gs_int(key: str, default: int) -> int:
    try:
        return int(float(_gs(key, str(default)) or default))
    except Exception:
        return default

# ── data ──────────────────────────────────────────────────────────────────────
def _fetch_klines(symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
    url = f"{BINANCE_URL}?symbol={symbol}&interval={interval}&limit={limit}"
    with urlopen(url) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    df = pd.DataFrame(
        data,
        columns=[
            "open_time","open","high","low","close","volume",
            "close_time","qav","num_trades","taker_base_vol","taker_quote_vol","ignore"
        ],
    )
    df = df[["open_time","open","high","low","close","volume"]].copy()
    df["ts"] = (df["open_time"] // 1000).astype(int)
    for col in ["open","high","low","close","volume"]:
        df[col] = df[col].astype(float)
    return df[["ts","open","high","low","close","volume"]]

# ── indicators (без сторонніх залежностей) ───────────────────────────────────
def _ema(series: pd.Series, span: int) -> float:
    return float(series.ewm(span=span, adjust=False).mean().iloc[-1])

def _rsi14(close: pd.Series) -> float:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = (-delta).clip(lower=0.0)
    gain = up.ewm(alpha=1/14, adjust=False).mean()
    loss = down.ewm(alpha=1/14, adjust=False).mean()
    rs = gain / (loss + 1e-12)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])

def _atr14(high: pd.Series, low: pd.Series, close: pd.Series) -> float:
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False).mean()
    return float(atr.iloc[-1])

def _vwap20(high: pd.Series, low: pd.Series, close: pd.Series, vol: pd.Series) -> float:
    tp = (high + low + close) / 3.0
    vp = (tp * vol).rolling(20).sum()
    vv = vol.rolling(20).sum()
    vwap = vp / vv.replace(0.0, pd.NA)
    return float(vwap.iloc[-1])

def _bollinger(close: pd.Series, window: int = 20, k: float = 2.0) -> tuple[float, float, float]:
    sma = close.rolling(window).mean()
    std = close.rolling(window).std(ddof=0)
    upper = sma + k * std
    lower = sma - k * std
    return float(lower.iloc[-1]), float(sma.iloc[-1]), float(upper.iloc[-1])

def _pivots_prev_candle(high: pd.Series, low: pd.Series, close: pd.Series):
    """Classic pivots з ПОПЕРЕДНЬОЇ свічки ([-2])"""
    if len(high) < 2:
        return None
    H = float(high.iloc[-2]); L = float(low.iloc[-2]); C = float(close.iloc[-2])
    P = (H + L + C) / 3.0
    R1 = 2*P - L; S1 = 2*P - H
    R2 = P + (H - L); S2 = P - (H - L)
    R3 = H + 2*(P - L); S3 = L - 2*(H - P)
    return dict(P=P, R1=R1, R2=R2, R3=R3, S1=S1, S2=S2, S3=S3)

def _swing(high: pd.Series, low: pd.Series, lookback: int = 20) -> tuple[float, float]:
    """Максимум/мінімум за lookback (включно з поточною)."""
    lb = min(len(high), lookback)
    h = float(high.tail(lb).max())
    l = float(low.tail(lb).min())
    return h, l

# ── dynamic TP ────────────────────────────────────────────────────────────────
def _rr(entry: float, sl: float, tp: float, direction: str) -> float:
    dist = abs(entry - sl) or 1e-12
    return ((tp - entry) / dist) if direction == "LONG" else ((entry - tp) / dist)

def _pick_tp(entry: float, sl: float, direction: str,
             pivots: Dict[str,float] | None,
             bb: tuple[float,float,float] | None,
             swing_hi: float, swing_lo: float,
             min_rr: float, rr_max: float) -> tuple[float, float, str]:
    """
    Обирає TP з кандидатів: Pivots, Bollinger, Swing.
    Повертає (tp, rr, source).
    """
    dist = abs(entry - sl) or 1e-12
    cands: List[tuple[str,float]] = []

    if direction == "LONG":
        # порядок: R1, BBupper, swingH, R2, R3
        if pivots: cands.append(("pivot:R1", pivots["R1"]))
        if bb:     cands.append(("bb:upper", bb[2]))
        cands.append(("swing:high", swing_hi))
        if pivots: cands.append(("pivot:R2", pivots["R2"])); cands.append(("pivot:R3", pivots["R3"]))
        # валідні тільки ціни > entry
        cands = [(n, p) for (n,p) in cands if p > entry]
    else:
        # порядок: S1, BBlow, swingL, S2, S3
        if pivots: cands.append(("pivot:S1", pivots["S1"]))
        if bb:     cands.append(("bb:lower", bb[0]))
        cands.append(("swing:low", swing_lo))
        if pivots: cands.append(("pivot:S2", pivots["S2"])); cands.append(("pivot:S3", pivots["S3"]))
        cands = [(n, p) for (n,p) in cands if p < entry]

    # Оцінюємо RR для кожного
    scored: List[tuple[str,float,float]] = []
    for name, price in cands:
        rr = _rr(entry, sl, price, direction)
        if rr > 0:
            scored.append((name, price, rr))

    # шукаємо перший, що >= min_rr (консервативно — ближчий)
    for name, price, rr in scored:
        if rr >= min_rr and rr <= rr_max:
            return price, rr, name

    # якщо жоден не досяг min_rr → беремо найбільший RR (але не більше rr_max),
    # або fallback на рівно min_rr*dist від entry
    if scored:
        name, price, rr = max(scored, key=lambda t: t[2])
        if rr > rr_max:  # притиснемо до rr_max уздовж напряму
            if direction == "LONG":
                price = entry + rr_max * dist
            else:
                price = entry - rr_max * dist
            rr = rr_max
        return price, rr, name

    # fallback — геометричний RR=min_rr
    if direction == "LONG":
        tp = entry + min_rr * dist
    else:
        tp = entry - min_rr * dist
    return tp, min_rr, "fallback:min_rr"

# ── main ─────────────────────────────────────────────────────────────────────
def collect_autopost_candidates() -> List[Dict[str, Any]]:
    symbols_raw = _gs("monitored_symbols", "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,LTCUSDT,XLMUSDT,ADAUSDT")
    timeframe   = _gs("analyze_timeframe", "1h")
    bars        = _gs_int("analyze_bars", 200)

    # ризик/TP параметри
    min_rr      = _gs_float("autopost_min_rr", _gs_float("min_entry_rr", 1.5))
    rr_max      = _gs_float("autopost_rr_max", 4.0)
    stop_mult   = _gs_float("stop_atr_mult", 1.5)

    # гейт-пороги (у відсотках до ціни)
    atr_min_pct   = _gs_float("autopost_min_atr_pct", 0.0)
    vwap_min_pct  = _gs_float("vwap_dist_min", 0.0)
    rsi_long_min  = _gs_float("rsi_long_min", 50.0)
    rsi_short_max = _gs_float("rsi_short_max", 50.0)
    swing_lb      = _gs_int("swing_lookback", 20)

    out: List[Dict[str, Any]] = []
    symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
    for sym in symbols:
        try:
            df = _fetch_klines(sym, timeframe, limit=bars)
            if len(df) < 60:
                continue

            c = df["close"]; h = df["high"]; l = df["low"]; v = df["volume"]
            last = float(c.iloc[-1])

            ema50  = _ema(c, 50)
            ema200 = _ema(c, 200) if len(c) >= 200 else _ema(c, max(50, len(c)//2))
            atr    = _atr14(h, l, c)
            rsi    = _rsi14(c)
            vwap   = _vwap20(h, l, c, v)

            direction = "LONG" if ema50 >= ema200 else "SHORT"

            # SL від ATR
            dist = stop_mult * atr
            if dist <= 0:
                continue
            sl = (last - dist) if direction == "LONG" else (last + dist)

            # Кандидати таргетів
            piv = _pivots_prev_candle(h, l, c)
            bb  = _bollinger(c, 20, 2.0) if len(c) >= 20 else None
            swing_hi, swing_lo = _swing(h, l, swing_lb)

            tp, rr_dyn, src = _pick_tp(
                entry=last, sl=sl, direction=direction,
                pivots=piv, bb=bb, swing_hi=swing_hi, swing_lo=swing_lo,
                min_rr=min_rr, rr_max=rr_max
            )

            # Гейт (у відсотках)
            atr_pct  = (atr / last * 100.0) if last else 0.0
            vwap_pct = (abs(last - vwap) / last * 100.0) if last else 0.0
            trend_ok = (direction == "LONG" and ema50 >= ema200) or (direction == "SHORT" and ema50 < ema200)
            atr_ok   = (atr_pct >= atr_min_pct) if atr_min_pct > 0 else True
            vwap_ok  = (vwap_pct >= vwap_min_pct) if vwap_min_pct > 0 else True
            rsi_ok   = (rsi >= rsi_long_min) if direction == "LONG" else (rsi <= rsi_short_max)

            passed = 0; total = 4
            reasons: List[str] = []
            reasons.append(("+TREND"  if trend_ok else "-TREND")  + f" ema50{'>=' if ema50>=ema200 else '<'}ema200")
            if trend_ok: passed += 1
            reasons.append(("+ATR"    if atr_ok else "-ATR")      + f" {atr_pct:.2f}%")
            if atr_ok: passed += 1
            reasons.append(("+VWAPΔ"  if vwap_ok else "-VWAPΔ")   + f" {vwap_pct:.2f}%")
            if vwap_ok: passed += 1
            if direction == "LONG":
                reasons.append(("+RSI14" if rsi_ok else "-RSI14") + f" {rsi:.1f}>={int(rsi_long_min)}")
            else:
                reasons.append(("+RSI14" if rsi_ok else "-RSI14") + f" {rsi:.1f}<={int(rsi_short_max)}")
            if rsi_ok: passed += 1

            out.append({
                "symbol": sym,
                "timeframe": timeframe,
                "direction": direction,
                "entry": last,
                "sl": float(sl),
                "tp": float(tp),
                "ind": {
                    # У цінах! (_ind_summary сам рахує відсотки)
                    "ema50": float(ema50),
                    "ema200": float(ema200),
                    "atr": float(atr),
                    "rsi14": float(rsi),
                    "vwap": float(vwap),
                },
                "gate_score": passed,
                "gate_total": total,
                "reasons": reasons + [f"TP_by={src} RR={rr_dyn:.2f}"],
                "df": df,  # для preset3 панелі
            })
        except Exception:
            continue

    return out
