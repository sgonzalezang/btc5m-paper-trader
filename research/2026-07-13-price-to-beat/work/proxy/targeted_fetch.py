#!/usr/bin/env python3
"""Targeted Pyth fetch: all 19 Coinbase-wrong intervals + stratified sample
concentrated on the near-flat danger zone, plus a control sample. Fetches only
boundaries not already cached. STDLIB ONLY."""
import json, os, time, random, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
BTC = "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"
OUT = os.path.join(HERE, "pyth_boundaries.json")
cb = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/cb1m.json"))
o = {t: v for t, v in zip(cb["t"], cb["o"])}
res = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data/pm_res_3d.json"))
cache = json.load(open(OUT)) if os.path.exists(OUT) else {}

rows = []
for t0, up in res:
    s, e = o.get(t0), o.get(t0 + 300)
    if s is None or e is None: continue
    mv = e - s
    rows.append({"t0": t0, "bps": mv / s * 1e4, "wrong": (mv > 0) != (up == 1)})

wrong = [r["t0"] for r in rows if r["wrong"]]
nearflat = [r["t0"] for r in rows if abs(r["bps"]) < 5]
control = [r["t0"] for r in rows if abs(r["bps"]) >= 10]
random.seed(42)
sel = set(wrong)
sel |= set(random.sample(nearflat, min(160, len(nearflat))))
sel |= set(random.sample(control, min(60, len(control))))

need = sorted({b for t0 in sel for b in (t0, t0 + 300)} - set(int(k) for k in cache))
print(f"selected intervals={len(sel)} boundaries_needed(new)={len(need)}", flush=True)

def fetch(ts):
    url = f"https://hermes.pyth.network/v2/updates/price/{ts}?ids[]={BTC}"
    req = urllib.request.Request(url, headers={"User-Agent": "btc5m/1.0"})
    for a in range(10):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.loads(r.read().decode())
            p = d["parsed"][0]["price"]
            time.sleep(1.1)
            return int(p["price"]) * 10 ** p["expo"], int(p["publish_time"])
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(4.0); continue
            if a >= 6: return None, f"HTTP{e.code}"
            time.sleep(2.0)
        except Exception as e:
            if a >= 6: return None, str(e)[:40]
            time.sleep(2.0)
    return None, "exhausted"

t0 = time.time()
for i, b in enumerate(need):
    price, pub = fetch(b)
    cache[str(b)] = {"price": price, "pub": pub}
    if (i + 1) % 20 == 0 or i == len(need) - 1:
        json.dump(cache, open(OUT, "w"))
        print(f"  {i+1}/{len(need)} ts={b} price={price} {time.time()-t0:.0f}s", flush=True)
json.dump(cache, open(OUT, "w"))
ok = sum(1 for v in cache.values() if isinstance(v.get("price"), (int, float)))
print(f"DONE_TARGETED cache={len(cache)} ok={ok}", flush=True)
