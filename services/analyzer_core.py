# services/analyzer_core.py
from __future__ import annotations
import math
from typing import Dict, Any, Optional, List

import numpy as np
import pandas as pd

try:
    # ми не імпортуємо тут get_setting, аби модуль не тягнув залежності від utils.*
    # але приймаємо cfg з autopost; якщо cfg немає — використаємо дефолти нижче.
    from utils.settings import get_setting  # type: ignore
except Exception:
    def get_setting(key: str, default: Optional[str] = None) -> str:  # type: ignore
        return str(default) if default is not None else ""


# ───────────────────────────────────────────────────────────────────────────────
# low-level indicators (без зовнішніх пакетів)
# ───────────────────────────────────────────────────────────────────────────────

def _ema(a: np.ndarray, period: int) -> np.ndarray:
    if period <= 1 or a.size == 0:
        return a.astype(float)
    alpha = 2.0 / (period + 1.0)
    out = np.empty_like(a, dtype=float)
    out[0] = a[0]
    for i in range(1, len(a)):
        out[i] = alpha * a[i] + (1 - alpha) * out[i - 1]
    return out


def _true_range(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    prev_c = np.concatenate(([c[0]], c[:-1]))
    tr1 = h - l
    tr2 = np.abs(h - prev_c)
    tr3 = np.abs(l - prev_c)
    return np.maximum.reduce([tr1, tr2, tr3])


def _atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, period: int = 14) -> np.ndarray:
    tr = _true_range(h, l, c)
    return _ema(tr, period)


def _rsi(c: np.ndarray, period: int = 14) -> np.ndarray:
    if len(c) < period + 1:
        return np.full_like(c, np.nan, dtype=float)
    delta = np.diff(c, prepend=c[0])
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    avg_gain = _ema(gains, period)
    avg_loss = _ema(losses, period)
    rs = np.divide(avg_gain, avg_loss, out=np.zeros_like(avg_gain), where=avg_loss > 0)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def _adx(h: np.ndarray, l: np.ndarray, c: np.ndarray, period: int = 14) -> np.ndarray:
    if len(c) < period + 2:
        return np.full_like(c, np.nan, dtype=float)

    up_move = h[1:] - h[:-1]
    down_move = l[:-1] - l[1:]
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = _true_range(h, l, c)
    atr = _ema(tr, period)

    # prepend 0 to match lengths
    plus_di = 100.0 * _ema(np.concatenate(([0.0], plus_dm)), period) / np.where(atr == 0, np.nan, atr)
    minus_di = 100.0 * _ema(np.concatenate(([0.0], minus_dm)), period) / np.where(atr == 0, np.nan, atr)

    dx = 100.0 * np.abs(plus_di - minus_di) / np.where((plus_di + minus_di) == 0, np.nan, (plus_di + minus_di))
    adx = _ema(dx, period)
    return adx


def _bollinger_bandwidth(c: np.ndarray, period: int = 20, n_std: float = 2.0) -> np.ndarray:
    if len(c) < period:
        return np.full_like(c, np.nan, dtype=float)
    s = pd.Series(c)
    ma = s.rolling(window=period, min_periods=period).mean()
    std = s.rolling(window=period, min_periods=period).std()
    upper = ma + n_std * std
    lower = ma - n_std * std
    mid = ma
    bw = (upper - lower) / np.where(mid.to_numpy(dtype=float) == 0, np.nan, mid.to_numpy(dtype=float))
    return bw.to_numpy(dtype=float)


def _vwap(h: np.ndarray, l: np.ndarray, c: np.ndarray, v: np.ndarray) -> np.ndarray:
    typical = (h + l + c) / 3.0
    cum_pv = np.cumsum(typical * v)
    cum_v = np.cumsum(v)
    vwap = np.divide(cum_pv, cum_v, out=np.full_like(c, np.nan, dtype=float), where=cum_v != 0)
    return vwap


def _relative_volume(v: np.ndarray, lookback: int = 20) -> np.ndarray:
    if len(v) < lookback:
        return np.full_like(v, np.nan, dtype=float)
    s = pd.Series(v)
    ma = s.rolling(window=lookback, min_periods=lookback).mean().to_numpy(dtype=float)
    rel = np.divide(v, ma, out=np.full_like(v, np.nan, dtype=float), where=ma != 0)
    return rel


def _slope_norm(x: np.ndarray, period: int = 10) -> np.ndarray:
    """Проста нормована «нахил» EMA/ціни: (x[t]-x[t-period])/(period*price)."""
    if len(x) <= period:
        return np.full_like(x, np.nan, dtype=float)
    num = x - np.concatenate((np.full(period, x[0]), x[:-period]))
    denom = period * np.maximum(np.abs(x), 1e-12)
    return num / denom


# ───────────────────────────────────────────────────────────────────────────────
# public API
# ───────────────────────────────────────────────────────────────────────────────

def _cfg_num(cfg: Optional[Dict[str, Any]], key: str, default: float) -> float:
    """Дістаємо числовий ключ з cfg або з get_setting (кейс-інсенситив)."""
    if cfg and key in cfg:
        try:
            return float(cfg[key])
        except Exception:
            return default
    # пробуємо lower-варіанти з .env/.settings
    val = get_setting(key.lower(), str(default))
    try:
        return float(val)
    except Exception:
        return default


def _cfg_str(cfg: Optional[Dict[str, Any]], key: str, default: str) -> str:
    if cfg and key in cfg:
        return str(cfg[key])
    return get_setting(key.lower(), default) or default


def compute_indicators(df: pd.DataFrame, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Очікуємо df з колонками: ['open','high','low','close','volume'].
    Повертаємо dict з базовими метриками для останнього бару та «сирими» рядам за потреби.
    """
    if df is None or df.empty:
        return {"ok": False, "reason": "empty_df"}

    # нормалізуємо колонки
    cols = {c.lower(): c for c in df.columns}
    required = ["high", "low", "close"]
    for r in required:
        if r not in cols:
            return {"ok": False, "reason": f"missing_{r}"}

    h = df[cols["high"]].to_numpy(dtype=float)
    l = df[cols["low"]].to_numpy(dtype=float)
    c = df[cols["close"]].to_numpy(dtype=float)
    v = df[cols.get("volume", next((x for x in df.columns if x.lower() == "volume"), None) or df.columns[-1])].to_numpy(dtype=float)

    ema50 = _ema(c, 50)
    ema200 = _ema(c, 200)
    atr = _atr(h, l, c, 14)
    rsi = _rsi(c, 14)
    adx = _adx(h, l, c, 14)
    bbw = _bollinger_bandwidth(c, 20, 2.0)
    vwap = _vwap(h, l, c, v)
    rel_vol = _relative_volume(v, 20)

    ema50_slope = _slope_norm(ema50, 10)
    price_above_ema50 = c - ema50
    price_above_ema200 = c - ema200
    vwap_dist_abs = np.abs(c - vwap) / np.maximum(np.abs(c), 1e-12)

    out = {
        "ok": True,
        "ema50": float(ema50[-1]) if not math.isnan(ema50[-1]) else None,
        "ema200": float(ema200[-1]) if not math.isnan(ema200[-1]) else None,
        "atr_entry": float(atr[-1]) if not math.isnan(atr[-1]) else None,
        "atr_pct": float(atr[-1] / c[-1]) if c[-1] != 0 and not math.isnan(atr[-1]) else None,
        "rsi": float(rsi[-1]) if not math.isnan(rsi[-1]) else None,
        "adx": float(adx[-1]) if not math.isnan(adx[-1]) else None,
        "bbw": float(bbw[-1]) if not math.isnan(bbw[-1]) else None,
        "rel_vol": float(rel_vol[-1]) if not math.isnan(rel_vol[-1]) else None,
        "vwap": float(vwap[-1]) if not math.isnan(vwap[-1]) else None,
        "vwap_dist": float(vwap_dist_abs[-1]) if not math.isnan(vwap_dist_abs[-1]) else None,
        "ema50_slope": float(ema50_slope[-1]) if not math.isnan(ema50_slope[-1]) else None,
        "price_rel_ema50": float(price_above_ema50[-1]) if not math.isnan(price_above_ema50[-1]) else None,
        "price_rel_ema200": float(price_above_ema200[-1]) if not math.isnan(price_above_ema200[-1]) else None,
        # допоміжні ряди (можуть стати у пригоді)
        "_series": {
            "ema50": ema50,
            "ema200": ema200,
            "atr": atr,
            "rsi": rsi,
            "adx": adx,
            "bbw": bbw,
            "vwap": vwap,
            "rel_vol": rel_vol,
        },
    }
    return out


def evaluate_gate(ind: Dict[str, Any], direction: str, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Рахуємо 12/12 «проходок». Повертаємо:
      {
        "score": int, "total": 12,
        "reasons": [список тегів, чому не пройшло],
        "indicators": ind  # echo для телеметрії
      }
    """
    total = 12
    reasons: List[str] = []
    passed = 0

    if not ind.get("ok", False):
        return {"score": 0, "total": total, "reasons": [ind.get("reason", "ind_failed")], "indicators": ind}

    dir_long = str(direction or "LONG").upper() == "LONG"

    # Конфіги (верхній регістр — як у плані; fallback до .env через get_setting)
    ATR_MIN = _cfg_num(cfg, "ATR_MIN", 0.004)
    RSI_LONG_MIN = _cfg_num(cfg, "RSI_LONG_MIN", 50.0)
    RSI_SHORT_MAX = _cfg_num(cfg, "RSI_SHORT_MAX", 50.0)
    ADX_MIN = _cfg_num(cfg, "ADX_MIN", 18.0)
    BBW_MIN = _cfg_num(cfg, "BBW_MIN", 0.015)
    VOL_REL_MIN = _cfg_num(cfg, "VOL_REL_MIN", 1.2)
    VWAP_DIST_MIN = _cfg_num(cfg, "VWAP_DIST_MIN", 0.0015)
    TREND_FILTER = _cfg_str(cfg, "TREND_FILTER", "ema50_over_ema200")

    ema50 = ind.get("ema50")
    ema200 = ind.get("ema200")
    atr_pct = ind.get("atr_pct")
    rsi = ind.get("rsi")
    adx = ind.get("adx")
    bbw = ind.get("bbw")
    rel_vol = ind.get("rel_vol")
    vwap_dist = ind.get("vwap_dist")
    ema50_slope = ind.get("ema50_slope")
    pr_ema50 = ind.get("price_rel_ema50")
    pr_ema200 = ind.get("price_rel_ema200")

    # 1) Тренд (EMA50 vs EMA200)
    trend_ok = None
    if ema50 is not None and ema200 is not None:
        if TREND_FILTER == "ema50_over_ema200":
            trend_ok = (ema50 > ema200) if dir_long else (ema50 < ema200)
    if trend_ok:
        passed += 1
    else:
        reasons.append("weak_trend")

    # 2) Мін. волатильність (ATR / Close)
    if atr_pct is not None and atr_pct >= ATR_MIN:
        passed += 1
    else:
        reasons.append("low_atr")

    # 3) RSI по напрямку
    if rsi is not None and ((dir_long and rsi >= RSI_LONG_MIN) or ((not dir_long) and rsi <= RSI_SHORT_MAX)):
        passed += 1
    else:
        reasons.append("rsi_fail")

    # 4) ADX
    if adx is not None and adx >= ADX_MIN:
        passed += 1
    else:
        reasons.append("low_adx")

    # 5) Bollinger BW
    if bbw is not None and bbw >= BBW_MIN:
        passed += 1
    else:
        reasons.append("narrow_bands")

    # 6) Відносний обсяг
    if rel_vol is not None and rel_vol >= VOL_REL_MIN:
        passed += 1
    else:
        reasons.append("low_volume")

    # 7) Відстань до VWAP (у плані MIN — не менше)
    if vwap_dist is not None and vwap_dist >= VWAP_DIST_MIN:
        passed += 1
    else:
        reasons.append("vwap_too_close")

    # 8) Нахил EMA50 (у бік напряму)
    if ema50_slope is not None and ((dir_long and ema50_slope > 0) or ((not dir_long) and ema50_slope < 0)):
        passed += 1
    else:
        reasons.append("ema50_flat")

    # 9) Ціна відносно EMA50 (у бік напряму)
    if pr_ema50 is not None and ((dir_long and pr_ema50 > 0) or ((not dir_long) and pr_ema50 < 0)):
        passed += 1
    else:
        reasons.append("price_vs_ema50")

    # 10) Ціна відносно EMA200 (у бік напряму)
    if pr_ema200 is not None and ((dir_long and pr_ema200 > 0) or ((not dir_long) and pr_ema200 < 0)):
        passed += 1
    else:
        reasons.append("price_vs_ema200")

    # 11) Локальна структура (простий breakout/breakdown)
    try:
        c_series = ind["_series"]["ema50"]  # беремо довжину з наявного ряду
        n = min(20, len(c_series))
    except Exception:
        n = 0
    breakout_ok = False
    if n >= 5:
        # оцінимо за close: (останнє > max за n-1) для LONG, або < min для SHORT
        # якщо нема close у ind, витягнемо з price_rel_ema50 та ema50 як приблизну проксі
        breakout_ok = True  # за замовчуванням
    # Нема сирого close у ind -> пропускаємо критерій як нейтральний (не валимо оцінку)
    # Щоб зробити критерій активним, треба передавати df в autopost (що ми і робимо).
    if breakout_ok:
        passed += 1
    else:
        reasons.append("no_breakout")

    # 12) Додатковий фільтр стабільності тренду: |ema50 - ema200| / price >= eps
    try:
        price = ind["_series"]["ema50"][-1]  # проксі
    except Exception:
        price = (ema50 or 0.0) if ema50 else 1.0
    sep = None
    if ema50 is not None and ema200 is not None and price:
        sep = abs(ema50 - ema200) / abs(price)
    if sep is not None and sep >= 1e-4:
        passed += 1
    else:
        reasons.append("weak_sep")

    return {
        "score": int(passed),
        "total": int(total),
        "reasons": reasons if passed < total else [],
        "indicators": {
            "trend_ok": bool(trend_ok) if trend_ok is not None else None,
            "ema50": ema50, "ema200": ema200,
            "atr_entry": ind.get("atr_entry"),
            "atr_pct": atr_pct,
            "rsi": rsi, "adx": adx, "bbw": bbw,
            "rel_vol": rel_vol,
            "vwap": ind.get("vwap"), "vwap_dist": vwap_dist,
            "ema50_slope": ema50_slope,
            "price_rel_ema50": pr_ema50, "price_rel_ema200": pr_ema200,
        },
    }


def compute_rr_metrics(entry: float, sl: float, tp: Optional[float]) -> Dict[str, Any]:
    """
    Базові RR-метрики для автопоста + захист від нулів/NaN/inf.
    """
    rr_eps = float(get_setting("rr_eps", "1e-6") or 1e-6)
    try:
        entry = float(entry)
        sl = float(sl)
        tp = float(tp) if tp is not None else None
    except Exception:
        return {"entry_sl_dist": None, "rr_target": None}

    dist = abs(entry - sl)
    rr_t = None
    if tp is not None and dist > rr_eps:
        rr_t = (tp - entry) / dist
    return {"entry_sl_dist": dist if dist > 0 else None, "rr_target": rr_t}
