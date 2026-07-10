#!/usr/bin/env python3
"""Quintile diagnostic: reversal win rate by feature quintile, TRAIN (first 40d) vs TEST (last 20d).
Uses the exact trade construction from regime_tournament.py (imported)."""
import json, sys
sys.argv = ["x"]
exec(open("/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/regime/regime_tournament.py").read().split("# ---- folds")[0])

t_split = t0 = t[0]
TRAIN_END = t[0] + 40 * 86400
train = [x for x in trades if x["t"] < TRAIN_END]
test  = [x for x in trades if x["t"] >= TRAIN_END]
print(f"train n={len(train)} wr={sum(x['win'] for x in train)/len(train):.4f}")
print(f"test  n={len(test)} wr={sum(x['win'] for x in test)/len(test):.4f}  breakeven={BREAKEVEN:.4f}")

feats = ["eff6", "eff12", "eff24", "vr", "atrpct", "rc", "cnt", "gap"]
out = {}
for f in feats:
    vs = sorted(x[f] for x in train)
    qs = [vs[int(len(vs)*q)] for q in (0.2, 0.4, 0.6, 0.8)]
    def binof(v):
        for bi, q in enumerate(qs):
            if v <= q: return bi
        return 4
    rowT = []; rowS = []
    for b in range(5):
        gT = [x for x in train if binof(x[f]) == b]
        gS = [x for x in test  if binof(x[f]) == b]
        rowT.append((len(gT), round(sum(x["win"] for x in gT)/max(1,len(gT)), 4)))
        rowS.append((len(gS), round(sum(x["win"] for x in gS)/max(1,len(gS)), 4)))
    out[f] = {"train_quintile_edges": [round(q,4) for q in qs], "train": rowT, "test": rowS}
    print(f"\n{f}: edges={[round(q,3) for q in qs]}")
    print("  TRAIN:", " | ".join(f"q{b+1} n={n} wr={w}" for b,(n,w) in enumerate(rowT)))
    print("  TEST :", " | ".join(f"q{b+1} n={n} wr={w}" for b,(n,w) in enumerate(rowS)))

json.dump(out, open("/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/regime/diag_monotone.json", "w"), indent=1)
