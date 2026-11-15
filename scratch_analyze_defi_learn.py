import os
import re
from glob import glob
from collections import Counter

target_file = r"C:\Users\WS\Desktop\antigravity\CAF\DeFi [L]Earn. Strategies\messages.html"

with open(target_file, "r", encoding="utf-8") as f:
    content = f.read()

title_m = re.search(r'<div class="text bold">\s*([^<]+)\s*</div>', content)
chat_name = title_m.group(1).strip() if title_m else "Unknown"

blocks = re.findall(
    r'<div class="message [^"]*" id="message-(\d+)">([\s\S]*?)(?=<div class="message [^"]*" id="message-|\Z)',
    content
)

all_messages = []
authors = Counter()

for msg_id, block in blocks:
    from_m = re.search(r'<div class="from_name">\s*([^<]+)\s*</div>', block)
    author = from_m.group(1).strip() if from_m else "Unknown"
    authors[author] += 1
    
    date_m = re.search(r'<div class="pull_right date details" title="([^"]+)">', block)
    date_str = date_m.group(1) if date_m else ""
    
    text_m = re.search(r'<div class="text">\s*([\s\S]*?)\s*</div>', block)
    if text_m:
        raw_text = text_m.group(1)
        clean_text = re.sub(r'<[^>]+>', ' ', raw_text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        if clean_text:
            all_messages.append({
                "id": msg_id,
                "date": date_str,
                "author": author,
                "text": clean_text
            })

print(f"Chat Name: {chat_name}")
print(f"Total parsed messages: {len(all_messages)}")
print(f"Authors: {authors.most_common(10)}")
if all_messages:
    print(f"Date range: {all_messages[0]['date']} to {all_messages[-1]['date']}")
    print("\n--- SAMPLE FIRST 5 MESSAGES ---")
    for m in all_messages[:5]:
        print(f"[{m['date']}] {m['author']}: {m['text'][:140]}")
    print("\n--- SAMPLE LAST 5 MESSAGES ---")
    for m in all_messages[-5:]:
        print(f"[{m['date']}] {m['author']}: {m['text'][:140]}")
