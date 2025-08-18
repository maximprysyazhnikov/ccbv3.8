from __future__ import annotations
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict

SOURCES = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
    "https://cointelegraph.com/rss",
]

def fetch_recent_news(symbol: str, max_items: int = 5) -> List[Dict]:
    sym = symbol.replace("USDT", "").upper()
    out: List[Dict] = []
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            root = ET.fromstring(r.text)
            for item in root.iterfind(".//item"):
                title = (item.findtext("title") or "").strip()
                desc = (item.findtext("description") or "").strip()
                link = (item.findtext("link") or "").strip()
                text = f"{title} {desc}".upper()
                if sym in text or ("CRYPTO" in text and len(out) < max_items):
                    out.append({"title": title, "link": link})
                    if len(out) >= max_items:
                        return out
        except Exception:
            continue
    return out[:max_items]
