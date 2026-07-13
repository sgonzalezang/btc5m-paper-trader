#!/usr/bin/env python3
"""
ADVERSARIAL VERIFICATION of wave-2 unit "dataset" (signals_60d.json).
Fresh, independent implementation of the bot's trigger+gate pipeline, written from
the _impulse_gate docstring / bot source (btc5m_bot.py) — array-indexed, NOT a copy
of build_signals.py's dict-based code.

Checks:
  A. cb5m gap audit + full-universe decision-bit comparison (ALL rows, not just 200)
  B. 200-row random-sample deep recompute (every numeric field, incl. feats)
  C. measure-book (36 records) re-verification from scratch
  D. direct ivlHist2 feed-vs-candle check on the claimed borderline trigger
  E. v3 ledger reconciliation (106 trades) from scratch
  F. prior-program count reconciliation (VARIANTS.md 4,022/2,742/.5511)
  G. label-vs-PM resolution agreement
  H. live-window coverage / censoring claim (50 vs 36 vs 30)
  I. borderline mass, vol sources, alt rows, real joins, headline stats
Python3 stdlib only.
"""
import json, math, random, datetime

D = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
OLD = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data"
DS = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work-deepen/dataset/signals_60d.json"
OUTD = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work-deepen/verify/dataset-0"
IVL = 300
TEST_T0 = 1782432000

def utc(t): return datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d %H:%M")

cb = json.load(open(f"{D}/cb5m.json"))
T, O, H, L, C = cb["t"], cb["o"], cb["h"], cb["l"], cb["c"]
N = len(T)
cb1 = json.load(open(f"{D}/cb1m.json"))
i1 = {t: k for k, t in enumerate(cb1["t"])}

res = {}

# ---------- A0. gap audit (independent) ----------
gaps5 = [(T[k], T[k+1]) for k in range(N-1) if T[k+1] - T[k] != IVL]
gaps1 = [(cb1["t"][k], cb1["t"][k+1]) for k in range(len(cb1["t"])-1)
         if cb1["t"][k+1] - cb1["t"][k] != 60]
res["gap_audit"] = dict(cb5m_candles=N, cb5m_gaps=len(gaps5),
                        cb5m_window=[utc(T[0]), utc(T[-1])],
                        cb1m_candles=len(cb1["t"]), cb1m_gaps=len(gaps1),
                        cb1m_gap_list=[[utc(a), utc(b)] for a, b in gaps1[:10]])
assert not gaps5, "cb5m has gaps -> everything below needs gap-aware logic"

# open-to-open return of interval starting at T[k]  (valid for k in 0..N-2)
R = [(O[k+1] - O[k]) / O[k] for k in range(N-1)]

def my_row(k):
    """Independent recompute for interval t0=T[k]. Needs 1<=k<=N-2."""
    t0 = T[k]
    rp = R[k-1]                                  # trigger interval return
    trig = abs(rp) * 100 >= 0.12
    side = ("down" if rp > 0 else "up") if trig else None
    ready = k >= 13                              # 13 contiguous returns R[k-13..k-1]
    eff6 = cnt12 = gp = None
    if ready:
        six = R[k-6:k]                           # trigger INCLUDED (R[k-1])
        den = sum(abs(x) for x in six)
        net = 1.0
        for x in six: net *= (1.0 + x)
        eff6 = abs(net - 1.0) / den if den > 0 else 1.0
        cnt12 = sum(1 for x in R[k-13:k-1] if abs(x) >= 0.0012)   # trigger EXCLUDED
        gp = (eff6 >= 0.10) and (cnt12 <= 6)
    r0 = R[k]
    label = "tie" if abs(r0) < 0.0001 else ("up" if r0 > 0 else "down")
    return dict(t0=t0, trigger=trig, rp=rp, side=side, ready=ready, eff6=eff6,
                cnt12=cnt12, gatePass=bool(ready and gp), r0=r0, label=label,
                split=("test" if t0 >= TEST_T0 else "train"))

def my_vol10m(t0):
    ms = [t0 - 600 + 60 * j for j in range(10)]
    if all(m in i1 for m in ms):
        hs = [cb1["h"][i1[m]] for m in ms]; ls = [cb1["l"][i1[m]] for m in ms]
        return (max(hs) - min(ls)) / min(ls) * 100, "1m"
    # 2x 5m proxy
    ks = []
    for tt in (t0 - 600, t0 - 300):
        j = (tt - T[0]) // IVL
        if 0 <= j < N and T[j] == tt: ks.append(j)
        else: return None, None
    hi = max(H[j] for j in ks); lo = min(L[j] for j in ks)
    return (hi - lo) / lo * 100, "5m2"

def my_retpct(k, nback):
    j = k - nback
    if j < 0: return None
    return (O[k] - O[j]) / O[j] * 100

# ---------- load dataset ----------
ds = json.load(open(DS))
rows = ds["rows"]
meta = ds["meta"]
byt0 = {r["t0"]: r for r in rows}
res["meta_counts_claimed"] = meta["counts"]

# ---------- A. full-universe decision-bit comparison ----------
mism = []
n_trig = n_gp = n_tie = n_ready = 0
gp_train = gp_test = 0
qw = dict(train=[0, 0], test=[0, 0])   # [wins_ex_tie, n_ex_tie]
ties_g = dict(train=0, test=0)
k_of_t0 = {T[k]: k for k in range(N)}
assert rows[0]["t0"] == T[1] and rows[-1]["t0"] == T[-2], "row window mismatch"
for r in rows:
    k = k_of_t0[r["t0"]]
    m = my_row(k)
    n_trig += m["trigger"]; n_ready += m["ready"]
    n_tie += (m["label"] == "tie")
    gp = m["trigger"] and m["gatePass"]
    if gp:
        n_gp += 1
        if m["split"] == "train": gp_train += 1
        else: gp_test += 1
        if m["label"] == "tie":
            ties_g[m["split"]] += 1
        else:
            qw[m["split"]][1] += 1
            qw[m["split"]][0] += (m["side"] == m["label"])
    for fld, mine in (("trigger", m["trigger"]), ("side", m["side"]),
                      ("gateReady", m["ready"]),
                      ("gatePass", bool(m["trigger"] and m["gatePass"]) if True else None),
                      ("label", m["label"]), ("split", m["split"])):
        theirs = r[fld]
        if fld == "gatePass":
            # dataset stores gatePass independent of trigger; compare raw gate bit
            theirs = r["gatePass"]; mine = m["gatePass"]
        if mine != theirs:
            mism.append(dict(t0=r["t0"], fld=fld, mine=mine, theirs=theirs))
res["full_universe"] = dict(
    rows=len(rows), decision_bit_mismatches=len(mism), mismatch_sample=mism[:20],
    my_triggers=n_trig, my_gateReady=n_ready, my_ties=n_tie,
    my_gated=(n_gp), my_gated_train=gp_train, my_gated_test=gp_test,
    my_gated_ties=dict(ties_g),
    my_q_ex_tie=dict(
        pooled=round((qw["train"][0]+qw["test"][0])/(qw["train"][1]+qw["test"][1]), 4),
        train=round(qw["train"][0]/qw["train"][1], 4),
        test=round(qw["test"][0]/qw["test"][1], 4)),
    my_q_tie_as_loss=dict(
        pooled=round((qw["train"][0]+qw["test"][0])/n_gp, 4),
        train=round(qw["train"][0]/(qw["train"][1]+ties_g["train"]), 4),
        test=round(qw["test"][0]/(qw["test"][1]+ties_g["test"]), 4)))

# ---------- B. 200-row random deep recompute ----------
random.seed(20260713)
sample = random.sample(rows, 200)
bad = []
tol = 5.1e-5   # 4dp rounding tolerance
for r in sample:
    k = k_of_t0[r["t0"]]
    m = my_row(k)
    errs = []
    def ck(name, mine, theirs, t=tol):
        if mine is None and theirs is None: return
        if mine is None or theirs is None or abs(mine - theirs) > t:
            errs.append((name, mine, theirs))
    ck("trig_move", m["rp"] * 100, r["trig_move"])
    ck("ret0", m["r0"] * 100, r["ret0"])
    ck("eff6", m["eff6"], r["eff6"])
    if m["cnt12"] != r["cnt12"]: errs.append(("cnt12", m["cnt12"], r["cnt12"]))
    f = r["feats"]
    ck("pm", abs(m["rp"]) * 100, f["pm"])
    if int((r["t0"] % 86400) // 3600) != f["hour"]: errs.append(("hour", None, f["hour"]))
    if datetime.datetime.utcfromtimestamp(r["t0"]).weekday() != f["dow"]:
        errs.append(("dow", None, f["dow"]))
    v, vsrc = my_vol10m(r["t0"])
    ck("vol10m", v, f["vol10m"])
    if vsrc != f["vol_src"]: errs.append(("vol_src", vsrc, f["vol_src"]))
    ck("ret15m", my_retpct(k, 3), f["ret15m"])
    ck("ret30m", my_retpct(k, 6), f["ret30m"])
    a1 = my_retpct(k, 12)
    ck("absret1h", abs(a1) if a1 is not None else None, f["absret1h"])
    # decision bits again (belt & braces)
    if m["trigger"] != r["trigger"]: errs.append(("trigger", m["trigger"], r["trigger"]))
    if bool(m["trigger"] and m["gatePass"]) != bool(r["trigger"] and r["gatePass"]):
        errs.append(("gated", None, None))
    if m["label"] != r["label"]: errs.append(("label", m["label"], r["label"]))
    if errs: bad.append(dict(t0=r["t0"], errs=[list(e) for e in errs]))
res["sample200"] = dict(n=200, rows_with_any_field_error=len(bad), detail=bad[:20])

# ---------- C. measure book ----------
st = json.load(open(f"{D}/state_extract.json"))
meas = st["measure"]
mc = dict(n=len(meas), beyond_horizon=0, in_window=0, trig_and_gp=0, side_ok=0,
          eff6_exact4=0, cnt12_exact=0, cnt12_pm1=0, n_feat=0, mismatches=[])
effd, cntd, pmd, vold = [], [], [], []
for m in meas:
    k = k_of_t0.get(m["t0"])
    if k is None or k > N - 2:
        mc["beyond_horizon"] += 1
        mc["mismatches"].append(dict(t0=m["t0"], utc=utc(m["t0"]), why="beyond candle horizon"))
        continue
    mc["in_window"] += 1
    mm = my_row(k)
    ok = mm["trigger"] and mm["gatePass"]
    mc["trig_and_gp"] += ok
    mc["side_ok"] += (mm["side"] == m["side"])
    if not ok:
        mc["mismatches"].append(dict(
            t0=m["t0"], utc=utc(m["t0"]), why="not candle trigger+gatePass",
            trigger=mm["trigger"], trig_move_bps=round(mm["rp"] * 1e4, 2),
            eff6=(round(mm["eff6"], 4) if mm["eff6"] is not None else None),
            cnt12=mm["cnt12"]))
    f = m.get("f")
    if f:
        mc["n_feat"] += 1
        if f.get("eff6") is not None and mm["eff6"] is not None:
            d = mm["eff6"] - f["eff6"]; effd.append(abs(d))
            mc["eff6_exact4"] += (abs(d) < 5e-5)
        if f.get("cnt12") is not None and mm["cnt12"] is not None:
            d = mm["cnt12"] - f["cnt12"]; cntd.append(abs(d))
            mc["cnt12_exact"] += (d == 0); mc["cnt12_pm1"] += (abs(d) <= 1)
        if f.get("pm") is not None:
            pmd.append(abs(abs(mm["rp"]) * 100 - f["pm"]) * 100)   # bps
        if f.get("vol") is not None:
            v, _ = my_vol10m(m["t0"])
            if v is not None: vold.append(abs(v - f["vol"]))
def med(x): x = sorted(x); return round(x[len(x)//2], 4) if x else None
mc["d_eff6"] = dict(n=len(effd), median=med(effd), max=round(max(effd), 4) if effd else None)
mc["d_cnt12"] = dict(n=len(cntd), median=med(cntd), max=max(cntd) if cntd else None)
mc["d_pm_bps"] = dict(n=len(pmd), median=med(pmd), max=round(max(pmd), 2) if pmd else None)
mc["d_vol"] = dict(n=len(vold), median=med(vold), max=round(max(vold), 4) if vold else None)
res["measure_book"] = mc

# ---------- D. ivlHist2 feed-vs-candle on the borderline trigger ----------
ih2 = st["ivlHist2"]
bl = {}
for t, rr in ih2:
    if t == 1783908900:
        k = k_of_t0[t]
        bl = dict(t0_interval=t, utc=utc(t), feed_ret_bps=round(rr * 1e4, 2),
                  candle_oo_bps=round(R[k] * 1e4, 2),
                  candle_oc_bps=round((C[k] - O[k]) / O[k] * 1e4, 2))
# also overall feed-vs-candle noise on the whole snapshot
diffs = []
for t, rr in ih2:
    k = k_of_t0.get(t)
    if k is not None and k <= N - 2:
        diffs.append(abs(rr - R[k]) * 1e4)
res["ivlhist2_check"] = dict(borderline=bl, n_snapshot=len(ih2),
                             feed_vs_candle_bps=dict(median=med(diffs),
                                                     max=round(max(diffs), 2) if diffs else None))

# ---------- E. ledger ----------
trades = json.load(open(f"{D}/trades_unified.json"))
v3 = [t for t in trades if t.get("eng") in ("impulse_v2", "impulse50", "reversal_v2")]
le = dict(n=len(v3), by_eng={}, exceptions=[])
exc_t0s = set()
for t in v3:
    e = t["eng"]; b = le["by_eng"].setdefault(e, dict(n=0, trigger=0, gatePass=0))
    b["n"] += 1
    k = k_of_t0.get(t["t0"])
    if k is None or k > N - 2 or k < 1:
        le["exceptions"].append(dict(eng=e, t0=t["t0"], utc=utc(t["t0"]), why="beyond candle window"))
        exc_t0s.add(t["t0"]); continue
    mm = my_row(k)
    b["trigger"] += mm["trigger"]
    b["gatePass"] += bool(mm["trigger"] and mm["gatePass"])
    bad_gate = (e in ("impulse_v2", "impulse50")) and not (mm["trigger"] and mm["gatePass"])
    bad_trig = (e == "reversal_v2") and not mm["trigger"]
    if bad_gate or bad_trig:
        le["exceptions"].append(dict(
            eng=e, t0=t["t0"], utc=utc(t["t0"]), trigger=mm["trigger"],
            trig_move_bps=round(mm["rp"] * 1e4, 2),
            eff6=(round(mm["eff6"], 4) if mm["eff6"] is not None else None),
            cnt12=mm["cnt12"]))
        exc_t0s.add(t["t0"])
le["exception_rows"] = len(le["exceptions"])
le["exception_t0s"] = sorted(exc_t0s)
res["ledger"] = le

# ---------- F. prior-program reconciliation ----------
old5 = json.load(open(f"{OLD}/cb5m.json"))
lo, hi = old5["t"][0], old5["t"][-1]
n_all = n_sel = w_sel = 0
for k in range(13, N - 1):
    t0 = T[k]
    if t0 < lo or t0 > hi: continue
    m = my_row(k)
    if not m["trigger"]: continue
    n_all += 1
    if not m["gatePass"]: continue
    n_sel += 1
    lab = "up" if m["r0"] > 0 else ("down" if m["r0"] < 0 else "up")  # sign rule, r0==0 -> up
    w_sel += (m["side"] == lab)
res["prior_recon"] = dict(window=[utc(lo), utc(hi)], n_all=n_all, n_sel=n_sel,
                          q_sel=round(w_sel / n_sel, 4),
                          claim=dict(n_all=4022, n_sel=2742, q_sel=0.5511))

# ---------- G. label vs PM ----------
rmap = {}
for t in trades:
    if t.get("result") in ("win", "loss") and t.get("side") in ("up", "down") and t.get("t0") in byt0:
        w = t["side"] if t["result"] == "win" else ("down" if t["side"] == "up" else "up")
        rmap.setdefault(t["t0"], set()).add(w)
rmap = {k: v.pop() for k, v in rmap.items() if len(v) == 1}
nontie = [(t0, w) for t0, w in rmap.items() if byt0[t0]["label"] != "tie"]
agree = sum(1 for t0, w in nontie if byt0[t0]["label"] == w)
ties = [(t0, w) for t0, w in rmap.items() if byt0[t0]["label"] == "tie"]
tie_up = sum(1 for _, w in ties if w == "up")
sub2 = [(t0, w) for t0, w in nontie if abs(byt0[t0]["ret0"]) < 0.02]
sub2_ag = sum(1 for t0, w in sub2 if byt0[t0]["label"] == w)
res["label_vs_pm"] = dict(n_resolved=len(rmap), nontie=len(nontie), nontie_agree=agree,
                          rate=round(agree / len(nontie), 4),
                          ties_resolved=len(ties), tie_up=tie_up,
                          sub2bps=len(sub2), sub2bps_agree=sub2_ag)

# ---------- H. live-window coverage ----------
mt0 = {m["t0"] for m in meas}
w0, w1 = min(mt0), max(mt0)
lt0 = {t["t0"] for t in v3}
gp_live = [T[k] for k in range(13, N - 1) if w0 <= T[k] <= w1
           and my_row(k)["trigger"] and my_row(k)["gatePass"]]
in_meas = sum(1 for t in gp_live if t in mt0)
led_only = sum(1 for t in gp_live if t not in mt0 and t in lt0)
unacc = [t for t in gp_live if t not in mt0 and t not in lt0]
res["coverage"] = dict(window=[utc(w0), utc(w1)], candle_gate_passes=len(gp_live),
                       measure_records=len(meas), in_measure=in_meas,
                       ledger_only=led_only, unaccounted=len(unacc),
                       unaccounted_t0=[utc(t) for t in unacc])

# ---------- I. misc headline checks ----------
n_bl = sum(1 for k in range(1, N - 1) if abs(R[k-1]) * 100 >= 0.12
           and abs(abs(R[k-1]) * 100 - 0.12) <= 0.015)
n_nm = sum(1 for k in range(1, N - 1) if 0.105 <= abs(R[k-1]) * 100 < 0.12)
alt_rows = [r for r in rows if "alt" in r]
real_rows = [r for r in rows if "real" in r]
real_led = sum(1 for r in real_rows if "ledger" in r["real"])
real_meas = sum(1 for r in real_rows if "measure" in r["real"])
real_gp = sum(1 for r in real_rows if r["trigger"] and r["gatePass"])
vs = {}
for r in rows:
    vs[r["feats"]["vol_src"]] = vs.get(r["feats"]["vol_src"], 0) + 1
fee = 0.07
anchors = [round(p + fee * p * (1 - p), 6) for p in (0.45, 0.49, 0.51)]
res["misc"] = dict(borderline_pm1p5=n_bl, near_miss_10p5_12=n_nm,
                   alt_rows=len(alt_rows),
                   alt_trigger_flips=sum(1 for r in alt_rows if r["alt"]["trigger"] != r["trigger"]),
                   alt_gate_flips=sum(1 for r in alt_rows if r["alt"]["gatePass"] != r["gatePass"]),
                   real_rows=len(real_rows), real_ledger=real_led, real_measure=real_meas,
                   real_on_gatepass=real_gp, vol_sources=vs,
                   my_cost_anchors=anchors,
                   file_cost_anchors=meta["fill_model"]["cost_anchors"])

json.dump(res, open(f"{OUTD}/results.json", "w"), indent=1)
print(json.dumps(res, indent=1))
