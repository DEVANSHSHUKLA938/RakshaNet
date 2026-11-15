import os
import sqlite3
import subprocess
import imagehash
from PIL import Image
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = "8837360885:AAEHFwfo048qipmIJpDeLmh1LF-v-iT8C40"
DB_FILE = "rakshanet.db"
os.makedirs("temp", exist_ok=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "RakshaNet Bot is online! Send any YouTube or video URL to scan."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if "http" not in text:
        await update.message.reply_text("Please send a valid video URL (starting with http).")
        return

    await update.message.reply_text("[RakshaNet] Scanning URL, please wait...")
    temp_vid = "temp/tg_vid.mp4"
    temp_img = "temp/tg_frame.jpg"

    try:
        subprocess.run(["yt-dlp", "-f", "worst[ext=mp4]/worst", "-o", temp_vid, text], check=True)
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "00:00:03", "-i", temp_vid, "-vframes", "1", temp_img],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
        )
        phash = str(imagehash.phash(Image.open(temp_img)))

        conn = sqlite3.connect(DB_FILE)
        conn.execute("CREATE TABLE IF NOT EXISTS videos (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE, phash TEXT, status TEXT)")
        row = conn.execute("SELECT url, status FROM videos WHERE phash = ?", (phash,)).fetchone()
        if row:
            msg = f"[Match Found] Seen before!\npHash: {phash}\nStatus: {row[1]}"
        else:
            conn.execute(
                "INSERT OR REPLACE INTO videos (url, phash, status) VALUES (?, ?, ?)",
                (text, phash, "SCANNED_VIA_TELEGRAM"),
            )
            conn.commit()
            msg = f"[New Video Logged]\npHash: {phash}\nTemp files cleaned."
        conn.close()
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"[Error] Could not scan link: {e}")
    finally:
        for f in (temp_vid, temp_img):
            if os.path.exists(f):
                os.remove(f)


print("[Bot] RakshaNet Telegram Bot is running... Press Ctrl+C to stop.")
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
app.run_polling()