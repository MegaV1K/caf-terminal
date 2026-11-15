import os
import re
from glob import glob

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

# Search for pain points, retro sentiments, trading shifts
keywords = ["ретро", "дроп", "скам", "бритв", "поинт", "убыт", "слил", "рынок", "депрес", "софт", "приватк", "нод"]

matched = []
for m in all_messages:
    if any(k in m["text"].lower() for k in ["бритв", "скам", "не дали", "нот элигбл", "минус", "разочар", "ретро мертв"]):
        matched.append(m)

print(f"Total matching critical sentiment posts: {len(matched)}")
for m in matched[-15:]:
    print(f"\n[{m['date']}] (ID {m['id']}):")
    print(m["text"][:300])
