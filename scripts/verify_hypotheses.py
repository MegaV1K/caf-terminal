import json
from pathlib import Path

def inspect_coingecko():
    p = Path("data/cache/coingecko_markets_top_300.json")
    if not p.exists():
        print("CoinGecko cache not found!")
        return
    
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    targets = [
        "btc", "eth", "hype", "aave", "tao", "akt", "ray", "jup",
        "sui", "trac", "pendle", "geod", "ondo", "fluid", "ena",
        "render", "grass", "inj", "deep", "drift", "ath", "kmno"
    ]
    
    print("=" * 80)
    print("COINGECKO CACHE AUDIT")
    print("=" * 80)
    by_sym = {d["symbol"].lower(): d for d in data}
    for t in targets:
        info = by_sym.get(t)
        if not info:
            print(f"[-] {t.upper()}: Not in top 300 cache")
            continue
        p = info.get("current_price")
        ath = info.get("ath")
        ath_d = info.get("ath_date", "")[:10]
        ath_chg = info.get("ath_change_percentage")
        mcap = info.get("market_cap")
        fdv = info.get("fully_diluted_valuation")
        circ = info.get("circulating_supply")
        total = info.get("total_supply")
        max_s = info.get("max_supply")
        print(f"[+] {t.upper():<7} Price: ${p} | ATH: ${ath} ({ath_d}, {ath_chg:.1f}%) | MCap: ${mcap:,} | FDV: ${fdv:,} | Circ: {circ:,.0f} | Max: {max_s}")

def inspect_defillama():
    f_path = Path("data/cache/defillama_fees.json")
    if not f_path.exists():
        print("DefiLlama fees not found!")
        return
    with open(f_path, "r", encoding="utf-8") as f:
        fees_data = json.load(f)
        
    protocols = fees_data.get("protocols", [])
    print("\n" + "=" * 80)
    print("DEFILLAMA FEES & REVENUE AUDIT (24h / 7d / 30d annualized)")
    print("=" * 80)
    names = ["hyperliquid", "aave", "raydium", "jupiter", "ethena", "pendle", "injective", "drift"]
    for p in protocols:
        name_lc = (p.get("name") or "").lower()
        module_lc = (p.get("module") or "").lower()
        matched = [n for n in names if n in name_lc or n in module_lc]
        if matched:
            t24 = p.get("total24h") or 0
            r24 = p.get("totalRevenue24h") or 0
            t30 = p.get("total30d") or 0
            r30 = p.get("totalRevenue30d") or 0
            print(f"[+] {p.get('name')} ({p.get('symbol')}): 24h Fees: ${t24:,.0f} | 24h Rev: ${r24:,.0f} | 30d Fees: ${t30:,.0f} | 30d Rev: ${r30:,.0f}")

if __name__ == "__main__":
    inspect_coingecko()
    inspect_defillama()
