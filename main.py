import os
import sqlite3
import subprocess
import textwrap
import urllib.parse
import cv2
import feedparser
import numpy as np
from dotenv import load_dotenv
from faster_whisper import WhisperModel
from PIL import Image, ImageDraw, ImageFont
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_FILE = "rakshanet.db"
os.makedirs("temp", exist_ok=True)
os.makedirs("output", exist_ok=True)
KEYWORDS = ["Indian Army", "LOC border", "LAC Ladakh", "DRDO missile", "PIB Fact Check"]
IGNORE_TAGS = ["parody", "satire", "animation", "trailer", "gaming", "comedy", "fan-made"]
whisper_model = None


def get_speech(vid_path):
    global whisper_model
    if whisper_model is None:
        print("[Whisper] Loading tiny audio model (first time only ~75MB)...")
        whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, _ = whisper_model.transcribe(vid_path, beam_size=1)
    return " ".join(s.text for s in segments).strip()


def make_fact_card(claim, fact):
    img = Image.new("RGB", (1080, 1080), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([(0, 0), (1080, 110)], fill=(20, 20, 20))
    d.rectangle([(0, 110), (1080, 120)], fill=(200, 30, 30))
    f_h, f_b, f_t = ImageFont.load_default(size=40), ImageFont.load_default(size=32), ImageFont.load_default(size=26)
    d.text((50, 32), "RAKSHANET | FACT & NARRATIVE CHECK", fill=(255, 255, 255), font=f_h)
    d.text((50, 170), "VIRAL CLAIM:", fill=(200, 30, 30), font=f_t)
    d.text((50, 215), textwrap.fill(claim, width=42), fill=(20, 20, 20), font=f_b)
    d.line([(50, 480), (1030, 480)], fill=(220, 220, 220), width=3)
    d.text((50, 520), "VERIFIED REFERENCE:", fill=(20, 100, 40), font=f_t)
    d.text((50, 565), textwrap.fill(fact, width=42), fill=(20, 20, 20), font=f_b)
    d.text((50, 990), "RakshaNet Open-Source Desk  |  Verify Before Sharing", fill=(110, 110, 110), font=f_t)
    out = "output/fact_card.png"
    img.save(out)
    return out


def build_counter(url, score, reason):
    raw, banner, out = "temp/c_raw.mp4", "temp/c_ban.png", "output/counter_live.mp4"
    subprocess.run(["yt-dlp", "-f", "worst[ext=mp4]/worst", "--download-sections", "*0:00-0:15", "-o", raw, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    im = Image.new("RGBA", (620, 90), (180, 20, 20, 220))
    d = ImageDraw.Draw(im)
    f = ImageFont.load_default(size=18)
    d.text((15, 12), f"RAKSHANET ALERT | RISK: {score}%", fill=(255, 255, 255), font=f)
    d.text((15, 45), reason[:55], fill=(255, 230, 150), font=f)
    im.save(banner)
    subprocess.run(["ffmpeg", "-y", "-t", "10", "-i", raw, "-i", banner, "-filter_complex", "overlay=10:10", "-c:a", "copy", out], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    for p in (raw, banner):
        if os.path.exists(p):
            os.remove(p)
    return out


def analyze_video(url):
    title = subprocess.check_output(["yt-dlp", "--get-title", "--no-playlist", url], text=True).strip()
    if any(tag in title.lower() for tag in IGNORE_TAGS):
        return 0, "SAFE (Entertainment/Disclaimer)", "", ["Skipped non-harmful content"]

    vid = "temp/main_vid.mp4"
    subprocess.run(["yt-dlp", "-f", "worst[ext=mp4]/worst", "--download-sections", "*0:00-0:15", "-o", vid, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    speech = get_speech(vid)
    cap = cv2.VideoCapture(vid)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    b_vals, blur_flags = [], 0
    for idx in range(0, total, max(1, total // 5)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        b_vals.append(float(np.mean(gray)))
        h, w = gray.shape
        fv = cv2.Laplacian(gray, cv2.CV_64F).var()
        if fv > 0 and cv2.Laplacian(gray[h//4:3*h//4, w//4:3*w//4], cv2.CV_64F).var() < fv * 0.25:
            blur_flags += 1
    cap.release()
    if os.path.exists(vid):
        os.remove(vid)

    score, reasons = 0, []
    if blur_flags >= 2:
        score += 25
        reasons.append("Center subject smoother than background")
    if len(b_vals) >= 2 and np.std(b_vals) > 35:
        score += 25
        reasons.append("Scene lighting jump detected")
    q_txt = speech if len(speech.split()) >= 4 else title
    fc = feedparser.parse(f"https://news.google.com/rss/search?q={urllib.parse.quote(chr(32).join(q_txt.split()[:6]) + ' fact check')}&hl=en-IN&gl=IN&ceid=IN:en")
    if fc.entries:
        score += 30
        reasons.append(f"Ref: {fc.entries[0].title[:45]}")
    verdict = "AUTO-COUNTER (HIGH RISK)" if score >= 85 else ("NEEDS 1-TAP REVIEW" if score >= 50 else "LIKELY SAFE")
    return score, verdict, speech[:120], reasons


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("RakshaNet Complete Engine ONLINE!\n- Send Video URL (Whisper + Forensics + Counter-Video)\n- Send Text Claim (1080x1080 Fact-Card)\n- Send /radar for Defence news")


async def radar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("[Radar] Scanning Defence & Fact-Check feeds...")
    lines = []
    for kw in KEYWORDS[:3]:
        feed = feedparser.parse(f"https://news.google.com/rss/search?q={urllib.parse.quote(kw)}&hl=en-IN&gl=IN&ceid=IN:en")
        if feed.entries:
            lines.append(f"• {kw}: {feed.entries[0].title}")
    await update.message.reply_text("\n".join(lines) or "No new items found.")


async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    txt = update.message.text.strip()
    if "http" not in txt:
        await update.message.reply_text("[Narrative] Checking official references...")
        q = urllib.parse.quote(f"{txt} PIB OR India official data OR fact check")
        feed = feedparser.parse(f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en")
        fact = feed.entries[0].title if feed.entries else "No official confirmation found; verify before sharing."
        purl = feed.entries[0].link if feed.entries else "https://factcheck.pib.gov.in/"
        conn = sqlite3.connect(DB_FILE)
        conn.execute("CREATE TABLE IF NOT EXISTS narratives (id INTEGER PRIMARY KEY AUTOINCREMENT, claim TEXT UNIQUE, source_type TEXT, counter_fact TEXT, proof_url TEXT)")
        conn.execute("INSERT OR REPLACE INTO narratives (claim, source_type, counter_fact, proof_url) VALUES (?, ?, ?, ?)", (txt, "TELEGRAM TEXT", fact, purl))
        conn.commit()
        conn.close()
        card = make_fact_card(txt, fact)
        await update.message.reply_photo(photo=open(card, "rb"), caption=f"Verified Ref: {fact}\nProof: {purl}")
        return

    await update.message.reply_text("[RakshaNet] Scanning video & Whisper speech...")
    try:
        score, verdict, speech, reasons = analyze_video(txt)
        r_txt = "; ".join(reasons) if reasons else "No anomalies detected"
        if score >= 85:
            out = build_counter(txt, score, r_txt)
            await update.message.reply_video(video=open(out, "rb"), caption=f"[{verdict}] Score: {score}%\nSpeech: {speech or 'N/A'}\n{r_txt}")
        elif score >= 50:
            context.user_data["pending"] = (txt, score, r_txt)
            kb = [[InlineKeyboardButton("Approve Counter-Video", callback_data="approve"), InlineKeyboardButton("Ignore", callback_data="ignore")]]
            await update.message.reply_text(f"[{verdict}] Score: {score}%\nSpeech: {speech or 'N/A'}\nReason: {r_txt}", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text(f"[{verdict}] Score: {score}%\nSpeech: {speech or 'N/A'}\n{r_txt}")
    except Exception as e:
        await update.message.reply_text(f"[Error] {e}")


async def button_tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "approve" and "pending" in context.user_data:
        url, score, reason = context.user_data.pop("pending")
        await q.edit_message_text("Rendering Counter-Video...")
        out = build_counter(url, score, reason)
        await q.message.reply_video(video=open(out, "rb"), caption=f"[Approved Counter-Video] Score: {score}%")
    else:
        await q.edit_message_text("Ignored. Marked as safe.")


print("[RakshaNet Complete] Running with Whisper + Fact-Card + Counter-Video... Press Ctrl+C to stop.")
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("radar", radar_cmd))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
app.add_handler(CallbackQueryHandler(button_tap))
app.run_polling()
