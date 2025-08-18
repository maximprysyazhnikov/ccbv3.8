from __future__ import annotations
from typing import List
from core_config import CFG
from router.analyzer_router import pick_route
from utils.openrouter import chat_completion
from utils.formatting import save_report
from market_data.candles import get_ohlcv
from market_data.orderbook import get_orderbook_summary
from market_data.news import fetch_recent_news

PROMPT = """You are a crypto market analyst.
Given OHLCV candles, orderbook summary and recent news, produce a compact Markdown trade brief:

- Direction: LONG/SHORT/NO_TRADE
- Confidence: 0..100%
- Entry: number
- Stop: number
- Take: number
- Reasoning: up to 5 concise bullets (mix tech+orderbook+news)

If NO_TRADE, explain briefly. Keep it crisp.

Data:
Symbol: {symbol}
Timeframe: {tf}, Bars: {bars}
OHLCV: {ohlcv}
OrderBook: {orderbook}
News: {news}
"""

def run_full_analysis(symbol: str, timeframe: str, bars: int) -> List[str]:
    route = pick_route(symbol)
    if not route:
        return [f"❌ No route for {symbol} (no API key/model)"]

    ohlcv = get_ohlcv(symbol, timeframe, min(bars, CFG.analyze_limit))
    orderbook = get_orderbook_summary(symbol)
    news = fetch_recent_news(symbol, max_items=5)

    prompt = PROMPT.format(
        symbol=symbol, tf=timeframe, bars=len(ohlcv),
        ohlcv=ohlcv, orderbook=orderbook, news=news
    )

    text = chat_completion(
        endpoint=CFG.analyzer_endpoint,
        api_key=route.api_key,
        model=route.model,
        messages=[{"role": "user", "content": prompt}],
        timeout=30
    )

    lines = [line for line in text.splitlines()]
    save_report(symbol, lines)
    return lines
