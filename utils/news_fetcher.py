# utils/news_fetcher.py
from __future__ import annotations
import html, re, time
from typing import List, Dict, Optional
from xml.etree import ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

# --- Набір джерел за замовчуванням (агрегація, коли немає query) ---
DEFAULT_FEEDS = [
    # Крипто
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
    "https://www.theblock.co/rss",
    "https://cryptoslate.com/feed/",
    "https://www.binance.com/en/blog/rss",
    # Фінансові
    "https://www.cnbc.com/id/10001147/device/rss/rss.html",       # CNBC Markets
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=BTC-USD", # Yahoo Finance BTC (може бути порожнім інколи)
    "https://www.investing.com/rss/news.rss",                     # Investing.com all news
    "https://www.investing.com/rss/commodities.rss",              # Commodities (золото)
    "https://feeds.reuters.com/reuters/businessNews",             # Reuters Business
]

# Google News RSS: безкоштовний спосіб робити пошук по темі (у т.ч. GOLD/USD/EUR)
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"

HTTP_TIMEOUT = 8.0
MAX_PER_FEED = 12

def _http_get(url: str, timeout: float = HTTP_TIMEOUT) -> Optional[str]:
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": "crypto-analyst-bot/1.0"}) as c:
            r = c.get(url, follow_redirects=True)
            if r.status_code == 200 and r.text:
                return r.text
    except Exception:
        pass
    return None

def _find_text(node: Optional[ET.Element], names: List[str]) -> str:
    if node is None:
        return ""
    for n in names:
        e = node.find(n)
        if e is not None and (e.text or "").strip():
            return e.text.strip()
    return ""

def _parse_date(s: str) -> float:
    try:
        dt = parsedate_to_datetime(s)
        return dt.timestamp()
    except Exception:
        return 0.0

def _parse_rss(xml_text: str) -> List[Dict]:
    out: List[Dict] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out

    # RSS 2.0
    for item in root.findall(".//item"):
        title = _find_text(item, ["title"])
        link  = _find_text(item, ["link"])
        pub   = _find_text(item, ["pubDate", "updated", "dc:date"])
        if title and link:
            out.append({"title": title, "link": link, "pub": pub, "ts": _parse_date(pub)})
        if len(out) >= MAX_PER_FEED:
            break

    # Atom (fallback)
    if not out:
        ns = "{http://www.w3.org/2005/Atom}"
        for entry in root.findall(f".//{ns}entry"):
            title = _find_text(entry, [f"{ns}title"])
            link_el = entry.find(f"{ns}link")
            link = link_el.get("href") if link_el is not None else ""
            pub = _find_text(entry, [f"{ns}updated", f"{ns}published"])
            if title and link:
                out.append({"title": title, "link": link, "pub": pub, "ts": _parse_date(pub)})
            if len(out) >= MAX_PER_FEED:
                break
    return out

def _md_esc(s: str) -> str:
    # Легкий Markdown-escape під Telegram
    return (
        s.replace("\\", "\\\\")
         .replace("_", "\\_")
         .replace("*", "\\*")
         .replace("[", "\\[")
         .replace("`", "\\`")
    )

def _short(s: str, n: int = 160) -> str:
    s = html.unescape((s or "").strip())
    s = re.sub(r"\s+", " ", s)
    return s if len(s) <= n else (s[: n - 1] + "…")

def _google_news_rss_query(q: str, lang: str) -> str:
    # lang: 'uk'/'en', регіон підбираємо відповідно
    if (lang or "").lower().startswith("uk"):
        return GOOGLE_NEWS_RSS.format(q=httpx.utils.quote(q), hl="uk", gl="UA", ceid="UA:uk")
    # дефолт ENG
    return GOOGLE_NEWS_RSS.format(q=httpx.utils.quote(q), hl="en", gl="US", ceid="US:en")

def get_latest_news(query: Optional[str] = None, max_items: int = 12, lang: str = "uk") -> List[Dict]:
    """
    Повертає список новин [{"title","title_md","link","source","ts"}]
    - Якщо query задано → шукає через Google News RSS (плюс пару явних фідів для тем GOLD/USD/EUR/crypto)
    - Якщо query немає → збирає стрічки з DEFAULT_FEEDS
    """
    items: List[Dict] = []

    if query:
        q = query.strip()
        # Google News
        url = _google_news_rss_query(q, lang)
        xml = _http_get(url)
        if xml:
            for it in _parse_rss(xml):
                items.append({
                    "title": it["title"],
                    "title_md": _md_esc(_short(it["title"])),
                    "link": it["link"],
                    "source": "GoogleNews",
                    "ts": it.get("ts", 0.0)
                })

        # Тематичні фіди, якщо шукаємо конкретні macro-теми
        topic_feeds = []
        q_low = q.lower()
        if any(k in q_low for k in ["gold", "xau", "золото"]):
            topic_feeds += ["https://www.investing.com/rss/commodities.rss"]
        if any(k in q_low for k in ["dollar", "usd", "долар"]):
            topic_feeds += ["https://www.reuters.com/markets/currencies/rss"]  # FX з Reuters
        if any(k in q_low for k in ["euro", "eur", "євро"]):
            topic_feeds += ["https://www.reuters.com/markets/currencies/rss"]
        if any(k in q_low for k in ["bitcoin", "btc", "ethereum", "eth", "crypto", "крипто"]):
            topic_feeds += [
                "https://www.coindesk.com/arc/outboundfeeds/rss/",
                "https://cointelegraph.com/rss",
                "https://decrypt.co/feed",
                "https://www.theblock.co/rss",
            ]

        for f in topic_feeds:
            xml = _http_get(f)
            if not xml:
                continue
            for it in _parse_rss(xml):
                items.append({
                    "title": it["title"],
                    "title_md": _md_esc(_short(it["title"])),
                    "link": it["link"],
                    "source": f,
                    "ts": it.get("ts", 0.0)
                })

    else:
        # Без запиту — агрегуємо стандартні фіди
        for f in DEFAULT_FEEDS:
            xml = _http_get(f)
            if not xml:
                continue
            for it in _parse_rss(xml):
                items.append({
                    "title": it["title"],
                    "title_md": _md_esc(_short(it["title"])),
                    "link": it["link"],
                    "source": f,
                    "ts": it.get("ts", 0.0)
                })

    # Сортуємо за часом і обрізаємо
    items.sort(key=lambda d: d.get("ts", 0.0), reverse=True)
    # Дедуп по title+link
    seen = set()
    uniq: List[Dict] = []
    for it in items:
        key = (it["title"], it["link"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
        if len(uniq) >= max_items:
            break
    return uniq
