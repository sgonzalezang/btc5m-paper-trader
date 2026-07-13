#!/usr/bin/env python3
"""
Wave-2 DEEPENING / dataset agent.
Build THE canonical 60d gated-signal dataset (signals_60d.json) from cb5m.json by
porting the bot's exact trigger+gate pipeline (_impulse_gate, btc5m_bot.py ~line 535),
then validate against (a) the 36-record live measurement book, (b) the v3-era ledger,
(c) the prior program's counts (VARIANTS.md: 2,742/4,022 gated, q_sel=.5511).

Conventions (bot-faithful port, stated precisely):
  - Interval return r(t) for interval [t, t+300): PRIMARY convention is buffered
    open-to-open from cb5m: r(t) = (open(t+300) - open(t)) / open(t).  This is the
    prior program's registered convention (VARIANTS.md baseline) and the only one
    computable without lookahead ambiguity from 5m candles.  The ALT convention
    open-to-close r_oc(t) = (close(t)-open(t))/open(t) is computed everywhere and
    rows where trigger/gatePass differ carry an "alt" object.
  - Trigger at t0: |r(t0-300)|*100 >= 0.12 (bot compares prior_move% >= revThr).
  - side = "down" if r(t0-300) > 0 else "up"   (bot: rev_side).
  - Gate (_impulse_gate): needs returns for the 13 contiguous intervals ending at the
    trigger (t0-300*k, k=1..13).  eff6 over k=6..1 (TRIGGER INCLUDED):
    net = prod(1+r)-1, den = sum|r|, eff6 = |net|/den (den==0 -> 1.0).
    cnt12 = #{k in 2..13 : |r| >= 0.0012} (TRIGGER EXCLUDED).
    gatePass iff eff6 >= 0.10 (unrounded) and cnt12 <= 6.  Missing history -> not ready.
  - Label at t0 from open-to-open r0 = r(t0): "tie" if |r0| < 0.0001 (1bp), else up/down.
Python3 stdlib only. No lookahead: every feature uses data strictly before t0
(vol10m window is [t0-600, t0), NOT the bot's [now-600s, now] which can reach 45s
into the trade interval — documented deviation, lookahead-safe direction).
"""
import json, math, datetime, os

D = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
OLD = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data"
W = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work-deepen/dataset"

FEE = 0.07
IVL = 300
TEST_T0 = 1782432000            # 2026-06-26 00:00:00 UTC (TRAIN before, TEST from here)
def utc(t): return datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d %H:%M")

cb = json.load(open(f"{D}/cb5m.json"))
T, O, H, L, C = cb["t"], cb["o"], cb["h"], cb["l"], cb["c"]
idx = {t: i for i, t in enumerate(T)}
cb1 = json.load(open(f"{D}/cb1m.json"))
T1 = cb1["t"]; idx1 = {t: i for i, t in enumerate(T1)}

def ret_oo(t):  # buffered open-to-open return of interval [t, t+300)
    i = idx.get(t)
    if i is None or i + 1 >= len(T) or T[i + 1] != t + IVL: return None
    return (O[i + 1] - O[i]) / O[i]

def ret_oc(t):  # open-to-close (candle) return of interval [t, t+300)
    i = idx.get(t)
    if i is None: return None
    return (C[i] - O[i]) / O[i]

def gate(t0, retf):
    """Faithful _impulse_gate port. Returns (ready, ok, eff6_unrounded, cnt12)."""
    rs = {}
    for k in range(1, 14):
        r = retf(t0 - IVL * k)
        if r is None: return False, False, None, None
        rs[k] = r
    last6 = [rs[k] for k in range(6, 0, -1)]
    den = sum(abs(r) for r in last6)
    net = 1.0
    for r in last6: net *= (1.0 + r)
    eff6 = (abs(net - 1.0) / den) if den > 0 else 1.0
    cnt12 = sum(1 for k in range(2, 14) if abs(rs[k]) >= 0.0012)
    return True, (eff6 >= 0.10 and cnt12 <= 6), eff6, cnt12

def vol10m(t0):
    """Trailing 10-min range%, (hi-lo)/lo*100 like bot update_vol, from cb1m when the
    10 minute-candles [t0-600, t0) all exist, else 2x5m-candle proxy. -> (val, src)."""
    ms = [t0 - 600 + 60 * k for k in range(10)]
    if all(m in idx1 for m in ms):
        hs = [cb1["h"][idx1[m]] for m in ms]; ls = [cb1["l"][idx1[m]] for m in ms]
        lo = min(ls)
        return (round((max(hs) - lo) / lo * 100, 4) if lo else None), "1m"
    js = [idx.get(t0 - 600), idx.get(t0 - 300)]
    if any(j is None for j in js): return None, None
    hs = [H[j] for j in js]; ls = [L[j] for j in js]
    lo = min(ls)
    return (round((max(hs) - lo) / lo * 100, 4) if lo else None), "5m2"

def retpct(t0, back):
    a, b = idx.get(t0 - back), idx.get(t0)
    if a is None or b is None: return None
    return round((O[b] - O[a]) / O[a] * 100, 4)

# ---------------- build rows ----------------
rows = []
t_first, t_last = T[1], T[-1] - IVL          # need ret(t0-300) and open(t0+300)
n_tie = 0
for t0 in range(t_first, t_last + 1, IVL):
    if t0 not in idx: continue               # (cb5m has zero gaps; belt & braces)
    rp = ret_oo(t0 - IVL)
    r0 = ret_oo(t0)
    if rp is None or r0 is None: continue
    trig = abs(rp) * 100 >= 0.12             # bot: prior_move% >= 0.12
    side = ("down" if rp > 0 else "up") if trig else None
    ready, ok, eff6, cnt12 = gate(t0, ret_oo)
    ready_oc, ok_oc, eff6_oc, cnt12_oc = gate(t0, ret_oc)
    rp_oc = ret_oc(t0 - IVL)
    trig_oc = (rp_oc is not None and abs(rp_oc) * 100 >= 0.12)
    if abs(r0) < 0.0001:
        label = "tie"; n_tie += 1
    else:
        label = "up" if r0 > 0 else "down"
    v, vsrc = vol10m(t0)
    row = dict(
        t0=t0,
        trigger=trig,
        trig_move=round(rp * 100, 4),                       # signed, % of open
        side=side,
        eff6=(round(eff6, 4) if eff6 is not None else None),
        cnt12=cnt12,
        gateReady=ready,
        gatePass=bool(ready and ok),
        label=label,
        ret0=round(r0 * 100, 4),                            # signed, % (label return)
        split=("test" if t0 >= TEST_T0 else "train"),
        feats=dict(
            pm=round(abs(rp) * 100, 4),                     # bot feature convention: |move|%
            eff6=(round(eff6, 4) if eff6 is not None else None),
            cnt12=cnt12,
            hour=int((t0 % 86400) // 3600),
            dow=datetime.datetime.utcfromtimestamp(t0).weekday(),
            vol10m=v, vol_src=vsrc,
            ret15m=retpct(t0, 900), ret30m=retpct(t0, 1800),
            absret1h=(abs(retpct(t0, 3600)) if retpct(t0, 3600) is not None else None),
        ),
    )
    # alt convention only where it changes a decision bit
    if (trig_oc != trig) or (bool(ready_oc and ok_oc) != row["gatePass"]):
        row["alt"] = dict(conv="open-to-close",
                          trigger=trig_oc,
                          trig_move=(round(rp_oc * 100, 4) if rp_oc is not None else None),
                          eff6=(round(eff6_oc, 4) if eff6_oc is not None else None),
                          cnt12=cnt12_oc,
                          gatePass=bool(ready_oc and ok_oc))
    rows.append(row)

byt0 = {r["t0"]: r for r in rows}
print(f"rows {len(rows)}  {utc(rows[0]['t0'])} -> {utc(rows[-1]['t0'])}")
print(f"triggers {sum(r['trigger'] for r in rows)}  gateReady {sum(r['gateReady'] for r in rows)}"
      f"  gated(trigger&pass) {sum(r['trigger'] and r['gatePass'] for r in rows)}  ties {n_tie}")
alt_rows = [r for r in rows if "alt" in r]
print(f"alt-convention decision flips: {len(alt_rows)} "
      f"(trigger flips {sum(1 for r in alt_rows if r['alt']['trigger'] != r['trigger'])}, "
      f"gatePass flips {sum(1 for r in alt_rows if r['alt']['gatePass'] != r['gatePass'])})")

# ---------------- validation (a): measurement book ----------------
st = json.load(open(f"{D}/state_extract.json"))
meas = st["measure"]
def p_from_cost(c):   # invert cost = 1.07p - 0.07p^2 for p in (0,1)
    return (1.07 - math.sqrt(1.07 * 1.07 - 4 * 0.07 * c)) / (2 * 0.07)

va = dict(n=len(meas), missing_t0=0, trigger=0, gatePass=0, side_ok=0,
          eff6_exact4=0, eff6_within_01=0, cnt12_exact=0, cnt12_pm1=0,
          pm_exact4=0, n_feats=0, details=[])
va_oc = dict(eff6_exact4=0, cnt12_exact=0, gatePass=0)
eff6_diffs, cnt12_diffs, pm_diffs, vol_diffs = [], [], [], []
for m in meas:
    r = byt0.get(m["t0"])
    if r is None:
        va["missing_t0"] += 1
        va["details"].append(dict(t0=m["t0"], err="t0 not in dataset")); continue
    va["trigger"] += bool(r["trigger"])
    va["gatePass"] += bool(r["gatePass"])
    va["side_ok"] += (r["side"] == m["side"])
    a = r.get("alt", {})
    va_oc["gatePass"] += bool(a.get("gatePass", r["gatePass"]))
    f = m.get("f")
    det = dict(t0=m["t0"], side_book=m["side"], side_cand=r["side"],
               trigger=r["trigger"], gatePass=r["gatePass"])
    if f:
        va["n_feats"] += 1
        de = (r["eff6"] - f["eff6"]) if (r["eff6"] is not None and f.get("eff6") is not None) else None
        dc = (r["cnt12"] - f["cnt12"]) if (r["cnt12"] is not None and f.get("cnt12") is not None) else None
        dp = (r["feats"]["pm"] - f["pm"]) if f.get("pm") is not None else None
        if de is not None:
            eff6_diffs.append(de)
            va["eff6_exact4"] += (abs(de) < 5e-5)
            va["eff6_within_01"] += (abs(de) <= 0.01)
        if dc is not None:
            cnt12_diffs.append(dc)
            va["cnt12_exact"] += (dc == 0); va["cnt12_pm1"] += (abs(dc) <= 1)
        if dp is not None:
            pm_diffs.append(dp); va["pm_exact4"] += (abs(dp) < 5e-5)
        if f.get("vol") is not None and r["feats"]["vol10m"] is not None:
            vol_diffs.append(r["feats"]["vol10m"] - f["vol"])
        # alt convention comparison
        e_oc = a.get("eff6", r["eff6"]); c_oc = a.get("cnt12", r["cnt12"])
        if e_oc is not None and f.get("eff6") is not None:
            va_oc["eff6_exact4"] += (abs(e_oc - f["eff6"]) < 5e-5)
        if c_oc is not None and f.get("cnt12") is not None:
            va_oc["cnt12_exact"] += (c_oc == f["cnt12"])
        det.update(eff6_book=f.get("eff6"), eff6_cand=r["eff6"], d_eff6=(round(de, 4) if de is not None else None),
                   cnt12_book=f.get("cnt12"), cnt12_cand=r["cnt12"],
                   pm_book=f.get("pm"), pm_cand=r["feats"]["pm"])
    va["details"].append(det)
def dstats(xs):
    if not xs: return None
    xs2 = sorted(abs(x) for x in xs)
    return dict(n=len(xs), mean_abs=round(sum(xs2) / len(xs2), 5),
                med_abs=round(xs2[len(xs2) // 2], 5), max_abs=round(xs2[-1], 5))
va["eff6_absdiff"] = dstats(eff6_diffs); va["cnt12_absdiff"] = dstats([float(x) for x in cnt12_diffs])
va["pm_absdiff_bps"] = dstats([x * 100 for x in pm_diffs])   # pm is %, x100 -> bps
va["vol_absdiff"] = dstats(vol_diffs)
va["alt_open_to_close"] = va_oc
print("\n[VAL A] measure book:", {k: v for k, v in va.items() if k not in ("details",)})

# ---------------- validation (b): v3-era ledger ----------------
trades = json.load(open(f"{D}/trades_unified.json"))
v3 = [t for t in trades if t.get("eng") in ("impulse_v2", "impulse50", "reversal_v2")]
vb = dict(n=len(v3), by_eng={}, exceptions=[])
for t in v3:
    e = t["eng"]; r = byt0.get(t["t0"])
    b = vb["by_eng"].setdefault(e, dict(n=0, trigger=0, gatePass=0))
    b["n"] += 1
    gated_eng = e in ("impulse_v2", "impulse50")
    if r is None:
        vb["exceptions"].append(dict(eng=e, t0=t["t0"], err="t0 not in dataset")); continue
    b["trigger"] += bool(r["trigger"]); b["gatePass"] += bool(r["gatePass"])
    if not r["trigger"] or (gated_eng and not r["gatePass"]):
        vb["exceptions"].append(dict(
            eng=e, t0=t["t0"], utc=utc(t["t0"]), trigger=r["trigger"], gatePass=r["gatePass"],
            trig_move=r["trig_move"], eff6=r["eff6"], cnt12=r["cnt12"],
            alt=r.get("alt"), driftPct_ledger=t.get("driftPct"),
            note="ledger fired on FEED returns; candle margin shown"))
print("\n[VAL B] ledger:", vb["by_eng"], f"exceptions {len(vb['exceptions'])}")
for x in vb["exceptions"]: print("   ", x)

# label vs PM resolution (all settled trades, dedup by t0, majority side truth)
res = {}
for t in trades:
    if t.get("result") in ("win", "loss") and t.get("t0") in byt0 and t.get("side") in ("up", "down"):
        wside = t["side"] if t["result"] == "win" else ("down" if t["side"] == "up" else "up")
        res.setdefault(t["t0"], set()).add(wside)
res = {k: v.pop() for k, v in res.items() if len(v) == 1}
agree = sum(1 for t0, w in res.items() if byt0[t0]["label"] == w)
n_res = len(res)
tie_rows = [(t0, w) for t0, w in res.items() if byt0[t0]["label"] == "tie"]
sub2 = [(t0, w) for t0, w in res.items() if abs(byt0[t0]["ret0"]) < 0.02 and byt0[t0]["label"] != "tie"]
sub2_agree = sum(1 for t0, w in sub2 if byt0[t0]["label"] == w)
tie_up = sum(1 for _, w in tie_rows if w == "up")
vl = dict(n_resolved_t0=n_res, label_agree=agree, agree_rate=round(agree / n_res, 4),
          ties_with_resolution=len(tie_rows), tie_resolved_up=tie_up,
          sub2bps_nontie=len(sub2), sub2bps_agree=sub2_agree,
          sub2bps_rate=(round(sub2_agree / len(sub2), 4) if sub2 else None))
print("\n[VAL label-vs-PM]", vl)

# ---------------- validation (c): prior program counts ----------------
old5 = json.load(open(f"{OLD}/cb5m.json"))
old_lo, old_hi = old5["t"][0], old5["t"][-1]
def recon(t_lo, t_hi, ties_up):
    n_all = n_sel = w_sel = 0
    for t0 in range(t_lo, t_hi + 1, IVL):
        r = byt0.get(t0)
        if r is None or not r["trigger"] or not r["gateReady"]: continue
        n_all += 1
        if not r["gatePass"]: continue
        n_sel += 1
        lab = r["label"]
        if lab == "tie":
            lab = "up" if ties_up else ("up" if r["ret0"] > 0 else ("down" if r["ret0"] < 0 else "up"))
        elif abs(r["ret0"]) < 1e-9:
            lab = "up"
        w_sel += (r["side"] == lab)
    return n_all, n_sel, w_sel
# prior program tie rule: ties->Up literally means r0 == 0 -> up; our 'tie' is |r0|<1bp.
# reconstruct with sign rule (r0>0 up, r0<0 down, r0==0 up):
def recon_sign(t_lo, t_hi):
    n_all = n_sel = w_sel = 0
    for t0 in range(t_lo, t_hi + 1, IVL):
        r = byt0.get(t0)
        if r is None or not r["trigger"] or not r["gateReady"]: continue
        n_all += 1
        if not r["gatePass"]: continue
        n_sel += 1
        lab = "up" if r["ret0"] > 0 else ("down" if r["ret0"] < 0 else "up")
        w_sel += (r["side"] == lab)
    return n_all, n_sel, w_sel
na, ns, ws = recon_sign(old_lo, old_hi)
vc = dict(prior_window=[utc(old_lo), utc(old_hi)],
          prior_claim=dict(n_all=4022, n_sel=2742, q_sel=0.5511),
          repro=dict(n_all=na, n_sel=ns, q_sel=(round(ws / ns, 4) if ns else None)),
          delta=dict(n_all=na - 4022, n_sel=ns - 2742,
                     q_sel=(round(ws / ns - 0.5511, 4) if ns else None)))
print("\n[VAL C] prior-count reconciliation:", vc)

# TRAIN/TEST canonical stats (ties as written: tie label excluded from win, counted separately)
def seg_stats(rs):
    sel = [r for r in rs if r["trigger"] and r["gatePass"]]
    ntie = sum(1 for r in sel if r["label"] == "tie")
    nont = [r for r in sel if r["label"] != "tie"]
    w = sum(1 for r in nont if r["side"] == r["label"])
    wtie_loss = sum(1 for r in sel if r["side"] == r["label"])  # tie counts as loss unless label==side (never)
    return dict(n_sel=len(sel), ties=ntie,
                q_ex_tie=(round(w / len(nont), 4) if nont else None),
                q_tie_as_loss=(round(wtie_loss / len(sel), 4) if sel else None))
stats = dict(all=seg_stats(rows),
             train=seg_stats([r for r in rows if r["split"] == "train"]),
             test=seg_stats([r for r in rows if r["split"] == "test"]))
print("\n[stats]", json.dumps(stats))

# ---------------- fill layer ----------------
FILL_MODEL = dict(
    desc="Frozen prior-program fill model (DESIGN.md rev2 CONFIRMED#1): contrarian fills "
         "censored to the 53c cap land at quantile anchors p25/p50/p75 = .45/.49/.51 "
         "(fill price INCLUDES the +1c slip over ask), share-weighted mean fill .4724, "
         "hurdle q* .4898, availability ~0.55 (unfillable signals are SKIPS, never 50c fills). "
         "EV/share = q - p - 0.07*p*(1-p); gas $0.004/trade.",
    fill_anchors=[0.45, 0.49, 0.51],
    cost_anchors=[round(p + FEE * p * (1 - p), 6) for p in (0.45, 0.49, 0.51)],
    mean_fill=0.4724, hurdle_q=0.4898, availability=0.55,
    fee="0.07*p*(1-p)", slip="ask+1c", gas=0.004)

meas_by_t0 = {m["t0"]: m for m in meas}
led_by_t0 = {}
for t in v3:
    led_by_t0.setdefault(t["t0"], []).append(t)
# join real fills to EVERY row with data at that t0 (not only gate-passes): the
# reversal_v2 control's gate-reject fills are needed for gate-increment analyses.
n_real_meas = n_real_led = n_real_gp = 0
for r in rows:
    real = {}
    m = meas_by_t0.get(r["t0"])
    if m:
        ask = (m.get("f") or {}).get("ask")
        if ask is None:
            ask = round(p_from_cost(m["cost"]) - 0.01, 4)   # invert first-poll cost, back out +1c slip
        real["measure"] = dict(ask=ask, cost_firstpoll=m["cost"], sized=m["sized"],
                               skip=m.get("skip"), win=m.get("win"))
        n_real_meas += 1
    if r["t0"] in led_by_t0:
        real["ledger"] = [dict(eng=t["eng"], ask=t.get("ask"), entry=t.get("entry"),
                               cost=(round(t["entry"] + FEE * t["entry"] * (1 - t["entry"]), 6)
                                     if isinstance(t.get("entry"), (int, float)) else None),
                               entrySec=t.get("entrySec"), result=t.get("result"),
                               side=t.get("side"))
                          for t in led_by_t0[r["t0"]]]
        n_real_led += 1
    if real:
        r["real"] = real
        if r["trigger"] and r["gatePass"]: n_real_gp += 1
print(f"\n[fill layer] real joins: measure {n_real_meas}, ledger {n_real_led}, "
      f"of which on gate-pass rows {n_real_gp}")

# availability sanity in the live window (measure book era)
w0, w1 = min(meas_by_t0), max(meas_by_t0)
gp_live = [r for r in rows if r["trigger"] and r["gatePass"] and w0 <= r["t0"] <= w1]
led_t0s = {t["t0"] for t in v3}
cov = dict(in_measure=0, ledger_only=0, unaccounted=0, unaccounted_t0=[])
for r in gp_live:
    if r["t0"] in meas_by_t0: cov["in_measure"] += 1
    elif r["t0"] in led_t0s: cov["ledger_only"] += 1
    else:
        cov["unaccounted"] += 1
        cov["unaccounted_t0"].append(dict(t0=r["t0"], utc=utc(r["t0"]), pm=r["feats"]["pm"]))
cov["note"] = ("unaccounted = candle gate-pass with no measure record and no v3 ledger entry: "
               "either unfillable at the 53c cap / one-sided book / spread / depth / stale "
               "(the bot only calls _measure_record when FILLABLE - availability censoring, "
               "prior program estimated ~55% availability), bot downtime, or a feed-vs-candle "
               "borderline where the bot's feed never saw >=12bps. Indistinguishable offline; "
               "n_unaccounted/n_gate_passes is an upper bound on the censored mass.")
print(f"[coverage] candle gate-passes in live measure window [{utc(w0)},{utc(w1)}]: "
      f"{len(gp_live)}; measure records: {len(meas)}; classification: in_measure "
      f"{cov['in_measure']}, ledger_only {cov['ledger_only']}, unaccounted {cov['unaccounted']}")

# borderline mass: triggers within +-1.5bps of the 12bps threshold (convention-sensitive band)
n_trig = sum(r["trigger"] for r in rows)
bl = sum(1 for r in rows if r["trigger"] and abs(r["feats"]["pm"] - 0.12) <= 0.015)
bl_near_miss = sum(1 for r in rows if not r["trigger"] and r["feats"]["pm"] >= 0.105)
borderline = dict(triggers_within_1p5bps_of_thr=bl, frac_of_triggers=round(bl / n_trig, 4),
                  near_misses_10p5_to_12bps=bl_near_miss,
                  note="feed-vs-candle per-interval return noise is ~1-2bps median, max ~5-7bps "
                       "(measured on the 20-interval live ivlHist2 snapshot and the measure-book pm "
                       "deltas); triggers inside this band can flip between the bot's feed and candles")
print("[borderline]", borderline)

# vol source split
vs = {}
for r in rows: vs[r["feats"]["vol_src"]] = vs.get(r["feats"]["vol_src"], 0) + 1
print("[vol sources]", vs)

# ---------------- write ----------------
validation = dict(measure_book=va, ledger=vb, label_vs_pm=vl, prior_counts=vc,
                  canonical_stats=stats,
                  live_window_coverage=dict(window=[w0, w1], candle_gate_passes=len(gp_live),
                                            measure_records=len(meas), classification=cov),
                  borderline=borderline,
                  vol_sources=vs,
                  alt_convention_flips=dict(n=len(alt_rows)))
out = dict(
    meta=dict(
        built=datetime.datetime.utcnow().isoformat() + "Z",
        source=dict(cb5m=f"{D}/cb5m.json", cb1m=f"{D}/cb1m.json",
                    measure=f"{D}/state_extract.json", ledger=f"{D}/trades_unified.json"),
        window=[rows[0]["t0"], rows[-1]["t0"]],
        window_utc=[utc(rows[0]["t0"]), utc(rows[-1]["t0"])],
        convention="open-to-open (buffered) primary; 'alt' object where open-to-close flips trigger/gatePass",
        split=dict(train_before=TEST_T0, note="TRAIN May 11-Jun 25, TEST Jun 26-Jul 13 (t0 >= 1782432000)"),
        tie_rule="|ret0| < 1bp => label 'tie'",
        counts=dict(rows=len(rows), triggers=sum(r["trigger"] for r in rows),
                    gate_passes=sum(r["trigger"] and r["gatePass"] for r in rows),
                    ties=n_tie),
        fill_model=FILL_MODEL,
    ),
    validation=validation,
    rows=rows,
)
with open(f"{W}/signals_60d.json", "w") as f:
    json.dump(out, f, separators=(",", ":"))
with open(f"{W}/validation.json", "w") as f:
    json.dump(validation, f, indent=1)
print(f"\nwrote {W}/signals_60d.json ({os.path.getsize(f'{W}/signals_60d.json')/1e6:.1f} MB)")
