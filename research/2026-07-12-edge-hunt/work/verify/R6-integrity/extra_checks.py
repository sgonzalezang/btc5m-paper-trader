"""Extra R6 checks: dupes detail, ungated daily rank of Jul 10, weekly heterogeneity test
(chi-square vs binomial sampling + block-bootstrap null), TEST-week concentration."""
import json, math, random, calendar, time
from collections import Counter, defaultdict

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
OUT = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R6-integrity"
FEE, P = 0.07, 0.51
COST = P + FEE*P*(1-P)
JUL10 = calendar.timegm((2026,7,10,0,0,0)); JUL11 = JUL10+86400

cb = json.load(open(f"{DATA}/cb5m.json")); t, o = cb["t"], cb["o"]; n = len(t)
r = [(o[i+1]-o[i])/o[i] for i in range(n-1)]
up = [o[i+1] >= o[i] for i in range(n-1)]

trig = []
for i in range(14, n-1):
    if abs(r[i-1]) < 0.0012: continue
    win = 1 if up[i] != (r[i-1] > 0) else 0
    den = sum(abs(o[j+1]-o[j]) for j in range(i-6, i))
    eff6 = abs(o[i]-o[i-6])/den if den > 0 else 1.0
    cnt12 = sum(1 for j in range(i-13, i-1) if abs(r[j]) >= 0.0012)
    trig.append((t[i], win, eff6 >= 0.10 and cnt12 <= 6))

out = {}

# ungated daily rank of Jul 10
dd = defaultdict(list)
for t0, w, g in trig: dd[t0//86400].append(w)
ds = sorted(((k, len(v), (sum(v)/len(v)-COST)*100) for k, v in dd.items() if len(v) >= 3), key=lambda x: x[2])
out["ungated_jul10_rank_worst"] = next((i+1 for i,(k,nn,e) in enumerate(ds) if k == JUL10//86400), None)
out["ungated_n_days"] = len(ds)
out["ungated_worst3"] = [(time.strftime("%m-%d", time.gmtime(k*86400)), nn, round(e,2)) for k,nn,e in ds[:3]]

# weekly heterogeneity: gated, full weeks only
W0 = calendar.timegm((2026,5,11,0,0,0))
wk = defaultdict(list)
for t0, w, g in trig:
    if g: wk[(t0-W0)//(7*86400)].append((t0, w))
weeks = {k: v for k, v in wk.items() if len(v) >= 50}
tot_w = sum(w for v in weeks.values() for _, w in v); tot_n = sum(len(v) for v in weeks.values())
qbar = tot_w/tot_n
chi2 = 0.0
for k, v in weeks.items():
    nn = len(v); q = sum(w for _, w in v)/nn
    chi2 += (q-qbar)**2 / (qbar*(1-qbar)/nn)
df = len(weeks)-1
out["weekly_chi2_binomial"] = {"chi2": round(chi2,2), "df": df}

# null distribution of chi2 under hour-block shuffle (preserves intra-hour correlation,
# breaks week structure): permute hour-blocks across the timeline, recompute chi2
by_hour = defaultdict(list)
for k, v in weeks.items():
    for t0, w in v: by_hour[t0//3600].append(w)
hours = sorted(by_hour)
week_of_hour = {}
for k, v in weeks.items():
    for t0, w in v: week_of_hour[t0//3600] = k
rng = random.Random(42)
null = []
for _ in range(2000):
    perm = hours[:]; rng.shuffle(perm)
    agg = defaultdict(lambda: [0,0])
    for h_orig, h_src in zip(hours, perm):
        k = week_of_hour[h_orig]
        agg[k][0] += sum(by_hour[h_src]); agg[k][1] += len(by_hour[h_src])
    c = 0.0
    tw = sum(a[0] for a in agg.values()); tn = sum(a[1] for a in agg.values())
    qb = tw/tn
    for k, (sw, sn) in agg.items():
        if sn: c += (sw/sn-qb)**2/(qb*(1-qb)/sn)
    null.append(c)
null.sort()
p_het = sum(1 for c in null if c >= chi2)/len(null)
out["weekly_heterogeneity_p_blockperm"] = round(p_het, 4)
out["null_chi2_median"] = round(null[len(null)//2], 2)

# TEST concentration: TEST gated EV with best week removed / best 2 removed
TEST_START = calendar.timegm((2026,6,26,0,0,0))
test_tr = [(t0, (w-COST)*100) for t0, w, g in trig if g and t0 >= TEST_START]
bywk = defaultdict(list)
for t0, e in test_tr: bywk[(t0-W0)//(7*86400)].append(e)
means = sorted(((sum(v)/len(v), k) for k, v in bywk.items()), reverse=True)
out["TEST_gated_ev_c"] = round(sum(e for _, e in test_tr)/len(test_tr), 2)
for drop in (1, 2):
    keep = [e for m, k in means[drop:] for e in bywk[k]]
    out[f"TEST_ev_c_drop_best{drop}_week"] = {"ev_c": round(sum(keep)/len(keep), 2), "n": len(keep)}

# ledger dupes detail
tr = json.load(open(f"{DATA}/trades_unified.json"))
c = Counter((x["eng"], x["slug"]) for x in tr)
dups = [k for k, v in c.items() if v > 1]
out["dup_pairs"] = [{"eng": e, "slug": s,
                     "t0s": [x["t0"] for x in tr if x["eng"]==e and x["slug"]==s],
                     "srcs": [x["_src"] for x in tr if x["eng"]==e and x["slug"]==s],
                     "pnls": [x["pnl"] for x in tr if x["eng"]==e and x["slug"]==s]} for e, s in dups]
out["dups_in_fresh_window"] = sum(1 for e, s in dups
                                  if any(x["t0"] >= 1783685700 for x in tr if x["eng"]==e and x["slug"]==s))

json.dump(out, open(f"{OUT}/extra_checks.json", "w"), indent=1)
print(json.dumps(out, indent=1))
