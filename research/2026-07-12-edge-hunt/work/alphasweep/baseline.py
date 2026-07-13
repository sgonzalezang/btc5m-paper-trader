"""Baselines: split sizes, tie/noise rates, unconditional up rate, and the
pre-registered 12bps-reversal refresh on fresh data (not a new hypothesis)."""
import json
from common import Table, eval_signal, SPLIT_TS, breakeven_q

tab = Table()
train_n = sum(1 for i in range(tab.n - 1) if tab.t[i] < SPLIT_TS)
test_n = (tab.n - 1) - train_n
ties = sum(1 for i in range(tab.n - 1) if tab.o[i + 1] == tab.o[i])
sub2 = sum(1 for i in range(tab.n - 1) if abs(tab.ret[i]) < 0.0002)
up_all = sum(tab.up[i] for i in range(tab.n - 1)) / (tab.n - 1)
up_test = sum(tab.up[i] for i in range(tab.n - 1) if tab.t[i] >= SPLIT_TS) / test_n

# 12bps contrarian refresh (pre-registered prior, threshold NOT refit)
fire = {}
for i in range(1, tab.n - 1):
    r = tab.prior_ret(i, 1)
    if r is not None and abs(r) >= 0.0012:
        fire[i] = "down" if r > 0 else "up"
res = eval_signal(tab, fire)

# same but only the truly fresh days Jul 10-13 (never seen by prior work)
import calendar
FRESH = calendar.timegm((2026, 7, 10, 15, 5, 0))
fresh_fire = {i: s for i, s in fire.items() if tab.t[i] >= FRESH}
res_fresh = eval_signal(tab, fresh_fire)

out = {
    "intervals_labeled": tab.n - 1, "train_n": train_n, "test_n": test_n,
    "exact_ties": ties, "sub_2bps_frac": round(sub2 / (tab.n - 1), 4),
    "up_rate_all": round(up_all, 4), "up_rate_test": round(up_test, 4),
    "breakeven_q_at_51c": round(breakeven_q(0.51), 5),
    "rev12_refresh": res,
    "rev12_fresh_jul10_13_only": {"TEST": res_fresh["TEST"]},
}
json.dump(out, open("baseline.json", "w"), indent=1)
print(json.dumps(out, indent=1))
