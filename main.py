import types
import os
import sqlite3
import subprocess
import textwrap
import urllib.parse
import cv2
import feedparser
import numpy as np
from dotenv import load_dotenv
class _GroqWhisper:
    def init(self, *a, **kw): pass
    def transcribe(self, path, *a, **kw):
        import requests
        r = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '')}"},
            files={"file": open(path, "rb")},
            data={"model": "whisper-large-v3-turbo"},
            timeout=30
        ).json()
        class _Seg:
            def init(self, t): self.text = t
        if "error" in r: raise RuntimeError(r["error"].get("message", str(r["error"])))
        return ([types.SimpleNamespace(text=r.get("text", ""))] if r.get("text") else []), None

setattr(_GroqWhisper, chr(95)*2+"init"+chr(95)*2, lambda self, x="": None)
if os.environ.get("GROQ_API_KEY"):
    WhisperModel = _GroqWhisper
else:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        WhisperModel = _GroqWhisper
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
        whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
    os.makedirs("temp", exist_ok=True)
    parts = []
    if os.path.exists(vid_path) and os.path.getsize(vid_path) > 20 * 1024 * 1024:
        subprocess.run(["ffmpeg", "-y", "-i", vid_path, "-f", "segment", "-segment_time", "600", "-c:a", "libmp3lame", "-b:a", "48k", "temp/chk_%03d.mp3"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        files = sorted(f"temp/{f}" for f in os.listdir("temp") if f.startswith("chk_") and f.endswith(".mp3"))
    else:
        files = [vid_path]
    offset = 0
    for fp in files:
        segs, _ = whisper_model.transcribe(fp, beam_size=1)
        for seg in segs:
            t_txt = getattr(seg, "text", "").strip()
            if t_txt:
                parts.append(t_txt)
        if fp != vid_path and os.path.exists(fp):
            os.remove(fp)
        offset += 600
    return " ".join(parts).strip()
#
def make_fact_card(claim, fact):
    claim = str(claim).replace("₹", "Rs.")
    fact = str(fact).replace("₹", "Rs.")
    img = Image.new("RGB", (1080, 1080), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([(0, 0), (1080, 110)], fill=(20, 20, 20))
    d.rectangle([(0, 110), (1080, 120)], fill=(200, 30, 30))
    f_h, f_b, f_t = ImageFont.load_default(size=40), ImageFont.load_default(size=32), ImageFont.load_default(size=26)
    d.text((50, 32), "RAKSHANET | FACT & NARRATIVE CHECK", fill=(255, 255, 255), font=f_h)
    d.text((50, 170), "VIRAL CLAIM:", fill=(200, 30, 30), font=f_t)
    d.text((50, 215), textwrap.fill(claim[:220], width=42), fill=(20, 20, 20), font=f_b)
    d.line([(50, 480), (1030, 480)], fill=(220, 220, 220), width=3)
    d.text((50, 520), "VERIFIED REFERENCE:", fill=(20, 100, 40), font=f_t)
    d.text((50, 565), textwrap.fill(fact[:320], width=42), fill=(20, 20, 20), font=f_b)
    d.text((50, 990), "RakshaNet Open-Source Desk | Verify Before Sharing", fill=(110, 110, 110), font=f_t)
    os.makedirs("output", exist_ok=True)
    out = "output/fact_card.png"
    img.save(out)
    return out
#
def build_counter(url, score, reason, dur=20):
    raw, banner, out = "temp/c_raw.mp4", "temp/c_ban.png", "output/counter_live.mp4"
    os.makedirs("temp", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    if subprocess.run(["yt-dlp", "-f", "worst[ext=mp4]/worst", "-o", raw, url]).returncode != 0:
        return None
    im = Image.new("RGBA", (620, 90), (180, 20, 20, 220))
    d = ImageDraw.Draw(im)
    f = ImageFont.load_default(size=18)
    d.text((15, 12), f"RAKSHANET ALERT | RISK: {score}%", fill=(255, 255, 255), font=f)
    d.text((15, 45), str(reason)[:55].replace("₹", "Rs."), fill=(255, 230, 150), font=f)
    im.save(banner)
    subprocess.run(["ffmpeg", "-y", "-t", str(dur), "-i", raw, "-i", banner, "-filter_complex", "overlay=10:10", "-c:a", "copy", out], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    for p in (raw, banner):
        if os.path.exists(p):
            os.remove(p)
    return out
#
def analyze_video(url):
    import urllib.parse, imagehash
    os.makedirs("temp", exist_ok=True)
    vid, aud = "temp/main_vid.mp4", "temp/full_aud.mp3"
    title = url
    try:
        import requests
        oe = requests.get(f"https://www.youtube.com/oembed?url={urllib.parse.quote(url)}&format=json", timeout=6).json()
        title = oe.get("title", url)
    except Exception:
        pass
    aud_ok = subprocess.run(["yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "9", "-o", aud, url]).returncode == 0
    vid_ok = subprocess.run(["yt-dlp", "-f", "worst[ext=mp4]/worst", "-o", vid, url]).returncode == 0
    if not aud_ok and not vid_ok:
        return 25, "CLOUD CHECK", title, ["Cloud video download restricted; title verified"]
    speech = get_speech(aud if aud_ok else vid)
    if os.path.exists(aud):
        os.remove(aud)
    b_vals, blur_flags, recycled = [], 0, False
    seen_hashes = set()
    if vid_ok and os.path.exists(vid):
        cap = cv2.VideoCapture(vid)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        conn = sqlite3.connect(DB_FILE)
        conn.execute("CREATE TABLE IF NOT EXISTS video_hashes (phash TEXT UNIQUE, label TEXT)")
        for idx in range(0, total, max(1, total // 10)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            ph = str(imagehash.phash(Image.fromarray(gray)))
            if ph in seen_hashes:
                continue
            seen_hashes.add(ph)
            if conn.execute("SELECT 1 FROM video_hashes WHERE phash=?", (ph,)).fetchone():
                recycled = True
            else:
                conn.execute("INSERT OR IGNORE INTO video_hashes (phash, label) VALUES (?, ?)", (ph, title[:80]))
            b_vals.append(float(np.mean(gray)))
            h, w = gray.shape
            fv = cv2.Laplacian(gray, cv2.CV_64F).var()
            if fv > 0 and cv2.Laplacian(gray[h//4:3*h//4, w//4:3*w//4], cv2.CV_64F).var() < fv * 0.25:
                blur_flags += 1
        conn.commit()
        conn.close()
        cap.release()
        os.remove(vid)
    score, reasons = 0, []
    if recycled:
        score += 40
        reasons.append("Recycled old clip matched in pHash memory")
    if blur_flags >= 2:
        score += 25
        reasons.append("Center subject smoother than background")
    if len(b_vals) >= 2 and np.std(b_vals) > 35:
        score += 25
        reasons.append("Scene lighting jump detected")
    q_txt = speech if len(speech.split()) >= 4 else title
    fc = feedparser.parse(f"https://news.google.com/rss/search?q={urllib.parse.quote(chr(32).join(q_txt.split()[:8]))}+fact+check&hl=en-IN&gl=IN&ceid=IN:en")
    if fc.entries:
        score += 30
        reasons.append(f"Ref: {fc.entries[0].title[:55]}")
    verdict = "AUTO-COUNTER (HIGH RISK)" if score >= 85 else ("NEEDS REVIEW" if score >= 50 else "LIKELY SAFE")
    return score, verdict, speech[:200] if speech else title[:120], reasons
#
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


def deep_verify(claim):
    import urllib.parse, re as _re
    q1 = " ".join(claim.split()[:10])
    queries = [q1]
    k = os.environ.get("GROQ_API_KEY", "")
    if k:
        try:
            import requests
            r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {k}"}, json={"model": "openai/gpt-oss-120b", "messages": [{"role": "user", "content": f"Extract 1 concise English search query (max 6 words, no quotes) to fact-check this claim using official/authentic sources: {claim[:220]}"}]}, timeout=12).json()
            q2 = r.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if q2 and len(q2.split()) <= 8:
                queries.append(q2)
        except Exception:
            pass
    auth_domains = ("pib.gov.in", "gov.in", "nic.in", "rbi.org.in", "isro.gov.in", "worldbank.org", "imf.org", "who.int", "un.org", "boomlive.in", "factly.in", "vishvasnews.com", "reuters.com", "apnews.com", "thehindu.com", "indianexpress.com", "ddnews.gov.in", "ptinews.com", "britannica.com")
    all_entries = []
    for q in queries:
        for suffix in ["", " fact check", " site:gov.in OR site:worldbank.org OR site:imf.org OR site:rbi.org.in"]:
            feed = feedparser.parse(f"https://news.google.com/rss/search?q={urllib.parse.quote(q + suffix)}&when:30d&hl=en-IN&gl=IN&ceid=IN:en")
            all_entries.extend(feed.entries[:5])
    _w = [w.lower() for w in _re.findall(r"[a-zA-Z]{4,}", claim)]
    best = next((e for e in all_entries if any(d in getattr(e, "link", "").lower() or d in getattr(e, "title", "").lower() for d in auth_domains) and (_w and sum(1 for w in _w if w in e.title.lower()) >= 1)), None)
    if not best:
        best = next((e for e in all_entries if _w and sum(1 for w in _w if w in e.title.lower()) >= min(2, len(_w))), None)
    heads = [e.title for e in all_entries[:4]]
    fb = best.title if best else "No official confirmation found yet; added to 24h auto-watchlist."
    purl = best.link if best else "https://factcheck.pib.gov.in/"
    return heads, fb, purl
#
async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import urllib.parse
    txt = (update.message.text or "").strip()
    if not txt:
        return
    if not txt.startswith("http"):
        await update.message.reply_text("[Narrative] Investigating authentic sources & data...")
        heads, fb, purl = deep_verify(txt)
        fact = ai_reason(txt, heads, fb)
        conn = sqlite3.connect(DB_FILE)
        conn.execute("CREATE TABLE IF NOT EXISTS narratives (id INTEGER PRIMARY KEY AUTOINCREMENT, claim TEXT UNIQUE, source_type TEXT, counter_fact TEXT, proof_url TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS watchlist (id INTEGER PRIMARY KEY AUTOINCREMENT, claim TEXT UNIQUE, source_url TEXT, checks INTEGER DEFAULT 0, status TEXT DEFAULT 'PENDING', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("INSERT OR REPLACE INTO narratives (claim, source_type, counter_fact, proof_url) VALUES (?, ?, ?, ?)", (txt, "TELEGRAM TEXT", fact, purl))
        if "[UNCONFIRMED]" in fact:
            conn.execute("INSERT OR IGNORE INTO watchlist (claim, source_url) VALUES (?, ?)", (txt, purl))
        conn.commit()
        conn.close()
        card = make_fact_card(txt, fact)
        x_url = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(f'{fact[:180]} Proof: {purl} #RakshaNet')}"
        kb = [[InlineKeyboardButton("Share on X (1-Click)", url=x_url)]]
        await update.message.reply_photo(photo=open(card, "rb"), caption=f"Verified Ref: {fact}\nProof: {purl}", reply_markup=InlineKeyboardMarkup(kb))
        pub_ch = os.environ.get("PUBLIC_CHANNEL", "")
        if pub_ch and any(tag in fact for tag in ("[FAKE]", "[MISLEADING]", "[VERIFIED]")):
            try:
                await context.bot.send_photo(chat_id=pub_ch, photo=open(card, "rb"), caption=f"RakshaNet Alert: {fact}\nProof: {purl}")
            except Exception:
                pass
        return
    await update.message.reply_text("[RakshaNet] Scanning full video & Whisper speech...")
    try:
        score, verdict, speech, reasons = analyze_video(txt)
        r_txt = "; ".join(reasons) if reasons else "No anomalies detected"
        if score >= 85:
            out = build_counter(txt, score, r_txt)
            if out:
                await update.message.reply_video(video=open(out, "rb"), caption=f"[{verdict}] Score: {score}%\nSpeech: {speech or 'N/A'}\n{r_txt}")
            else:
                await update.message.reply_text(f"[{verdict}] Score: {score}%\nSpeech: {speech or 'N/A'}\n{r_txt}")
        else:
            await update.message.reply_text(f"[{verdict}] Score: {score}%\nSpeech: {speech or 'N/A'}\nReason: {r_txt}")
    except Exception as e:
        await update.message.reply_text(f"[Error] {e}")
#def ai_reason(claim, heads, fb):
    k = os.environ.get("GROQ_API_KEY", "")
    if not k:
        return fb
    try:
        import requests
        ctx = " | ".join(heads) if heads else "No matching headlines found."
        p = f"Claim: {claim}\nAuthentic Headlines/Data: {ctx}\nRules: 1) Start strictly with [FAKE], [MISLEADING], [VERIFIED], or [UNCONFIRMED]. 2) If it is anti-India false data or a foreign video falsely tagged as India, expose it with factual data/origin. 3) NEVER accuse [FAKE] without contradicting evidence in headlines or known official facts; otherwise use [UNCONFIRMED]. 4) Reply in 1 crisp factual sentence."
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {k}"}, json={"model": "openai/gpt-oss-120b", "messages": [{"role": "user", "content": p}]}, timeout=20).json()
        txt = r.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return txt if txt else fb
    except Exception:
        return fb
#
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import urllib.parse
    m = update.message.video or update.message.voice or update.message.audio or update.message.video_note
    if not m:
        return
    await update.message.reply_text("[RakshaNet] Scanning full forwarded media with Whisper Large-v3...")
    os.makedirs("temp", exist_ok=True)
    f = await context.bot.get_file(m.file_id)
    ext = ".mp4" if (update.message.video or update.message.video_note) else ".ogg"
    p = f"temp/tg_media{ext}"
    await f.download_to_drive(p)
    try:
        speech = get_speech(p)
        if not speech:
            await update.message.reply_text("No clear speech detected in this media.")
            return
        heads, fb, purl = deep_verify(speech[:220])
        fact = ai_reason(speech[:220], heads, fb)
        card = make_fact_card(speech[:180], fact)
        x_url = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(f'{fact[:180]} Proof: {purl} #RakshaNet')}"
        kb = [[InlineKeyboardButton("Share on X (1-Click)", url=x_url)]]
        await update.message.reply_photo(photo=open(card, "rb"), caption=f"Speech: {speech[:200]}\nRef: {fact}\nProof: {purl}", reply_markup=InlineKeyboardMarkup(kb))
        pub_ch = os.environ.get("PUBLIC_CHANNEL", "")
        if pub_ch and any(tag in fact for tag in ("[FAKE]", "[MISLEADING]", "[VERIFIED]")):
            try:
                await context.bot.send_photo(chat_id=pub_ch, photo=open(card, "rb"), caption=f"RakshaNet Alert: {fact}\nProof: {purl}")
            except Exception:
                pass
    except Exception as e:
        await update.message.reply_text(f"[Media Error] {e}")
    finally:
        if os.path.exists(p):
            os.remove(p)
#
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
app.add_handler(MessageHandler(filters.VIDEO | filters.VOICE | filters.AUDIO | filters.VIDEO_NOTE, handle_media))
app.add_handler(CallbackQueryHandler(button_tap))

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
if os.environ.get("PORT"):
    class H(BaseHTTPRequestHandler):
        def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"RakshaNet OK")
        def log_message(self, *a): pass
    threading.Thread(target=lambda: HTTPServer(("0.0.0.0", int(os.environ["PORT"])), H).serve_forever(), daemon=True).start()

def _render_switch(action):
    k = os.environ.get("RENDER_API_KEY")
    if k and not os.environ.get("PORT"):
        try:
            import requests, time
            requests.post(f"https://api.render.com/v1/services/srv-dbsifk6k1f9s739ctpi0/{action}", headers={"Authorization": f"Bearer {k}"}, timeout=10)
            if action == "suspend":
                time.sleep(15)
            print(f"[Auto-Switch] Render {action}d!")
        except Exception as e:
            print(f"[Auto-Switch] Note: {e}")

if not os.environ.get("PORT") and os.environ.get("RENDER_API_KEY"):
    _render_switch("suspend")
try:
    app.run_polling()
finally:
    _render_switch("resume")

