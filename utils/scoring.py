def score_signal(row) -> dict:
    score = 0
    max_score = 0

    # === ТРЕНД ===
    max_score += 3
    if row["CLOSE"] > row["EMA50"]:
        score += 1
    if row["EMA50"] > row["EMA200"]:
        score += 1
    if row["MACD"] > row["MACD_SIGNAL"]:
        score += 1

    # === МОМЕНТУМ ===
    max_score += 3
    if 45 <= row["RSI"] <= 65:
        score += 1
    if row.get("STOCHRSI_K", 0) > row.get("STOCHRSI_D", 0):
        score += 1
    if row.get("CCI", 0) > 0:
        score += 1

    # === ВОЛАТИЛЬНІСТЬ / ТРЕНДОВІСТЬ ===
    max_score += 2
    if row["ADX"] >= 20:
        score += 1
    if 0.4 <= row.get("PCTB", 0.5) <= 0.8:
        score += 1

    # === ОБ'ЄМ ===
    max_score += 2
    if row["MFI"] >= 50:
        score += 1
    if "OBV" in row and row["OBV"] == row["OBV"]:
        score += 1

    confidence = round(score / max_score, 2)
    if confidence >= 0.66:
        direction = "LONG"
    elif confidence <= 0.33:
        direction = "SHORT"
    else:
        direction = "NEUTRAL"

    return {
        "direction": direction,
        "confidence": confidence,
        "reasons": _reasons_from_row(row),
        "risk_box": {"atr": float(row["ATR"]), "volatility": _volatility_bucket(row)},
    }


def _reasons_from_row(r):
    out = []
    out.append(f"Close vs EMA50: {'above' if r['CLOSE']>r['EMA50'] else 'below'}")
    out.append(f"Trend EMA50>EMA200: {bool(r['EMA50']>r['EMA200'])}")
    out.append(f"MACD>Signal: {bool(r['MACD']>r['MACD_SIGNAL'])}")
    out.append(f"RSI={int(r['RSI'])}, StochRSI(K>D)={bool(r.get('STOCHRSI_K',0)>r.get('STOCHRSI_D',0))}")
    out.append(f"ADX={int(r['ADX'])}, CCI={int(r.get('CCI',0))}, %B={round(r.get('PCTB',0.5),2)}")
    out.append(f"MFI={int(r['MFI'])}, OBV(check)=ok")
    if "FIB_PIVOT" in r:
        out.append(_pivot_summary(r))
    return out


def _pivot_summary(r):
    def dist(a, b):
        return 100 * abs(a - b) / max(b, 1e-9)
    close = r["CLOSE"]
    parts = []
    for k in ["FIB_PIVOT", "FIB_R1", "FIB_S1", "FIB_R2", "FIB_S2", "FIB_R3", "FIB_S3"]:
        if k in r:
            parts.append(f"{k}~{dist(close, r[k]):.2f}%")
    return " | ".join(parts)


def _volatility_bucket(r):
    rel = r["ATR"] / max(r["CLOSE"], 1e-9)
    if rel > 0.015:
        return "high"
    if rel > 0.0075:
        return "medium"
    return "low"
