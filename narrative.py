import re
import os, textwrap, feedparser
from datetime import datetime
from urllib.parse import quote
from PIL import Image, ImageDraw, ImageFont

def get_font(size, bold=False):
    paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def verify_claim(claim):
    q = quote(claim[:80])
    feed = feedparser.parse(f"https://news.google.com/rss/search?q={q}+when:7d&hl=en-IN&gl=IN&ceid=IN:en")
    words = [w.lower() for w in re.findall(r"[a-zA-Z]{4,}", claim)]
    for e in feed.entries[:5]:
        if words and sum(1 for w in words if w in e.title.lower()) >= min(2, len(words)):
            return e.title, e.link
    return "No official confirmation found in recent PIB/News feeds; verify before sharing.", "https://factcheck.pib.gov.in/"

def make_card(claim, fact, out_path="output/fact_card.png"):
    os.makedirs("output", exist_ok=True)
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), "#F1F5F9")
    d = ImageDraw.Draw(img)

    # Top Editorial Header
    d.rectangle([0, 0, W, 130], fill="#0F172A")
    d.rectangle([0, 130, W, 140], fill="#DC2626")
    d.text((60, 38), "RAKSHANET", fill="#FFFFFF", font=get_font(42, bold=True))
    d.text((60, 88), "FACT & NARRATIVE INTELLIGENCE DESK", fill="#94A3B8", font=get_font(20, bold=True))

    date_str = datetime.now().strftime("%d %b %Y").upper()
    d.rounded_rectangle([830, 42, 1020, 92], radius=8, fill="#1E293B", outline="#334155", width=2)
    d.text((855, 55), date_str, fill="#E2E8F0", font=get_font(22, bold=True))

    # Card 1: Viral Claim
    d.rounded_rectangle([55, 185, 1025, 540], radius=18, fill="#FFFFFF", outline="#CBD5E1", width=2)
    d.rounded_rectangle([55, 185, 73, 540], radius=6, fill="#DC2626")
    d.rounded_rectangle([105, 215, 365, 255], radius=6, fill="#FEE2E2")
    d.text((122, 224), "CLAIM UNDER REVIEW", fill="#B91C1C", font=get_font(19, bold=True))

    y = 285
    for line in textwrap.wrap(claim, width=38)[:5]:
        d.text((105, y), line, fill="#0F172A", font=get_font(38, bold=True))
        y += 48

    # Card 2: Verified Reference
    unconfirmed = "No official confirmation" in fact
    accent = "#D97706" if unconfirmed else "#059669"
    bg_tint = "#FFFBEB" if unconfirmed else "#ECFDF5"
    pill_bg = "#FEF3C7" if unconfirmed else "#D1FAE5"
    pill_txt = "#B45309" if unconfirmed else "#047857"
    label = "UNVERIFIED / CAUTION" if unconfirmed else "VERIFIED REFERENCE"

    d.rounded_rectangle([55, 575, 1025, 955], radius=18, fill=bg_tint, outline="#CBD5E1", width=2)
    d.rounded_rectangle([55, 575, 73, 955], radius=6, fill=accent)
    d.rounded_rectangle([105, 605, 375, 645], radius=6, fill=pill_bg)
    d.text((122, 614), label, fill=pill_txt, font=get_font(19, bold=True))

    y = 675
    for line in textwrap.wrap(fact, width=42)[:5]:
        d.text((105, y), line, fill="#1E293B", font=get_font(34, bold=False))
        y += 46

    # Bottom Footer
    d.rectangle([0, 995, W, H], fill="#0F172A")
    d.text((60, 1028), "Source: PIB Fact Check & Official Feeds", fill="#94A3B8", font=get_font(22))
    d.text((760, 1028), "Verify Before Sharing", fill="#F8FAFC", font=get_font(22, bold=True))

    img.save(out_path)
    return out_path

if __name__ == "__main__":
    p = make_card(
        "Viral forward claims emergency curfew imposed across Delhi tonight.",
        "PIB Fact Check & Delhi Police confirm no such order exists; normal operations continue."
    )
    print("Saved new Fact-Card:", p)
