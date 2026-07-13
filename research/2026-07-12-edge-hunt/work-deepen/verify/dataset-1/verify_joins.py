#!/usr/bin/env python3
"""Verify joins/validation claims: prior recon, measure book, ledger, label-vs-PM,
live coverage, ivlHist2 feed-vs-candle noise, borderline mass, alt rows, real joins."""
import json, datetime
D = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
OLD = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data"
W = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work-deepen/dataset"
IVL = 300
def utc(t): return datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d %H:%M")

pub = json.load(open(f"{W}/signals_60d.json"))
rows = pub["rows"]; byt0 = {r["t0"]: r for r in rows}

# ---------- prior recon (independent, their tie rule: sign, r0==0 -> up) ----------
old5 = json.load(open(f"{OLD}/cb5m.json"))
lo, hi = old5["t"][0], old5["t"][-1]
print("prior cb5m window:", utc(lo), "->", utc(hi), "candles:", len(old5["t"]))
og = [(old5["t"][i], old5["t"][i+1]) for i in range(len(old5["t"])-1) if old5["t"][i+1]-old5["t"][i] != 300]
print("prior cb5m gaps:", len(og))
# also: do old and new cb5m agree on overlapping opens?
cb = json.load(open(f"{D}/cb5m.json"))
idxn = {t: i for i, t in enumerate(cb["t"])}
diff_o = sum(1 for i, t in enumerate(old5["t"]) if t in idxn and old5["o"][i] != cb["o"][idxn[t]])
print("old-vs-new cb5m open disagreements on overlap:", diff_o)

n_all = n_sel = w = 0
for t0 in range(lo, hi + 1, IVL):
    r = byt0.get(t0)
    if r is None or not r["trigger"] or not r["gateReady"]: continue
    n_all += 1
    if not r["gatePass"]: continue
    n_sel += 1
    lab = "up" if r["ret0"] > 0 else ("down" if r["ret0"] < 0 else "up")
    w += (r["side"] == lab)
print(f"recon: n_all {n_all} (claim 4022) n_sel {n_sel} (claim 2742) q {w/n_sel:.4f} (claim .5511) wins {w} delta_wins {round((0.5511 - w/n_sel)*n_sel, 1)}")

# ---------- ivlHist2 feed-vs-candle ----------
st = json.load(open(f"{D}/state_extract.json"))
ih2 = st["ivlHist2"]
O = cb["o"]
ds = []
for t0, rfeed in ih2:
    i = idxn.get(t0)
    if i is None or idxn.get(t0 + 300) is None: continue
    rc = (O[idxn[t0+300]] - O[i]) / O[i]
    ds.append((t0, rfeed * 1e4, rc * 1e4, abs(rfeed - rc) * 1e4))
ds_abs = sorted(x[3] for x in ds)
print(f"\nivlHist2 n={len(ds)} |feed-candle| bps: median {ds_abs[len(ds_abs)//2]:.2f} max {ds_abs[-1]:.2f}")
b = [x for x in ds if x[0] == 1783908900]
print("interval 1783908900 feed vs candle bps:", [(round(x[1],2), round(x[2],2)) for x in b], "(claim +12.90 vs +11.10)")

# ---------- ledger ----------
trades = json.load(open(f"{D}/trades_unified.json"))
v3 = [t for t in trades if t.get("eng") in ("impulse_v2", "impulse50", "reversal_v2")]
from collections import Counter
print("\nv3 trades:", len(v3), Counter(t["eng"] for t in v3))
exc = []
for t in v3:
    r = byt0.get(t["t0"])
    gated = t["eng"] in ("impulse_v2", "impulse50")
    if r is None: exc.append((t["eng"], t["t0"], "past-horizon")); continue
    if not r["trigger"] or (gated and not r["gatePass"]):
        exc.append((t["eng"], t["t0"], f"trig={r['trigger']} gp={r['gatePass']} cnt12={r['cnt12']} eff6={r['eff6']} pm={r['feats']['pm']}"))
print("exceptions:", len(exc), "(claim 13)")
c = Counter(x[1] for x in exc)
print("by t0:", dict(c), "distinct t0s:", len(c))
# measurement-first: every fired impulse_v2/impulse50 trade t0 in measure book?
meas_t0 = {m["t0"] for m in st["measure"]}
fired = {t["t0"] for t in v3 if t["eng"] in ("impulse_v2", "impulse50")}
print("fired gated-engine t0s missing from measure book:", sorted(fired - meas_t0))

# ---------- label vs PM ----------
res = {}
for t in trades:
    if t.get("result") in ("win", "loss") and t.get("t0") in byt0 and t.get("side") in ("up", "down"):
        wside = t["side"] if t["result"] == "win" else ("down" if t["side"] == "up" else "up")
        res.setdefault(t["t0"], set()).add(wside)
amb = sum(1 for v in res.values() if len(v) > 1)
res = {k: v.pop() for k, v in res.items() if len(v) == 1}
agree = sum(1 for t0, wn in res.items() if byt0[t0]["label"] == wn)
nont = [(t0, wn) for t0, wn in res.items() if byt0[t0]["label"] != "tie"]
na = sum(1 for t0, wn in nont if byt0[t0]["label"] == wn)
ties = [(t0, wn) for t0, wn in res.items() if byt0[t0]["label"] == "tie"]
tu = sum(1 for _, wn in ties if wn == "up")
print(f"\nPM join: resolved t0s {len(res)} (ambiguous dropped {amb}); non-tie {len(nont)} agree {na} ({na/len(nont):.4f}) "
      f"(claim 929/940=.988); ties {len(ties)} up {tu} ({tu/len(ties):.3f}) (claim 32/74=.432)")

# ---------- live window coverage ----------
w0, w1 = min(meas_t0), max(meas_t0)
gp_live = [r for r in rows if r["trigger"] and r["gatePass"] and w0 <= r["t0"] <= w1]
led_t0 = {t["t0"] for t in v3}
in_m = sum(1 for r in gp_live if r["t0"] in meas_t0)
l_only = sum(1 for r in gp_live if r["t0"] not in meas_t0 and r["t0"] in led_t0)
un = [r for r in gp_live if r["t0"] not in meas_t0 and r["t0"] not in led_t0]
print(f"\nlive window [{utc(w0)},{utc(w1)}]: candle gate-passes {len(gp_live)} (claim 50); in_measure {in_m} (30); ledger_only {l_only} (0); unaccounted {len(un)} (20)")
# sanity: 36 = 30 match + 5 mismatch + 1 horizon
mism = [m["t0"] for m in st["measure"] if m["t0"] in byt0 and not (byt0[m["t0"]]["trigger"] and byt0[m["t0"]]["gatePass"])]
print("measure recs that are NOT candle trigger+gatePass:", len(mism), [utc(x) for x in mism])
print("measure recs past horizon:", sum(1 for m in st['measure'] if m['t0'] not in byt0))
# were the 20 unaccounted t0s inside known bot-downtime? check ledger activity around them
print("unaccounted pm range:", min(r["feats"]["pm"] for r in un), max(r["feats"]["pm"] for r in un))

# ---------- real joins / alt / borderline ----------
n_real = sum(1 for r in rows if "real" in r)
n_rm = sum(1 for r in rows if r.get("real", {}).get("measure"))
n_rl = sum(1 for r in rows if r.get("real", {}).get("ledger"))
n_rgp = sum(1 for r in rows if "real" in r and r["trigger"] and r["gatePass"])
print(f"\nreal joins: rows {n_real} measure {n_rm} (claim 35) ledger {n_rl} (claim 43) on-gate-pass {n_rgp} (claim 30)")
alt = [r for r in rows if "alt" in r]
tf = sum(1 for r in alt if r["alt"]["trigger"] != r["trigger"])
gf = sum(1 for r in alt if r["alt"]["gatePass"] != r["gatePass"])
print(f"alt rows {len(alt)} (claim 270) trigger-flips {tf} (claim 45) gatePass-flips {gf} (claim 228)")
n_trig = sum(r["trigger"] for r in rows)
bl = sum(1 for r in rows if r["trigger"] and abs(r["feats"]["pm"] - 0.12) <= 0.015)
nm = sum(1 for r in rows if not r["trigger"] and r["feats"]["pm"] >= 0.105)
print(f"borderline triggers {bl}/{n_trig} = {bl/n_trig:.4f} (claim 637/4102=.155); near-misses {nm} (claim 847)")

# ---------- alt-row eff6 spot recompute (open-to-close) ----------
Cc = cb["c"]
def r_oc(t):
    i = idxn.get(t)
    return None if i is None else (Cc[i] - O[i]) / O[i]
bad = 0
import random
random.seed(7)
for r in random.sample(alt, 40):
    t0 = r["t0"]
    rs = [r_oc(t0 - 300 * k) for k in range(1, 14)]
    if any(x is None for x in rs): continue
    last6 = rs[:6][::-1]
    den = sum(abs(x) for x in last6); net = 1.0
    for x in last6: net *= 1 + x
    e = abs(net - 1) / den if den > 0 else 1.0
    c12 = sum(1 for x in rs[1:13] if abs(x) >= 0.0012)
    gp = e >= 0.10 and c12 <= 6
    rp = r_oc(t0 - 300)
    tr = abs(rp) * 100 >= 0.12
    if r["alt"]["gatePass"] != gp or r["alt"]["trigger"] != tr: bad += 1
print("alt-row o-c recompute mismatches (of 40 sampled):", bad)
