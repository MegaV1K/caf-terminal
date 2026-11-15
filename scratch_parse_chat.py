import os
import re
from glob import glob

folder = r"C:\Users\WS\Desktop\antigravity\CAF\что-то про крипту"
html_files = sorted(glob(os.path.join(folder, "messages*.html")))

print(f"Found {len(html_files)} html files.")

chat_name = None
all_messages = []

for file_path in html_files:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    if not chat_name:
        title_m = re.search(r'<div class="text bold">\s*([^<]+)\s*</div>', content)
        if title_m:
            chat_name = title_m.group(1).strip()
            
    # Extract messages: date, from_name, text
    # Telegram HTML export structure:
    # <div class="message default clearfix" id="...">
    #   <div class="from_name">...</div>
    #   <div class="pull_right date details" title="...">...</div>
    #   <div class="text">...</div>
    blocks = re.findall(
        r'<div class="message [^"]*" id="message-(\d+)">([\s\S]*?)(?=<div class="message [^"]*" id="message-|\Z)',
        content
    )
    for msg_id, block in blocks:
        from_m = re.search(r'<div class="from_name">\s*([^<]+)\s*</div>', block)
        author = from_m.group(1).strip() if from_m else "Unknown"
        
        date_m = re.search(r'<div class="pull_right date details" title="([^"]+)">', block)
        date_str = date_m.group(1) if date_m else ""
        
        text_m = re.search(r'<div class="text">\s*([\s\S]*?)\s*</div>', block)
        if text_m:
            raw_text = text_m.group(1)
            # Remove html tags
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
if all_messages:
    print(f"Date range: {all_messages[0]['date']} to {all_messages[-1]['date']}")
    print("\nSample first 5 messages:")
    for m in all_messages[:5]:
        print(f"[{m['date']}] {m['author']}: {m['text'][:120]}")
    print("\nSample last 5 messages:")
    for m in all_messages[-5:]:
        print(f"[{m['date']}] {m['author']}: {m['text'][:120]}")
