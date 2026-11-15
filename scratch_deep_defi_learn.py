import os
import re
from collections import Counter, defaultdict

target_file = r"C:\Users\WS\Desktop\antigravity\CAF\DeFi [L]Earn. Strategies\messages.html"

with open(target_file, "r", encoding="utf-8") as f:
    content = f.read()

blocks = re.findall(
    r'<div class="message [^"]*" id="message-(\d+)">([\s\S]*?)(?=<div class="message [^"]*" id="message-|\Z)',
    content
)

all_messages = []
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

print(f"Total messages: {len(all_messages)}")

by_year = defaultdict(list)
for m in all_messages:
    m_year = re.search(r'\.(\d{4})\b', m["date"])
    year = m_year.group(1) if m_year else "Unknown"
    by_year[year].append(m)

for y in sorted(by_year.keys()):
    print(f"Year {y}: {len(by_year[y])} messages")

# Search protocols mentioned
protocols = [
    "Aave", "Compound", "Maker", "MakerDAO", "Sky", "Morpho", "Euler", "Fluid", "Pendle",
    "Uniswap", "Curve", "Convex", "Yearn", "Ethena", "USDe", "EigenLayer", "Lido",
    "Steakhouse", "Re7", "Gauntlet", "Zama", "Gearbox", "GMX", "Hyperliquid", "Synthetix",
    "Liquity", "Frax", "Balanc", "Abracadabra", "Anchor", "Celsius"
]

proto_counter = Counter()
for m in all_messages:
    t_lower = m["text"].lower()
    for p in protocols:
        if p.lower() in t_lower:
            proto_counter[p] += 1

print("\nTop protocols mentioned:")
for p, c in proto_counter.most_common(20):
    print(f"  {p}: {c}")

# Let's see strategies and post titles/topics
print("\n--- DETAILED LOOK AT RECENT POSTS (2025-2026) ---")
recent = [m for m in all_messages if any(y in m["date"] for y in [".2025", ".2026"])]
print(f"Recent posts (2025-2026): {len(recent)}")
for m in recent[-15:]:
    first_line = m["text"][:100]
    print(f"[{m['date']}] (ID {m['id']}): {first_line}...")
