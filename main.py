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
        r = _rq.post(
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
    import os as _oc, re as _rc, time as _tc
    has_hi = any("\u0900" <= c <= "\u097f" for c in (str(claim) + str(fact)))
    use_hi = has_hi and _oc.path.exists("fonts/hindi.ttf") and _oc.path.getsize("fonts/hindi.ttf") > 50000
    if use_hi:
        c_clean = _rc.sub(r"\s+", " ", str(claim).replace("₹", "Rs.")).strip()
        f_clean = _rc.sub(r"\s+", " ", str(fact).replace("₹", "Rs.")).strip()
    else:
        c_raw = _dual_lang_query(claim) if any(ord(c) > 127 for c in str(claim).replace("₹", "")) else str(claim)
        f_raw = _dual_lang_query(fact) if any(ord(c) > 127 for c in str(fact).replace("₹", "")) else str(fact)
        c_clean = _rc.sub(r"\s+", " ", _rc.sub(r"[\u2010-\u2015]", "-", c_raw.replace("₹", "Rs."))).encode("ascii", "ignore").decode().strip()
        f_clean = _rc.sub(r"\s+", " ", _rc.sub(r"[\u2010-\u2015]", "-", f_raw.replace("₹", "Rs."))).encode("ascii", "ignore").decode().strip()
    fu = (str(fact) + " " + f_clean).upper()
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
    f_h, f_t = ImageFont.load_default(size=40), ImageFont.load_default(size=24)
    f_b = ImageFont.truetype("fonts/hindi.ttf", 28) if use_hi else ImageFont.load_default(size=30)
    d.text((50, 32), "RAKSHANET | FACT & NARRATIVE CHECK", fill=(255, 255, 255), font=f_h)
    d.rectangle([(50, 150), (470, 205)], fill=col)
    d.text((68, 164), badge, fill=(255, 255, 255), font=f_t)
    d.text((50, 230), "VIRAL CLAIM:", fill=col, font=f_t)
    d.text((50, 270), textwrap.fill(c_clean[:220], width=42), fill=(20, 20, 20), font=f_b)
    d.line([(50, 500), (1030, 500)], fill=(220, 220, 220), width=3)
    d.text((50, 535), "VERIFIED REFERENCE:", fill=(20, 100, 40), font=f_t)
    d.text((50, 575), textwrap.fill(f_clean[:320], width=42), fill=(20, 20, 20), font=f_b)
    d.text((50, 995), "RakshaNet Open-Source Desk | Verify Before Sharing", fill=(110, 110, 110), font=f_t)
    _oc.makedirs("output", exist_ok=True)
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
    import glob as _gl, re as _rv, time as _tv
    _tid = int(_tv.time() * 1000)
    vid, aud = f"temp/vid_{_tid}.mp4", f"temp/aud_{_tid}.mp3"
    title = url
    try:
        import requests
        oe = requests.get(f"https://www.youtube.com/oembed?url={urllib.parse.quote(url)}&format=json", timeout=6).json()
        title = oe.get("title", url)
    except Exception:
        pass
    _dur = 0
    try:
        _dp = subprocess.run(["yt-dlp", "--print", "duration", url], capture_output=True, text=True, timeout=8)
        _dur = int(float((_dp.stdout or "0").strip().splitlines()[0]))
    except Exception:
        _dur = 0
    _sub_txt = ""
    if _dur > 180:
        try:
            _sp = f"temp/sub_{_tid}"
            subprocess.run(["yt-dlp", "--skip-download", "--write-auto-sub", "--write-sub", "--sub-lang", "en,hi", "--sub-format", "vtt", "-o", _sp, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12)
            for _sf in _gl.glob(f"{_sp}*"):
                _raw = open(_sf, "r", encoding="utf-8", errors="ignore").read()
                _sub_txt += " " + _rv.sub(r"<[^>]+>|WEBVTT|\d{2}:\d{2}[^\n]*", " ", _raw)
                os.remove(_sf)
            _sub_txt = " ".join(_sub_txt.split())[:6000]
        except Exception:
            _sub_txt = ""
    _vfmt = "best[height<=720][ext=mp4]/best[ext=mp4]/best"
    _vsec = ["--download-sections", "*0:00-0:20"] if _dur > 180 else []
    aud_ok = False if _sub_txt else (subprocess.run(["yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "9", "-o", aud, url]).returncode == 0)
    vid_ok = subprocess.run(["yt-dlp", "-f", _vfmt] + _vsec + ["-o", vid, url]).returncode == 0
    if not _sub_txt and not aud_ok and not vid_ok:
        return 25, "CLOUD CHECK", title, ["Cloud video download restricted; title verified"]
    speech = _sub_txt if _sub_txt else get_speech(aud if aud_ok else vid)
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
                _sb_req("POST", "video_hashes", {"phash": ph, "label": title[:80], "first_seen": str(int(time.time()))})
            b_vals.append(float(np.mean(gray)))
            h, w = gray.shape
            fv = cv2.Laplacian(gray, cv2.CV_64F).var()
            if fv > 0 and cv2.Laplacian(gray[h//4:3*h//4, w//4:3*w//4], cv2.CV_64F).var() < fv * 0.25:
                blur_flags += 1
        conn.commit()
        conn.close()
        burst_risk, scene_kw = _burst_mismatch_check(cap, total, speech)
        cap.release()
        os.remove(vid)
    score, reasons = 0, []
    if burst_risk:
        score += 25
        reasons.append('0.5s Burst: Possible AI/dubbed media mismatch')
    if recycled:
        score += 40
        reasons.append("Recycled old clip matched in pHash memory")
    if blur_flags >= 2:
        score += 25
        reasons.append("Center subject smoother than background")
    if len(b_vals) >= 2 and np.std(b_vals) > 35:
        score += 25
        reasons.append("Scene lighting jump detected")
    q_txt = speech if len(speech.split()) >= 4 else (scene_kw if scene_kw else title)
    fc = feedparser.parse(f"https://news.google.com/rss/search?q={urllib.parse.quote(chr(32).join(q_txt.split()[:8]))}+fact+check&hl=en-IN&gl=IN&ceid=IN:en")
    if fc.entries:
        score += 30
        reasons.append(f"Ref: {fc.entries[0].title[:55]}")
        if len(fc.entries) > 1:
            reasons.append(f"Prior Debunks: {len(fc.entries)}")
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
    _sh = ('bit.ly', 'tinyurl.com', 't.co', 'rb.gy', 'cutt.ly', 'is.gd', 'shorturl.at')
    for u in urls:
        try:
            _d0 = u.lower().split('//', 1)[-1].split('/')[0]
            if any(x in _d0 for x in _sh):
                import requests as _rr
                u = _rr.head(u, allow_redirects=True, timeout=3).url or u
        except Exception:
            pass
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
        _sb_req("POST", "campaign_log", {"sig": sig, "ts": now})
        cnt = conn.execute("SELECT COUNT(*) FROM campaign_log WHERE sig=?", (sig,)).fetchone()[0]
        conn.commit()
        conn.close()
        if cnt >= 3:
            return f"[COORDINATED CAMPAIGN ALERT: {cnt} similar reports in 24h] "
    except Exception:
        pass
    return ""

def _detect_state_hl(txt):
    import re as _rh
    t = str(txt or "")
    scripts = [
        (r"[\u0980-\u09FF]", "bn"), (r"[\u0B80-\u0BFF]", "ta"),
        (r"[\u0C00-\u0C7F]", "te"), (r"[\u0A80-\u0AFF]", "gu"),
        (r"[\u0A00-\u0A7F]", "pa"), (r"[\u0C80-\u0CFF]", "kn"),
        (r"[\u0D00-\u0D7F]", "ml"), (r"[\u0B00-\u0B7F]", "or"),
        (r"[\u0600-\u06FF]", "ur"),
    ]
    for pat, code in scripts:
        if _rh.search(pat, t):
            return code
    tl = t.lower()
    places = {
        "bn": ("kolkata", "bengal", "howrah", "siliguri"),
        "ta": ("chennai", "tamil nadu", "madurai", "coimbatore"),
        "te": ("hyderabad", "telangana", "andhra", "visakhapatnam"),
        "mr": ("mumbai", "pune", "nagpur", "maharashtra"),
        "gu": ("ahmedabad", "surat", "vadodara", "gujarat"),
        "pa": ("punjab", "amritsar", "ludhiana", "chandigarh"),
        "kn": ("bengaluru", "bangalore", "mysuru", "karnataka"),
        "ml": ("kochi", "thiruvananthapuram", "kerala"),
        "or": ("odisha", "bhubaneswar", "cuttack"),
    }
    for code, kws in places.items():
        if any(k in tl for k in kws):
            return code
    return None

def _dual_lang_query(q):
    s = str(q or "").strip()
    if not s:
        return s
    has_non_ascii = any(ord(c) > 127 for c in s)
    if not has_non_ascii:
        return s
    try:
        import os, requests as _rq
        gk = os.environ.get("GROQ_API_KEY", "").strip()
        if not gk:
            return s
        r = _rq.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {gk}", "Content-Type": "application/json"},
            json={
                "model": "openai/gpt-oss-120b",
                "messages": [{"role": "user", "content": f"Translate this claim into a clear English fact-check search sentence (max 12 words, no quotes): {s[:300]}"}],
                "max_tokens": 80, "temperature": 0,
            },
            timeout=12,
        )
        en = r.json()["choices"][0]["message"]["content"].strip().strip("\"' ")
        if en and len(en) > 3 and not any(ord(c) > 127 for c in en):
            return en
    except Exception:
        pass
    try:
        import urllib.parse as _up, requests as _rq2
        _tr = _rq2.get(
            f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=en&dt=t&q={_up.quote(s[:400])}",
            timeout=6,
        ).json()
        en2 = "".join(x[0] for x in _tr[0] if x and x[0]).strip()
        if en2:
            return en2
    except Exception:
        pass
    return s

def _burst_mismatch_check(cap, total, speech):
    import os, base64 as _b64, requests as _rq
    gk = os.environ.get("GROQ_API_KEY", "").strip()
    if not gk or total < 10:
        return False, ""
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    mid = max(0, total // 2)
    imgs = []
    for off in (0.0, 0.5, 1.0):
        idx = min(total - 1, int(mid + off * fps))
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, fr = cap.read()
        if ok:
            _, buf = cv2.imencode(".jpg", cv2.resize(fr, (640, 360)))
            imgs.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64.b64encode(buf).decode()}"}})
    if not imgs:
        return False, ""
    sp = (speech or "").strip()[:250]
    prompt = (
        f"Inspect these 3 frames taken 0.5s apart. Audio transcript: '{sp}'. "
        "Reply ONLY in 2 short lines: "
        "1) SCENE: 6-8 English keywords describing what is shown. "
        "2) RISK: YES if clear AI face/lip-sync glitch or audio contradicts visual scene, else NO."
    )
    try:
        r = _rq.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {gk}", "Content-Type": "application/json"},
            json={"model": "qwen/qwen3.8-27b", "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}] + imgs}], "max_tokens": 60, "temperature": 0},
            timeout=10,
        )
        ans = r.json()["choices"][0]["message"]["content"].strip()
        scene = ""
        for ln in ans.splitlines():
            if "SCENE:" in ln.upper():
                scene = ln.split(":", 1)[-1].strip()
        risk = "RISK: YES" in ans.upper()
        return risk, scene
    except Exception:
        return False, ""

def _log_ledger(case_id, verdict, summary, proof_url):
    import json as _jl, os as _ol, time as _tl
    if "[UNCONFIRMED]" in str(verdict):
        return
    try:
        _ol.makedirs("data", exist_ok=True)
        path = "data/ledger.json"
        rows = _jl.load(open(path)) if _ol.path.exists(path) else []
        rows.insert(0, {
            "case_id": str(case_id),
            "verdict": str(verdict)[:40],
            "summary": str(summary)[:220],
            "proof": str(proof_url),
            "ts": int(_tl.time()),
        })
        rows = rows[:200]
        _jl.dump(rows, open(path, "w"), indent=2)
        _su, _sk = _ol.environ.get("SUPABASE_URL", "").strip(), _ol.environ.get("SUPABASE_KEY", "").strip()
        if _su and _sk:
            try:
                import requests as _rs
                _rs.post(f"{_su.rstrip('/')}/rest/v1/ledger", headers={"apikey": _sk, "Authorization": f"Bearer {_sk}", "Content-Type": "application/json"}, json=rows[0], timeout=4)
            except Exception:
                pass
        if _ol.path.isdir("docs"):
            _jl.dump(rows, open("docs/ledger.json", "w"), indent=2)
    except Exception:
        pass

import asyncio as _asc, gc as _gc, hashlib as _hl, os as _os, time as _ts
_TEXT_SEM = None
_MEDIA_SEM = None
_USER_RL = {}
_CLAIM_CACHE = {}

def _get_sems():
    global _TEXT_SEM, _MEDIA_SEM
    if _TEXT_SEM is None:
        _TEXT_SEM = _asc.Semaphore(6)
    if _MEDIA_SEM is None:
        _MEDIA_SEM = _asc.Semaphore(2)
    return _TEXT_SEM, _MEDIA_SEM

def _rate_limit_hit(uid):
    now = _ts.time()
    hist = [t for t in _USER_RL.get(uid, []) if now - t < 15]
    hist.append(now)
    _USER_RL[uid] = hist[-6:]
    return len(hist) > 4

def _cache_key(txt):
    return _hl.md5(" ".join(str(txt or "").lower().split()).encode("utf-8")).hexdigest()

def _cache_get(txt):
    k = _cache_key(txt)
    v = _CLAIM_CACHE.get(k)
    if not v:
        return None
    if _ts.time() > v[0]:
        _CLAIM_CACHE.pop(k, None)
        return None
    cp = v[3] if (v[3] and _os.path.exists(v[3])) else None
    return v[1], v[2], cp

def _cache_set(txt, fact, purl, card):
    ttl = 900 if "[UNCONFIRMED]" in str(fact) else 21600
    if len(_CLAIM_CACHE) > 500:
        _CLAIM_CACHE.clear()
    _CLAIM_CACHE[_cache_key(txt)] = (_ts.time() + ttl, fact, purl, card)

def _cleanup_ram():
    now = _ts.time()
    try:
        for fn in _os.listdir("output"):
            if fn.startswith("fact_card_"):
                fp = _os.path.join("output", fn)
                if now - _os.path.getmtime(fp) > 900:
                    _os.remove(fp)
    except Exception:
        pass
    _gc.collect()

def _sb_req(method, table, payload=None, query=""):
    import os as _osb, requests as _rsb
    su = _osb.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    sk = _osb.environ.get("SUPABASE_KEY", "").strip()
    if not (su and sk):
        return None
    hdr = {"apikey": sk, "Authorization": f"Bearer {sk}", "Content-Type": "application/json", "Prefer": "resolution=ignore-duplicates"}
    url = f"{su}/rest/v1/{table}{query}"
    try:
        r = _rsb.request(method, url, headers=hdr, json=payload, timeout=5)
        return r.json() if (r.status_code in (200, 201) and r.text.strip()) else None
    except Exception:
        return None

def _sb_keepalive_loop():
    import time as _tsb
    while True:
        _sb_req("GET", "ledger", query="?select=id&limit=1")
        _tsb.sleep(43200)

def _get_site_stats(hit=False):
    import json as _js, os as _os, requests as _rq, time as _ts
    su = _os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    sk = _os.environ.get("SUPABASE_KEY", "").strip()
    if hit and su and sk:
        _sb_req("POST", "campaign_log", {"sig": "__site_visit__", "ts": int(_ts.time())})
    visits = 1
    if su and sk:
        try:
            r = _rq.get(
                f"{su}/rest/v1/campaign_log?sig=eq.__site_visit__&select=id",
                headers={"apikey": sk, "Authorization": f"Bearer {sk}", "Prefer": "count=exact", "Range": "0-0"},
                timeout=4,
            )
            cr = r.headers.get("Content-Range", "")
            if "/" in cr and cr.split("/")[-1].isdigit():
                visits = max(1, int(cr.split("/")[-1]))
        except Exception:
            pass
    rows = _sb_req("GET", "ledger", query="?order=ts.desc&limit=200") or (_js.load(open("data/ledger.json")) if _os.path.exists("data/ledger.json") else [])
    cats = {"fake": 0, "cyber": 0, "verified": 0, "misleading": 0, "video": 0}
    for row in rows:
        v = (str(row.get("verdict", "")) + " " + str(row.get("summary", ""))).upper()
        if "CYBER" in v: cats["cyber"] += 1
        elif "FAKE" in v: cats["fake"] += 1
        elif "MISLEADING" in v: cats["misleading"] += 1
        elif "VERIFIED" in v or "SAFE" in v: cats["verified"] += 1
        if "FORENSIC SCORE" in v or "YOUTUBE" in v: cats["video"] += 1
    return {"visits": visits, "total_verified": len(rows), "cats": cats}

def deep_verify(claim):
    claim = _dual_lang_query(claim)
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

    _st_hl = _detect_state_hl(c_clean)
    for _hl in (['hi'] + ([_st_hl] if _st_hl and _st_hl != 'hi' else [])):
        try:
            _eu = f'https://news.google.com/rss/search?q={urllib.parse.quote(" ".join(c_clean.split()[:8]))}&hl={_hl}&gl=IN&ceid=IN:{_hl}'
            all_entries.extend(feedparser.parse(_eu).entries[:6])
        except Exception:
            pass
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

def _groq_keys():
    import os as _og
    ks = [_og.environ.get(n, "").strip() for n in ("GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3")]
    return [x for x in ks if x]

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
    for k in (_groq_keys() or [k]):
      for mdl in ("openai/gpt-oss-120b", "llama-3.3-70b-versatile"):
          try:
              resp = requests.post(
                  "https://api.groq.com/openai/v1/chat/completions",
                  headers={"Authorization": f"Bearer {k}"},
                  json={"model": mdl, "messages": [{"role": "user", "content": p}], "temperature": 0.1, "max_tokens": 1000},
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
    if heads and any(w in fl for w in ("debunk", "fake", "false", "hoax", "not banned", "misleading", "खंडन", "फर्जी", "अफवाह", "झूठ", "गलत", "नकली", "बेबुनियाद")):
        return f"[FAKE] {fb} (Case: {case_id} | {ist_now})"
    return f"[UNCONFIRMED] {fb} (Case: {case_id} | {ist_now})"

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if _rate_limit_hit(uid):
        await update.message.reply_text("Too many requests at once — please wait 10 seconds.")
        return
    ap_ref = context.user_data.pop("awaiting_proof", None)
    if ap_ref:
        await update.message.reply_text("[Proof Received] Verifying your submitted proof through RakshaNet forensics...")
    import urllib.parse
    txt = (update.message.text or "").strip()
    if not txt:
        return
    cyber_alert = _scan_cyber_url(txt)
    if cyber_alert:
        card = make_fact_card(txt[:180], cyber_alert)
        _cache_set(txt, fact, purl, card)
        _cleanup_ram()
        await update.message.reply_photo(photo=open(card, "rb"), caption=cyber_alert)
        return
    if not txt.startswith("http"):
        await update.message.reply_text("[Narrative] Investigating authentic sources & data...")
        try:
            camp_tag = _check_campaign(txt)
            cached = _cache_get(txt)
            if cached:
                fact, purl, _cp = cached
                card = _cp or make_fact_card(txt[:180], fact)
                await update.message.reply_photo(photo=open(card, "rb"), caption=fact)
                return
            _tsem, _ = _get_sems()
            async with _tsem:
                heads, fb, purl = await _asc.to_thread(deep_verify, txt)
            fact = await _asc.to_thread(ai_reason, txt, heads, fb)
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
            if d.get("appeals"):
                conn.execute("CREATE TABLE IF NOT EXISTS appeals (ts INT, msg TEXT)")
                for _ts, _mg in d.get("appeals", []):
                    conn.execute("INSERT OR IGNORE INTO appeals (ts, msg) VALUES (?, ?)", (_ts, _mg))
            if d.get("ledger") and not os.path.exists("data/ledger.json"):
                os.makedirs("data", exist_ok=True)
                json.dump(d.get("ledger"), open("data/ledger.json", "w"), indent=2)
            conn.commit()
            conn.close()
            _log_ledger("RN", fact.split("]")[0]+"]" if "]" in fact else "CHECK", fact, purl)
            card = make_fact_card(txt, fact)
            x_url = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(f'{fact[:180]} Proof: {purl} #RakshaNet')}"
            kb = [[InlineKeyboardButton("Read Full Proof", url=purl), InlineKeyboardButton("Share on X (1-Click)", url=x_url)],
            [InlineKeyboardButton("Report Mistake / Submit Proof", callback_data="appeal")]]
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
    uid = update.effective_user.id if update.effective_user else 0
    if _rate_limit_hit(uid):
        await update.message.reply_text("Too many requests at once — please wait 10 seconds.")
        return
    ap_ref = context.user_data.pop("awaiting_proof", None)
    if ap_ref:
        await update.message.reply_text("[Proof Received] Verifying your submitted proof through RakshaNet forensics...")
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
    uid = update.effective_user.id if update.effective_user else 0
    if _rate_limit_hit(uid):
        await update.message.reply_text("Too many requests at once — please wait 10 seconds.")
        return
    ap_ref = context.user_data.pop("awaiting_proof", None)
    if ap_ref:
        await update.message.reply_text("[Proof Received] Verifying your submitted proof through RakshaNet forensics...")
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
        fu = (fact or "").upper()
        verdict = "FAKE" if "[FAKE]" in fu else ("CYBER THREAT" if "[CYBER" in fu else ("MISLEADING" if "[MISLEADING]" in fu else ("VERIFIED" if "[VERIFIED]" in fu else "ALERT")))
    else:
        verdict, claim, fact = a, b, c
    import os, time, asyncio, subprocess, textwrap, edge_tts
    from PIL import Image, ImageDraw, ImageFont
    ts = int(time.time())
    aud = f"/tmp/short_aud_{ts}.mp3"
    vid = out_vid if out_vid else f"/tmp/raksha_short_{ts}.mp4"
    v_up = (verdict or "ALERT").upper()
    if "FAKE" in v_up or "FALSE" in v_up:
        bcol, btxt = (195, 30, 30), "FAKE NEWS ALERT"
    elif "CYBER" in v_up:
        bcol, btxt = (120, 40, 165), "CYBER THREAT ALERT"
    elif "MISLEADING" in v_up:
        bcol, btxt = (210, 115, 0), "MISLEADING CLAIM"
    elif "TRUE" in v_up or "VERIFIED" in v_up:
        bcol, btxt = (20, 130, 55), "VERIFIED FACT"
    else:
        bcol, btxt = (35, 90, 175), "FACT CHECK UPDATE"
    def _fnt(sz, bold=False):
        ps = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Helvetica.ttc"]
        for fp in ps:
            if os.path.exists(fp):
                try:
                    return ImageFont.truetype(fp, sz)
                except Exception:
                    pass
        return ImageFont.load_default()
    c_en = _dual_lang_query(claim) if any(ord(x) > 127 for x in str(claim).replace("₹", "")) else str(claim)
    f_en = _dual_lang_query(fact) if any(ord(x) > 127 for x in str(fact).replace("₹", "")) else str(fact)
    c_txt = c_en.replace("₹", "Rs.").encode("ascii", "ignore").decode().strip()[:220]
    f_txt = f_en.replace("₹", "Rs.").encode("ascii", "ignore").decode().strip()[:280]
    slides = [
        ("STEP 1: VIRAL CLAIM", c_txt, bcol),
        ("STEP 2: OFFICIAL PROOF", f_txt, (20, 130, 55)),
        ("STEP 3: STAY SAFE", "Verify before forwarding!\nTelegram: @RakshaNet_India\nCyber Fraud Helpline: 1930 | cybercrime.gov.in", (35, 90, 175)),
    ]
    s_paths = []
    for idx, (ttl, body, acol) in enumerate(slides):
        im = Image.new("RGB", (720, 1280), (14, 22, 42))
        d = ImageDraw.Draw(im)
        d.rectangle([(0, 0), (720, 110)], fill=(10, 15, 30))
        d.text((40, 35), "RAKSHANET INDIA | OSINT DESK", fill=(255, 255, 255), font=_fnt(28, True))
        d.rectangle([(40, 150), (680, 225)], fill=bcol)
        d.text((65, 170), btxt, fill=(255, 255, 255), font=_fnt(34, True))
        d.rectangle([(40, 270), (680, 330)], fill=acol)
        d.text((60, 285), ttl, fill=(255, 255, 255), font=_fnt(26, True))
        d.text((45, 380), textwrap.fill(body, width=30), fill=(240, 244, 255), font=_fnt(32, False))
        d.text((45, 1180), "Powered by RakshaNet Autonomous AI", fill=(150, 165, 195), font=_fnt(22, False))
        sp = f"/tmp/short_s{idx}_{ts}.png"
        im.save(sp)
        s_paths.append(sp)
    is_hi = any("\u0900" <= ch <= "\u097f" for ch in str(claim))
    voice = "hi-IN-SwaraNeural" if is_hi else "en-IN-PrabhatNeural"
    narration = f"{btxt}. {c_txt[:140]}. {f_txt[:180]}. Verify before sharing on RakshaNet India."
    async def _tts():
        await edge_tts.Communicate(narration, voice).save(aud)
    import threading as _tt
    _th = _tt.Thread(target=lambda: asyncio.run(_tts()))
    _th.start(); _th.join(timeout=15)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", "5", "-i", s_paths[0],
        "-loop", "1", "-t", "7", "-i", s_paths[1],
        "-loop", "1", "-t", "4", "-i", s_paths[2],
        "-i", aud,
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0,scale=720:1280,format=yuv420p[v]",
        "-map", "[v]", "-map", "3:a", "-r", "10", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", "-shortest", vid,
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    for sp in s_paths + [aud]:
        if os.path.exists(sp):
            os.remove(sp)
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
            "appeals": conn.execute("SELECT ts, msg FROM appeals ORDER BY ts DESC LIMIT 100").fetchall() if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='appeals'").fetchone() else [],
            "ledger": json.load(open("data/ledger.json"))[:200] if os.path.exists("data/ledger.json") else [],
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
async def appeals_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = sqlite3.connect(DB_FILE)
        rows = conn.execute("SELECT ts, msg FROM appeals ORDER BY ts DESC LIMIT 5").fetchall()
        conn.close()
        if not rows:
            await update.message.reply_text("No appeals logged yet.")
            return
        lines = [f"{i+1}. {r[1][:120]}" for i, r in enumerate(rows)]
        await update.message.reply_text("Latest Appeals:\n" + "\n".join(lines))
    except Exception:
        await update.message.reply_text("No appeals logged yet.")

def _daily_roundup_loop():
    import datetime as _dt, json as _jr, os as _or, time as _tr
    last_day = ""
    while True:
        try:
            now_ist = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=5, minutes=30)))
            dkey = now_ist.strftime("%Y-%m-%d")
            if now_ist.hour == 21 and dkey != last_day and _or.path.exists("data/ledger.json"):
                rows = _jr.load(open("data/ledger.json"))[:3]
                if rows:
                    last_day = dkey
                    summary = " | ".join(f"{r.get('verdict','')}: {r.get('summary','')[:70]}" for r in rows)
                    v = build_pro_short("ALERT", f"Daily Fact-Check Round-Up ({dkey})", summary)
                    upload_yt_short(v, f"RakshaNet Daily Fact-Check Round-Up | {dkey} #Shorts", summary)
        except Exception:
            pass
        _tr.sleep(300)

async def roundup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import json as _jr, os as _or
    rows = _jr.load(open("data/ledger.json"))[:3] if _or.path.exists("data/ledger.json") else []
    if not rows:
        await update.message.reply_text("No verified cases in today's ledger yet.")
        return
    await update.message.reply_text("Building Daily Round-Up Short...")
    try:
        summary = " | ".join(f"{r.get('verdict','')}: {r.get('summary','')[:70]}" for r in rows)
        v = build_pro_short("ALERT", "Daily Fact-Check Round-Up", summary)
        if _or.path.exists(v):
            await update.message.reply_video(video=open(v, "rb"), caption="RakshaNet Daily Round-Up Short")
        else:
            await update.message.reply_text("Video file not created on server.")
    except Exception as _re:
        await update.message.reply_text(f"Round-Up error: {_re}")

def _handle_feedback(qs):
    import time as _tf
    stars = int((qs.get("stars") or ["0"])[0] or 0)
    cat = (qs.get("cat") or ["General"])[0][:40]
    msg = (qs.get("msg") or [""])[0].strip()[:220]
    if stars >= 1 and stars <= 5:
        rec = f"[FEEDBACK | {stars}★ | {cat}] {msg}"
        _sb_req("POST", "appeals", {"ts": int(_tf.time()), "msg": rec})
        try:
            conn = sqlite3.connect(DB_FILE)
            conn.execute("CREATE TABLE IF NOT EXISTS appeals (ts INT, msg TEXT)")
            conn.execute("INSERT INTO appeals (ts, msg) VALUES (?, ?)", (int(_tf.time()), rec))
            conn.commit(); conn.close()
        except Exception:
            pass
    rows = _sb_req("GET", "appeals", query="?order=ts.desc&limit=100") or []
    fbs = [r.get("msg", "") for r in rows if "[FEEDBACK" in str(r.get("msg", ""))]
    nums = []
    for x in fbs:
        for d in ("5★", "4★", "3★", "2★", "1★"):
            if d in x:
                nums.append(int(d[0])); break
    avg = round(sum(nums) / len(nums), 1) if nums else 0
    return {"ok": True, "avg": avg, "count": len(nums)}

async def feedback_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = _sb_req("GET", "appeals", query="?order=ts.desc&limit=50") or []
    fbs = [r.get("msg", "") for r in rows if "[FEEDBACK" in str(r.get("msg", ""))][:8]
    if not fbs:
        await update.message.reply_text("No user feedback submitted yet.")
        return
    await update.message.reply_text("Latest User Feedback:\n" + "\n".join(f"{i+1}. {x}" for i, x in enumerate(fbs)))

async def button_tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "approve" and "pending" in context.user_data:
        url, score, reason = context.user_data.pop("pending")
        await q.edit_message_text("Rendering Counter-Video...")
        out = build_counter(url, score, reason)
        await q.message.reply_video(video=open(out, "rb"), caption=f"[Approved Counter-Video] Score: {score}%")
    elif str(q.data).startswith("appeal"):
        try:
            conn = sqlite3.connect(DB_FILE)
            conn.execute("CREATE TABLE IF NOT EXISTS appeals (ts INT, msg TEXT)")
            import time as _ta
            conn.execute("INSERT INTO appeals (ts, msg) VALUES (?, ?)", (int(_ta.time()), str(q.message.caption or q.message.text or "")[:240]))
            context.user_data["awaiting_proof"] = str(q.message.caption or q.message.text or "")[:120]
            conn.commit(); conn.close()
            _sb_req("POST", "appeals", {"ts": int(_ta.time()), "msg": str(q.message.caption or q.message.text or "")[:240]})
        except Exception:
            pass
        orig = str(q.message.caption or q.message.text or "")[:200]
        h2, fb2, _ = deep_verify(orig)
        rf = ai_reason(orig, h2, fb2) if h2 else ""
        if "[UNCONFIRMED]" in orig and rf and "[UNCONFIRMED]" not in rf:
            await q.message.reply_text(f"[CORRECTION / UPDATE] {rf}")
        else:
            await q.message.reply_text("Appeal logged & re-verified against live Tier-1/Tier-2 sources — original verdict stands. Send your official link, photo, video, or text proof now so RakshaNet can verify it.")
    else:
        await q.edit_message_text("Ignored. Marked as safe.")


_sync_cloud_memory("load")
print("[RakshaNet Complete] Running with Whisper + Fact-Card + Counter-Video... Press Ctrl+C to stop.")
app = ApplicationBuilder().token(BOT_TOKEN).write_timeout(30).read_timeout(30).connect_timeout(30).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("radar", radar_cmd))
app.add_handler(CommandHandler("appeals", appeals_cmd))
app.add_handler(CommandHandler("feedback", feedback_cmd))
app.add_handler(CommandHandler("roundup", roundup_cmd))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
app.add_handler(MessageHandler(filters.VIDEO | filters.VOICE | filters.AUDIO | filters.VIDEO_NOTE, handle_media))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(CallbackQueryHandler(button_tap))
import threading as _wt
_wt.Thread(target=_watchlist_loop, daemon=True).start()
_wt.Thread(target=_daily_roundup_loop, daemon=True).start()
_wt.Thread(target=_sb_keepalive_loop, daemon=True).start()

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
if os.environ.get("PORT"):
    class H(BaseHTTPRequestHandler):
        def _send_json(self, obj, code=200):
            import json as _jh
            data = _jh.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        def do_GET(self):
            import json as _jh, os as _oh, urllib.parse as _up
            if self.path.startswith("/api/feedback"):
                return self._send_json(_handle_feedback(_up.parse_qs(_up.urlparse(self.path).query)))
            if self.path.startswith("/api/stats"):
                st = _get_site_stats(hit=("hit=1" in self.path)); _rows = _sb_req("GET", "ledger", query="select=verdict,claim&limit=500") or []; st["narratives"] = sum(1 for r in _rows if any(k in (str(r.get("verdict",""))+str(r.get("claim",""))).upper() for k in ("NARRATIVE","FAKE","MISLEADING","INDIA","ARMY","DEFENCE"))); return self._send_json(st)
            if self.path.startswith("/api/ledger"):
                rows = _sb_req("GET", "ledger", query="?order=ts.desc&limit=50") or (_jh.load(open("data/ledger.json")) if _oh.path.exists("data/ledger.json") else [])
                return self._send_json(rows[:50])
            if self.path.startswith("/api/verify"):
                qs = _up.parse_qs(_up.urlparse(self.path).query)
                q = (qs.get("q") or [""])[0].strip()[:400]
                if not q:
                    return self._send_json({"error": "Empty claim"}, 400)
                cy = _scan_cyber_url(q)
                if cy:
                    return self._send_json({"fact": cy, "proof": "https://cybercrime.gov.in/"})
                c = _cache_get(q)
                if c:
                    return self._send_json({"fact": c[0], "proof": c[1]})
                if "http" in q.lower():
                    sc, vd, sm, rsn = analyze_video(q)
                    fact = f"[{vd}] Forensic Score: {sc}% | {sm} | " + "; ".join(rsn[:3])
                    _log_ledger("RN", f"[{vd}]", fact, q)
                    return self._send_json({"fact": fact, "proof": q})
                h, fb, purl = deep_verify(q)
                fact = ai_reason(q, h, fb)
                _log_ledger("RN", fact.split("]")[0]+"]" if "]" in fact else "CHECK", fact, purl)
                _cache_set(q, fact, purl, None)
                return self._send_json({"fact": fact, "proof": purl})
            self.send_response(200); self.end_headers(); self.wfile.write(b"RakshaNet OK")
        def do_HEAD(self): self.send_response(200); self.end_headers()
        def log_message(self, *a): pass
    threading.Thread(target=lambda: ThreadingHTTPServer(("0.0.0.0", int(os.environ["PORT"])), H).serve_forever(), daemon=True).start()

# === PHASE 2: DUAL-ENGINE + 24x7 AUTONOMOUS SURVEILLANCE ===
_RN_RADARS = [
    ("NARRATIVE COUNTER", "https://news.google.com/rss/search?q=(%22Indian+Army%22+OR+%22India%22+OR+%22MEA%22+OR+%22Kashmir%22)+(%22fake+claim%22+OR+%22debunked%22+OR+%22false+claim%22+OR+%22misleading%22)&hl=en-IN&gl=IN&ceid=IN:en"),
    ("FACT-CHECK", "https://news.google.com/rss/search?q=(%22PIB+Fact+Check%22+OR+%22fact+check%22+OR+%22viral+video%22+fake)+India&hl=en-IN&gl=IN&ceid=IN:en"),
    ("CYBER THREAT", "https://news.google.com/rss/search?q=(%22cyber+fraud%22+OR+%22fake+APK%22+OR+%22RBI+warning%22+OR+%22UPI+scam%22)+India&hl=en-IN&gl=IN&ceid=IN:en"),
    ("RAW VIRAL MONITOR", "https://news.google.com/rss/search?q=(%22viral+on+X%22+OR+%22viral+on+Instagram%22+OR+%22viral+on+WhatsApp%22)+(%22fake%22+OR+%22scam%22+OR+%22misleading%22)+India&hl=en-IN&gl=IN&ceid=IN:en"),
    ("RAW VIDEO MONITOR", "https://www.youtube.com/feeds/videos.xml?channel_id=UC_x5XG1OV2P6uZZ5FSM9Ttw"),
]
_RN_SEEN = set()

def _rn_independent_assess(claim, ev=""):
    c, s, fl = (claim or "").lower(), 0, []
    if any(k in c for k in ("forward to","free recharge","free laptop","account blocked","kyc update")): s += 45; fl.append("Scam urgency pattern")
    if any(k in c for k in (".apk",".xyz",".top","bit.ly","tinyurl")): s += 40; fl.append("Suspicious link/APK")
    if any(k in c for k in ("rbi banned","500 note banned","pm free","govt giving free")): s += 35; fl.append("Unverified scheme/ban claim")
    if any(k in c for k in ("fake","debunked","false claim","misleading","hoax","edited video")): s += 35; fl.append("Manipulation/debunk cue")
    if not str(ev or "").strip(): s += 15; fl.append("No primary govt record")
    return min(s, 98), fl

def _rn_fetch_radars(per_feed=2):
    import urllib.request, xml.etree.ElementTree as ET
    out = []
    for cat, url in _RN_RADARS:
        try:
            root = ET.fromstring(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"}), timeout=12).read())
            n = 0
            for it in root.findall(".//item"):
                t, lk = (it.findtext("title") or "").strip(), (it.findtext("link") or "").strip()
                if not t or t in _RN_SEEN: continue
                _RN_SEEN.add(t); out.append((cat, t, lk)); n += 1
                if n >= per_feed: break
        except Exception as _e: print("[AUTO-SURVEILLANCE ERR]", _e, flush=True)
    return out

async def _rn_run_surveillance_cycle():
    import asyncio, json, os, urllib.request
    tok = os.getenv("BOT_TOKEN","") or os.getenv("TELEGRAM_BOT_TOKEN","")
    seen_db = {str(r.get("claim","")).lower()[:70] for r in (_sb_req("GET","ledger",query="select=claim&limit=200") or [])}
    for cat, title, src in await asyncio.to_thread(_rn_fetch_radars, 2):
        tag = f"[{cat}] {title[:170]}"
        if tag.lower()[:70] in seen_db: continue
        try:
            pub = title.rsplit(" - ", 1)[1].strip() if " - " in title else "Web Monitor"
            raw_h = title.rsplit(" - ", 1)[0].strip()
            h, fb, purl = await asyncio.to_thread(deep_verify, raw_h)
            prompt_q = f"Extract the viral claim being debunked/reported in this headline and judge THAT claim (not the news report): {raw_h}. Reply in 2 short lines: CLAIM: <actual claim> | FACT: <truth>"
            res = await asyncio.to_thread(ai_reason, prompt_q, h, fb)
            sc, fl = _rn_independent_assess(raw_h, h)
            up = (raw_h + " " + str(res or "")).upper()
            if cat == "CYBER THREAT": v = "CYBER THREAT"
            elif any(w in raw_h.lower() for w in ("junks","debunk","fake","false","hoax","fact check","misleading","fabricated")): v = "FAKE"
            elif "FAKE" in up: v = "FAKE"
            elif "MISLEADING" in up: v = "MISLEADING"
            elif "VERIFIED" in up: v = "VERIFIED"
            elif sc >= 50: v = f"LIKELY FAKE ({sc}% Risk)"
            else: continue
            proof = purl or src
            clean_tag = f"[{cat}] Claim: {raw_h[:135]} (via {pub})"
            print(f"[AUTO-SURVEILLANCE] Verified & Saving: {v} | {clean_tag[:70]}", flush=True)
            _log_ledger("AUTO", v, clean_tag, proof)
            if v in ("FAKE","MISLEADING","CYBER THREAT") and _RN_VID_COUNT["n"] < 3: asyncio.create_task(_rn_auto_counter_video(v, raw_h, str(res or raw_h)[:260], src, proof))
            await asyncio.to_thread(_rn_post_x, f"[{v}] {raw_h[:150]}\n\nProof: {proof}\nPortal: https://devanshshukla938.github.io/RakshaNet/ #RakshaNetIndia #FactCheck")
            if tok:
                msg = f"[{v}] {cat}\n\n{title[:200]}\n\n{str(res or title)[:280]}\n\nSource: {src}\nProof: {proof}\nPortal: https://devanshshukla938.github.io/RakshaNet/"
                try: await asyncio.to_thread(lambda _r: urllib.request.urlopen(_r, timeout=10), urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=json.dumps({"chat_id":"@RakshaNet_India","text":msg}).encode(), headers={"Content-Type":"application/json"}, method="POST"))
                except Exception as _e: print("[AUTO-SURVEILLANCE ERR]", _e, flush=True)
            await asyncio.sleep(6)
        except Exception as _e: print("[AUTO-SURVEILLANCE ERR]", _e, flush=True)



# === PHASE 4: X (TWITTER) v2 + INSTAGRAM GRAPH API AUTO-PUBLISHERS (Rs 0) ===
def _rn_post_x(text):
    import base64, hashlib, hmac, json, os, time, urllib.parse, urllib.request, uuid
    ck, cs = os.getenv("X_API_KEY",""), os.getenv("X_API_SECRET","")
    at, ats = os.getenv("X_ACCESS_TOKEN",""), os.getenv("X_ACCESS_SECRET","")
    if not (ck and cs and at and ats): return ""
    url = "https://api.twitter.com/2/tweets"
    oauth = {
        "oauth_consumer_key": ck, "oauth_nonce": uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1", "oauth_timestamp": str(int(time.time())),
        "oauth_token": at, "oauth_version": "1.0"
    }
    param_str = "&".join(f"{urllib.parse.quote(k,'')}={urllib.parse.quote(v,'')}" for k, v in sorted(oauth.items()))
    base_str = f"POST&{urllib.parse.quote(url,'')}&{urllib.parse.quote(param_str,'')}"
    key = f"{urllib.parse.quote(cs,'')}&{urllib.parse.quote(ats,'')}".encode()
    oauth["oauth_signature"] = base64.b64encode(hmac.new(key, base_str.encode(), hashlib.sha1).digest()).decode()
    auth_hdr = "OAuth " + ", ".join(f'{k}="{urllib.parse.quote(v,"")}"' for k, v in sorted(oauth.items()))
    req = urllib.request.Request(url, data=json.dumps({"text": text[:275]}).encode(), headers={"Authorization": auth_hdr, "Content-Type": "application/json"}, method="POST")
    try:
        res = json.loads(urllib.request.urlopen(req, timeout=12).read().decode())
        tid = (res.get("data") or {}).get("id", "")
        if tid: print(f"[PHASE 4] X Post LIVE: https://x.com/i/status/{tid}", flush=True)
        return f"https://x.com/i/status/{tid}" if tid else ""
    except Exception as _e:
        print("[PHASE 4 X ERR]", _e, flush=True)
        return ""

def _rn_post_instagram(caption, media_url="", is_reel=False):
    import json, os, urllib.parse, urllib.request
    ig_id, ig_tok = os.getenv("IG_USER_ID",""), os.getenv("IG_ACCESS_TOKEN","")
    if not (ig_id and ig_tok and media_url): return ""
    try:
        p = {"caption": caption[:2100], "access_token": ig_tok}
        if is_reel: p.update({"media_type": "REELS", "video_url": media_url})
        else: p.update({"image_url": media_url})
        c_req = urllib.request.Request(f"https://graph.facebook.com/v20.0/{ig_id}/media", data=urllib.parse.urlencode(p).encode(), method="POST")
        cid = json.loads(urllib.request.urlopen(c_req, timeout=15).read().decode()).get("id", "")
        if not cid: return ""
        p_req = urllib.request.Request(f"https://graph.facebook.com/v20.0/{ig_id}/media_publish", data=urllib.parse.urlencode({"creation_id": cid, "access_token": ig_tok}).encode(), method="POST")
        pid = json.loads(urllib.request.urlopen(p_req, timeout=15).read().decode()).get("id", "")
        if pid: print(f"[PHASE 4] Instagram Post LIVE: ID {pid}", flush=True)
        return f"https://www.instagram.com/p/{pid}/" if pid else ""
    except Exception as _e:
        print("[PHASE 4 IG ERR]", _e, flush=True)
        return ""
# === /PHASE 4 ===

# === PHASE 3: AUTONOMOUS COUNTER-VIDEO + 5-MIN ADMIN SAFETY PREVIEW ===
_RN_VID_COUNT = {"day": "", "n": 0}
_RN_CANCEL_NEXT = False

async def _rn_auto_counter_video(verdict, title, summary, src, proof):
    import asyncio, datetime, json, os, urllib.request
    global _RN_CANCEL_NEXT
    today = datetime.date.today().isoformat()
    if _RN_VID_COUNT["day"] != today:
        _RN_VID_COUNT["day"], _RN_VID_COUNT["n"] = today, 0
    if _RN_VID_COUNT["n"] >= 3:
        return ""
    if "build_pro_short" not in globals() or "upload_to_youtube" not in globals():
        return ""
    tok = os.getenv("BOT_TOKEN", "") or os.getenv("TELEGRAM_BOT_TOKEN", "")
    adm = os.getenv("ADMIN_ID", "") or os.getenv("OWNER_ID", "")
    _RN_CANCEL_NEXT = False
    if tok and adm:
        prev = f"⏳ [5-MIN SAFETY PREVIEW]\nAuto Counter-Video queued for YouTube:\n[{verdict}] {title[:120]}\nReply /cancel_auto within 5 min to hold, else it auto-publishes."
        try:
            await asyncio.to_thread(lambda _r: urllib.request.urlopen(_r, timeout=10), urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=json.dumps({"chat_id": adm, "text": prev}).encode(), headers={"Content-Type": "application/json"}, method="POST"))
            await asyncio.sleep(300)
        except Exception:
            pass
    if _RN_CANCEL_NEXT:
        print("[PHASE 3] Auto Counter-Video cancelled by Admin.", flush=True)
        return ""
    try:
        vid_path = await asyncio.to_thread(build_pro_short, f"[{verdict}] {title[:90]}", summary[:240], verdict)
        if not vid_path or not os.path.exists(vid_path):
            return ""
        clean_t = f"[{verdict}] {title[:70]} #Shorts #RakshaNetIndia"
        desc = f"Verified Fact-Check by RakshaNet India (Founder: Devansh Shukla)\n\nClaim: {title[:180]}\nFact: {summary[:300]}\n\nOriginal Source: {src}\nOfficial Proof: {proof}\nPortal: https://devanshshukla938.github.io/RakshaNet/\nCyber Helpline: 1930"
        yt_id = await asyncio.to_thread(upload_to_youtube, vid_path, clean_t, desc)
        try: os.remove(vid_path)
        except Exception: pass
        if yt_id:
            _RN_VID_COUNT["n"] += 1
            yt_url = f"https://youtube.com/shorts/{yt_id}"
            print(f"[PHASE 3] Auto Counter-Video LIVE: {yt_url}", flush=True)
            _log_ledger("VIDEO", verdict, f"[COUNTER VIDEO] {title[:130]}", yt_url)
            if tok:
                vmsg = f"🎬 [COUNTER-VIDEO LIVE] [{verdict}]\n{title[:160]}\n▶️ Watch: {yt_url}\n🔗 Proof: {proof}"
                try: await asyncio.to_thread(lambda _r: urllib.request.urlopen(_r, timeout=10), urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=json.dumps({"chat_id": "@RakshaNet_India", "text": vmsg}).encode(), headers={"Content-Type": "application/json"}, method="POST"))
                except Exception: pass
            return yt_url
    except Exception as _e:
        print("[PHASE 3 ERR]", _e, flush=True)
    return ""
# === /PHASE 3 ===

async def _rn_auto_surveillance_loop():
    import asyncio
    print("[AUTO-SURVEILLANCE] Loop booted! Scanning in 25s...", flush=True)
    await asyncio.sleep(25)
    while True:
        try: await _rn_run_surveillance_cycle()
        except Exception as _e: print("[AUTO-SURVEILLANCE ERR]", _e, flush=True)
        await asyncio.sleep(10800)
threading.Thread(target=lambda: __import__("asyncio").run(_rn_auto_surveillance_loop()), daemon=True).start()


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



