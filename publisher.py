import os
import subprocess
from PIL import Image, ImageDraw, ImageFont

os.makedirs("temp", exist_ok=True)
os.makedirs("output", exist_ok=True)


def create_counter_video(video_url, score, reason):
    temp_vid = "temp/raw_clip.mp4"
    banner_img = "temp/banner.png"
    out_vid = "output/counter_video.mp4"

    print("[Publisher] Downloading short clip...")
    subprocess.run(
        ["yt-dlp", "-f", "worst[ext=mp4]/worst", "-o", temp_vid, video_url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
    )

    print("[Publisher] Creating Fact-Check banner...")
    img = Image.new("RGBA", (620, 90), (180, 20, 20, 220))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=18)
    draw.text((15, 12), f"RAKSHANET ALERT | RISK: {score}%", fill=(255, 255, 255), font=font)
    draw.text((15, 45), reason[:55], fill=(255, 230, 150), font=font)
    img.save(banner_img)

    print("[Publisher] Rendering 10-sec Counter-Video with FFmpeg...")
    subprocess.run(
        [
            "ffmpeg", "-y", "-t", "10", "-i", temp_vid, "-i", banner_img,
            "-filter_complex", "overlay=10:10", "-c:a", "copy", out_vid,
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
    )

    for f in (temp_vid, banner_img):
        if os.path.exists(f):
            os.remove(f)

    print(f"[Publisher] Done! Counter-video ready at: {out_vid}")
    return out_vid


create_counter_video(
    "https://www.youtube.com/watch?v=aqz-KE-bpKQ",
    92,
    "AI Manipulation / Unverified Claim Detected",
)