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
    import os, subprocess, requests
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not groq_key or not os.path.exists(vid_path):
        return ""
    os.makedirs("temp", exist_ok=True)
    for fn in os.listdir("temp"):
        if fn.startswith("chk_") and fn.endswith(".mp3"):
            try:
                os.remove(os.path.join("temp", fn))
            except Exception:
                pass
    r_ff = subprocess.run(
        ["ffmpeg", "-y", "-i", vid_path, "-vn", "-f", "segment", "-segment_time", "600",
         "-c:a", "libmp3lame", "-b:a", "48k", "temp/chk_%03d.mp3"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    if r_ff.returncode != 0:
        return ""
    files = sorted(f"temp/{f}" for f in os.listdir("temp") if f.startswith("chk_") and f.endswith(".mp3"))
    parts = []
    for fp in files:
        try:
            with open(fp, "rb") as af:
                resp = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {groq_key}"},
                    files={"file": (os.path.basename(fp), af, "audio/mpeg")},
                    data={"model": "whisper-large-v3"},
                    timeout=45,
                )
            if resp.status_code == 200:
                txt = resp.json().get("text", "").strip()
                if txt:
                    parts.append(txt)
        except Exception:
            pass
        finally:
            if os.path.exists(fp):
                os.remove(fp)
    return " ".join(parts).strip()

def make_fact_card(claim, fact):
    import re as _rc
    c_clean = _rc.sub(r"\s+", " ", _rc.sub(r"[\u2010-\u2015]", "-", str(claim).replace("₹", "Rs."))).encode("ascii", "ignore").decode().strip()
    f_clean = _rc.sub(r"\s+", " ", _rc.sub(r"[\u2010-\u2015]", "-", str(fact).replace("₹", "Rs."))).encode("ascii", "ignore").decode().strip()
    img = Image.new("RGB", (1080, 1080), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([(0, 0), (1080, 110)], fill=(20, 20, 20))
    d.rectangle([(0, 110), (1080, 120)], fill=(200, 30, 30))
    f_h, f_b, f_t = ImageFont.load_default(size=40), ImageFont.load_default(size=32), ImageFont.load_default(size=26)
    d.text((50, 32), "RAKSHANET | FACT & NARRATIVE CHECK", fill=(255, 255, 255), font=f_h)
    d.text((50, 170), "VIRAL CLAIM:", fill=(200, 30, 30), font=f_t)
    d.text((50, 215), textwrap.fill(c_clean[:220], width=42), fill=(20, 20, 20), font=f_b)
    d.line([(50, 480), (1030, 480)], fill=(220, 220, 220), width=3)
    d.text((50, 520), "VERIFIED REFERENCE:", fill=(20, 100, 40), font=f_t)
    d.text((50, 565), textwrap.fill(f_clean[:320], width=42), fill=(20, 20, 20), font=f_b)
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
    import urllib.parse, re as _re, requests as _rq
    q1 = " ".join(claim.split()[:10])
    queries = [q1]
    k = os.environ.get("GROQ_API_KEY", "")
    if k:
        try:
            r = _rq.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {k}"}, json={"model": "openai/gpt-oss-120b", "messages": [{"role": "user", "content": f"Extract 1 concise English search query (max 6 words, no quotes) to fact-check this claim using official/authentic sources: {claim[:220]}"}]}, timeout=12).json()
            q2 = r.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if q2 and len(q2.split()) <= 8:
                queries.append(q2)
        except Exception:
            pass
    auth_domains = ("pib.gov.in", "gov.in", "nic.in", "rbi.org.in", "isro.gov.in", "worldbank.org", "imf.org", "who.int", "un.org", "boomlive.in", "factly.in", "vishvasnews.com", "reuters.com", "apnews.com", "thehindu.com", "indianexpress.com", "ddnews.gov.in", "ptinews.com", "britannica.com", "bbc.com", "aljazeera.com", "theguardian.com")
    all_entries = []
    for q in queries[:2]:
        try:
            res = _rq.get(f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&when:30d&hl=en-IN&gl=IN&ceid=IN:en", timeout=6).text
            all_entries.extend(feedparser.parse(res).entries[:5])
        except Exception:
            pass
    _w = [w.lower() for w in _re.findall(r"[a-zA-Z]{4,}", claim)]
    best = next((e for e in all_entries if any(d in getattr(e, "link", "").lower() or d in getattr(e, "title", "").lower() for d in auth_domains) and (_w and sum(1 for w in _w if w in e.title.lower()) >= 1)), None)
    if not best:
        best = next((e for e in all_entries if _w and sum(1 for w in _w if w in e.title.lower()) >= min(2, len(_w))), None)
    if not best and all_entries:
        best = all_entries[0]
    heads = ([best.title] if best else []) + [e.title for e in all_entries if e is not best][:3]
    fb = best.title if best else "No official confirmation found yet; added to 24h auto-watchlist."
    purl = best.link if best else "https://factcheck.pib.gov.in/"
    return heads, fb, purl
#
def ai_reason(claim, heads, fb):
    k = os.environ.get("GROQ_API_KEY", "")
    if not k:
        return fb
    try:
        import requests
        ctx = " | ".join(heads) if heads else "No matching headlines found."
        p = f"Claim: {claim}\nLive Verified Headlines (fetched right now, treat as 100% real): {ctx}\nRules: 1) If input is just a greeting/casual chat (Hi, Hello, Test, Kya haal), start with [CASUAL]. 2) Otherwise start strictly with [FAKE], [MISLEADING], [VERIFIED], or [UNCONFIRMED]. 3) NEVER say the live headlines are fabricated or missing from archives. 4) Judge ONLY the Claim: if headlines cover/confirm it, use [VERIFIED]; if they debunk/contradict it or it is anti-India false data/misattributed foreign clip, use [FAKE] or [MISLEADING]; else [UNCONFIRMED]. 5) Reply in 1-2 crisp factual sentences naming the exact source/agency, key date or figure, and real context; NEVER write vague phrases like recent headlines confirm."
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {k}"}, json={"model": "openai/gpt-oss-120b", "messages": [{"role": "user", "content": p}]}, timeout=20).json()
        txt = r.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return txt if txt else fb
    except Exception:
        return fb
#
async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import urllib.parse
    txt = (update.message.text or "").strip()
    if not txt:
        return
    if not txt.startswith("http"):
        await update.message.reply_text("[Narrative] Investigating authentic sources & data...")
        try:
            heads, fb, purl = deep_verify(txt)
            fact = ai_reason(txt, heads, fb)
            if fact.startswith("[CASUAL]"):
                await update.message.reply_text("Please send a news claim, photo/screenshot, voice note, or video link to verify.")
                return
            conn = sqlite3.connect(DB_FILE)
            conn.execute("CREATE TABLE IF NOT EXISTS narratives (id INTEGER PRIMARY KEY AUTOINCREMENT, claim TEXT UNIQUE, source_type TEXT, counter_fact TEXT, proof_url TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS watchlist (id INTEGER PRIMARY KEY AUTOINCREMENT, claim TEXT UNIQUE, source_url TEXT, chat_id INTEGER DEFAULT 0, checks INTEGER DEFAULT 0, status TEXT DEFAULT 'PENDING', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
            try:
                conn.execute("ALTER TABLE watchlist ADD COLUMN chat_id INTEGER DEFAULT 0")
            except Exception:
                pass
            conn.execute("INSERT OR REPLACE INTO narratives (claim, source_type, counter_fact, proof_url) VALUES (?, ?, ?, ?)", (txt, "TELEGRAM TEXT", fact, purl))
            if "[UNCONFIRMED]" in fact:
                conn.execute("INSERT OR IGNORE INTO watchlist (claim, source_url, chat_id) VALUES (?, ?, ?)", (txt, purl, update.effective_chat.id))
            conn.commit()
            conn.close()
            card = make_fact_card(txt, fact)
            x_url = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(f'{fact[:180]} Proof: {purl} #RakshaNet')}"
            kb = [[InlineKeyboardButton("Read Full Proof", url=purl), InlineKeyboardButton("Share on X (1-Click)", url=x_url)]]
            full_msg = f"Verified Ref: {fact}\nProof: {purl}"
            if len(full_msg) <= 1000:
                await update.message.reply_photo(photo=open(card, "rb"), caption=full_msg, reply_markup=InlineKeyboardMarkup(kb))
            else:
                await update.message.reply_photo(photo=open(card, "rb"), caption=f"Verified Ref: {fact[:900]}", reply_markup=InlineKeyboardMarkup(kb))
                await update.message.reply_text(full_msg)
            pub_ch = os.environ.get("PUBLIC_CHANNEL", "")
            if pub_ch and any(tag in fact for tag in ("[FAKE]", "[MISLEADING]", "[VERIFIED]")):
                try:
                    await context.bot.send_photo(chat_id=pub_ch, photo=open(card, "rb"), caption=f"RakshaNet Alert: {fact[:900]}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Read Full Proof", url=purl)]]))
                    _yt_bg(locals().get("txt") or locals().get("claim") or locals().get("speech", "")[:180], fact, purl)
                except Exception:
                    pass
        except Exception as e:
            await update.message.reply_text(f"[Error] {e}")
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
            q_src = speech if (speech and len(speech.split()) >= 4) else txt
            heads, fb, purl = deep_verify(q_src[:220])
            fact = ai_reason(q_src[:220], heads, fb)
            card = make_fact_card(q_src[:180], fact)
            x_url = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(f'{fact[:180]} Proof: {purl} #RakshaNet')}"
            kb = [[InlineKeyboardButton("Read Full Proof", url=purl), InlineKeyboardButton("Share on X (1-Click)", url=x_url)]]
            await update.message.reply_photo(photo=open(card, "rb"), caption=f"[{verdict}] Score: {score}%\nRef: {fact[:700]}", reply_markup=InlineKeyboardMarkup(kb))
            pub_ch = os.environ.get("PUBLIC_CHANNEL", "")
            if pub_ch and any(tag in fact for tag in ("[FAKE]", "[MISLEADING]", "[VERIFIED]")):
                try:
                    await context.bot.send_photo(chat_id=pub_ch, photo=open(card, "rb"), caption=f"RakshaNet Video Alert: {fact[:900]}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Read Full Proof", url=purl)]]))
                    _yt_bg(locals().get("txt") or locals().get("claim") or locals().get("speech", "")[:180], fact, purl)
                except Exception:
                    pass
    except Exception as e:
        await update.message.reply_text(f"[Error] {e}")
#async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        speech = extract_video_claim(p, get_speech(p))
        if not speech or "[NO FACTUAL CLAIM]" in speech:
            await update.message.reply_text("No factual claim detected in this media (music/entertainment clip).")
            return
        heads, fb, purl = deep_verify(speech[:220])
        fact = ai_reason(speech[:220], heads, fb)
        card = make_fact_card(speech[:180], fact)
        x_url = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(f'{fact[:180]} Proof: {purl} #RakshaNet')}"
        kb = [[InlineKeyboardButton("Read Full Proof", url=purl), InlineKeyboardButton("Share on X (1-Click)", url=x_url)]]
        full_msg = f"Speech: {speech[:200]}\nRef: {fact}\nProof: {purl}"
        if len(full_msg) <= 1000:
            await update.message.reply_photo(photo=open(card, "rb"), caption=full_msg, reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_photo(photo=open(card, "rb"), caption=f"Speech: {speech[:200]}\nRef: {fact[:700]}", reply_markup=InlineKeyboardMarkup(kb))
            await update.message.reply_text(full_msg)
        pub_ch = os.environ.get("PUBLIC_CHANNEL", "")
        if pub_ch and any(tag in fact for tag in ("[FAKE]", "[MISLEADING]", "[VERIFIED]")):
            try:
                await context.bot.send_photo(chat_id=pub_ch, photo=open(card, "rb"), caption=f"RakshaNet Alert: {fact}\nProof: {purl}")
                _yt_bg(locals().get("txt") or locals().get("claim") or locals().get("speech", "")[:180], fact, purl)
            except Exception:
                pass
    except Exception as e:
        await update.message.reply_text(f"[Media Error] {e}")
    finally:
        if os.path.exists(p):
            os.remove(p)
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
        speech = extract_video_claim(p, get_speech(p))
        if not speech or "[NO FACTUAL CLAIM]" in speech:
            await update.message.reply_text("No factual claim detected in this media (music/entertainment clip).")
            return
        heads, fb, purl = deep_verify(speech[:220])
        fact = ai_reason(speech[:220], heads, fb)
        card = make_fact_card(speech[:180], fact)
        x_url = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(f'{fact[:180]} Proof: {purl} #RakshaNet')}"
        kb = [[InlineKeyboardButton("Read Full Proof", url=purl), InlineKeyboardButton("Share on X (1-Click)", url=x_url)]]
        full_msg = f"Speech: {speech[:200]}\nRef: {fact}\nProof: {purl}"
        if len(full_msg) <= 1000:
            await update.message.reply_photo(photo=open(card, "rb"), caption=full_msg, reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_photo(photo=open(card, "rb"), caption=f"Speech: {speech[:200]}\nRef: {fact[:700]}", reply_markup=InlineKeyboardMarkup(kb))
            await update.message.reply_text(full_msg)
        pub_ch = os.environ.get("PUBLIC_CHANNEL", "")
        if pub_ch and any(tag in fact for tag in ("[FAKE]", "[MISLEADING]", "[VERIFIED]")):
            try:
                await context.bot.send_photo(chat_id=pub_ch, photo=open(card, "rb"), caption=f"RakshaNet Alert: {fact[:900]}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Read Full Proof", url=purl)]]))
                _yt_bg(locals().get("txt") or locals().get("claim") or locals().get("speech", "")[:180], fact, purl)
            except Exception:
                pass
    except Exception as e:
        await update.message.reply_text(f"[Media Error] {e}")
    finally:
        if os.path.exists(p):
            os.remove(p)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import base64, requests, urllib.parse
    if not update.message.photo:
        return
    await update.message.reply_text("[RakshaNet] Scanning image/screenshot with Vision AI...")
    os.makedirs("temp", exist_ok=True)
    p = "temp/tg_photo.jpg"
    try:
        f = await context.bot.get_file(update.message.photo[-1].file_id)
        await f.download_to_drive(p)
        k = os.environ.get("GROQ_API_KEY", "")
        b64 = base64.b64encode(open(p, "rb").read()).decode()
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {k}"}, json={"model": "meta-llama/llama-4-scout-17b-16e-instruct", "messages": [{"role": "user", "content": [{"type": "text", "text": "Extract the main viral claim, notice text, or country/location clues from this image in 1-2 short English sentences."}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]}, timeout=20).json()
        claim = r.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not claim:
            await update.message.reply_text("Could not read clear text/claim from this image.")
            return
        heads, fb, purl = deep_verify(claim[:220])
        fact = ai_reason(claim[:220], heads, fb)
        card = make_fact_card(claim[:180], fact)
        x_url = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(f'{fact[:180]} Proof: {purl} #RakshaNet')}"
        kb = [[InlineKeyboardButton("Read Full Proof", url=purl), InlineKeyboardButton("Share on X (1-Click)", url=x_url)]]
        await update.message.reply_photo(photo=open(card, "rb"), caption=f"Image Claim: {claim[:220]}\nRef: {fact[:650]}", reply_markup=InlineKeyboardMarkup(kb))
        pub_ch = os.environ.get("PUBLIC_CHANNEL", "")
        if pub_ch and any(tag in fact for tag in ("[FAKE]", "[MISLEADING]", "[VERIFIED]")):
            try:
                await context.bot.send_photo(chat_id=pub_ch, photo=open(card, "rb"), caption=f"RakshaNet Alert: {fact[:900]}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Read Full Proof", url=purl)]]))
                _yt_bg(locals().get("txt") or locals().get("claim") or locals().get("speech", "")[:180], fact, purl)
            except Exception:
                pass
    except Exception as e:
        await update.message.reply_text(f"[Photo Error] {e}")
    finally:
        if os.path.exists(p):
            os.remove(p)
#
def _watchlist_loop():
    import time, requests
    while True:
        time.sleep(7200)
        try:
            conn = sqlite3.connect(DB_FILE)
            rows = conn.execute("SELECT id, claim, chat_id, checks FROM watchlist WHERE status='PENDING' AND checks < 12").fetchall()
            for wid, wclaim, wchat, wchk in rows:
                heads, fb, purl = deep_verify(wclaim)
                fact = ai_reason(wclaim, heads, fb)
                if any(tag in fact for tag in ("[FAKE]", "[MISLEADING]", "[VERIFIED]")):
                    conn.execute("UPDATE watchlist SET status='RESOLVED', checks=? WHERE id=?", (wchk + 1, wid))
                    msg = f"Watchlist Update: {wclaim[:100]}\n{fact}\nProof: {purl}"
                    if wchat:
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": wchat, "text": msg}, timeout=10)
                    pub_ch = os.environ.get("PUBLIC_CHANNEL", "")
                    if pub_ch:
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": pub_ch, "text": msg}, timeout=10)
                else:
                    conn.execute("UPDATE watchlist SET checks=? WHERE id=?", (wchk + 1, wid))
            conn.commit()
            conn.close()
        except Exception:pass
#

def extract_video_claim(vid_path, speech_text=""):
    import os, base64, requests, cv2
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not groq_key:
        return (speech_text or "")[:300]

    headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
    clean_speech = (speech_text or "").strip()

    if len(clean_speech) >= 25:
        try:
            prompt = (
                "Extract the single main factual, news, political, financial, or public claim from this video transcript "
                "in 1 concise English sentence (max 25 words). If the transcript is purely music lyrics, greetings, "
                "or entertainment with no factual claim, reply with exactly: [NO FACTUAL CLAIM]\n\n"
                f"Transcript:\n{clean_speech[:6000]}"
            )
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 120,
                },
                timeout=20,
            )
            if r.status_code == 200:
                ans = r.json()["choices"][0]["message"]["content"].strip()
                if ans and "[NO FACTUAL CLAIM]" not in ans:
                    return ans
        except Exception:
            pass

    try:
        cap = cv2.VideoCapture(vid_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        frames_b64 = []
        indices = [max(0, int(total * 0.25)), max(0, int(total * 0.65))] if total > 5 else [0]
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if ok and frame is not None:
                ok_enc, buf = cv2.imencode(".jpg", frame)
                if ok_enc:
                    frames_b64.append(base64.b64encode(buf.tobytes()).decode("utf-8"))
        cap.release()

        if frames_b64:
            content = [
                {
                    "type": "text",
                    "text": (
                        "Read any on-screen text, news headline, caption, or factual claim shown in these video frames "
                        "and summarize the main claim in 1 concise English sentence (max 25 words). "
                        "If there is no factual claim or news/text overlay (just music, nature, or pure entertainment), "
                        "reply with exactly: [NO FACTUAL CLAIM]"
                    ),
                }
            ]
            for b64 in frames_b64:
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

            rv = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json={
                    "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                    "messages": [{"role": "user", "content": content}],
                    "temperature": 0.1,
                    "max_tokens": 140,
                },
                timeout=25,
            )
            if rv.status_code == 200:
                vis_ans = rv.json()["choices"][0]["message"]["content"].strip()
                if vis_ans and "[NO FACTUAL CLAIM]" not in vis_ans:
                    return vis_ans
    except Exception:
        pass

    return "[NO FACTUAL CLAIM]"


def extract_video_claim(vid_path, speech_text=""):
    import os, base64, requests, cv2
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not groq_key:
        return (speech_text or "")[:300]

    headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
    clean_speech = (speech_text or "").strip()

    if len(clean_speech) >= 25:
        try:
            prompt = (
                "Extract the single main factual, news, political, financial, or public claim from this video transcript "
                "in 1 concise English sentence (max 25 words). If the transcript is purely music lyrics, greetings, "
                "or entertainment with no factual claim, reply with exactly: [NO FACTUAL CLAIM]\n\n"
                f"Transcript:\n{clean_speech[:6000]}"
            )
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 120,
                },
                timeout=20,
            )
            if r.status_code == 200:
                ans = r.json()["choices"][0]["message"]["content"].strip()
                if ans and "[NO FACTUAL CLAIM]" not in ans:
                    return ans
        except Exception:
            pass

    try:
        cap = cv2.VideoCapture(vid_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        frames_b64 = []
        indices = [max(0, int(total * 0.25)), max(0, int(total * 0.65))] if total > 5 else [0]
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if ok and frame is not None:
                ok_enc, buf = cv2.imencode(".jpg", frame)
                if ok_enc:
                    frames_b64.append(base64.b64encode(buf.tobytes()).decode("utf-8"))
        cap.release()

        if frames_b64:
            content = [
                {
                    "type": "text",
                    "text": (
                        "Read any on-screen text, news headline, caption, or factual claim shown in these video frames "
                        "and summarize the main claim in 1 concise English sentence (max 25 words). "
                        "If there is no factual claim or news/text overlay (just music, nature, or pure entertainment), "
                        "reply with exactly: [NO FACTUAL CLAIM]"
                    ),
                }
            ]
            for b64 in frames_b64:
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

            rv = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json={
                    "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                    "messages": [{"role": "user", "content": content}],
                    "temperature": 0.1,
                    "max_tokens": 140,
                },
                timeout=25,
            )
            if rv.status_code == 200:
                vis_ans = rv.json()["choices"][0]["message"]["content"].strip()
                if vis_ans and "[NO FACTUAL CLAIM]" not in vis_ans:
                    return vis_ans
    except Exception:
        pass

    return "[NO FACTUAL CLAIM]"


def build_pro_short(verdict, claim, fact, out_vid="/tmp/raksha_short.mp4"):
    import os, time, asyncio, subprocess, textwrap, edge_tts
    from PIL import Image, ImageDraw, ImageFont

    ts = int(time.time())
    card_bg = f"/tmp/short_bg_{ts}.png"
    aud = f"/tmp/short_aud_{ts}.mp3"
    vid = out_vid if out_vid else f"/tmp/raksha_short_{ts}.mp4"

    v_up = (verdict or "ALERT").upper()
    if "FAKE" in v_up or "FALSE" in v_up:
        badge_col = (195, 30, 30)
        badge_txt = "FAKE NEWS ALERT"
    elif "MISLEADING" in v_up:
        badge_col = (210, 115, 0)
        badge_txt = "MISLEADING CLAIM"
    elif "TRUE" in v_up or "VERIFIED" in v_up:
        badge_col = (20, 130, 55)
        badge_txt = "VERIFIED FACT"
    else:
        badge_col = (35, 90, 175)
        badge_txt = "FACT CHECK UPDATE"

    img = Image.new("RGB", (720, 1280), (14, 22, 42))
    d = ImageDraw.Draw(img)

    def _font(sz, bold=False):
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        for fp in paths:
            if os.path.exists(fp):
                try:
                    return ImageFont.truetype(fp, sz)
                except Exception:
                    pass
        return ImageFont.load_default()

    f_hdr = _font(30, bold=True)
    f_bdg = _font(32, bold=True)
    f_s = _font(22, bold=True)
    f_b = _font(28, bold=True)
    f_f = _font(25, bold=False)
    f_ft = _font(20, bold=False)

    d.rectangle([(0, 0), (720, 110)], fill=(10, 16, 32))
    d.text((40, 38), "RAKSHANET INDIA  •  FACT CHECK", fill=(255, 255, 255), font=f_hdr)
    d.rectangle([(0, 110), (720, 116)], fill=(245, 165, 35))

    d.rounded_rectangle([(45, 148), (675, 224)], radius=14, fill=badge_col)
    d.text((70, 168), badge_txt, fill=(255, 255, 255), font=f_bdg)

    d.rounded_rectangle([(35, 250), (685, 1130)], radius=22, fill=(248, 250, 253))
    c_txt = (claim or "").replace("₹", "Rs.").strip()
    f_txt = (fact or "").replace("₹", "Rs.").strip()

    d.text((55, 275), "VIRAL CLAIM:", fill=(185, 28, 28), font=f_s)
    d.text((55, 315), textwrap.fill(c_txt[:180], width=34), fill=(20, 20, 20), font=f_b)
    d.line([(55, 535), (665, 535)], fill=(220, 220, 220), width=3)

    d.text((55, 565), "VERIFIED REALITY & PROOF:", fill=(15, 110, 45), font=f_s)
    f_wrap = textwrap.fill(f_txt[:310], width=34)
    d.text((55, 610), f_wrap, fill=(30, 35, 45), font=f_f)

    d.rectangle([(0, 1165), (720, 1280)], fill=(10, 16, 32))
    d.text((45, 1190), "Verify any news: t.me/rakshanet_devansh_bot", fill=(220, 230, 245), font=f_ft)
    d.text((45, 1225), "Live Feed: t.me/RakshaNet_India", fill=(245, 185, 65), font=f_ft)
    img.save(card_bg)

    narration = f"{badge_txt}. Claim: {c_txt[:160]}. Reality: {f_txt[:260]}. Verify news anytime on RakshaNet."
    async def _tts():
        comm = edge_tts.Communicate(narration, "en-IN-NeerjaNeural")
        await comm.save(aud)
    asyncio.run(_tts())

    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-framerate", "2", "-i", card_bg, "-i", aud,
        "-vf", "fade=t=in:st=0:d=0.4",
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1", "-r", "12",
        "-c:a", "aac", "-shortest", "-pix_fmt", "yuv420p", vid
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    for fp in (aud, card_bg):
        if os.path.exists(fp):
            os.remove(fp)
    return vid

def upload_yt_short(claim, fact, purl):
    import datetime, requests
    cid = os.environ.get("YT_CLIENT_ID", "").strip()
    csec = os.environ.get("YT_CLIENT_SECRET", "").strip()
    rtok = os.environ.get("YT_REFRESH_TOKEN", "").strip()
    if not (cid and csec and rtok):
        print("[YT] Missing YT env vars", flush=True)
        return
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("CREATE TABLE IF NOT EXISTS yt_log (id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT, claim TEXT)")
        today = datetime.date.today().isoformat()
        cnt = conn.execute("SELECT COUNT(*) FROM yt_log WHERE day=?", (today,)).fetchone()[0]
        if cnt >= 3:
            conn.close()
            print("[YT] Daily 3-upload limit reached", flush=True)
            return
        conn.execute("INSERT INTO yt_log (day, claim) VALUES (?, ?)", (today, claim[:120]))
        conn.commit()
        conn.close()
        vid = build_pro_short(claim, fact)
        tok_r = requests.post("https://oauth2.googleapis.com/token", data={"client_id": cid, "client_secret": csec, "refresh_token": rtok, "grant_type": "refresh_token"}, timeout=15).json()
        tok = tok_r.get("access_token", "")
        if not tok:
            print(f"[YT Auth Error] {tok_r}", flush=True)
            return
        tag = "[FAKE]" if "[FAKE]" in fact else ("[MISLEADING]" if "[MISLEADING]" in fact else "[VERIFIED]")
        meta = {
            "snippet": {
                "title": f"{tag} {claim[:75]} #Shorts #FactCheck",
                "description": f"{fact}\n\nProof: {purl}\n\nVerify: https://t.me/rakshanet_devansh_bot\nDesk: https://t.me/RakshaNet_India\n#Shorts #FactCheck #India",
                "categoryId": "25"
            },
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
        }
        init_r = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            json=meta, timeout=15
        )
        up_url = init_r.headers.get("Location", "")
        if not up_url:
            print(f"[YT Init Error] {init_r.status_code} {init_r.text[:200]}", flush=True)
            return
        up_r = requests.put(up_url, headers={"Content-Type": "video/mp4"}, data=open(vid, "rb").read(), timeout=60)
        print(f"[YT Uploaded] {up_r.status_code} {up_r.text[:150]}", flush=True)
    except Exception as e:
        print(f"[YT Error] {e}", flush=True)
#
def _yt_bg(q, fact, purl):
    import threading
    threading.Thread(target=upload_yt_short, args=(q, fact, purl), daemon=True).start()
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
app = ApplicationBuilder().token(BOT_TOKEN).write_timeout(30).read_timeout(30).connect_timeout(30).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("radar", radar_cmd))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
app.add_handler(MessageHandler(filters.VIDEO | filters.VOICE | filters.AUDIO | filters.VIDEO_NOTE, handle_media))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(CallbackQueryHandler(button_tap))
import threading as _wt
_wt.Thread(target=_watchlist_loop, daemon=True).start()

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
if os.environ.get("PORT"):
    class H(BaseHTTPRequestHandler):
        def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"RakshaNet OK")
        def do_HEAD(self): self.send_response(200); self.end_headers()
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

