import os
import re
from glob import glob
from collections import Counter

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
        from_m = re.search(r'<div class="from_name">\s*([^<]+)\s*</div>', block)
        author = from_m.group(1).strip() if from_m else "Unknown"
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

print(f"Total messages: {len(all_messages)}")

# Tokens of interest
tokens = [
    "Akash", "AKT", "Render", "RNDR", "RENDER", "Injective", "INJ", "Fluid", "FLUID",
    "Pendle", "PENDLE", "Jupiter", "JUP", "Solana", "SOL", "Bitcoin", "BTC", "Ethereum", "ETH",
    "Hyperliquid", "HYPE", "Sui", "SUI", "Aptos", "APT", "Taiko", "ZkSync", "Starknet", "STRK",
    "LayerZero", "Arbitrum", "ARB", "Optimism", "OP", "Celestia", "TIA", "Sei", "SEI",
    "Near", "NEAR", "Bittensor", "TAO", "Kaspa", "KAS", "Ethena", "ENA", "Aave", "AAVE",
    "Grass", "GRASS", "Raydium", "RAY"
]

token_counts = Counter()
token_mentions = {t: [] for t in tokens}

for m in all_messages:
    t_upper = m["text"].upper()
    for t in tokens:
        pattern = r'\b' + re.escape(t.upper()) + r'\b'
        if re.search(pattern, t_upper):
            token_counts[t] += 1
            if len(token_mentions[t]) < 10:
                token_mentions[t].append((m["date"], m["text"][:150]))

print("\n--- TOKEN MENTIONS IN CHANNEL ---")
for t, count in token_counts.most_common(30):
    print(f"{t}: {count} mentions")

# Major Themes search
themes = {
    "Ретродропы / Тестнеты": ["ретро", "дроп", "тестнет", "сибил", "нода", "амбассадор", "клейм", "points", "поинт"],
    "Трейдинг / Фьючерсы / Спот": ["шорт", "лонг", "плечо", "фьюч", "спот", "стоп", "ликвид", "тейк", "купил", "продал"],
    "Опционы / Деривативы": ["опцион", "deribit", "дерибит", "страйк", "волатильн", "грек", "гамма"],
    "DeFi / Доходность / Стейкинг": ["стейкинг", "фарминг", "apy", "tvl", "ликвидност", "пул", "процент", "лендинг"],
    "AI / DePIN": ["ai", "ии", "depin", "gpu", "вычислени", "майнинг", "нейросет"],
    "Психология / Рефлексия / Убытки": ["фомо", "fomo", "убыток", "минус", "слил", "тильт", "устал", "депресси", "заработал", "просадка"]
}

theme_counts = Counter()
for m in all_messages:
    t_lower = m["text"].lower()
    for theme, keywords in themes.items():
        if any(kw in t_lower for kw in keywords):
            theme_counts[theme] += 1

print("\n--- THEMATIC DISTRIBUTION ---")
for th, count in theme_counts.most_common():
    print(f"{th}: {count} messages ({count/len(all_messages)*100:.1f}%)")
