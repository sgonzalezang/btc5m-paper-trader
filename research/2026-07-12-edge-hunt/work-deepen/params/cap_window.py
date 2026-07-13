#!/usr/bin/env python3
"""Wave-2 params: cap (revEntryMax) sweep, entry-window sweep, and the <=47c
first-fill cap (task 2). These CANNOT be pure candle backtests (no per-signal ask
history), so they are MODELED overlays on measured objects:
  - measurement book (36 first-poll asks/costs on cap-compliant gated signals)
  - v3-era ledger fills (impulse_v2 27 / impulse50 35 / reversal_v2 44)
  - frozen fill model + wave-1 R2/R4/micro corrected numbers
Every assumption is stated in the output. Stdlib only.
"""
import json, math

BASE = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt"
FEE = 0.07
SLIP = 0.01

def cost_of(p):            # p = fill price incl slip
    return p + FEE * p * (1 - p)

def p_of_cost(c):          # invert
    return (1.07 - math.sqrt(1.07 ** 2 - 4 * FEE * c)) / (2 * FEE)

state = json.load(open(BASE + "/data/state_extract.json"))
ms = state["measure"]
trades = json.load(open(BASE + "/data/trades_unified.json"))
DS = json.load(open(BASE + "/work-deepen/dataset/signals_60d.json"))

# ---- reconstruct first-poll fill price p for all 36 measure records ----
book = []
for m in ms:
    p = round(p_of_cost(m["cost"]), 4)          # fill incl slip; ask = p - .01
    book.append(dict(t0=m["t0"], p=p, ask=round(p - SLIP, 2), cost=m["cost"],
                     sized=m["sized"], skip=m.get("skip"), win=m.get("win")))

# ---- v3 ledger ----
v3 = {}
for eng in ("impulse_v2", "impulse50", "reversal_v2"):
    rows = [t for t in trades if t.get("eng") == eng and t.get("status") == "settled"]
    v3[eng] = [dict(t0=t["t0"], entry=t["entry"], ask=t.get("ask"),
                    entrySec=round(t["at"] / 1000 - t["t0"], 1),
                    result=t.get("result"), side=t.get("side")) for t in rows]

# frozen-cell TEST economics from sweep1d (reference)
s1 = json.load(open(BASE + "/work-deepen/params/sweep1d.json"))
FROZ_TE = s1["frozen"]["test"]
q_xt, q_tl = FROZ_TE["q_xt"], FROZ_TE["q_tl"]
n_day = FROZ_TE["n_per_day"]
AVAIL, STAKE, GAS = 0.55, 50.0, 0.004

# =====================================================================
# CAP SWEEP (revEntryMax): flat-arm basis. Two q-poles:
#   A) price-independent q (frozen fill-model assumption)
#   B) R2-adjusted: fills with cost>=0.50 carry zone EV = -2.6c/share
#      (R2 corrected interval-dedup central); the cheap fills absorb the
#      complement so the cap-.53 mixture matches the cell's unconditional q.
# Availability: empirical first-poll ask CDF from the 36-record book
# (cap-compliant at .53 by construction), refill-corrected with the only
# measured dip rate P(refill | rich first quote) = 12/21 = .571 (R4).
# =====================================================================
CAPS = [0.47, 0.49, 0.51, 0.53]
REFILL_P, REFILL_IMPROVE = 12 / 21, 0.112       # measured: refills ~11.2c cheaper

def cap_cell(cap, q_uncond, refill=True):
    fills = []                                   # (p, weight)
    for b in book:
        if b["p"] <= cap + 1e-9:
            fills.append((b["p"], 1.0))
        elif refill:
            pr = min(b["p"] - REFILL_IMPROVE, cap)
            fills.append((pr, REFILL_P))
    W = sum(w for _, w in fills)
    if W == 0:
        return None
    mean_p = sum(p * w for p, w in fills) / W
    mean_cost = sum(cost_of(p) * w for p, w in fills) / W
    frac = W / len(book)                         # availability multiplier vs .53 book
    # pole A: q independent of price
    evA = (q_uncond - mean_cost) * 100
    # pole B: zone-adjusted. Calibrate q_rest on the cap-.53 mixture.
    hi53 = [(p, w) for p, w in ((b["p"], 1.0) for b in book) if cost_of(p) >= 0.50]
    w_hi53 = len(hi53) / len(book)
    mean_cost_hi53 = sum(cost_of(p) for p, _ in hi53) / len(hi53)
    q_hi_of = lambda c: c - 0.026                # zone EV -2.6c
    q_rest = (q_uncond - w_hi53 * q_hi_of(mean_cost_hi53)) / (1 - w_hi53)
    ev_hi_lo = 0.0
    for p, w in fills:
        c = cost_of(p)
        qq = q_hi_of(c) if c >= 0.50 else q_rest
        ev_hi_lo += w * (qq - c)
    evB = ev_hi_lo / W * 100
    usdA = n_day * AVAIL * frac * ((STAKE / mean_p) * (q_uncond - mean_cost) - GAS)
    return dict(cap=cap, avail_mult=round(frac, 3),
                fills_day=round(n_day * AVAIL * frac, 1),
                mean_fill=round(mean_p, 4), mean_cost=round(mean_cost, 4),
                ev_qflat_c=round(evA, 2), ev_r2adj_c=round(evB, 2),
                usd_day_qflat=round(usdA, 2))

cap_sweep = dict(
    assumptions=[
        "flat-arm basis (impulse50-like): the OPERATED flagship's f>0 rule already caps "
        "first fills at cost<qlo=.5068 (ask<=.47 at penny quotes), so revEntryMax in "
        "{.49,.51,.53,.55} is nearly INERT for impulse_v2 as operated — this table is the "
        "signal-population/flat-arm economics that feed the measurement book and day-60 verdict",
        "ask CDF = 36-record measurement book first-poll asks (censored <=.52 ask by the .53 cap)",
        "refill correction: P(dip below cap | rich first quote)=12/21=.571 at ~11.2c "
        "improvement (R4 measured, for dips to ~.47) applied to ALL caps — optimistic for "
        ".47, conservative bracket = no_refill variant",
        "pole q_flat: q independent of fill price (frozen model); pole r2_adj: cost>=.50 "
        "zone EV pinned to -2.6c/share (R2 corrected), cheap fills absorb the complement",
        "q_uncond = frozen-cell TEST ex-tie q = %.4f (ties-as-loss %.4f shown separately)" % (q_xt, q_tl),
        "NORMALIZATION: this table's cost mix comes from the empirical book (mean cost "
        ".4911 at cap .53), NOT the frozen anchors (.5025) — so its cap-.53 row (+7.89c "
        "ex-tie) is ~1.1c above sweep1d's frozen +6.76c; compare WITHIN the table only"],
    ex_tie=dict(refill=[cap_cell(c, q_xt, True) for c in CAPS],
                no_refill=[cap_cell(c, q_xt, False) for c in CAPS]),
    ties_as_loss=dict(refill=[cap_cell(c, q_tl, True) for c in CAPS]),
    cap_55=dict(
        verdict="DOMINATED per share; do not raise",
        basis="wave-1 dead-end #36: the 53-55c marginal band ran q=.433 at ~.55 fills "
              "(EV -12.9c/share); every unit of added mass is fee-dead. Added mass "
              "unmeasurable from the censored book (cap-blocked misses lack asks - "
              "wave-1 Tier-2 #7 logging fix)."))

# =====================================================================
# WINDOW SWEEP (revWinMin): modeled from ledger entrySec dists + micro a1.
# =====================================================================
def esec_dist(eng):
    xs = sorted(t["entrySec"] for t in v3[eng])
    return xs

def frac_le(xs, w):
    return sum(1 for x in xs if x <= w) / len(xs) if xs else None

first_fill = sorted(esec_dist("impulse50") + esec_dist("reversal_v2"))
flag_fills = esec_dist("impulse_v2")
WINS = [15, 30, 45, 60, 90]
micro = json.load(open(BASE + "/work/micro/a1_entrysec.json"))
rev_bins = micro["rev_family"]

window_sweep = dict(
    assumptions=[
        "availability(W<=45) = empirical P(entrySec<=W) on v3 first-fill engines "
        "(impulse50+reversal_v2 pooled, n=%d, window-censored at 45s)" % len(first_fill),
        "c/share for W in {15,30,45} held at the frozen level: micro F3 found NO speed "
        "alpha (price-stratified fast-vs-slow diff -4.45c fast-WORSE, p=.75) and the "
        "rev-family entry price mix is flat across bins (.486/.471/.484/.489)",
        "flagship refill loss for W<45: impulse_v2 entries later than W lose the R1 "
        "refill benefit (~11.2c cheaper re-entries)",
        "W in {60,90}: added fills bracketed by micro a5 late-only misses q_cf=.548 "
        "(unconditional, ~breakeven at 51c) and wave-1 dead-end #32 (mid-interval cheap "
        "dips: q collapses to .32-.33, adverse-selection bait). No candle-side label "
        "exists for 'would have filled at 45-90s', so this is a bracket, not an estimate."],
    entrySec=dict(first_fill_engines=dict(
                      n=len(first_fill),
                      p25=first_fill[len(first_fill)//4], p50=first_fill[len(first_fill)//2],
                      p75=first_fill[3*len(first_fill)//4], max=max(first_fill)),
                  impulse_v2=dict(
                      n=len(flag_fills),
                      p25=flag_fills[len(flag_fills)//4], p50=flag_fills[len(flag_fills)//2],
                      p75=flag_fills[3*len(flag_fills)//4], max=max(flag_fills))),
    cells=[])

froz_usd = FROZ_TE["usd_day_mid"]
for W in WINS:
    if W <= 45:
        a = frac_le(first_fill, W)
        a_flag = frac_le(flag_fills, W)
        window_sweep["cells"].append(dict(
            window_s=W, avail_mult=round(a, 3), flagship_entry_frac=round(a_flag, 3),
            ev_c="~frozen (no speed alpha measured; CI ~ +/-8c)",
            usd_day_mid_scaled=round(froz_usd * a, 2),
            note=("frozen" if W == 45 else
                  "loses %d%% of first fills and %d%% of flagship entries (incl. refills)"
                  % (round((1 - a) * 100), round((1 - a_flag) * 100)))))
    else:
        window_sweep["cells"].append(dict(
            window_s=W, avail_mult=">1 (unmeasurable, cap-blocked misses lack asks)",
            ev_added_fills_bracket_c=[-15.0, 2.0],
            basis="q_added in [.32 (#32 cheap-dip conditional), .548 (a5 late-only misses)] "
                  "at ~.50-.53 costs",
            note="EXTENSION UNPROVEN-TO-HARMFUL: every measured selection effect beyond "
                 "45s is adverse; 45+ pooled ledger bin ran -3.47c/share (n=814)"))

# =====================================================================
# TASK 2: firstFillMax = 0.47 (R1's action) — exact decision-change audit
# =====================================================================
QLO, QHI = state["impulse_cfg"]["qlo"], state["impulse_cfg"]["qhi"]   # .5068 / .503
QLO_REG = 0.4954                                   # R8: registered prior-200 formula, same data

def f_rule_skips(p, qlo, qhi):
    """True if the per-poll Kelly check skips a fill at price p."""
    c = cost_of(p)
    qh = qlo if c < 0.50 else qhi
    return not (qh - (1 - qh) * c / (1 - c) > 0)   # f<=0 -> skip

def implicit_ask_cap(qlo, qhi):
    """Largest penny ask the f>0 rule would take."""
    a = 0.60
    while a > 0.20:
        if not f_rule_skips(round(a + SLIP, 4), qlo, qhi):
            return round(a, 2)
        a = round(a - 0.01, 2)
    return None

cap_now = implicit_ask_cap(QLO, QHI)               # current implicit first-fill ask cap
cap_reg = implicit_ask_cap(QLO_REG, QHI)           # post-R8-fix
cap_max_drift = implicit_ask_cap(0.56, 0.56)       # qhat ceiling .56 (code cap)

# decision-change count on the 36-record book under firstFillMax=.47
changes = []
for b in book:
    cap_blocks = b["ask"] > 0.47 + 1e-9
    f_skips = f_rule_skips(b["p"], QLO, QHI)
    if cap_blocks and not f_skips:
        changes.append(b)
# flagship ledger fills above .47 ask (would a hard any-poll .47 cap have blocked?)
flag_above = [t for t in v3["impulse_v2"] if t["ask"] is not None and t["ask"] > 0.47 + 1e-9]
i50_above = [t for t in v3["impulse50"] if t["ask"] is not None and t["ask"] > 0.47 + 1e-9]

def pnl_cshare(ts):
    """realized EV c/share at ledger entries (win pays 1)."""
    if not ts: return None
    tot = sum((1 if t["result"] == "win" else 0) - cost_of(t["entry"]) for t in ts)
    return round(tot / len(ts) * 100, 2)

skipbook = [b for b in book if b["skip"] == "f_nonpos" and b["win"] is not None]
task2 = dict(
    implicit_cap_audit=dict(
        current_qlo_qhi=[QLO, QHI],
        implicit_first_fill_ask_cap_now=cap_now,
        post_R8_prior200_qlo=QLO_REG,
        implicit_cap_post_fix=cap_reg,
        implicit_cap_if_qhat_drifts_to_ceiling_056=cap_max_drift,
        note="f>0 skips iff cost>=qhat_bucket; at penny asks the CURRENT rule already "
             "blocks every first fill above the implicit cap"),
    decision_changes_on_measure_book=dict(
        n_records=len(book),
        blocked_by_cap47_but_sized_by_f=len(changes), detail=changes,
        interpretation="0 changes = the .47 explicit cap is REDUNDANT today at penny "
                       "quotes; it binds only if nightly qhat drifts UP"),
    flagship_ledger_fills_above_47c=dict(
        n=len(flag_above), of=len(v3["impulse_v2"]),
        asks=sorted(t["ask"] for t in flag_above),
        realized_ev_cshare=pnl_cshare(flag_above),
        all_fills_ev_cshare=pnl_cshare(v3["impulse_v2"])),
    impulse50_fills_above_47c=dict(
        n=len(i50_above), of=len(v3["impulse50"]),
        realized_ev_cshare=pnl_cshare(i50_above),
        all_fills_ev_cshare=pnl_cshare(v3["impulse50"])),
    insurance_value=dict(
        leak_if_drift_reopens_rich_fills="measurement book f_nonpos cohort: n=%d, "
            "q=%.4f, mean first-poll cost %.4f, EV %sc/share (micro F2: -9.99c)" % (
            len(skipbook),
            sum(b["win"] for b in skipbook) / len(skipbook) if skipbook else float("nan"),
            sum(b["cost"] for b in skipbook) / len(skipbook) if skipbook else float("nan"),
            round((sum(b["win"] for b in skipbook) / len(skipbook)
                   - sum(b["cost"] for b in skipbook) / len(skipbook)) * 100, 2) if skipbook else "?"),
        drift_scenario="if qhat drifted to its .56 code ceiling the implicit cap rises "
                       "to ask %.2f — i.e. the whole R2 fee-dead 48-53c zone reopens; "
                       "the explicit cap forecloses this at zero cost" % (cap_max_drift or -1)),
)

out = dict(cap_sweep=cap_sweep, window_sweep=window_sweep, task2_firstfill47=task2,
           v3_ledger_counts={k: len(v) for k, v in v3.items()})
json.dump(out, open(BASE + "/work-deepen/params/cap_window.json", "w"), indent=1)
print(json.dumps(out, indent=1))
