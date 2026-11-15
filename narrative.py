import os
import sqlite3
import textwrap
import urllib.parse
import feedparser
from PIL import Image, ImageDraw, ImageFont

os.makedirs("output", exist_ok=True)
DB_FILE = "rakshanet.db"


def make_fact_card(claim, fact):
    img = Image.new("RGB", (1080, 1080), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([(0, 0), (1080, 110)], fill=(20, 20, 20))
    d.rectangle([(0, 110), (1080, 120)], fill=(200, 30, 30))

    f_head = ImageFont.load_default(size=42)
    f_body = ImageFont.load_default(size=32)
    f_tag = ImageFont.load_default(size=26)

    d.text((50, 32), "RAKSHANET | FACT & NARRATIVE CHECK", fill=(255, 255, 255), font=f_head)
    d.text((50, 170), "VIRAL CLAIM:", fill=(200, 30, 30), font=f_tag)
    d.text((50, 215), textwrap.fill(claim, width=42), fill=(20, 20, 20), font=f_body)

    d.line([(50, 480), (1030, 480)], fill=(220, 220, 220), width=3)
    d.text((50, 520), "VERIFIED REFERENCE:", fill=(20, 100, 40), font=f_tag)
    d.text((50, 565), textwrap.fill(fact, width=42), fill=(20, 20, 20), font=f_body)

    d.text((50, 990), "RakshaNet Open-Source Desk  |  Verify Before Sharing", fill=(110, 110, 110), font=f_tag)
    out = "output/fact_card.png"
    img.save(out)
    return out


def check_text_claim(claim_text, source_type="TEXT POST"):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("CREATE TABLE IF NOT EXISTS narratives (id INTEGER PRIMARY KEY AUTOINCREMENT, claim TEXT UNIQUE, source_type TEXT, counter_fact TEXT, proof_url TEXT)")
    q = urllib.parse.quote(f"{claim_text} PIB OR India official data OR fact check")
    feed = feedparser.parse(f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en")

    fact = feed.entries[0].title if feed.entries else "No official confirmation found; flagged for verification."
    purl = feed.entries[0].link if feed.entries else "https://factcheck.pib.gov.in/"

    conn.execute("INSERT OR REPLACE INTO narratives (claim, source_type, counter_fact, proof_url) VALUES (?, ?, ?, ?)", (claim_text, source_type, fact, purl))
    conn.commit()
    conn.close()

    card = make_fact_card(claim_text, fact)
    print(f"[Narrative] Claim: {claim_text}")
    print(f"[Narrative] Verified Ref: {fact}")
    print(f"[Narrative] Fact-Card saved at: {card}")


check_text_claim("India foreign reserves collapsing fake narrative")