import re
import sqlite3
import urllib.parse
import urllib.request
import feedparser
from reach import build_public_site

DB_FILE = "rakshanet.db"
FEEDS = [
    ("PIB Official", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3"),
    ("The Hindu", "https://www.thehindu.com/news/national/feeder/default.rss"),
    ("Indian Express", "https://indianexpress.com/section/india/feed/"),
    ("DD News YouTube", "https://www.youtube.com/feeds/videos.xml?channel_id=UCKwucPzHZ7zCUIf7If-Wo1g"),
    ("PIB FactCheck", "https://news.google.com/rss/search?q=site:factcheck.pib.gov.in&hl=en-IN&gl=IN&ceid=IN:en"),
    ("BOOMLive IFCN", "https://news.google.com/rss/search?q=site:boomlive.in+fact+check&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Factly IFCN", "https://news.google.com/rss/search?q=site:factly.in+fact+check&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Vishvas IFCN", "https://news.google.com/rss/search?q=site:vishvasnews.com+fact+check&hl=en-IN&gl=IN&ceid=IN:en"),
]
KEYWORDS = [
    "Indian Army",
    "LOC border",
    "LAC Ladakh",
    "DRDO missile",
    "PIB Fact Check",
    "India fake video",
    "India GDP World Bank",
    "RBI UPI scam",
    "cyber honeytrap India",
]
PLATFORMS = [
    ("X", "site:x.com (India OR \"Indian Army\" OR fake OR misleading)"),
    ("Instagram", "site:instagram.com (India OR \"Look at India\" OR fake)"),
    ("YouTube", "site:youtube.com (\"India fake\" OR \"Indian Army\" OR \"anti-India\")"),
]
TG_CHANNELS = ["PIBFactCheck"]

conn = sqlite3.connect(DB_FILE)
conn.execute("CREATE TABLE IF NOT EXISTS seen_urls (url TEXT UNIQUE, title TEXT, risk_hint TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS keywords (kw TEXT UNIQUE)")
conn.execute("CREATE TABLE IF NOT EXISTS narratives (id INTEGER PRIMARY KEY AUTOINCREMENT, claim TEXT UNIQUE, source_type TEXT, counter_fact TEXT, proof_url TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS watchlist (id INTEGER PRIMARY KEY AUTOINCREMENT, claim TEXT UNIQUE, source_url TEXT, checks INTEGER DEFAULT 0, status TEXT DEFAULT 'PENDING', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")

for kw in KEYWORDS:
    try:
        conn.execute("INSERT OR IGNORE INTO keywords (kw) VALUES (?)", (kw,))
        feed = feedparser.parse(f"https://news.google.com/rss/search?q={urllib.parse.quote(kw)}&hl=en-IN&gl=IN&ceid=IN:en")
        for e in feed.entries[:2]:
            conn.execute("INSERT OR IGNORE INTO seen_urls (url, title, risk_hint) VALUES (?, ?, ?)", (e.link, e.title, "STANDARD"))
    except Exception:
        pass

for name, url in FEEDS:
    try:
        for e in feedparser.parse(url).entries[:3]:
            conn.execute("INSERT OR IGNORE INTO seen_urls (url, title, risk_hint) VALUES (?, ?, ?)", (e.link, f"{e.title} - {name}", "STANDARD"))
    except Exception:
        pass

platform_hits = []
for pname, pq in PLATFORMS:
    try:
        feed = feedparser.parse(f"https://news.google.com/rss/search?q={urllib.parse.quote(pq)}&hl=en-IN&gl=IN&ceid=IN:en")
        for e in feed.entries[:2]:
            words = set(re.findall(r"[a-zA-Z]{4,}", e.title.lower())) - {"india", "indian", "video", "fake", "news", "https", "watch"}
            platform_hits.append((pname, e.link, e.title, words))
    except Exception:
        pass

for ch in TG_CHANNELS:
    try:
        req = urllib.request.Request(f"https://t.me/s/{ch}", headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", "ignore")
        msgs = re.findall(r'tgme_widget_message_text[^>]*>(.*?)</div>', html, re.S)
        for m in msgs[-3:]:
            clean = re.sub(r"<[^>]+>", " ", m).strip()
            clean = " ".join(clean.split())[:140]
            if len(clean) > 20:
                words = set(re.findall(r"[a-zA-Z]{4,}", clean.lower())) - {"india", "indian", "video", "fake", "fact", "check"}
                platform_hits.append(("Telegram", f"https://t.me/s/{ch}", f"{clean} - Telegram/{ch}", words))
    except Exception:
        pass
for i, (pname, link, title, words) in enumerate(platform_hits):
    other_platforms = {op for j, (op, _, _, ow) in enumerate(platform_hits) if j != i and op != pname and len(words & ow) >= 2}
    hint = "HIGH ALERT" if other_platforms else pname
    conn.execute("INSERT OR IGNORE INTO seen_urls (url, title, risk_hint) VALUES (?, ?, ?)", (link, f"[{pname}] {title}", hint))

conn.commit()
conn.close()
build_public_site()
print("[CloudSync] Cross-Platform Radar + IFCN updated cleanly!")


# Auto-inject RakshaNet Live Verifier Widget
try:
    import os as _ow, re as _rw
    import os as _os, re as _re
    if _os.path.exists("docs/rn_widget.html"):
        _rw = open("docs/rn_widget.html", encoding="utf-8").read()
        html = _re.sub(r"\n?<!-- RN_WIDGET_START -->.*?<!-- RN_WIDGET_END -->\n?", "", html, flags=_re.S)
        _rm = _re.search(r'<div[^>]*>[^<]*Home\s*(?:›|&rsaquo;|&#8250;|&gt;|>)[^<]*India', html, _re.I)
        _rb = "\n<!-- RN_WIDGET_START -->\n" + _rw + "\n<!-- RN_WIDGET_END -->\n"
        html = (html[:_rm.start()] + _rb + html[_rm.start():]) if _rm else html.replace("<body>", "<body>" + _rb, 1)
except Exception:
    pass
