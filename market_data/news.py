# market_data/news.py
import requests
import xml.etree.ElementTree as ET

FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
    "https://cointelegraph.com/rss",
]

def _fetch(url: str) -> list[dict]:
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if title and link:
                items.append({"title": title, "link": link})
        return items
    except Exception:
        return []

def get_latest_news(limit: int = 8) -> list[dict]:
    out: list[dict] = []
    for url in FEEDS:
        out.extend(_fetch(url))
        if len(out) >= limit:
            break
    return out[:limit]
