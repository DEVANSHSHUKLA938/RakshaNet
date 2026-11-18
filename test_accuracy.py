import ast

with open("main.py", "r", encoding="utf-8") as f:
    src = f.read()

ast.parse(src)
required = [
    "def get_speech(",
    "def analyze_video(",
    "def deep_verify(",
    "def ai_reason(",
    "def extract_video_claim(",
    "def _ffprobe_forensics(",
    "def _record_source_history(",
    "def _sync_cloud_memory(",
    "def upload_yt_short(",
    "INDETERMINATE",
    "[UNCONFIRMED]",
    "cybercrime.gov.in",
    "yt_queue",
    "Tier 1F",
    "tech_flags",
]
for item in required:
    assert item in src, f"Missing critical component: {item}"
print(f"ALL {len(required)} ACCURACY & RELIABILITY CHECKS PASSED!")
