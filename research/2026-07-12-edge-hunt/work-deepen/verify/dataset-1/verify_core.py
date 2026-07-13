#!/usr/bin/env python3
"""Adversarial verification of signals_60d.json — COVERAGE lens.
Independent re-derivation of the pipeline from cb5m.json (no code reuse from
build_signals.py), then row-by-row comparison against the published dataset,
plus candle-gap / alignment / tie / contiguity / DST checks.
"""
import json, math, datetime

D = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
W = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work-deepen/dataset"
IVL = 300
TEST_T0 = 1782432000

def utc(t): return datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d %H:%M")

# ---------- 0. epoch / boundary sanity ----------
print("== epoch checks ==")
# Jun 26 00:00 UTC epoch
d = datetime.datetime(2026, 6, 26, 0, 0, tzinfo=datetime.timezone.utc)
print("Jun26 epoch:", int(d.timestamp()), "claimed split:", TEST_T0, "match:", int(d.timestamp()) == TEST_T0)

cb = json.load(open(f"{D}/cb5m.json"))
T, O, H, L, C = cb["t"], cb["o"], cb["h"], cb["l"], cb["c"]
print("cb5m candles:", len(T), utc(T[0]), "->", utc(T[-1]))
mis = [t for t in T if t % 300 != 0]
print("cb5m not-300-aligned:", len(mis))
diffs = [T[i+1] - T[i] for i in range(len(T)-1)]
gaps = [(T[i], T[i+1]) for i in range(len(T)-1) if T[i+1] - T[i] != 300]
print("cb5m gaps (diff!=300):", len(gaps), gaps[:10])
dupes = sum(1 for x in diffs if x <= 0)
print("cb5m non-monotonic/dupes:", dupes)
# any null/zero opens?
bad = sum(1 for i, o in enumerate(O) if not isinstance(o, (int, float)) or o <= 0)
print("cb5m bad opens:", bad)
# expected interval count in span
span_n = (T[-1] - T[0]) // 300 + 1
print("expected candles for span:", span_n, "actual:", len(T), "missing:", span_n - len(T))

cb1 = json.load(open(f"{D}/cb1m.json"))
T1 = cb1["t"]
print("\ncb1m candles:", len(T1), utc(T1[0]), "->", utc(T1[-1]))
g1 = [(T1[i], T1[i+1], (T1[i+1]-T1[i])//60 - 1) for i in range(len(T1)-1) if T1[i+1] - T1[i] != 60]
print("cb1m gaps:", len(g1), [(utc(a), utc(b), f"{m} min missing") for a, b, m in g1])
mis1 = sum(1 for t in T1 if t % 60 != 0)
print("cb1m not-60-aligned:", mis1)

# ---------- 1. independent pipeline ----------
idx = {t: i for i, t in enumerate(T)}

def r_oo(t):
    i = idx.get(t)
    if i is None: return None
    j = idx.get(t + 300)
    if j is None: return None
    return (O[j] - O[i]) / O[i]

my = {}
for i, t0 in enumerate(T):
    if i == 0 or i + 1 >= len(T): continue  # need prior return and label
    rp = r_oo(t0 - 300); r0 = r_oo(t0)
    if rp is None or r0 is None: continue
    trig = abs(rp) * 100 >= 0.12
    side = ("down" if rp > 0 else "up") if trig else None
    # gate: 13 contiguous returns ending at trigger (k=1..13)
    rs = []
    ready = True
    for k in range(1, 14):
        r = r_oo(t0 - 300 * k)
        if r is None: ready = False; break
        rs.append(r)
    if ready:
        last6 = rs[:6][::-1]
        den = sum(abs(x) for x in last6)
        net = 1.0
        for x in last6: net *= 1 + x
        eff6 = abs(net - 1) / den if den > 0 else 1.0
        cnt12 = sum(1 for x in rs[1:13] if abs(x) >= 0.0012)
        ok = eff6 >= 0.10 and cnt12 <= 6
    else:
        eff6 = cnt12 = None; ok = False
    label = "tie" if abs(r0) < 0.0001 else ("up" if r0 > 0 else "down")
    my[t0] = dict(trigger=trig, side=side, ready=ready, gatePass=bool(ready and ok),
                  eff6=eff6, cnt12=cnt12, label=label, r0=r0, rp=rp)

print("\n== independent pipeline ==")
n_rows = len(my)
n_trig = sum(v["trigger"] for v in my.values())
n_ready = sum(v["ready"] for v in my.values())
n_gp = sum(v["trigger"] and v["gatePass"] for v in my.values())
n_tie = sum(v["label"] == "tie" for v in my.values())
print(f"rows {n_rows} triggers {n_trig} gateReady {n_ready} gated {n_gp} ties(all rows) {n_tie}")

sel = [v for v in my.values() if v["trigger"] and v["gatePass"]]
def q(sel):
    ties = [v for v in sel if v["label"] == "tie"]
    non = [v for v in sel if v["label"] != "tie"]
    w = sum(1 for v in non if v["side"] == v["label"])
    return len(sel), len(ties), w / len(non), w / len(sel)
tr = [v for t0, v in my.items() if t0 < TEST_T0 and v["trigger"] and v["gatePass"]]
te = [v for t0, v in my.items() if t0 >= TEST_T0 and v["trigger"] and v["gatePass"]]
for name, s in (("all", sel), ("train", tr), ("test", te)):
    n, nt, qx, ql = q(s)
    print(f"{name}: n_sel {n} ties {nt} q_ex_tie {qx:.4f} q_tie_as_loss {ql:.4f}")

# ---------- 2. row-by-row vs published dataset (ALL rows, not a sample) ----------
pub = json.load(open(f"{W}/signals_60d.json"))
rows = pub["rows"]
print("\n== published file ==")
print("meta.counts:", pub["meta"]["counts"], "window:", pub["meta"]["window_utc"])
print("published rows:", len(rows))
mm = dict(trigger=0, gatePass=0, ready=0, label=0, side=0, eff6=0, cnt12=0, missing=0)
exs = []
pub_t0 = set()
for r in rows:
    t0 = r["t0"]; pub_t0.add(t0)
    v = my.get(t0)
    if v is None:
        mm["missing"] += 1; exs.append(("not in mine", t0)); continue
    if r["trigger"] != v["trigger"]: mm["trigger"] += 1; exs.append(("trigger", t0))
    if r["gatePass"] != v["gatePass"]: mm["gatePass"] += 1; exs.append(("gatePass", t0))
    if r["gateReady"] != v["ready"]: mm["ready"] += 1
    if r["label"] != v["label"]: mm["label"] += 1; exs.append(("label", t0))
    if r["side"] != v["side"]: mm["side"] += 1; exs.append(("side", t0))
    if v["eff6"] is not None and r["eff6"] is not None and abs(r["eff6"] - round(v["eff6"], 4)) > 1e-9:
        mm["eff6"] += 1; exs.append(("eff6", t0))
    if v["cnt12"] is not None and r["cnt12"] != v["cnt12"]: mm["cnt12"] += 1
mine_only = [t for t in my if t not in pub_t0]
print("row-by-row mismatches:", mm, "in-mine-not-published:", len(mine_only), mine_only[:5])
if exs: print("first exceptions:", exs[:10])

# ---------- 3. coverage: what fraction of real intervals is dropped ----------
print("\n== coverage ==")
full = set(range(T[0], T[-1] + 1, 300))
in_file = set(T)
print(f"5m grid points in span: {len(full)}; candles present: {len(in_file)}; missing from cb5m: {len(full - in_file)}")
drop = sorted(full - pub_t0)  # grid intervals with no dataset row
print(f"grid intervals with NO dataset row: {len(drop)} -> {[utc(t) for t in drop[:15]]}")
# are drops just the boundary? classify
bound = [t for t in drop if t == T[0] or t == T[-1]]
print("boundary drops:", len(bound), "non-boundary drops:", len(drop) - len(bound))

# vol_src fallback within TEST era (cb1m availability)
n1m_expected_start = T1[0] + 600  # first t0 with full 10x1m window
fb = [r for r in rows if r["t0"] >= n1m_expected_start and r["feats"]["vol_src"] != "1m"]
print(f"\nrows at/after cb1m start+600 ({utc(n1m_expected_start)}) NOT using 1m vol: {len(fb)}")
for r in fb[:20]:
    print("  ", utc(r["t0"]), "src", r["feats"]["vol_src"], "vol", r["feats"]["vol10m"],
          "trigger", r["trigger"], "gatePass", r["gatePass"])
# vol comparison: fallback rows vs neighbors
if fb:
    allv = [r["feats"]["vol10m"] for r in rows if r["t0"] >= n1m_expected_start and r["feats"]["vol10m"] is not None and r["feats"]["vol_src"] == "1m"]
    allv.sort()
    med = allv[len(allv)//2]
    print(f"TEST-era 1m-vol median {med:.4f}; fallback rows vol values:", [r['feats']['vol10m'] for r in fb])

# vol_src split + collinearity with train/test split
from collections import Counter
c = Counter((r["split"], r["feats"]["vol_src"]) for r in rows)
print("split x vol_src:", dict(c))

# ---------- 4. ties ----------
print("\n== ties ==")
# tie rule boundary: |ret0| < 1bp on UNROUNDED; check published ret0 rounding consistency
near = [r for r in rows if r["label"] != "tie" and abs(r["ret0"]) < 0.01]
print("non-tie rows with |ret0%|<0.01 (should be 0 if tie=1bp on % units... note 1bp = 0.01%):", len(near))
tie_rows = [r for r in rows if r["label"] == "tie"]
print("tie rows total:", len(tie_rows), "max |ret0| among ties:", max(abs(r["ret0"]) for r in tie_rows))
gated_ties = [r for r in tie_rows if r["trigger"] and r["gatePass"]]
print("gated ties:", len(gated_ties), "claimed 182")
# exact-zero ties
z = sum(1 for r in tie_rows if r["ret0"] == 0)
print("exact-zero ret0 ties:", z)
