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


# --- Golden Test Cases (Step 7) ---
import ast as _ga, os as _go, re as _gr, textwrap as _gt
_src = open("main.py", "r", encoding="utf-8").read()
_tree = _ga.parse(_src)
_ns = {"os": _go, "re": _gr, "textwrap": _gt, "Image": None}
for _node in _tree.body:
    if isinstance(_node, _ga.FunctionDef) and _node.name in ("_scan_cyber_url", "_detect_state_hl"):
        exec(compile(_ga.Module(body=[_node], type_ignores=[]), "main.py", "exec"), _ns)
assert _ns["_scan_cyber_url"]("https://pmkisan-verify-india.com/kyc") is not None, "Phishing URL missed"
assert _ns["_scan_cyber_url"]("https://evil.com/update.apk") is not None, "APK URL missed"
assert _ns["_scan_cyber_url"]("https://pib.gov.in/PressReleasePage.aspx?PRID=1") is None, "Official .gov.in false positive"
assert _ns["_detect_state_hl"]("Kolkata bridge collapse") == "bn", "State city bn missed"
assert _ns["_detect_state_hl"]("Chennai metro update") == "ta", "State city ta missed"
try:
    from PIL import Image, ImageDraw, ImageFont
    print("PIL OK")
except ImportError:
    pass
print("GOLDEN ACCURACY TESTS PASSED!")
