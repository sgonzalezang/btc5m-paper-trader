"""T3: De-censor the fill decision.
(a) Reconstruct ALL 12bps-trigger intervals (buffered open-to-open, cb5m) in the
    live window; join PM resolutions; compare q of FILLED vs UNFILLED signals.
(b) Cap-rejected near-misses (state misses: 'Rev<=53c'/'Rev<=55c' shortfall):
    q of the signals the price cap rejected.
(c) Measure-book f_nonpos skips (cost>qhat): q of expensive-skips vs sized.
PM resolutions primary; cb-proxy-extended as sensitivity (|move|>=1bp only).
"""
import json, collections
import common as C

out = {}
res, _ = C.resolution_map()
cb = C.cb5m_map()
trades = C.load_trades()

REV = {"reversal","reversal2","reversal_v2","latentfire","impulse_v2","impulse50"}
# fills by t0 (any trigger-family engine) with entry price
fills = {}
for t in trades:
    if t["eng"] in REV and t.get("entry") is not None:
        fills.setdefault(t["t0"], []).append(t)

# --- (a) trigger universe
T0_MIN = 1783386300           # first ledger t0 (Jul 7 01:05)
T0_MAX = 1783914000           # last  ledger t0 (Jul 13 03:40)
ts = sorted(cb.keys())
trigger_rows = []             # (t0, side, filled?, up)
for t0 in ts:
    if not (T0_MIN <= t0 <= T0_MAX):
        continue
    prev = cb.get(t0 - 300)
    cur = cb.get(t0)
    if not prev or not cur:
        continue
    mv = (cur["o"] - prev["o"]) / prev["o"]
    if abs(mv) < 0.0012:
        continue
    side = "down" if mv > 0 else "up"     # contrarian; ties->up (mv>0 strict)
    filled = t0 in fills
    up_pm = res.get(t0)
    outc = cur["c"] >= cur["o"]           # cb proxy outcome
    mv_out = (cur["c"] - cur["o"]) / cur["o"]
    trigger_rows.append(dict(t0=t0, side=side, filled=filled, up_pm=up_pm,
                             up_cb=1 if outc else 0, mv_out_bp=mv_out * 1e4))

out["n_triggers"] = len(trigger_rows)
out["n_triggers_with_pm_res"] = sum(1 for r in trigger_rows if r["up_pm"] is not None)
out["n_triggers_filled"] = sum(1 for r in trigger_rows if r["filled"])

def q_of(rows, up_key):
    n = len(rows)
    w = sum(1 for r in rows if (r[up_key] == 1) == (r["side"] == "up"))
    ph, l, h = C.wilson(w, n)
    return dict(n=n, w=w, q=round(ph,4) if n else None,
                ci=[round(l,4), round(h,4)] if n else None)

def fill_split(rows, up_key, label):
    f = [r for r in rows if r["filled"]]
    u = [r for r in rows if not r["filled"]]
    qf, qu = q_of(f, up_key), q_of(u, up_key)
    z, pv = C.two_prop_z(qf["w"], qf["n"], qu["w"], qu["n"]) if f and u else (None, None)
    return dict(label=label, filled=qf, unfilled=qu,
                z=round(z,3) if z is not None else None,
                p=round(pv,4) if pv is not None else None)

# PM-resolution-only, by era
pmrows = [r for r in trigger_rows if r["up_pm"] is not None]
out["fillsplit_pm_all"] = fill_split(pmrows, "up_pm", "PM res, all eras")
out["fillsplit_pm_pre_v3"] = fill_split([r for r in pmrows if r["t0"] < C.V3_CUT], "up_pm", "PM res, pre-v3")
out["fillsplit_pm_v3"] = fill_split([r for r in pmrows if r["t0"] >= C.V3_CUT], "up_pm", "PM res, v3")
# cb-proxy sensitivity (exclude sub-1bp outcome moves = resolution-noise zone)
cbrows = [r for r in trigger_rows if abs(r["mv_out_bp"]) >= 1.0]
out["fillsplit_cbproxy_ge1bp"] = fill_split(cbrows, "up_cb", "CB proxy, |out|>=1bp")
out["fillsplit_cbproxy_v3"] = fill_split([r for r in cbrows if r["t0"] >= C.V3_CUT], "up_cb", "CB proxy v3")

# engine-live-window restriction: first reversal-family fill Jul 9 02:35;
# before that, 'unfilled' mostly means 'engine not deployed'
LIVE0 = 1783478100  # 2026-07-09 02:35
liverows = [r for r in pmrows if r["t0"] >= LIVE0]
out["fillsplit_pm_livewindow"] = fill_split(liverows, "up_pm", "PM res, t0>=Jul9 02:35")
out["fillsplit_pm_livewindow_pre_v3"] = fill_split(
    [r for r in liverows if r["t0"] < C.V3_CUT], "up_pm", "PM res, live window pre-v3")

# coverage bias check: PM-res availability by filled status
out["pmres_coverage"] = dict(
    filled=round(sum(1 for r in trigger_rows if r["filled"] and r["up_pm"] is not None) /
                 max(1, out["n_triggers_filled"]), 3),
    unfilled=round(sum(1 for r in trigger_rows if not r["filled"] and r["up_pm"] is not None) /
                   max(1, out["n_triggers"] - out["n_triggers_filled"]), 3))

# --- (b) cap-rejected misses
st = C.load_state()
miss = st["misses_btc"]
cap_missed = {}
for m in miss:
    if "Rev≤53c" in m["note"] or "Rev≤55c" in m["note"]:
        cap_missed.setdefault(m["t0"], m)      # dedupe by t0
rows = []
for t0, m in cap_missed.items():
    up = res.get(t0)
    if up is None:
        cd = cb.get(t0)
        if cd and abs((cd["c"]-cd["o"])/cd["o"]) >= 1e-4:
            up = 1 if cd["c"] >= cd["o"] else 0
    if up is not None:
        rows.append(dict(t0=t0, side=m["side"], up=up))
w = sum(1 for r in rows if (r["up"] == 1) == (r["side"] == "up"))
ph, l, h = C.wilson(w, len(rows))
out["cap_rejected_misses"] = dict(n_t0=len(cap_missed), n_resolved=len(rows), w=w,
                                  q=round(ph,4) if rows else None,
                                  ci=[round(l,4), round(h,4)] if rows else None,
                                  note="misses ring-buffer covers Jul10 16:40-Jul13 only")

# --- (c) measure book: sized vs f_nonpos skips
meas = st["measure"]
meas = [m for m in meas if m.get("win") is not None]
for grp, sel in (("sized", [m for m in meas if m["sized"]]),
                 ("skip_f_nonpos", [m for m in meas if m["skip"] == "f_nonpos"])):
    n = len(sel); w = sum(m["win"] for m in sel)
    ph, l, h = C.wilson(w, n)
    cost = sum(m["cost"] for m in sel) / n if n else None
    out[f"measure_{grp}"] = dict(n=n, w=w, q=round(ph,4) if n else None,
                                 ci=[round(l,4), round(h,4)] if n else None,
                                 mean_cost=round(cost,4) if cost else None)

json.dump(out, open("decensor.json","w"), indent=1)
print(json.dumps(out, indent=1))
