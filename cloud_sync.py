import sqlite3
import urllib.parse
import feedparser
from reach import build_public_site

DB_FILE = "rakshanet.db"
FEEDS = [
    ("PIB Official", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3"),
    ("The Hindu", "https://www.thehindu.com/news/national/feeder/default.rss"),
    ("Indian Express", "https://indianexpress.com/section/india/feed/"),
]
KEYWORDS = ["Indian Army", "LOC border", "LAC Ladakh", "DRDO missile", "PIB Fact Check"]

conn = sqlite3.connect(DB_FILE)
conn.execute("CREATE TABLE IF NOT EXISTS seen_urls (url TEXT UNIQUE, title TEXT, risk_hint TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS keywords (kw TEXT UNIQUE)")
conn.execute("CREATE TABLE IF NOT EXISTS narratives (id INTEGER PRIMARY KEY AUTOINCREMENT, claim TEXT UNIQUE, source_type TEXT, counter_fact TEXT, proof_url TEXT)")
for kw in KEYWORDS:
    conn.execute("INSERT OR IGNORE INTO keywords (kw) VALUES (?)", (kw,))
    feed = feedparser.parse(f"https://news.google.com/rss/search?q={urllib.parse.quote(kw)}&hl=en-IN&gl=IN&ceid=IN:en")
    for e in feed.entries[:2]:
        conn.execute("INSERT OR IGNORE INTO seen_urls (url, title, risk_hint) VALUES (?, ?, ?)", (e.link, e.title, "STANDARD"))
for name, url in FEEDS:
    for e in feedparser.parse(url).entries[:3]:
        conn.execute("INSERT OR IGNORE INTO seen_urls (url, title, risk_hint) VALUES (?, ?, ?)", (e.link, f"{e.title} - {name}", "STANDARD"))
conn.commit()
conn.close()
build_public_site()
print("[CloudSync] Website updated cleanly!")
