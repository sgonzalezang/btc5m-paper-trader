#!/usr/bin/env python3
"""Backfill Pyth BTC/USD at each oracle boundary. STDLIB ONLY.
Caches {ts: {price, pub}} to pyth_boundaries.json, checkpointing every 20."""
import json, time, urllib.request, os

BTC = "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"
HERE = os.path.dirname(os.path.abspath(__file__))
RES = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data/pm_res_3d.json"
OUT = os.path.join(HERE, "pyth_boundaries.json")

res = json.load(open(RES))
rts = sorted(r[0] for r in res)
boundaries = sorted(set(rts) | set(t + 300 for t in rts))  # strike + settle instants

cache = {}
if os.path.exists(OUT):
    cache = json.load(open(OUT))

def fetch(ts):
    url = f"https://hermes.pyth.network/v2/updates/price/{ts}?ids[]={BTC}"
    req = urllib.request.Request(url, headers={"User-Agent": "btc5m-proxy/1.0"})
    for attempt in range(8):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.loads(r.read().decode())
            p = d["parsed"][0]["price"]
            time.sleep(1.2)                       # pace ~1 req/s to respect Hermes limit
            return int(p["price"]) * 10 ** p["expo"], int(p["publish_time"])
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(4.0)                  # rolling-window backoff, retry same ts
                continue
            if attempt >= 5:
                return None, f"HTTP{e.code}"
            time.sleep(2.0)
        except Exception as e:
            if attempt >= 5:
                return None, str(e)[:60]
            time.sleep(2.0)
    return None, "retries_exhausted"

todo = [b for b in boundaries if str(b) not in cache]
print(f"boundaries total={len(boundaries)} cached={len(cache)} todo={len(todo)}", flush=True)
t0 = time.time()
for i, b in enumerate(todo):
    price, pub = fetch(b)
    cache[str(b)] = {"price": price, "pub": pub}
    if (i + 1) % 20 == 0 or i == len(todo) - 1:
        json.dump(cache, open(OUT, "w"))
        el = time.time() - t0
        print(f"  {i+1}/{len(todo)}  last ts={b} price={price} pub={pub}  {el:.0f}s", flush=True)
json.dump(cache, open(OUT, "w"))
ok = sum(1 for v in cache.values() if isinstance(v.get("price"), (int, float)))
print(f"DONE cached={len(cache)} ok={ok}", flush=True)
