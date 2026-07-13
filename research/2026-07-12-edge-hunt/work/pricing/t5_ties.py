"""T5: Ties / near-ties and resolution noise.
- Frequency of exact ties and |move|<1bp/<2bp on cb5m (TRAIN May11-Jun25 / TEST Jun26-Jul13).
- PM-vs-proxy disagreement by |move| bucket (n=1,078 actual resolutions).
- Off-by-one contamination screen in pm_res_3d.
- Near-tie predictability: trailing 12-ivl mean |ret| -> P(|out|<2bp), fit TRAIN, eval TEST.
- Cost impact on the trigger subset: P(|out|<2bp | trigger) and q drag.
"""
import json, math, collections
import common as C

out = {}
cb = C.cb5m_map()          # Jul window (2026-07-12 harvest: May 11 - Jul 13)
ts = sorted(cb.keys())
TRAIN_END = 1782432000     # 2026-06-26 00:00 UTC
rows = []
for i, t0 in enumerate(ts):
    cd = cb[t0]
    mv = (cd["c"] - cd["o"]) / cd["o"]
    rows.append((t0, mv, cd))

def tie_stats(sel):
    n = len(sel)
    return dict(n=n,
        exact_tie=round(sum(1 for _, m, _ in sel if m == 0)/n, 5),
        lt_1bp=round(sum(1 for _, m, _ in sel if abs(m) < 1e-4)/n, 5),
        lt_2bp=round(sum(1 for _, m, _ in sel if abs(m) < 2e-4)/n, 5))

out["ties_train"] = tie_stats([r for r in rows if r[0] < TRAIN_END])
out["ties_test"] = tie_stats([r for r in rows if r[0] >= TRAIN_END])

# --- PM vs proxy disagreement by bucket (from resolution map)
res, conflicts = C.resolution_map()
out["resmap_n"] = len(res); out["resmap_conflicts"] = conflicts
bybp = collections.defaultdict(lambda: [0, 0])
offby1 = 0
for t0, up in res.items():
    cd = cb.get(t0)
    if not cd: continue
    mv = (cd["c"] - cd["o"]) / cd["o"] * 1e4
    pup = 1 if mv >= 0 else 0
    b = "0-1bp" if abs(mv) < 1 else "1-2bp" if abs(mv) < 2 else "2-4bp" if abs(mv) < 4 else ">=4bp"
    bybp[b][0] += (pup == up); bybp[b][1] += 1
    if abs(mv) >= 4:
        cn = cb.get(t0 + 300)
        if cn and pup != up and (1 if cn["c"] >= cn["o"] else 0) == up:
            offby1 += 1
out["proxy_agreement"] = {b: dict(agree=a, n=n, rate=round(a/n, 4))
                          for b, (a, n) in sorted(bybp.items())}
out["large_move_disagreements_matching_next_interval"] = offby1

# --- near-tie predictability from trailing vol
# feature: mean |open-to-open ret| over trailing 12 intervals (known at t0)
opens = {t0: cb[t0]["o"] for t0 in ts}
def trailing_vol(t0):
    vals = []
    for k in range(1, 13):
        a, b = opens.get(t0 - 300*k), opens.get(t0 - 300*(k-1))
        if a is None or b is None: return None
        vals.append(abs(b - a) / a)
    return sum(vals) / len(vals)

feat = []
for t0, mv, cd in rows:
    tv = trailing_vol(t0)
    if tv is not None:
        feat.append((t0, tv, abs(mv) < 2e-4))
train = [f for f in feat if f[0] < TRAIN_END]
test = [f for f in feat if f[0] >= TRAIN_END]
tvs = sorted(f[1] for f in train)
qs = [tvs[int(len(tvs)*k/4)] for k in (1, 2, 3)]
out["train_vol_quartile_cuts_bp"] = [round(q*1e4, 3) for q in qs]
def quart(v):
    return sum(1 for q in qs if v >= q)
def bytier(sel):
    d = collections.defaultdict(lambda: [0, 0])
    for _, tv, tie in sel:
        d[quart(tv)][0] += tie; d[quart(tv)][1] += 1
    return {f"Q{k+1}": dict(n=n, p_neartie=round(w/n, 4)) for k, (w, n) in sorted(d.items())}
out["neartie_by_trailvol_TRAIN"] = bytier(train)
out["neartie_by_trailvol_TEST"] = bytier(test)

# --- trigger subset: after |prior|>=12bps, near-tie frequency (fee-drag relevance)
trig_tie = [1 if abs(mv) < 2e-4 else 0
            for t0, mv, cd in rows
            if opens.get(t0-300) is not None
            and abs(opens[t0]-opens[t0-300])/opens[t0-300] >= 0.0012]
out["neartie_given_trigger"] = dict(n=len(trig_tie),
                                    p=round(sum(trig_tie)/len(trig_tie), 5) if trig_tie else None)
alln = [1 if abs(mv) < 2e-4 else 0 for _, mv, _ in rows]
out["neartie_unconditional"] = round(sum(alln)/len(alln), 5)

json.dump(out, open("ties.json", "w"), indent=1)
print(json.dumps(out, indent=1))
