"""A5: guard analysis. (a) Which guard blocks most near-miss signals (misses_btc/misses_top).
(b) Counterfactual outcome of guarded-out signals via Coinbase 1m proxy:
    win for side s at t0  <=>  s=='up' ? o(t0+300) >= o(t0) : o(t0+300) < o(t0)   (tie -> Up).
(c) The cap question: for 'Rev<=53c' misses the ask exceeded the cap, so any fill would have
    been > 54c effective; EV bound reported at p=0.54 and p=0.57.
Also: skip counters from impulse_cfg (f_nonpos) and measure-book sized vs skipped outcomes.
"""
import json, collections, sys
sys.path.insert(0, "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/micro")
from common import mean, fee

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
s = json.load(open(f"{DATA}/state_extract.json"))
cb = json.load(open(f"{DATA}/cb1m.json"))
om = dict(zip(cb["t"], cb["o"]))

def resolve(t0):
    a, b = om.get(t0), om.get(t0 + 300)
    if a is None or b is None:
        return None, None
    up = 1 if b >= a else 0
    move_bps = abs(b - a) / a * 1e4
    return up, move_bps

# dedupe misses by (t0, eng)
seen = {}
for m in s["misses_btc"] + s["misses_top"]:
    seen[(m["t0"], m["eng"])] = m
misses = list(seen.values())

res = {"n_misses_unique": len(misses)}
reason_counts = collections.Counter()
rows = []
for m in misses:
    reasons = [r.strip() for r in m["note"].split("short:")[-1].split(",")]
    for r in reasons:
        reason_counts[r] += 1
    up, mv = resolve(m["t0"])
    if up is None:
        continue
    win = up if m["side"] == "up" else 1 - up
    rows.append(dict(t0=m["t0"], eng=m["eng"], side=m["side"], reasons=reasons, win=win, move_bps=round(mv, 1)))
res["guard_block_counts"] = dict(reason_counts.most_common())

def grp(pred, label):
    g = [r for r in rows if pred(r)]
    if not g:
        return dict(n=0)
    wr = mean([r["win"] for r in g])
    n = len(g)
    import math
    se = math.sqrt(wr * (1 - wr) / n) if n else 0
    tiny = sum(1 for r in g if r["move_bps"] < 2)
    return dict(n=n, q_counterfactual=round(wr, 4), se=round(se, 4),
                n_sub2bps_proxy_noise=tiny,
                ev_at_54c=round(100 * (wr - 0.54 - fee(0.54)), 2),
                ev_at_57c=round(100 * (wr - 0.57 - fee(0.57)), 2),
                ev_at_51c=round(100 * (wr - 0.51 - fee(0.51)), 2))

res["counterfactual_all_misses"] = grp(lambda r: True, "all")
res["counterfactual_by_reason"] = {}
for reason in reason_counts:
    res["counterfactual_by_reason"][reason] = grp(lambda r, rr=reason: rr in r["reasons"], reason)
# dedupe by t0 (unique intervals) for the cap reason, since engines overlap
capt0 = {}
for r in rows:
    if any(x.startswith("Rev≤") for x in r["reasons"]):
        capt0[r["t0"]] = r
res["counterfactual_cap_unique_t0"] = grp(lambda r: r["t0"] in capt0 and capt0[r["t0"]] is r, "cap")
lat0 = {}
for r in rows:
    if "Near open" in r["reasons"]:
        lat0[r["t0"]] = r
res["counterfactual_late_unique_t0"] = grp(lambda r: r["t0"] in lat0 and lat0[r["t0"]] is r, "late")
iso0 = {}
for r in rows:
    if "Isolated" in r["reasons"]:
        iso0[r["t0"]] = r
res["counterfactual_gate_unique_t0"] = grp(lambda r: r["t0"] in iso0 and iso0[r["t0"]] is r, "gate")

# measure book: sized vs f_nonpos-skipped outcomes (PM-resolved wins already in state)
mb = [x for x in s["measure"] if x.get("win") is not None]
sized = [x for x in mb if x["sized"]]
skipped = [x for x in mb if not x["sized"]]
def mline(g):
    if not g:
        return dict(n=0)
    wr = mean([x["win"] for x in g])
    cost = mean([x["cost"] for x in g])
    ev = mean([x["win"] - x["cost"] for x in g])  # cost already includes fee
    return dict(n=len(g), q=round(wr, 4), mean_cost=round(cost, 4), ev_net_c=round(100 * ev, 2))
res["measure_sized"] = mline(sized)
res["measure_skipped_f_nonpos"] = mline(skipped)
res["impulse_cfg_skips"] = s["impulse_cfg"].get("skips")

json.dump(res, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/micro/a5_guards_misses.json", "w"), indent=1)
print(json.dumps(res, indent=1))
