import json, urllib.request, time, datetime
res={t0:up for t0,up in json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data/pm_res_3d.json"))}
# 19 disagreements + 6 agreement samples
dis=[1783438800,1783440600,1783450800,1783452900,1783460400,1783472100,1783497600,1783504500,1783526100,1783527900,1783537200,1783547700,1783591800,1783594800,1783614300,1783618800,1783621800,1783632600,1783654200]
agree=[1783425300,1783425600,1783426500,1783500000,1783600000-100,1783683900]
def fetch(t0):
    url=f"https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{t0}"
    req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    try:
        d=json.load(urllib.request.urlopen(req,timeout=25))
    except Exception as e: return None,str(e)
    if not d: return None,"empty"
    for e in d:
        for m in e.get('markets',[]):
            outs=json.loads(m.get('outcomes','[]')) if isinstance(m.get('outcomes'),str) else m.get('outcomes')
            prices=json.loads(m.get('outcomePrices','[]')) if isinstance(m.get('outcomePrices'),str) else m.get('outcomePrices')
            q=m.get('question')
            # Up price
            up_price=None
            if outs and prices:
                for o,p in zip(outs,prices):
                    if o.lower()=="up": up_price=float(p)
            return (1 if up_price and up_price>0.5 else 0), q
    return None,"nomarket"
mism=0
for t0 in dis+agree:
    g,q=fetch(t0)
    r=res.get(t0)
    tag="DIS" if t0 in dis else "agr"
    ok = (g==r)
    if not ok: mism+=1
    print(f"{tag} t0={t0} {datetime.datetime.utcfromtimestamp(t0)}UTC  gamma_up={g} pm_res_up={r} {'OK' if ok else 'MISMATCH!!'}  {q}")
    time.sleep(0.3)
print("\nmismatches gamma-vs-pm_res:", mism)
