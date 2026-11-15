import os
import sqlite3
import subprocess
import imagehash
from PIL import Image

DB_FILE = "rakshanet.db"
os.makedirs("temp", exist_ok=True)


def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            phash TEXT,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()


def scan_and_clean(video_url):
    init_db()
    temp_vid = "temp/sample.mp4"
    temp_img = "temp/frame.jpg"

    print("[Memory] Downloading video to temp folder...")
    subprocess.run(
        ["yt-dlp", "-f", "worst[ext=mp4]/worst", "-o", temp_vid, video_url],
        check=True,
    )

    print("[Memory] Extracting frame and computing pHash...")
    subprocess.run(
        ["ffmpeg", "-y", "-ss", "00:00:03", "-i", temp_vid, "-vframes", "1", temp_img],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )

    phash = str(imagehash.phash(Image.open(temp_img)))
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT OR REPLACE INTO videos (url, phash, status) VALUES (?, ?, ?)",
        (video_url, phash, "TESTED"),
    )
    conn.commit()
    conn.close()

    for f in (temp_vid, temp_img):
        if os.path.exists(f):
            os.remove(f)

    print(f"[Memory] Done! Saved pHash ({phash}) and cleaned temp files.")


scan_and_clean("https://www.youtube.com/watch?v=aqz-KE-bpKQ")