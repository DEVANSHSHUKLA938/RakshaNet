import os
import re
import sqlite3
import time
import urllib.parse
import feedparser
import requests
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_FILE = "rakshanet.db"

SEED_KEYWORDS = [
    "Indian Army", "LOC border", "LAC Ladakh", "DRDO missile", "PIB Fact Check",
    "BSF", "IAF", "Indian Navy", "Agniveer", "Siachen", "Kashmir", "Ceasefire",
    "Army Bharti", "CSD Canteen", "Bridge Collapse", "Riot", "Cyber Fraud APK",
]


def init_snowball_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("CREATE TABLE IF NOT EXISTS keywords (kw TEXT UNIQUE)")
    conn.execute("CREATE TABLE IF NOT EXISTS seen_urls (url TEXT UNIQUE, title TEXT, risk_hint TEXT)")
    for kw in SEED_KEYWORDS:
        conn.execute("INSERT OR IGNORE INTO keywords (kw) VALUES (?)", (kw,))
    conn.commit()
    conn.close()


def get_owner_chat_id():
    r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates", timeout=10).json()
    for upd in reversed(r.get("result", [])):
        msg = upd.get("message") or upd.get("callback_query", {}).get("message")
        if msg and "chat" in msg:
            return msg["chat"]["id"]
    return None


def send_tg(chat_id, text):
    if chat_id and BOT_TOKEN:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )


def run_snowball_cycle(chat_id):
    conn = sqlite3.connect(DB_FILE)
    kws = [row[0] for row in conn.execute("SELECT kw FROM keywords").fetchall()]
    new_hits = 0

    for kw in kws[:10]:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(kw)}&hl=en-IN&gl=IN&ceid=IN:en"
        feed = feedparser.parse(url)
        for item in feed.entries[:2]:
            exists = conn.execute("SELECT 1 FROM seen_urls WHERE url = ?", (item.link,)).fetchone()
            if not exists:
                tags = re.findall(r"#\w+", item.title)
                for t in tags:
                    conn.execute("INSERT OR IGNORE INTO keywords (kw) VALUES (?)", (t,))
                hint = "COORDINATED/FOREIGN_SIGNAL" if any(w in item.title.lower() for w in ["fake", "viral", "propaganda", "pakistan", "china"]) else "STANDARD"
                conn.execute("INSERT INTO seen_urls (url, title, risk_hint) VALUES (?, ?, ?)", (item.link, item.title, hint))
                new_hits += 1
                if hint != "STANDARD":
                    send_tg(chat_id, f"[Snowball Alert | {kw}]\n{item.title}\n{item.link}")

    total_kws = conn.execute("SELECT COUNT(*) FROM keywords").fetchone()[0]
    conn.commit()
    conn.close()
    print(f"[Autopilot] Cycle complete. New items: {new_hits} | Total tracked keywords: {total_kws}")


init_snowball_db()
chat_id = get_owner_chat_id()
print(f"[Autopilot] Started 15-min loop (Telegram Chat ID: {chat_id}). Press Ctrl+C to stop.")

while True:
    run_snowball_cycle(chat_id)
    print("[Autopilot] Sleeping 15 minutes before next scan...")
    time.sleep(900)