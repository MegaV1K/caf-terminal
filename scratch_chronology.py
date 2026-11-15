import os
import re
from glob import glob
from collections import defaultdict

folder = r"C:\Users\WS\Desktop\antigravity\CAF\что-то про крипту"
html_files = sorted(glob(os.path.join(folder, "messages*.html")))

all_messages = []
for file_path in html_files:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    blocks = re.findall(
        r'<div class="message [^"]*" id="message-(\d+)">([\s\S]*?)(?=<div class="message [^"]*" id="message-|\Z)',
        content
    )
    for msg_id, block in blocks:
        date_m = re.search(r'<div class="pull_right date details" title="([^"]+)">', block)
        date_str = date_m.group(1) if date_m else ""
        text_m = re.search(r'<div class="text">\s*([\s\S]*?)\s*</div>', block)
        if text_m:
            raw_text = text_m.group(1)
            clean_text = re.sub(r'<[^>]+>', ' ', raw_text)
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            if clean_text:
                all_messages.append({"id": msg_id, "date": date_str, "text": clean_text})

by_year = defaultdict(list)
for m in all_messages:
    # date_str format: "30.12.2021 10:02:57 GMT+02:00"
    m_year = re.search(r'\.(\d{4})\b', m["date"])
    year = m_year.group(1) if m_year else "Unknown"
    by_year[year].append(m)

print("Messages per year:")
for y in sorted(by_year.keys()):
    print(f"  {y}: {len(by_year[y])} messages")

# Let's inspect long, detailed, thoughtful posts in each year (posts > 200 chars)
for y in ["2022", "2023", "2024", "2025", "2026"]:
    print(f"\n=================== KEY POSTS FROM {y} ===================")
    long_posts = [m for m in by_year[y] if len(m["text"]) > 250]
    print(f"Total long posts in {y}: {len(long_posts)}")
    for p in long_posts[:5]:
        print(f"--- [{p['date']}] ---")
        print(p["text"][:350] + ("..." if len(p["text"]) > 350 else ""))
