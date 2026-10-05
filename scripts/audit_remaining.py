import json
from pathlib import Path

def inspect_remaining_assets():
    p = Path("data/cache/coingecko_markets_top_300.json")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    by_s = {d["symbol"].lower(): d for d in data}
    tokens = ["tao", "sui", "pendle", "ondo", "fluid", "inj", "render", "grass", "drift", "ath", "kmno"]
    
    print("=" * 90)
    print("DETAILED REMAINING TOKENS AUDIT (COINGECKO CACHE)")
    print("=" * 90)
    for t in tokens:
        d = by_s.get(t)
        if not d:
            print(f"[-] {t.upper()} not found in top 300 cache")
            continue
        p = d.get("current_price")
        mcap = d.get("market_cap") or 0
        fdv = d.get("fully_diluted_valuation") or 0
        circ = d.get("circulating_supply") or 0
        tot = d.get("total_supply") or circ
        max_s = d.get("max_supply") or tot
        ratio = (circ / max_s * 100.0) if max_s else 100.0
        fdv_mcap = (fdv / mcap) if mcap > 0 else 1.0
        print(f"[+] {t.upper():<7} Price: ${p:<8} | MCap: ${mcap:>13,} | FDV: ${fdv:>13,} | Circ%: {ratio:>5.1f}% | FDV/MCap: {fdv_mcap:.2f}x")

def inspect_tvl_and_chains():
    p = Path("data/cache/defillama_protocols.json")
    if not p.exists():
        return
    with open(p, "r", encoding="utf-8") as f:
        protos = json.load(f)
    print("\n" + "=" * 90)
    print("DEFILLAMA PROTOCOL TVL AUDIT")
    print("=" * 90)
    targets = ["aave", "fluid", "pendle", "kamino", "raydium", "drift", "ethena", "deepbook"]
    by_name = {}
    for pr in protos:
        name_lc = (pr.get("name") or "").lower()
        slug_lc = (pr.get("slug") or "").lower()
        for t in targets:
            if t == name_lc or t == slug_lc:
                tvl = pr.get("tvl") or 0
                chain = pr.get("chain")
                chains = pr.get("chains") or []
                print(f"[+] {pr.get('name'):<16} ({pr.get('symbol')}): TVL: ${tvl:>14,.0f} | Main Chain: {chain} | Chains: {len(chains)}")

if __name__ == "__main__":
    inspect_remaining_assets()
    inspect_tvl_and_chains()
