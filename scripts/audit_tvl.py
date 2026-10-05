import json
from pathlib import Path

def inspect_tvl():
    p = Path("data/cache/defillama_protocols.json")
    if not p.exists():
        print("defillama_protocols.json not found")
        return
    with open(p, "r", encoding="utf-8") as f:
        protocols = json.load(f)

    keywords = ["aave", "fluid", "pendle", "kamino", "raydium", "drift", "ethena", "deepbook", "hyperliquid", "sui"]
    found = []
    for pr in protocols:
        name = pr.get("name") or ""
        sym = pr.get("symbol") or ""
        slug = pr.get("slug") or ""
        tvl = pr.get("tvl") or 0
        if any(k in name.lower() or k == sym.lower() or k in slug.lower() for k in keywords):
            found.append({
                "name": name,
                "symbol": sym,
                "tvl": tvl,
                "category": pr.get("category"),
                "chain": pr.get("chain"),
                "chains_count": len(pr.get("chains") or [])
            })

    found.sort(key=lambda x: x["tvl"], reverse=True)
    print("=" * 80)
    print("KEY PROTOCOLS TVL (DEFILLAMA CACHE)")
    print("=" * 80)
    for f_item in found[:20]:
        print(f"[+] {f_item['name']:<24} ({f_item['symbol']:<8}) TVL: ${f_item['tvl']:>14,.0f} | Cat: {f_item['category']:<16} | Chain: {f_item['chain']}")

if __name__ == "__main__":
    inspect_tvl()
