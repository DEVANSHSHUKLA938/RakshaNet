import os
import sqlite3
from datetime import datetime

os.makedirs("docs", exist_ok=True)
DB_FILE = "rakshanet.db"


def build_public_site():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("CREATE TABLE IF NOT EXISTS seen_urls (url TEXT UNIQUE, title TEXT, risk_hint TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS keywords (kw TEXT UNIQUE)")
    conn.execute("CREATE TABLE IF NOT EXISTS narratives (id INTEGER PRIMARY KEY AUTOINCREMENT, claim TEXT UNIQUE, source_type TEXT, counter_fact TEXT, proof_url TEXT)")
    rows = conn.execute("SELECT title, url, risk_hint FROM seen_urls ORDER BY rowid DESC LIMIT 20").fetchall()
    nar_rows = conn.execute("SELECT claim, source_type, counter_fact, proof_url FROM narratives ORDER BY id DESC LIMIT 15").fetchall()
    kw_rows = [r[0] for r in conn.execute("SELECT kw FROM keywords ").fetchall()]
    conn.close()

    feed_html = ""
    for claim, stype, fact, purl in nar_rows:
        feed_html += f"""
        <article class="story" data-type="narrative">
          <span class="cat alert">NARRATIVE COUNTER &bull; {stype}</span>
          <h3><a href="{purl}" target="_blank">Claim: {claim}</a></h3>
          <p class="fact-box"><b>Verified Fact:</b> {fact}</p>
          <div class="byline">PROOF: <a href="{purl}" target="_blank">Read Official Source &rarr;</a></div>
        </article>"""

    for title, url, hint in rows:
        is_debunk = hint == "FACT_CHECK_DEBUNK"
        cls = "alert" if is_debunk else "safe"
        cat = "VERIFIED DEBUNK" if is_debunk else "DEFENCE MONITOR"
        parts = title.rsplit(" - ", 1)
        headline = parts[0]
        source = parts[1] if len(parts) > 1 else "Public Feed"
        feed_html += f"""
        <article class="story" data-type="{cls}">
          <span class="cat {cls}">{cat}</span>
          <h3><a href="{url}" target="_blank">{headline}</a></h3>
          <div class="byline">SOURCE: <b>{source.upper()}</b> &bull; <a href="{url}" target="_blank">Read Original &rarr;</a></div>
        </article>"""

    lead_title = f"Claim Checked: {nar_rows[0][0]}" if nar_rows else (rows[0][0].rsplit(" - ", 1)[0] if rows else "RakshaNet Desk Ready")
    lead_fact = nar_rows[0][2] if nar_rows else "Automated OSINT & Fact-Check verification log."
    lead_url = nar_rows[0][3] if nar_rows else (rows[0][1] if rows else "#")

    kw_links = "".join(f"<span class='kw'>{k}</span>" for k in kw_rows)
    today_str = datetime.now().strftime("%A, %B %d, %Y")
    time_str = datetime.now().strftime("%d %b %Y, %I:%M %p IST")

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RakshaNet by Devansh Shukla — Indian Defence &amp; Fact-Check Portal</title>
<meta name="description" content="RakshaNet by Devansh Shukla: 24x7 open-source Indian defence monitor, PIB fact-check portal, and AI narrative counter desk.">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#ffffff;color:#1a1a1a;line-height:1.55;}}
  .top-strip{{background:#111111;color:#d4d4d4;font-size:0.78rem;}}
  .top-in{{max-width:1080px;margin:0 auto;padding:7px 20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;}}
  .top-btn{{background:#eab308;color:#111;text-decoration:none;font-weight:700;padding:4px 10px;border-radius:3px;font-size:0.72rem;letter-spacing:0.4px;}}
  .masthead{{max-width:1080px;margin:0 auto;padding:18px 20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:14px;}}
  .logo{{font-family:Georgia,'Times New Roman',serif;font-size:2.5rem;font-weight:700;letter-spacing:-1px;color:#1a1a1a;line-height:1;}}
  .logo span{{color:#c81e1e;}}
  .tagline{{border-left:3px solid #c81e1e;padding-left:12px;font-size:0.85rem;color:#525252;max-width:440px;}}
  .cat-bar{{background:#1f1f1f;color:#fff;}}
  .cat-in{{max-width:1080px;margin:0 auto;padding:0 20px;display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px;}}
  .nav-tabs{{display:flex;flex-wrap:wrap;}}
  .tab{{background:none;border:none;color:#e5e5e5;padding:12px 14px;cursor:pointer;font-size:0.78rem;font-weight:700;letter-spacing:0.6px;text-transform:uppercase;}}
  .tab:hover,.tab.active{{background:#c81e1e;color:#fff;}}
  .search-box input{{background:#333;border:none;color:#fff;padding:6px 12px;border-radius:3px;font-size:0.82rem;outline:none;width:210px;}}
  .search-box input::placeholder{{color:#a3a3a3;}}
  .wrap{{max-width:1080px;margin:0 auto;padding:24px 20px 60px;}}
  .crumb{{font-size:0.78rem;color:#737373;margin-bottom:10px;}}
  .lead-box{{border-bottom:2px solid #e5e5e5;padding-bottom:22px;margin-bottom:24px;}}
  .lead-cat{{display:inline-block;background:#c81e1e;color:#fff;font-size:0.72rem;font-weight:700;padding:3px 8px;text-transform:uppercase;margin-bottom:10px;}}
  .lead-box h1{{font-family:Georgia,'Times New Roman',serif;font-size:2rem;font-weight:700;color:#111;line-height:1.25;margin-bottom:10px;}}
  .lead-sub{{font-size:1rem;color:#404040;margin-bottom:10px;}}
  .byline{{font-size:0.78rem;color:#737373;text-transform:uppercase;letter-spacing:0.3px;}}
  .byline b{{color:#c81e1e;}}
  .byline a{{color:#1d4ed8;text-decoration:none;font-weight:600;}}
  .layout{{display:grid;grid-template-columns:2fr 1fr;gap:32px;align-items:start;}}
  .story{{padding:16px 0;border-bottom:1px solid #e5e5e5;}}
  .cat{{font-size:0.7rem;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;display:inline-block;margin-bottom:5px;}}
  .cat.alert{{color:#c81e1e;}}
  .cat.safe{{color:#1e40af;}}
  .story h3{{font-family:Georgia,'Times New Roman',serif;font-size:1.14rem;font-weight:700;line-height:1.35;margin-bottom:6px;}}
  .story h3 a{{color:#111;text-decoration:none;}}
  .story h3 a:hover{{color:#c81e1e;}}
  .fact-box{{font-size:0.88rem;color:#374151;background:#fef2f2;border-left:3px solid #c81e1e;padding:6px 10px;margin:8px 0;}}
  .side-box{{background:#f9f9f9;border-top:3px solid #1f1f1f;padding:18px;margin-bottom:20px;}}
  .side-box h4{{font-size:0.85rem;text-transform:uppercase;letter-spacing:0.6px;margin-bottom:10px;color:#111;}}
  .stat-row{{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #e5e5e5;font-size:0.88rem;}}
  .tg-btn{{display:block;text-align:center;background:#c81e1e;color:#fff;text-decoration:none;font-weight:700;font-size:0.84rem;padding:10px;border-radius:3px;margin-top:12px;text-transform:uppercase;}}
  .kw{{display:inline-block;background:#fff;border:1px solid #d4d4d4;font-size:0.75rem;padding:3px 8px;margin:3px 3px 0 0;color:#404040;}}
  .portals a{{display:block;color:#1e40af;text-decoration:none;font-size:0.85rem;padding:5px 0;font-weight:600;}}
  @media(max-width:760px){{.layout{{grid-template-columns:1fr;}}.lead-box h1{{font-size:1.5rem;}}}}
</style></head>
<body>
<div class="top-strip"><div class="top-in">
  <div>{today_str} &bull; India Edition</div>
  <a class="top-btn" href="https://t.me/rakshanet_devansh_bot" target="_blank">VERIFY A VIDEO OR CLAIM</a>
</div></div>
<div class="masthead">
  <div class="logo">Raksha<span>Net</span></div>
  <div class="tagline">Evidence-First Fact-Check, Narrative Counter &amp; OSINT Desk &bull; Updated {time_str}</div>
</div>
<div class="cat-bar"><div class="cat-in">
  <div class="nav-tabs">
    <button class="tab active" onclick="setType('all',this)">All</button>
    <button class="tab" onclick="setType('narrative',this)">Narrative Counter</button>
    <button class="tab" onclick="setType('safe',this)">Defence Monitor</button>
  </div>
  <div class="search-box"><input id="q" type="text" placeholder="Search claims or news..." oninput="filterItems()"></div>
</div></div>
<div class="wrap">
  <div class="crumb">Home &rsaquo; India &rsaquo; Fact-Check &amp; Narrative Desk</div>
  <section class="lead-box">
  <span class="lead-cat">Verified Counter-Report</span>
    <h1>{lead_title}</h1>
    <p class="lead-sub">{lead_fact}</p>
    <div class="byline">Verified By: <b>RakshaNet Engine</b> &bull; {time_str} &bull; <a href="{lead_url}" target="_blank">View Official Proof &rarr;</a></div>
  </section>
  <div class="layout">
    <main>{feed_html or '<p>No items logged yet.</p>'}</main>
    <aside>
      <div class="side-box">
        <h4>Desk Summary</h4>
        <div class="stat-row"><span>Narrative Counters</span><strong style="color:#c81e1e">{len(nar_rows)}</strong></div>
        <div class="stat-row"><span>Defence Monitor</span><strong>{len(rows)}</strong></div>
        <div class="stat-row"><span>Tracked Keywords</span><strong>{len(kw_rows)}+</strong></div>
        <a class="tg-btn" href="https://t.me/rakshanet_devansh_bot" target="_blank">Submit Claim / Video</a>
      </div>
      <div class="side-box"><h4>Active Keywords</h4>{kw_links}</div>
      <div class="side-box portals">
        <h4>Official Govt Portals</h4>
        <a href="https://factcheck.pib.gov.in/" target="_blank">PIB Fact Check &rarr;</a>
        <a href="https://sancharsaathi.gov.in/sfc" target="_blank">Sanchar Saathi (Chakshu) &rarr;</a>
        <a href="https://cybercrime.gov.in/" target="_blank">National Cyber Crime Portal &rarr;</a>
      </div>
    </aside>
  </div>
</div>
<script>
let cur='all';
function setType(t,el){{cur=t;document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));el.classList.add('active');filterItems();}}
function filterItems(){{const q=document.getElementById('q').value.toLowerCase();document.querySelectorAll('.story').forEach(c=>{{const okT=(cur==='all'||c.dataset.type===cur);const okQ=c.innerText.toLowerCase().includes(q);c.style.display=(okT&&okQ)?'block':'none';}});}}
</script></body></html>"""

    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("[Reach] Proof-first portal updated at: docs/index.html")


build_public_site()