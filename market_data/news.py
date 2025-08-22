# market_data/news.py
from __future__ import annotations
import aiohttp
import asyncio
from typing import List, Dict
from datetime import datetime
import xml.etree.ElementTree as ET

SOURCES = [
    ("CoinDesk",     "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph","https://cointelegraph.com/rss"),
]

def _parse_rss(xml_text: str, source: str) -> List[Dict]:
    items: List[Dict] = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link") or "").strip()
            pub   = (item.findtext("pubDate") or "").strip()
            items.append({
                "title": title,
                "url": link,
                "source": source,
                "published_at": pub
            })
    except Exception:
        pass
    return items

async def _fetch(session: aiohttp.ClientSession, name: str, url: str) -> List[Dict]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            r.raise_for_status()
            txt = await r.text()
            return _parse_rss(txt, name)
    except Exception:
        return []

async def search_news(query: str = "crypto", lang: str = "en") -> List[Dict]:
    """
    Простий агрегатор RSS (CoinDesk / CoinTelegraph). Фільтрує за підрядком у title.
    """
    out: List[Dict] = []
    async with aiohttp.ClientSession() as s:
        tasks = [_fetch(s, name, url) for name, url in SOURCES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, list):
                out.extend(res)
    q = (query or "").strip().lower()
    if q:
        out = [it for it in out if q in it["title"].lower()]
    # відсортуємо за наявністю pubdate (не у всіх є парсинг дати)
    return out[:30]
