import os
import re

target_file = r"C:\Users\WS\Desktop\antigravity\CAF\DeFi [L]Earn. Strategies\messages.html"

with open(target_file, "r", encoding="utf-8") as f:
    content = f.read()

blocks = re.findall(
    r'<div class="message [^"]*" id="message-(\d+)">([\s\S]*?)(?=<div class="message [^"]*" id="message-|\Z)',
    content
)

key_ids = ["335", "337", "338", "345", "346", "347", "348", "353", "354"]

for msg_id, block in blocks:
    if msg_id in key_ids:
        date_m = re.search(r'<div class="pull_right date details" title="([^"]+)">', block)
        date_str = date_m.group(1) if date_m else ""
        text_m = re.search(r'<div class="text">\s*([\s\S]*?)\s*</div>', block)
        if text_m:
            raw_text = text_m.group(1)
            clean_text = re.sub(r'<[^>]+>', ' ', raw_text)
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            print(f"\n=================== POST ID {msg_id} ({date_str}) ===================")
            print(clean_text)
