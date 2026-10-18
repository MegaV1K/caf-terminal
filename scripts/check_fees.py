import json

f = json.load(open('data/cache/defillama_fees.json', encoding='utf-8'))
protos = f.get('protocols', [])

targets = ['RAYDIUM', 'JUPITER', 'PENDLE', 'FLUID', 'ETHENA', 'DEEPBOOK', 'COW', 'MAPLE', 'SYRUP', 'AKASH', 'RENDER', 'GEOD', 'ORIGINTRAIL', 'TRAC', 'GMX']

found = {}
for p in protos:
    name = p.get('name', '')
    sym = p.get('symbol', '')
    combined = (name + ' ' + sym).upper()
    for t in targets:
        if t in combined:
            found[name] = {
                'symbol': sym,
                'total24h_fees': p.get('total24h', 0),
                'total30d_fees': p.get('total30d', 0),
                'total24h_rev': p.get('dailyRevenue', 0),
                'total30d_rev': p.get('monthlyRevenue', 0),
            }

for name, data in sorted(found.items()):
    f24 = f"${data['total24h_fees']:,.0f}" if data['total24h_fees'] else "$0"
    f30 = f"${data['total30d_fees']:,.0f}" if data['total30d_fees'] else "$0"
    r24 = f"${data['total24h_rev']:,.0f}" if data['total24h_rev'] else "$0"
    r30 = f"${data['total30d_rev']:,.0f}" if data['total30d_rev'] else "$0"
    print(f"{name:<25} ({data['symbol']}): Fees 24h={f24:<10} 30d={f30:<12} | Rev 24h={r24:<10} 30d={r30}")
