import pandas as pd
from market_data.klines import get_klines
from utils.indicators import compute_indicators
from utils.news import get_latest_news
from core_config import ANALYZE_BARS, DEFAULT_TIMEFRAME, COMPACT_MODE


def run_full_analysis(symbol: str, timeframe: str = None) -> list[str]:
    """
    Повний аналіз ринку: тягнемо дані з Binance, рахуємо індикатори, додаємо новини,
    формуємо Markdown-звіт (у компактному або розширеному вигляді).
    """
    tf = timeframe or DEFAULT_TIMEFRAME

    # 1. Отримати дані по свічках
    df = get_klines(symbol, interval=tf, limit=ANALYZE_BARS)
    if df is None or df.empty:
        return [f"⚠️ Немає даних по {symbol} ({tf})"]

    # 2. Рахуємо індикатори
    df = compute_indicators(df)

    # 3. Новини (якщо є)
    news_items = get_latest_news(symbol)

    # 4. Формування звіту
    if COMPACT_MODE:
        # Відправляємо GPT тільки таблицю з індикаторами
        md_report = _make_compact_report(symbol, tf, df, news_items)
    else:
        # Повний звіт з секціями
        md_report = _make_full_report(symbol, tf, df, news_items)

    return md_report


def _make_compact_report(symbol: str, tf: str, df: pd.DataFrame, news_items: list) -> list[str]:
    """Компактний режим: тільки таблиця індикаторів + короткі новини"""
    table = df.tail(ANALYZE_BARS).to_markdown(index=False)

    lines = [f"### 📊 Technical Indicators for {symbol} (TF={tf}, last {ANALYZE_BARS} bars)"]
    lines.append(table)

    if news_items:
        lines.append("\n### 📰 Latest News")
        for n in news_items:
            lines.append(f"- [{n['title']}]({n['link']})")

    return lines


def _make_full_report(symbol: str, tf: str, df: pd.DataFrame, news_items: list) -> list[str]:
    """Розширений режим: Markdown з секціями"""
    last_row = df.iloc[-1].to_dict()

    lines = [
        f"# 📈 Market Analysis Report",
        f"**Symbol:** {symbol}",
        f"**Timeframe:** {tf}",
        f"**Bars analyzed:** {ANALYZE_BARS}",
        "",
        "## 🔹 Latest Candle",
        f"- Close: {last_row.get('close')}",
        f"- Volume: {last_row.get('volume')}",
        "",
        "## 🔹 Indicators Table (last bars)",
        df.tail(ANALYZE_BARS).to_markdown(index=False),
    ]

    if news_items:
        lines.append("\n## 📰 Latest News")
        for n in news_items:
            lines.append(f"- [{n['title']}]({n['link']})")

    lines.append("\n---\n🤖 *Generated automatically by AI Analyst*")

    return lines
