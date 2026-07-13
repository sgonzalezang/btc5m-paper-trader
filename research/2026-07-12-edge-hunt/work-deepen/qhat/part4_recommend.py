#!/usr/bin/env python3
"""Part 4 — the recommended parameter set, isolated and quantified.

hybrid_cost_M200 = KEEP the code's cost<0.50 bucket boundary (part3 stress test:
it quarantines the R2 fee-dead 48-53c cost zone; flipping to the registered
p_eff<0.50 pollutes the lo bucket), ADOPT the registered prior (w+100)/(n+200)
at mean 0.5 (R8 fix: removes the ~1.1c anti-conservative seed anchoring).
Also isolates seed-vs-mass: cost_M200_seedled = cost bucket, M=200 at .5057/.5068.

Reports: base + stress walk-forward, paired TEST boots vs a_current, live-book
decision flips, expected sized/day. stdlib only. Writes part4_results.json.
"""
import json, os, math, random

HERE = os.path.dirname(os.path.abspath(__file__))
DS = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/"
                    "work-deepen/dataset/signals_60d.json"))
ST = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/"
                    "data/state_extract.json"))
TEST_T0 = 1782432000
FEE, GAS, MINORD = 0.07, 0.004, 1.0
ANCHORS = [(0.45, 0.25 * 0.55), (0.49, 0.50 * 0.55), (0.51, 0.25 * 0.55)]
COST = {p: p + FEE * p * (1 - p) for p, _ in ANCHORS}
TIE_UP = 0.432

signals = []
for r in DS["rows"]:
    if not (r["trigger"] and r["gatePass"]): continue
    if r["side"] == "up":
        pwin = 1.0 if r["label"] == "up" else (TIE_UP if r["label"] == "tie" else 0.0)
    else:
        pwin = 1.0 if r["label"] == "down" else ((1 - TIE_UP) if r["label"] == "tie" else 0.0)
    signals.append(dict(t0=r["t0"], split=r["split"], pwin=pwin))
signals.sort(key=lambda s: s["t0"])
T0, T1 = signals[0]["t0"], signals[-1]["t0"]
DAYS = dict(train=(TEST_T0 - T0) / 86400.0, test=(T1 + 300 - TEST_T0) / 86400.0)
TICKS = []
t = ((T0 // 86400) + 1) * 86400 + 600
while t <= T1 + 86400: TICKS.append(t); t += 86400

FAMS = dict(
    a_current=dict(bucket="cost", M=400, seed=(0.5057, 0.5068), cap=0.56),
    b_spec=dict(bucket="peff", M=200, seed=(0.5, 0.5), cap=0.56),
    hybrid_cost_M200=dict(bucket="cost", M=200, seed=(0.5, 0.5), cap=0.56),
    cost_M200_seedled=dict(bucket="cost", M=200, seed=(0.5057, 0.5068), cap=0.56),
)

def bucket_is_lo(famc, p):
    return (COST[p] < 0.50) if famc["bucket"] == "cost" else (p < 0.50)

def run(famc, stress_zone=False, collect=False):
    book = []; qlo, qhi = famc["seed"]
    bank, bank_reset = 1000.0, False; tick_i = 0
    stats = {sp: dict(pnl=0.0, shares=0.0, sized_w=0.0, brier=0.0, rec_w=0.0,
                      pnl_anchor={0.45: 0.0, 0.49: 0.0, 0.51: 0.0}) for sp in ("train", "test")}
    rows = {} if collect else None
    q_traj = []
    def upd():
        nonlocal qlo, qhi
        tick = TICKS[tick_i]
        lo_w = lo_s = hi_w = hi_s = 0.0
        for (t0, lo, pw, w, c) in book:
            if t0 + 360 > tick or (tick - t0) / 86400.0 > 30: continue
            if lo: lo_w += w; lo_s += w * pw
            else:  hi_w += w; hi_s += w * pw
        M = famc["M"]; slo, shi = famc["seed"]
        qlo = min(famc["cap"], round((lo_s + M * slo) / (lo_w + M), 4))
        qhi = min(famc["cap"], round((hi_s + M * shi) / (hi_w + M), 4))
        q_traj.append((tick, qlo, qhi))
    for s in signals:
        while tick_i < len(TICKS) - 1 and TICKS[tick_i + 1] <= s["t0"]:
            tick_i += 1; upd()
        if not bank_reset and s["t0"] >= TEST_T0: bank, bank_reset = 1000.0, True
        st = stats[s["split"]]
        for p, w in ANCHORS:
            c = COST[p]; lo = bucket_is_lo(famc, p)
            pw = 0.5 if (stress_zone and c >= 0.50) else s["pwin"]
            q = qlo if lo else qhi
            st["rec_w"] += w
            st["brier"] += w * (pw * (1 - q) ** 2 + (1 - pw) * q ** 2)
            book.append((s["t0"], lo, pw, w, c))
            if bank < 250: continue
            f = q - (1 - q) * c / (1 - c)
            if f <= 0: continue
            stake = min(0.25 * f * bank, 0.05 * bank)
            if stake < MINORD: continue
            sh = stake / p
            epnl = sh * (pw * (1 - c) - (1 - pw) * c) - GAS
            st["pnl"] += w * epnl; st["shares"] += w * sh; st["sized_w"] += w
            st["pnl_anchor"][p] += w * epnl
            bank += w * epnl
            if collect and s["split"] == "test":
                rows[s["t0"]] = rows.get(s["t0"], 0.0) + w * epnl
    out = {sp: dict(pnl=round(stats[sp]["pnl"], 2),
                    cps=round(100 * stats[sp]["pnl"] / stats[sp]["shares"], 3) if stats[sp]["shares"] else None,
                    brier=round(stats[sp]["brier"] / stats[sp]["rec_w"], 5),
                    sized_per_day=round(stats[sp]["sized_w"] / DAYS[sp], 2),
                    pnl_anchor={str(k): round(v, 2) for k, v in stats[sp]["pnl_anchor"].items()})
           for sp in ("train", "test")}
    out["q_final"] = q_traj[-1][1:] if q_traj else None
    if collect: out["_rows"] = rows
    return out

res = {}
for nm, f in FAMS.items():
    res[nm] = dict(base=run(f), stress=run(f, stress_zone=True))

def paired_boot(nmA, nmB, stress_zone):
    ra = run(FAMS[nmA], stress_zone, collect=True)["_rows"]
    rb = run(FAMS[nmB], stress_zone, collect=True)["_rows"]
    hrs = {}
    for t0, v in ra.items(): hrs.setdefault(t0 // 3600, [0.0, 0.0])[0] += v
    for t0, v in rb.items(): hrs.setdefault(t0 // 3600, [0.0, 0.0])[1] += v
    blocks = [b - a for a, b in hrs.values()]
    rng = random.Random(13); bs = []
    for _ in range(4000): bs.append(sum(rng.choice(blocks) for _ in range(len(blocks))))
    bs.sort()
    return dict(point=round(sum(blocks), 2), n_blocks=len(blocks),
                ci90=[round(bs[int(.05 * len(bs))], 2), round(bs[int(.95 * len(bs))], 2)],
                p_le_0=round(sum(1 for x in bs if x <= 0) / len(bs), 4))

boots = dict(
    hybrid_vs_current_base=paired_boot("a_current", "hybrid_cost_M200", False),
    hybrid_vs_current_stress=paired_boot("a_current", "hybrid_cost_M200", True),
    seed_effect_base=paired_boot("cost_M200_seedled", "hybrid_cost_M200", False),
    mass_effect_base=paired_boot("a_current", "cost_M200_seedled", False))

# ---- live-book flips for the hybrid (cost bucket, M200 @ 0.5) ----
ms = ST["measure"]; settled = [m for m in ms if m["win"] is not None]
lo_n = sum(1 for m in settled if m["cost"] < 0.50)
lo_w = sum(m["win"] for m in settled if m["cost"] < 0.50)
hi_n = len(settled) - lo_n; hi_w = sum(m["win"] for m in settled) - lo_w
qlo_h = min(0.56, round((lo_w + 100) / (lo_n + 200), 4))
qhi_h = min(0.56, round((hi_w + 100) / (hi_n + 200), 4))
def dec(qlo, qhi):
    return [bool((qlo if m["cost"] < 0.50 else qhi) -
                 (1 - (qlo if m["cost"] < 0.50 else qhi)) * m["cost"] / (1 - m["cost"]) > 0)
            for m in ms]
d_cur = dec(ST["impulse_cfg"]["qlo"], ST["impulse_cfg"]["qhi"])
d_hyb = dec(qlo_h, qhi_h)
flips = [i for i in range(len(ms)) if d_cur[i] != d_hyb[i]]
ev = 0.0; detail = []
for i in flips:
    m = ms[i]
    if m["win"] is None: continue
    net = (1 - m["cost"]) if m["win"] else -m["cost"]
    ev += net if d_hyb[i] else -net
    detail.append(dict(t0=m["t0"], cost=m["cost"], win=m["win"],
                       now="sized" if d_hyb[i] else "skip"))
live = dict(qlo_hybrid=qlo_h, qhi_hybrid=qhi_h,
            deployed=(ST["impulse_cfg"]["qlo"], ST["impulse_cfg"]["qhi"]),
            n_sized_deployed=sum(d_cur), n_sized_hybrid=sum(d_hyb),
            flips=len(flips), flip_ev_firstpoll_per_share=round(ev, 3), flip_detail=detail)

out = dict(families=FAMS, results=res, paired_test_boots=boots, live_book_hybrid=live,
           K_part4_runs=len(FAMS) * 2 + 4)
json.dump(out, open(os.path.join(HERE, "part4_results.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
