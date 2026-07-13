#!/usr/bin/env python3
"""R8 adversarial verification: re-derive nightly qhat from raw state_extract measure rows.

Bot code (btc5m_bot.py:627-635):
  settled = rows in trailing 31d with win != None (as of nightly run time ns)
  bucket by cost < 0.50
  qhat_b = min(0.56, (wins_b + 400*seed_b) / (n_b + 400)), seeds .5057/.5068
Registered design (FINAL-DESIGN 4.2):
  bucket by p_eff < 0.50; qhat_b = (wins_b + 100)/(n_b + 200)  [n0=200 at mean 0.5]
State claims qlo=0.5068 qhi=0.5030, lastNightly(due)=1783901400.
"""
import json, math, datetime

D = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
st = json.load(open(D + "/state_extract.json"))
m = st["measure"]
cfg = st["impulse_cfg"]
due = cfg["lastNightly"]          # nightly ran at first tick with ns >= due
print("due =", due, datetime.datetime.utcfromtimestamp(due).isoformat() + "Z")
print("state qlo/qhi =", cfg["qlo"], cfg["qhi"])

SEED_LO, SEED_HI, PRIOR = 0.5057, 0.5068, 400

def cost_to_peff(c):
    # invert c = p + 0.07 p (1-p)  =>  0.07 p^2 - 1.07 p + c = 0
    return (1.07 - math.sqrt(1.07**2 - 4 * 0.07 * c)) / (2 * 0.07)

def bot_qhat(settled):
    out = []
    for lo, seed in ((True, SEED_LO), (False, SEED_HI)):
        xs = [r for r in settled if (r["cost"] < 0.50) == lo]
        w = sum(r["win"] for r in xs)
        out.append((round(min(0.56, (w + PRIOR * seed) / (len(xs) + PRIOR)), 4), len(xs), w))
    return out

def design_qhat(settled):
    out = []
    for lo in (True, False):
        xs = [r for r in settled if (cost_to_peff(r["cost"]) < 0.50) == lo]
        w = sum(r["win"] for r in xs)
        out.append((round(min(0.56, (w + 100) / (len(xs) + 200)), 4), len(xs), w))
    return out

# The nightly at time ns uses rows already SETTLED at ns. Settlement happens
# shortly after t1 = t0+300. We don't know exact settle timestamps, so scan
# plausible cutoffs: rows with t0 <= due - lag for lag in a few values, plus
# the possibility the most recent row(s) had lagged settlement.
res = {}
settled_all = [r for r in m if r["win"] is not None]
print("\nrows total=%d settled_by_extract=%d" % (len(m), len(settled_all)))

for lag in (0, 300, 600, 900):
    s = [r for r in settled_all if r["t0"] + lag <= due]
    (qlo, nlo, wlo), (qhi, nhi, whi) = bot_qhat(s)
    tag = "lag=%ds n=%d" % (lag, len(s))
    print("%-16s bot: qlo=%.4f (n=%d w=%d)  qhi=%.4f (n=%d w=%d)  match=%s" %
          (tag, qlo, nlo, wlo, qhi, nhi, whi,
           (qlo == cfg["qlo"], qhi == cfg["qhi"])))
    res[tag] = dict(qlo=qlo, qhi=qhi, nlo=nlo, nhi=nhi, wlo=wlo, whi=whi)

# also try dropping the single most-recent pre-due settled row (lagged settlement)
s0 = [r for r in settled_all if r["t0"] + 300 <= due]
for drop in range(1, 4):
    s = sorted(s0, key=lambda r: r["t0"])[:-drop] if drop else s0
    (qlo, nlo, wlo), (qhi, nhi, whi) = bot_qhat(s)
    print("drop_last=%d n=%d bot: qlo=%.4f qhi=%.4f  match=%s" %
          (drop, len(s), qlo, qhi, (qlo == cfg["qlo"], qhi == cfg["qhi"])))

# exhaustive: which (n_lo, w_lo) reproduce qlo=0.5068 and (n_hi, w_hi) -> qhi=0.5030?
print("\nexhaustive integer solutions within observed row counts:")
lo_rows = sorted([r for r in settled_all if r["cost"] < 0.50], key=lambda r: r["t0"])
hi_rows = sorted([r for r in settled_all if r["cost"] >= 0.50], key=lambda r: r["t0"])
print("extract totals: lo n=%d w=%d   hi n=%d w=%d" %
      (len(lo_rows), sum(r["win"] for r in lo_rows), len(hi_rows), sum(r["win"] for r in hi_rows)))
for n in range(0, len(lo_rows) + 1):
    for w in range(0, n + 1):
        if round(min(0.56, (w + PRIOR * SEED_LO) / (n + PRIOR)), 4) == cfg["qlo"]:
            print("  qlo=0.5068 <= n_lo=%d w_lo=%d" % (n, w))
for n in range(0, len(hi_rows) + 1):
    for w in range(0, n + 1):
        if round(min(0.56, (w + PRIOR * SEED_HI) / (n + PRIOR)), 4) == cfg["qhi"]:
            print("  qhi=0.5030 <= n_hi=%d w_hi=%d" % (n, w))

# prefix check: nightly saw a time-prefix of the settled rows. Which prefixes work?
print("\nprefix scan (rows sorted by t0, settled subset only):")
srt = sorted(settled_all, key=lambda r: r["t0"])
hits = []
for k in range(len(srt) + 1):
    s = srt[:k]
    (qlo, _, _), (qhi, _, _) = bot_qhat(s)
    if qlo == cfg["qlo"] and qhi == cfg["qhi"]:
        t = srt[k - 1]["t0"] if k else None
        hits.append((k, t))
        print("  MATCH prefix k=%d last_t0=%s" % (k, datetime.datetime.utcfromtimestamp(t).isoformat() if t else None))
# and prefixes matching each separately
for k in range(len(srt) + 1):
    s = srt[:k]
    (qlo, _, _), (qhi, _, _) = bot_qhat(s)
    if qlo == cfg["qlo"] or qhi == cfg["qhi"]:
        pass

# design-formula counterfactual on the same rows (best-matching prefix or lag=300 set)
use = srt if not hits else srt[:hits[0][0]]
(dlo, dnlo, dwlo), (dhi, dnhi, dwhi) = design_qhat(use)
(blo, _, _), (bhi, _, _) = bot_qhat(use)
print("\non the reconciling row set (n=%d):" % len(use))
print("  bot formula     qlo=%.4f qhi=%.4f" % (blo, bhi))
print("  design formula  qlo=%.4f (n=%d w=%d)  qhi=%.4f (n=%d w=%d)" % (dlo, dnlo, dwlo, dhi, dnhi, dwhi))

# bucket boundary displacement: which rows straddle cost<0.50 vs p_eff<0.50?
strad = [r for r in settled_all if (r["cost"] < 0.50) != (cost_to_peff(r["cost"]) < 0.50)]
print("\nrows bucketed differently under cost<0.50 vs p_eff<0.50: %d / %d" % (len(strad), len(settled_all)))
for r in strad[:10]:
    print("   cost=%.4f p_eff=%.4f win=%s" % (r["cost"], cost_to_peff(r["cost"]), r["win"]))

json.dump(dict(due=due, state=dict(qlo=cfg["qlo"], qhi=cfg["qhi"]),
               prefix_hits=hits, straddle_rows=len(strad),
               design_on_reconciling=dict(qlo=dlo, qhi=dhi),
               lag_scan=res),
          open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R8-integrity/replicate_qhat.json", "w"), indent=1)
print("\nwrote replicate_qhat.json")
