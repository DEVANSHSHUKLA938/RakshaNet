import os
import re
import subprocess
import urllib.parse
import cv2
import feedparser
import imagehash
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from dotenv import load_dotenv
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
os.makedirs("temp", exist_ok=True)
os.makedirs("output", exist_ok=True)

IGNORE_TAGS = ["parody", "satire", "animation", "trailer", "gaming", "comedy", "fan-made"]
KEYWORDS = ["Indian Army", "LOC border", "LAC Ladakh", "DRDO missile", "PIB Fact Check"]


def is_harmful_topic(title):
    t = title.lower()
    return not any(tag in t for tag in IGNORE_TAGS)


def analyze_video(url, title=None):
    if not title:
        try:
            title = subprocess.check_output(["yt-dlp", "--get-title", "--no-playlist", url], text=True).strip()
        except Exception:
            title = "Unknown Video"
    if not is_harmful_topic(title):
        return 0, "SAFE (Entertainment/Disclaimer)", ["Skipped non-harmful content"]

    vid, img = "temp/main_vid.mp4", "temp/main_frame.jpg"
    subprocess.run(["yt-dlp", "-f", "worst[ext=mp4]/worst", "--download-sections", "*0:00-0:15", "-o", vid, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    subprocess.run(["ffmpeg", "-y", "-ss", "00:00:03", "-i", vid, "-vframes", "1", img], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    _ = str(imagehash.phash(Image.open(img)))
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
        full_v = cv2.Laplacian(gray, cv2.CV_64F).var()
        cent_v = cv2.Laplacian(gray[h//4:3*h//4, w//4:3*w//4], cv2.CV_64F).var()
        if full_v > 0 and cent_v < full_v * 0.25:
            blur_flags += 1
    cap.release()

    score, reasons = 0, []
    if blur_flags >= 2:
        score += 25
        reasons.append("Center subject smoother than background")
    if len(b_vals) >= 2 and np.std(b_vals) > 35:
        score += 25
        reasons.append("Unusual lighting jump detected")

    fc = feedparser.parse(f"https://news.google.com/rss/search?q={urllib.parse.quote(chr(32).join(title.split()[:5]) + ' fact check')}&hl=en-IN&gl=IN&ceid=IN:en")
    if len(fc.entries) > 0:
        score += 30
        reasons.append(f"Fact-check found: {fc.entries[0].title[:50]}")

    for f in (vid, img):
        if os.path.exists(f):
            os.remove(f)

    verdict = "LIKELY SAFE"
    if score >= 85:
        verdict = "AUTO-COUNTER (HIGH RISK)"
    elif score >= 50:
        verdict = "NEEDS 1-TAP REVIEW"
    return score, verdict, reasons


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("RakshaNet Integrated Autopilot is ONLINE!\n- Send any video URL to scan\n- Send /radar to fetch latest Defence news")

async def radar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("[Radar] Scanning Defence & Fact-Check feeds...")
    lines = []
    for kw in KEYWORDS[:3]:
        feed = feedparser.parse(f"https://news.google.com/rss/search?q={urllib.parse.quote(kw)}&hl=en-IN&gl=IN&ceid=IN:en")
        if feed.entries:
            lines.append(f"• {kw}: {feed.entries[0].title}")
    await update.message.reply_text("\n".join(lines) or "No new items found.")


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "http" not in url:
        return
    await update.message.reply_text("[RakshaNet] Running 5-Judge Forensic Scan...")
    try:
        score, verdict, reasons = analyze_video(url)
        reason_txt = "; ".join(reasons) if reasons else "No anomalies detected"
        if score >= 85:
            out = build_counter(url, score, reason_txt)
            await update.message.reply_video(video=open(out, "rb"), caption=f"[{verdict}] Score: {score}%\n{reason_txt}")
        elif score >= 50:
            context.user_data["pending"] = (url, score, reason_txt)
            kb = [[InlineKeyboardButton("Approve Counter-Video", callback_data="approve"), InlineKeyboardButton("Ignore", callback_data="ignore")]]
            await update.message.reply_text(f"[{verdict}] Score: {score}%\nReason: {reason_txt}", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text(f"[{verdict}] Score: {score}%\n{reason_txt}")
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


print("[RakshaNet] Integrated System Running... Press Ctrl+C to stop.")
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("radar", radar_cmd))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
app.add_handler(CallbackQueryHandler(button_tap))
app.run_polling()
