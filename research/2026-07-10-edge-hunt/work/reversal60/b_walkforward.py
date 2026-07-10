#!/usr/bin/env python3
"""(b) Walk-forward threshold selection on cb5m 60d: trailing 10d calibrates thr
(grid 6..25bps), next 10d trades it. Two selectors: (i) forced best-thr by total
calibration net pnl at 51c, (ii) same but abstain if best calibration pnl <= 0.
Benchmark: fixed 12bps. Exact fee model, fills at 51c. Output: b_walkforward.json"""
import json

S = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
d = json.load(open(f"{S}/data/cb5m.json"))
t, o, c = d["t"], d["o"], d["c"]
N = len(t)
mv = [0.0]*N; up=[0]*N
for i in range(1, N):
    mv[i] = (o[i]-o[i-1])/o[i-1]*1e4
    up[i] = 1 if c[i] >= o[i] else 0
def rev_win(i): return (1-up[i]) if mv[i] > 0 else up[i]

P = 0.51; FEE = 0.07*P*(1-P)
WIN, LOSE = (1-P)-FEE, -P-FEE
THRS = [6,8,10,12,14,16,20,25]
IVL10D = 2880  # 10 days of 5m intervals

def window_pnl(indices, thr):
    n = w = 0
    for i in indices:
        if abs(mv[i]) >= thr:
            n += 1; w += rev_win(i)
    pnl = w*WIN + (n-w)*LOSE
    return n, w, pnl

wins = []  # trading windows: start at 10d..50d
results = {"per_window": [], "P": P}
tot = {"wf": 0.0, "wf_abst": 0.0, "fx12": 0.0}
cnt = {"wf": 0, "wf_abst": 0, "fx12": 0}
test_tot = dict(tot); test_cnt = dict(cnt)
TRAIN_END = 1 + int((N-1)*2/3)   # ~day 40 boundary

for wstart in range(IVL10D, N-1, IVL10D):
    cal = range(max(1, wstart-IVL10D), wstart)
    trd = range(wstart, min(N, wstart+IVL10D))
    # selector: max total calibration pnl, n>=30
    best_thr, best_pnl = None, -1e18
    cal_tbl = {}
    for thr in THRS:
        n, w, pnl = window_pnl(cal, thr)
        cal_tbl[thr] = [n, w/n if n else None, pnl]
        if n >= 30 and pnl > best_pnl:
            best_pnl, best_thr = pnl, thr
    # trade
    nT, wT, pnlT = window_pnl(trd, best_thr)
    abstain = best_pnl <= 0
    n12, w12, pnl12 = window_pnl(trd, 12)
    rec = dict(trade_window_start_day=wstart/288, chosen_thr=best_thr,
               cal_best_pnl=best_pnl, abstained=abstain,
               wf=dict(n=nT, q=wT/nT if nT else None, pnl=pnlT,
                       per_trade=pnlT/nT if nT else None),
               fx12=dict(n=n12, q=w12/n12 if n12 else None, pnl=pnl12,
                         per_trade=pnl12/n12 if n12 else None),
               cal_table={str(k): v for k, v in cal_tbl.items()})
    results["per_window"].append(rec)
    tot["wf"] += pnlT; cnt["wf"] += nT
    if not abstain: tot["wf_abst"] += pnlT; cnt["wf_abst"] += nT
    tot["fx12"] += pnl12; cnt["fx12"] += n12
    in_test = wstart >= TRAIN_END - 1   # windows fully in the last 1/3 (approx: start>=day40)
    if in_test:
        test_tot["wf"] += pnlT; test_cnt["wf"] += nT
        if not abstain: test_tot["wf_abst"] += pnlT; test_cnt["wf_abst"] += nT
        test_tot["fx12"] += pnl12; test_cnt["fx12"] += n12
    print(f"trade d{wstart/288:>4.0f}-{min(N,wstart+IVL10D)/288:<4.0f} chosen thr={best_thr:>2} "
          f"(cal pnl {best_pnl:+7.2f}{' ABSTAIN' if abstain else ''}) | "
          f"WF n={nT:>4} q={wT/nT:.3f} pnl={pnlT:+7.2f} ({pnlT/nT:+.4f}/tr) | "
          f"12bps n={n12:>4} q={w12/n12:.3f} pnl={pnl12:+7.2f} ({pnl12/n12:+.4f}/tr)")

print("\n== totals (per-share pnl units; 5 trading windows, days 10-60) ==")
for k in ["wf","wf_abst","fx12"]:
    per = tot[k]/cnt[k] if cnt[k] else 0
    print(f"{k:>8}: n={cnt[k]:>5} pnl={tot[k]:+8.2f} per_trade={per:+.4f}")
print("== TEST-only (windows starting day >= 40) ==")
for k in ["wf","wf_abst","fx12"]:
    per = test_tot[k]/test_cnt[k] if test_cnt[k] else 0
    print(f"{k:>8}: n={test_cnt[k]:>5} pnl={test_tot[k]:+8.2f} per_trade={per:+.4f}")

results["totals"] = {k: dict(n=cnt[k], pnl=tot[k]) for k in tot}
results["test_totals"] = {k: dict(n=test_cnt[k], pnl=test_tot[k]) for k in test_tot}
json.dump(results, open(f"{S}/work/reversal60/b_walkforward.json","w"), indent=1)
print("saved b_walkforward.json")
