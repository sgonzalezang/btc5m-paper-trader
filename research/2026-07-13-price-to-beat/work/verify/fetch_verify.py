import json, urllib.request, time, hashlib, random, datetime as dt

prior = {r['t0'] for r in json.load(open('../source/meta_rows.json'))}
pm = dict((t0,up) for t0,up in json.load(open('/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data/pm_res_3d.json')))

random.seed(42)
# Sample A: 25 t0s that ARE in pm_res_3d (to cross-check outcome truth); mix of prior/not-prior
res_t0s = sorted(pm.keys())
sampA = random.sample(res_t0s, 25)
# Sample B: brand-new t0s NOT in prior 67 and NOT in pm_res_3d — extend coverage.
# recent grid: Jul 11-13 window, pick 15 across hours
base = 1783700000 - (1783700000 % 300)
candB=[]
t=base
while t < 1783960000:
    if t not in prior and t not in pm:
        candB.append(t)
    t+=300
sampB = random.sample(candB, 15)

cands = sorted(set(sampA)|set(sampB))
rows=[]
for t0 in cands:
    slug=f"btc-updown-5m-{t0}"
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://gamma-api.polymarket.com/events?slug={slug}", headers={"User-Agent":"Mozilla/5.0"}), timeout=25) as r:
            d=json.load(r)
    except Exception as e:
        rows.append({'t0':t0,'ok':False,'err':str(e)}); time.sleep(0.3); continue
    if not d:
        rows.append({'t0':t0,'ok':False,'err':'empty'}); time.sleep(0.3); continue
    ev=d[0]; m=ev['markets'][0]
    desc=m.get('description') or ''
    op=m.get('outcomePrices')
    try:
        opl=json.loads(op); up_price=float(opl[0])
    except: up_price=None
    rows.append({
      't0':t0,'ok':True,
      'in_prior':t0 in prior,'in_pm':t0 in pm,
      'title':ev.get('title'),
      'mkt_resSrc':m.get('resolutionSource'),
      'ev_resSrc':ev.get('resolutionSource'),
      'closed':m.get('closed'),'uma':m.get('umaResolutionStatus'),
      'outcomes':m.get('outcomes'),'outcomePrices':op,
      'up_from_prices': (1 if up_price==1.0 else 0 if up_price==0.0 else None),
      'pm_up': pm.get(t0),
      'desc_sha': hashlib.sha256(desc.encode()).hexdigest()[:12],
      'desc_len':len(desc),
      'mentions_coinbase':'coinbase' in desc.lower(),
      'mentions_chainlink':'chainlink' in desc.lower(),
      'has_ge':'greater than or equal' in desc.lower(),
      'endDate':m.get('endDate'),'umaEndDate':m.get('umaEndDate'),
      'secondsDelay':m.get('secondsDelay'),
    })
    time.sleep(0.25)
json.dump(rows,open('verify_rows.json','w'),indent=1)
ok=[r for r in rows if r.get('ok')]
print('fetched',len(rows),'ok',len(ok))
