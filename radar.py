import urllib.parse
import feedparser

KEYWORDS = [
    "Indian Army",
    "LOC border",
    "LAC Ladakh",
    "DRDO missile",
    "PIB Fact Check",
]

print("[RakshaNet Radar] Starting scan...\n")

for kw in KEYWORDS:
    query = urllib.parse.quote(kw)
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    feed = feedparser.parse(url)
    print(f"[Keyword: {kw}] Found {len(feed.entries)} articles")
    for item in feed.entries[:2]:
        print(f"  - {item.title}")
        print(f"    URL: {item.link}")
    print()
    