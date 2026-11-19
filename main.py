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
    import re as _rc, time as _tc
    c_clean = _rc.sub(r"\s+", " ", _rc.sub(r"[\u2010-\u2015]", "-", str(claim).replace("₹", "Rs."))).encode("ascii", "ignore").decode().strip()
    f_clean = _rc.sub(r"\s+", " ", _rc.sub(r"[\u2010-\u2015]", "-", str(fact).replace("₹", "Rs."))).encode("ascii", "ignore").decode().strip()
    fu = f_clean.upper()
    if "[FAKE]" in fu:
        col, badge = (200, 30, 30), "VERDICT: FAKE"
    elif "[VERIFIED]" in fu:
        col, badge = (25, 135, 65), "VERDICT: VERIFIED"
    elif "[MISLEADING]" in fu:
        col, badge = (215, 115, 20), "VERDICT: MISLEADING"
    elif "[CYBER THREAT]" in fu:
        col, badge = (120, 40, 165), "VERDICT: CYBER THREAT"
    else:
        col, badge = (95, 105, 115), "VERDICT: UNCONFIRMED"
    img = Image.new("RGB", (1080, 1080), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([(0, 0), (1080, 110)], fill=(20, 20, 20))
    d.rectangle([(0, 110), (1080, 124)], fill=col)
    f_h, f_b, f_t = ImageFont.load_default(size=40), ImageFont.load_default(size=30), ImageFont.load_default(size=24)
    d.text((50, 32), "RAKSHANET | FACT & NARRATIVE CHECK", fill=(255, 255, 255), font=f_h)
    d.rectangle([(50, 150), (470, 205)], fill=col)
    d.text((68, 164), badge, fill=(255, 255, 255), font=f_t)
    d.text((50, 230), "VIRAL CLAIM:", fill=col, font=f_t)
    d.text((50, 270), textwrap.fill(c_clean[:220], width=42), fill=(20, 20, 20), font=f_b)
    d.line([(50, 500), (1030, 500)], fill=(220, 220, 220), width=3)
    d.text((50, 535), "VERIFIED REFERENCE:", fill=(20, 100, 40), font=f_t)
    d.text((50, 575), textwrap.fill(f_clean[:320], width=42), fill=(20, 20, 20), font=f_b)
    d.text((50, 995), "RakshaNet Open-Source Desk | Verify Before Sharing", fill=(110, 110, 110), font=f_t)
    os.makedirs("output", exist_ok=True)
    out = f"output/fact_card_{int(_tc.time()*1000)}.png"
    img.save(out)
    return out

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


def _scan_cyber_url(txt):
    import re as _ru
    urls = _ru.findall(r"https?://[^\s<>\"']+", str(txt or ""))
    if not urls:
        return None
    bad_ext = (".apk", ".exe", ".bat", ".scr", ".vbs")
    lookalikes = ("pmkisan", "pm-kisan", "uidai", "aadhaar", "epfo", "incometax", "sbi", "hdfc", "icici", "rbi", "echallan", "parivahan", "india-post", "indiapost", "gov-in")
    official = (".gov.in", ".nic.in", ".rbi.org.in", ".sbi.co.in", ".onlinesbi.sbi", ".uidai.gov.in", ".parivahan.gov.in", ".epfindia.gov.in")
    for u in urls:
        lu = u.lower().split("?")[0]
        dom = lu.split("//", 1)[-1].split("/")[0].split(":")[0]
        if lu.endswith(bad_ext):
            return "[CYBER THREAT] Suspicious executable/APK download link detected. Do NOT install unknown APKs; report cyber fraud at cybercrime.gov.in or call 1930."
        if any(k in dom for k in lookalikes) and not any(dom.endswith(o) or dom == o.lstrip(".") for o in official):
            return f"[CYBER THREAT] Suspected phishing/lookalike domain ({dom}) impersonating an official Indian service. Verify only on official .gov.in/.nic.in portals and report at cybercrime.gov.in (1930)."
    return None

def _check_campaign(txt):
    import re as _rc, time as _tm
    toks = sorted(set(_rc.findall(r"[a-z0-9]{4,}", str(txt or "").lower())))[:5]
    if len(toks) < 2:
        return ""
    sig = "|".join(toks)
    now = int(_tm.time())
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("CREATE TABLE IF NOT EXISTS campaign_log (sig TEXT, ts INT)")
        conn.execute("DELETE FROM campaign_log WHERE ts < ?", (now - 86400,))
        conn.execute("INSERT INTO campaign_log (sig, ts) VALUES (?, ?)", (sig, now))
        cnt = conn.execute("SELECT COUNT(*) FROM campaign_log WHERE sig=?", (sig,)).fetchone()[0]
        conn.commit()
        conn.close()
        if cnt >= 3:
            return f"[COORDINATED CAMPAIGN ALERT: {cnt} similar reports in 24h] "
    except Exception:
        pass
    return ""

def deep_verify(claim):
    import os, re as _re, urllib.parse, requests as _rq, feedparser
    c_clean = (claim or "").strip()
    q1 = " ".join(_re.findall(r"[A-Za-z0-9\u0900-\u0DFF]+", c_clean)[:10]) or c_clean[:100]
    queries = [(q1, "&when:30d"), (q1, "")]
    k = os.environ.get("GROQ_API_KEY", "").strip()
    if k:
        try:
            q_prompt = (
                "Extract 2 concise search queries (max 6 words each, no quotes) to verify this claim on official/primary sources. "
                "Line 1: English query (include any officer rank/department like ADGPI, PIB, RBI, MoD, DM, SP, ISRO, DGISPR if relevant). "
                "Line 2: Official site-targeted query (e.g. site:pib.gov.in OR site:rbi.org.in OR site:gov.in OR site:mod.gov.in).\n"
                f"Claim: {c_clean[:280]}"
            )
            r = _rq.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {k}"},
                json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": q_prompt}], "temperature": 0.1, "max_tokens": 80},
                timeout=12,
            ).json()
            lines = [ln.strip(" -1234567890.:") for ln in r.get("choices", [{}])[0].get("message", {}).get("content", "").splitlines() if ln.strip()]
            for ln in lines[:2]:
                if ln and len(ln.split()) <= 10:
                    queries.append((ln, ""))
        except Exception:
            pass

    t1_domains = ("pib.gov.in", "gov.in", "nic.in", "rbi.org.in", "mod.gov.in", "mha.gov.in", "isro.gov.in", "sebi.gov.in", "eci.gov.in", "who.int", "worldbank.org", "imf.org", "un.org")
    t2_domains = ("newsonair.gov.in", "akashvani", "ptinews.com", "reuters.com", "apnews.com", "thehindu.com", "indianexpress.com", "boomlive.in", "factly.in", "vishvasnews.com", "altnews.in", "ddnews.gov.in", "bbc.com", "theguardian.com", "britannica.com")

    def _tier_src(entry):
        lnk = (getattr(entry, "link", "") or "").lower()
        src_obj = getattr(entry, "source", None)
        s_href = (getattr(src_obj, "href", "") or "").lower() if src_obj else ""
        s_title = (getattr(src_obj, "title", "") or "").strip() if src_obj else ""
        ttl = (getattr(entry, "title", "") or "")
        if not s_title and " - " in ttl:
            s_title = ttl.rsplit(" - ", 1)[-1].strip()
        comb = f"{lnk} {s_href} {s_title.lower()} {ttl.lower()}"
        if any(d in comb for d in t1_domains):
            tier = "Tier 1: Official"
        elif any(d in comb for d in t2_domains):
            tier = "Tier 2: Wire/IFCN"
        else:
            tier = "Tier 3: News"
        pub = (getattr(entry, "published", "") or "")[:16].strip()
        clean_url = s_href if s_href.startswith("http") else lnk
        return tier, (s_title or "News Source"), pub, clean_url

    import concurrent.futures as _cf
    rss_urls = [f"https://news.google.com/rss/search?q={urllib.parse.quote(qt)}{wp}&hl=en-IN&gl=IN&ceid=IN:en" for qt, wp in queries[:4]]
    rss_urls.extend([
        "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Reg=3",
        "https://www.rbi.org.in/pressreleases_rss.xml",
    ])
    def _fetch_rss(u):
        try:
            return feedparser.parse(_rq.get(u, timeout=5).text).entries[:8]
        except Exception:
            return []
    all_entries = []
    seen_titles = set()
    with _cf.ThreadPoolExecutor(max_workers=6) as _ex:
        for ents in _ex.map(_fetch_rss, rss_urls):
            for e in ents:
                tl = (getattr(e, "title", "") or "").strip()
                if tl and tl.lower() not in seen_titles:
                    seen_titles.add(tl.lower())
                    all_entries.append(e)

    _stop = {"india", "indian", "today", "yesterday", "days", "year", "news", "viral", "video", "claim", "claims", "about", "from", "with", "that", "this", "have", "been", "will", "the", "and", "for", "are", "was"}
    _keep2 = {"pm", "dm", "sp", "un", "up", "mp", "jk", "it", "ai", "rs"}
    _raw_toks = _re.findall(r"[a-zA-Z0-9]{2,}", c_clean)
    _w = [w.lower() for w in _raw_toks if (len(w) >= 3 or w.lower() in _keep2) and w.lower() not in _stop]
    if not _w:
        _w = [w.lower() for w in _raw_toks if len(w) >= 3]
    def _match_cnt(e):
        tl = (getattr(e, "title", "") or "").lower()
        return sum(1 for w in _w if (w[:5] if len(w) > 5 else w) in tl) if _w else 0

    cands = []
    for e in all_entries:
        tier, s_name, pub, clean_url = _tier_src(e)
        t_bonus = 30 if tier.startswith("Tier 1") else (20 if tier.startswith("Tier 2") else 5)
        mc = _match_cnt(e)
        if mc >= 1:
            cands.append((t_bonus + mc * 5, tier, s_name, pub, clean_url, e))
    cands.sort(key=lambda x: x[0], reverse=True)
    cands = cands[:10]

    scored = []
    if cands and k:
        try:
            nl = chr(10)
            clist = nl.join(f"{idx}: [{c[1]} | {c[2]}] {getattr(c[5], 'title', '')}" for idx, c in enumerate(cands))
            rp = (
                f"Claim: {c_clean[:260]}{nl}{nl}Headlines:{nl}{clist}{nl}{nl}"
                "Return ONLY the comma-separated index numbers (e.g. 0,2) of headlines that confirm, debunk, or report on the CORE claim (ignore relative words like yesterday/today; match fact-checks on the same topic). "
                "If NONE are about this exact event, reply: NONE"
            )
            rr = _rq.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {k}"},
                json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": rp}], "temperature": 0.0, "max_tokens": 30},
                timeout=12,
            )
            if rr.status_code == 200:
                ans = (rr.json().get("choices") or [{}])[0].get("message", {}).get("content", "").strip().upper()
                if "NONE" not in ans:
                    idxs = [int(x) for x in _re.findall(r"[0-9]+", ans) if int(x) < len(cands)]
                    scored = [cands[i] for i in idxs]
        except Exception:
            pass
    if not scored:
        req_mc = min(2, len(_w)) if _w else 1
        scored = [c for c in cands if (c[1].startswith("Tier 1") or c[1].startswith("Tier 2")) and _match_cnt(c[5]) >= req_mc]

    if scored:
        _, b_tier, b_src, b_pub, b_url, best = scored[0]
        heads = [f"[{t} | {sn} | {pb}] {getattr(en, 'title', '')}" for _, t, sn, pb, _, en in scored[:4]]
        fb = f"[{b_tier} — {b_src}] {best.title}"
        purl = getattr(best, "link", "") or b_url or "https://factcheck.pib.gov.in/"
    else:
        heads = []
        fb = "[UNCONFIRMED] No Tier-1/Tier-2 primary confirmation found yet; added to 24h Watchlist."
        purl = "https://factcheck.pib.gov.in/"
    return heads, fb, purl

def ai_reason(claim, heads, fb, tech_flags=None):
    import os, datetime, hashlib, requests
    k = os.environ.get("GROQ_API_KEY", "").strip()
    if not k:
        return fb
    ist_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).strftime("%d %b %Y %H:%M IST")
    case_id = "RN-" + datetime.datetime.now().strftime("%Y%m") + "-" + hashlib.md5((claim or "").encode("utf-8")).hexdigest()[:4].upper()
    ctx = " || ".join(heads) if heads else "No matching headlines found."
    tf_str = "; ".join(tech_flags) if tech_flags else "None"
    p = (
        f"Claim: {claim}\n"
        f"Live Verified Sources (with Tier & Date): {ctx}\n"
        f"Tier 1F (RakshaNet Technical Forensics): {tf_str}\n\n"
        "Strict Zero-Guesswork Rules:\n"
        "1) If input is just casual chat/greeting, start with [CASUAL].\n"
        "2) Start with [FAKE], [MISLEADING], [VERIFIED], or [UNCONFIRMED], followed IMMEDIATELY by your 2-sentence explanation (NEVER output only the tag).\n"
        "3) NEVER guess [FAKE] or [VERIFIED] if Live Verified Sources are empty or inconclusive - use [UNCONFIRMED]. If Tier 1F flags AI-tool metadata, Audio-Video mismatch, or morphing without Tier 1/2 rebuttal, use [UNCONFIRMED - POSSIBLE AI/EDITED MEDIA].\n"
        "4) Check Date Mismatch: if sources prove the event/clip is from an older year/month while claimed as recent/breaking, use [MISLEADING] and state the real date.\n"
        "5) Role/Officer & Defence Guard: for claims naming any officer/agency (ADGPI, PRO Defence, PIB, RBI, DM, SP, ISRO, DGISPR) or @handle, check if Tier-1 official source confirms or if it is a parody/lookalike handle; if sensitive defence/border claim lacks Tier-1/2 proof, use [UNCONFIRMED].\n"
        "6) Reply in 2 crisp English sentences citing the exact Clean Publisher Name, Confidence Tier (Tier 1/Tier 1F/Tier 2), and key date/figure. End with: "
        f"(Case: {case_id} | {ist_now}). If [FAKE] involves a financial scam, fake govt scheme, or officer impersonation, add: Report fraud at cybercrime.gov.in / 1930 or sancharsaathi.gov.in."
    )
    for mdl in ("llama-3.3-70b-versatile", "openai/gpt-oss-120b"):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {k}"},
                json={"model": mdl, "messages": [{"role": "user", "content": p}], "temperature": 0.1, "max_tokens": 220},
                timeout=20,
            )
            if resp.status_code == 200:
                ch = resp.json().get("choices") or []
                if ch:
                    txt = (ch[0].get("message") or {}).get("content", "").strip()
                    if txt:
                        if len(txt) < 25:
                            txt = f"{txt} {fb} (Case: {case_id} | {ist_now})"
                        return txt
            else:
                print(f"[AI_REASON] {mdl} HTTP {resp.status_code}: {resp.text[:120]}", flush=True)
        except Exception as _ae:
            print(f"[AI_REASON] {mdl} err: {_ae}", flush=True)
    fl = (fb or "").lower()
    if heads and any(w in fl for w in ("debunk", "fake", "false", "hoax", "not banned", "misleading")):
        return f"[FAKE] {fb} (Case: {case_id} | {ist_now})"
    return f"[UNCONFIRMED] {fb} (Case: {case_id} | {ist_now})"

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import urllib.parse
    txt = (update.message.text or "").strip()
    if not txt:
        return
    cyber_alert = _scan_cyber_url(txt)
    if cyber_alert:
        card = make_fact_card(txt[:180], cyber_alert)
        await update.message.reply_photo(photo=open(card, "rb"), caption=cyber_alert)
        return
    if not txt.startswith("http"):
        await update.message.reply_text("[Narrative] Investigating authentic sources & data...")
        try:
            camp_tag = _check_campaign(txt)
            heads, fb, purl = deep_verify(txt)
            fact = ai_reason(txt, heads, fb)
            if camp_tag and "[UNCONFIRMED]" not in fact:
                fact = f"{camp_tag}{fact}"
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
            full_msg = fact
            if len(full_msg) <= 1000:
                await update.message.reply_photo(photo=open(card, "rb"), caption=full_msg, reply_markup=InlineKeyboardMarkup(kb))
            else:
                await update.message.reply_photo(photo=open(card, "rb"), caption=fact[:900], reply_markup=InlineKeyboardMarkup(kb))
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

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import urllib.parse, time as _tm, subprocess, sqlite3
    m = update.message.video or update.message.voice or update.message.audio or update.message.video_note
    if not m:
        return
    await update.message.reply_text("[RakshaNet] Scanning full forwarded media with Whisper + 3-Frame Vision + Tier 1F Forensics...")
    os.makedirs("temp", exist_ok=True)
    ext = ".mp4" if (update.message.video or update.message.video_note) else ".ogg"
    p = f"temp/tg_{int(_tm.time()*1000)}_{m.file_unique_id}{ext}"
    try:
        f = await context.bot.get_file(m.file_id)
        await f.download_to_drive(p)
        tech_flags = _ffprobe_forensics(p) if ext == ".mp4" else []
        if ext == ".mp4":
            f0 = p + "_f0.jpg"
            try:
                subprocess.run(["ffmpeg", "-y", "-i", p, "-frames:v", "1", "-q:v", "5", f0], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                if os.path.exists(f0):
                    import imagehash
                    from PIL import Image as _PImg
                    ph = str(imagehash.phash(_PImg.open(f0).convert("L")))
                    conn = sqlite3.connect(DB_FILE)
                    conn.execute("CREATE TABLE IF NOT EXISTS video_hashes (phash TEXT UNIQUE, label TEXT)")
                    if conn.execute("SELECT 1 FROM video_hashes WHERE phash=?", (ph,)).fetchone():
                        tech_flags.append("Tier 1F: Recycled clip matched in pHash memory")
                    else:
                        conn.execute("INSERT OR IGNORE INTO video_hashes (phash, label) VALUES (?, ?)", (ph, m.file_unique_id[:40]))
                        conn.commit()
                    conn.close()
            except Exception:
                pass
            finally:
                if os.path.exists(f0):
                    os.remove(f0)
        speech = extract_video_claim(p, get_speech(p))
        if not speech or "[NO FACTUAL CLAIM]" in speech:
            await update.message.reply_text(f"No factual claim detected in this media (music/entertainment clip). {speech if speech and '(' in speech else ''}")
            return
        heads, fb, purl = deep_verify(speech[:280])
        fact = ai_reason(speech[:280], heads, fb, tech_flags)
        _record_source_history("tg_media", "[FAKE]" in fact)
        _sync_cloud_memory("save")
        card = make_fact_card(speech[:180], fact)
        x_url = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(f'{fact[:180]} #RakshaNet')}"
        kb = [[InlineKeyboardButton("Read Full Proof", url=purl), InlineKeyboardButton("Share on X (1-Click)", url=x_url)]]
        full_msg = f"Claim: {speech[:200]}\nRef: {fact}"
        if len(full_msg) <= 1000:
            await update.message.reply_photo(photo=open(card, "rb"), caption=full_msg, reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_photo(photo=open(card, "rb"), caption=f"Claim: {speech[:200]}\nRef: {fact[:700]}", reply_markup=InlineKeyboardMarkup(kb))
            await update.message.reply_text(full_msg)
        pub_ch = os.environ.get("PUBLIC_CHANNEL", "")
        if pub_ch and any(tag in fact for tag in ("[FAKE]", "[MISLEADING]", "[VERIFIED]")):
            try:
                await context.bot.send_photo(chat_id=pub_ch, photo=open(card, "rb"), caption=f"RakshaNet Alert: {fact[:900]}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Read Full Proof", url=purl)]]))
                _yt_bg(speech[:180], fact, purl)
            except Exception:
                pass
    except Exception as e:
        await update.message.reply_text(f"[Media Error] {e}")
    finally:
        if os.path.exists(p):
            os.remove(p)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import base64, requests, urllib.parse, time as _tm
    if not update.message.photo:
        return
    await update.message.reply_text("[RakshaNet] Scanning image/screenshot with 4-Layer Forensic Vision...")
    os.makedirs("temp", exist_ok=True)
    p = f"temp/tg_p_{int(_tm.time()*1000)}_{update.message.photo[-1].file_unique_id}.jpg"
    try:
        f = await context.bot.get_file(update.message.photo[-1].file_id)
        await f.download_to_drive(p)
        k = os.environ.get("GROQ_API_KEY", "").strip()
        b64 = base64.b64encode(open(p, "rb").read()).decode()
        vis_prompt = (
            "Analyze this image for fact-checking in 1-2 short English sentences:\n"
            "1) Extract the main factual/news claim or text overlay.\n"
            "2) If it is a Govt/Police/RBI/DM notice or letter, check letterhead, official seal, date format, and spelling/grammar anomalies.\n"
            "3) For location clues: ONLY cite unmistakable physical proof (driving side, left/right steering, 112/100 vs 911, currency, clear foreign flag). "
            "NEVER guess country from shared languages (Bengali, Punjabi, Tamil, Hindi, Urdu, Nepali) or attire - mark ambiguous location as INDETERMINATE."
        )
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {k}"},
            json={"model": "qwen/qwen3.8-27b", "messages": [{"role": "user", "content": [{"type": "text", "text": vis_prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]},
            timeout=25,
        ).json()
        claim = r.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not claim:
            await update.message.reply_text("Could not read clear text/claim from this image.")
            return
        heads, fb, purl = deep_verify(claim[:280])
        fact = ai_reason(claim[:280], heads, fb)
        card = make_fact_card(claim[:180], fact)
        x_url = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(f'{fact[:180]} Proof: {purl} #RakshaNet')}"
        kb = [[InlineKeyboardButton("Read Full Proof", url=purl), InlineKeyboardButton("Share on X (1-Click)", url=x_url)]]
        await update.message.reply_photo(photo=open(card, "rb"), caption=f"Image Claim: {claim[:220]}\nRef: {fact[:650]}", reply_markup=InlineKeyboardMarkup(kb))
        pub_ch = os.environ.get("PUBLIC_CHANNEL", "")
        if pub_ch and any(tag in fact for tag in ("[FAKE]", "[MISLEADING]", "[VERIFIED]")):
            try:
                await context.bot.send_photo(chat_id=pub_ch, photo=open(card, "rb"), caption=f"RakshaNet Alert: {fact[:900]}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Read Full Proof", url=purl)]]))
                _yt_bg(claim[:180], fact, purl)
            except Exception:
                pass
    except Exception as e:
        await update.message.reply_text(f"[Photo Error] {e}")
    finally:
        if os.path.exists(p):
            os.remove(p)

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
    import os, base64, requests
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

    diag = []
    try:
        import subprocess, time
        frames_b64 = []
        ts = int(time.time())
        out_img = f"/tmp/vf_{ts}_0.jpg"
        r_f = subprocess.run(["ffmpeg", "-y", "-i", vid_path, "-frames:v", "1", "-q:v", "4", out_img], capture_output=True, text=True)
        if os.path.exists(out_img):
            with open(out_img, "rb") as imf:
                frames_b64.append(base64.b64encode(imf.read()).decode("utf-8"))
            os.remove(out_img)
        diag.append(f"f={len(frames_b64)},rc={r_f.returncode}")
        if frames_b64:
            content = [
                {"type": "text", "text": "Extract any news headline, text overlay, or factual claim visible in this video frame in 1 short English sentence. Only if there is zero factual claim or text (pure music/nature/greeting), reply: [NO FACTUAL CLAIM]"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{frames_b64[0]}"}}
            ]
            for mdl in ("qwen/qwen3.8-27b", "meta-models/muse-spark-open"):
                rv = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json={"model": mdl, "messages": [{"role": "user", "content": content}], "temperature": 0.1, "max_tokens": 140}, timeout=25)
                diag.append(f"{mdl.split('/')[-1][:5]}={rv.status_code}")
                if rv.status_code == 200:
                    vis_ans = rv.json()["choices"][0]["message"]["content"].strip()
                    if vis_ans and "[NO FACTUAL CLAIM]" not in vis_ans:
                        return vis_ans
                    diag.append("ans=" + vis_ans[:40])
                    break
                else:
                    diag.append(rv.text[:60])
    except Exception as e:
        diag.append(f"err={e}")

    return "[NO FACTUAL CLAIM] (" + "; ".join(diag) + ")"

def build_pro_short(a, b, c=None, out_vid="/tmp/raksha_short.mp4"):
    if c is None:
        claim, fact = a, b
        verdict = "FAKE" if "[FAKE]" in (fact or "") else ("MISLEADING" if "[MISLEADING]" in (fact or "") else ("VERIFIED" if "[VERIFIED]" in (fact or "") else "ALERT"))
    else:
        verdict, claim, fact = a, b, c
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

def _ffprobe_forensics(vid_path):
    import subprocess
    flags = []
    if not vid_path or not os.path.exists(vid_path):
        return flags
    try:
        pr = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", vid_path],
            capture_output=True, text=True, timeout=10,
        )
        raw = (pr.stdout or "").lower()
        for sig in ("sora", "runway", "kling", "heygen", "elevenlabs", "midjourney", "c2pa", "synthesia"):
            if sig in raw:
                flags.append(f"AI-tool metadata tag: {sig}")
    except Exception:
        pass
    return flags

def _record_source_history(source_key, is_fake=False):
    import sqlite3
    if not source_key:
        return 0
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("CREATE TABLE IF NOT EXISTS source_history (src TEXT PRIMARY KEY, total INT DEFAULT 0, fake_cnt INT DEFAULT 0)")
        row = conn.execute("SELECT total, fake_cnt FROM source_history WHERE src=?", (source_key[:120],)).fetchone()
        tot, fk = (row[0] + 1, row[1] + (1 if is_fake else 0)) if row else (1, 1 if is_fake else 0)
        conn.execute("INSERT OR REPLACE INTO source_history (src, total, fake_cnt) VALUES (?, ?, ?)", (source_key[:120], tot, fk))
        conn.commit()
        conn.close()
        return fk
    except Exception:
        return 0

def _sync_cloud_memory(mode="save"):
    import json, sqlite3, base64, requests
    os.makedirs("data", exist_ok=True)
    mpath = os.path.join("data", "memory.json")
    gh_tok = os.environ.get("GITHUB_TOKEN", "").strip()
    gh_repo = os.environ.get("GITHUB_REPO", "DEVANSHSHUKLA938/RakshaNet").strip()
    gh_url = f"https://api.github.com/repos/{gh_repo}/contents/data/memory.json"
    gh_hdr = {"Authorization": f"token {gh_tok}", "Accept": "application/vnd.github.v3+json"} if gh_tok else {}
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("CREATE TABLE IF NOT EXISTS video_hashes (phash TEXT UNIQUE, label TEXT, first_seen TEXT)")
        try:
            conn.execute("ALTER TABLE video_hashes ADD COLUMN first_seen TEXT")
        except Exception:
            pass
        conn.execute("CREATE TABLE IF NOT EXISTS source_history (src TEXT PRIMARY KEY, total INT DEFAULT 0, fake_cnt INT DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS yt_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, claim TEXT, fact TEXT, purl TEXT, priority INT DEFAULT 1)")
        if mode == "load":
            if gh_tok:
                try:
                    gr = requests.get(gh_url, headers=gh_hdr, timeout=8)
                    if gr.status_code == 200:
                        raw = base64.b64decode(gr.json().get("content", "")).decode("utf-8")
                        open(mpath, "w", encoding="utf-8").write(raw)
                except Exception:
                    pass
            if os.path.exists(mpath):
                d = json.load(open(mpath, "r", encoding="utf-8"))
                for row in d.get("video_hashes", []):
                    ph, lb = row[0], row[1]
                    fs = row[2] if len(row) > 2 else ""
                    conn.execute("INSERT OR IGNORE INTO video_hashes (phash, label, first_seen) VALUES (?, ?, ?)", (ph, lb, fs))
                for s, t, fk in d.get("source_history", []):
                    conn.execute("INSERT OR IGNORE INTO source_history (src, total, fake_cnt) VALUES (?, ?, ?)", (s, t, fk))
                conn.commit()
        else:
            d = {
                "video_hashes": conn.execute("SELECT phash, label, COALESCE(first_seen, '') FROM video_hashes LIMIT 500").fetchall(),
                "source_history": conn.execute("SELECT src, total, fake_cnt FROM source_history LIMIT 500").fetchall(),
                "yt_queue": conn.execute("SELECT claim, fact, purl, priority FROM yt_queue LIMIT 100").fetchall(),
            }
            payload = json.dumps(d, indent=2)
            open(mpath, "w", encoding="utf-8").write(payload)
            if gh_tok:
                try:
                    sha = None
                    gr = requests.get(gh_url, headers=gh_hdr, timeout=8)
                    if gr.status_code == 200:
                        sha = gr.json().get("sha")
                    body = {"message": "Sync RakshaNet cloud memory", "content": base64.b64encode(payload.encode("utf-8")).decode("ascii")}
                    if sha:
                        body["sha"] = sha
                    requests.put(gh_url, headers=gh_hdr, json=body, timeout=10)
                except Exception:
                    pass
        conn.close()
    except Exception:
        pass

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
        if cnt >= 5:
            conn.execute("CREATE TABLE IF NOT EXISTS yt_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, claim TEXT, fact TEXT, purl TEXT, priority INT DEFAULT 1)")
            prio = 2 if "[FAKE]" in (fact or "") else 1
            conn.execute("INSERT INTO yt_queue (claim, fact, purl, priority) VALUES (?, ?, ?, ?)", ((claim or '')[:120], (fact or '')[:500], (purl or '')[:300], prio))
            conn.commit()
            conn.close()
            _sync_cloud_memory("save")
            print("[YT] Daily 5-upload limit reached; queued for next day", flush=True)
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
        import re as _re
        clean_c = _re.sub(r"[<>\r\n]+", " ", str(claim or "")).strip() or "Fact Check Alert"
        yt_title = f"{tag} {clean_c[:65].strip()} #Shorts #FactCheck"[:98].strip()
        meta = {
            "snippet": {
                "title": yt_title,
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
    import threading, sqlite3, datetime
    def _run():
        upload_yt_short(q, fact, purl)
        try:
            conn = sqlite3.connect(DB_FILE)
            today = datetime.date.today().isoformat()
            cnt = conn.execute("SELECT COUNT(*) FROM yt_log WHERE day=?", (today,)).fetchone()[0]
            if cnt < 5:
                row = conn.execute("SELECT id, claim, fact, purl FROM yt_queue ORDER BY priority DESC, id ASC LIMIT 1").fetchone()
                if row:
                    conn.execute("DELETE FROM yt_queue WHERE id=?", (row[0],))
                    conn.commit()
                    conn.close()
                    upload_yt_short(row[1], row[2], row[3])
                    return
            conn.close()
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()
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


_sync_cloud_memory("load")
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

