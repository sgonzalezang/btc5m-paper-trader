#!/usr/bin/env python3
"""Refetch CLOB prices-history for ALL triggered markets in pm_res_3d span.
Goal: entry-time (last point <= t0+15) reversal-side price conditional on the
12bps trigger, plus gate features, plus actual resolution. Public GETs only,
>=0.15s sleep, sequential."""
import json, time, urllib.request

S = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
UA = {"User-Agent": "Mozilla/5.0 (research; paper-trading study)"}

def get_json(url, tries=3):
    back = 0.6
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(back); back *= 2
    return None

d = json.load(open(S + "/data/cb5m.json"))
t, o, c = d["t"], d["o"], d["c"]
idx = {tt: i for i, tt in enumerate(t)}
THR = 0.0012

res3 = json.load(open(S + "/data/pm_res_3d.json"))
print("pm_res_3d markets:", len(res3))

trigs = []
for t0, up_won in res3:
    i = idx.get(t0)
    if i is None or i < 14: continue
    pm = (o[i]-o[i-1])/o[i-1]
    if abs(pm) < THR: continue
    num = abs(o[i]-o[i-6]); den = sum(abs(o[j+1]-o[j]) for j in range(i-6,i))
    eff6 = num/den if den>0 else 0.0
    cnt = sum(1 for j in range(i-13,i-1) if abs(o[j+1]-o[j])/o[j] >= THR)
    trigs.append({"t0": t0, "up_won": up_won, "pm": pm, "eff6": eff6, "cnt": cnt,
                  "gated": eff6 >= 0.32 and cnt <= 6, "i": i})
print("triggered markets in span:", len(trigs), " gated:", sum(x["gated"] for x in trigs))

out = []
for k, m in enumerate(trigs):
    t0 = m["t0"]
    ev = get_json(f"https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{t0}")
    time.sleep(0.17)
    if not ev or not ev[0].get("markets"):
        continue
    mk = ev[0]["markets"][0]
    try:
        outcomes = json.loads(mk["outcomes"]); tokens = json.loads(mk["clobTokenIds"])
        up_tok = tokens[outcomes.index("Up")]
    except Exception:
        continue
    h = get_json(f"https://clob.polymarket.com/prices-history?market={up_tok}&startTs={t0-120}&endTs={t0+310}&fidelity=1")
    time.sleep(0.17)
    pts = sorted((p["t"], p["p"]) for p in (h or {}).get("history", []) if "t" in p and "p" in p)
    if not pts: continue
    def last_le(target, maxage=150):
        best = None
        for tt, pp in pts:
            if tt <= target: best = (tt, pp)
            else: break
        if best and target - best[0] <= maxage: return best
        return None
    e = last_le(t0 + 15)
    m2 = dict(m); m2.pop("i")
    m2["entry_up_mid"] = None if e is None else e[1]
    m2["entry_pt_age"] = None if e is None else (t0 + 15 - e[0])
    m2["n_pts"] = len(pts)
    out.append(m2)
    if (k+1) % 25 == 0: print(f"  {k+1}/{len(trigs)}", flush=True)

json.dump(out, open(S + "/work/verify-regime/trig_prices.json", "w"))
print("saved", len(out), "->", S + "/work/verify-regime/trig_prices.json")
