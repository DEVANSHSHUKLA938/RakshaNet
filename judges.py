import os
import subprocess
import urllib.parse
import cv2
import feedparser
import numpy as np


def evaluate_video(video_url, title="Test Video"):
    os.makedirs("temp", exist_ok=True)
    temp_vid = "temp/judge_vid.mp4"
    reasons = []
    score = 0

    print("[Judges] Downloading video for forensic scan...")
    subprocess.run(
        ["yt-dlp", "-f", "worst[ext=mp4]/worst", "-o", temp_vid, video_url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
    )

    cap = cv2.VideoCapture(temp_vid)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    brightness_vals = []
    blur_flags = 0

    for idx in range(0, total_frames, max(1, total_frames // 5)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness_vals.append(float(np.mean(gray)))

        h, w = gray.shape
        center = gray[h//4:3*h//4, w//4:3*w//4]
        center_var = cv2.Laplacian(center, cv2.CV_64F).var()
        full_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        if full_var > 0 and center_var < (full_var * 0.45):
            blur_flags += 1

    cap.release()
    if os.path.exists(temp_vid):
        os.remove(temp_vid)

    if blur_flags >= 2:
        score += 40
        reasons.append("Center subject smoother than background (possible AI synthesis)")
    if len(brightness_vals) >= 2 and np.std(brightness_vals) > 35:
        score += 25
        reasons.append("Unusual frame-to-frame lighting jump detected")

    q = urllib.parse.quote(f"{title} fact check fake")
    fc_feed = feedparser.parse(
        f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
    )
    if len(fc_feed.entries) > 0:
        score += 30
        reasons.append(f"Related fact-check coverage found: {fc_feed.entries[0].title}")

    verdict = "LIKELY SAFE"
    if score >= 85:
        verdict = "AUTO-COUNTER (HIGH RISK)"
    elif score >= 50:
        verdict = "NEEDS 1-TAP REVIEW (DOUBTFUL)"

    print(f"\n[Verdict] {verdict} | Risk Score: {score}%")
    print("[Reasons]", "; ".join(reasons) if reasons else "No major anomalies detected.")
    return score, verdict, reasons


evaluate_video("https://www.youtube.com/watch?v=aqz-KE-bpKQ", "Big Buck Bunny")