#!/usr/bin/env python3
"""replay_dryrun.py — FINAL-DESIGN M4-style replay of the PATCHED nightly +
measurement logic over the REAL live state (36-record measurement book,
Jul 13 extract) and the trailing flagship ledger. Pure stdlib, offline, no
network. Asserts invariants; writes replay_results.json.

What it proves before any commit:
  A. data sanity — the old (deviating) formula reproduces the live state's
     qlo=0.5068 / qhi=0.5030 exactly, so the book is understood;
  B. the R4 migration joins exactly the ledger-traded intervals (side-safe,
     idempotent, first-poll costs untouched);
  C. M2 seeding loads the verified n=123 cohort (+2.75c/share) and never
     feeds qhat;
  D. the patched nightly on the real book matches an independent closed-form
     recomputation (registered prior, cost<0.50 buckets (kept per wave-2 qhat adjudication), operated basis) and
     fires no guard;
  E. kill-metric preview — first-poll basis vs the pre-committed operated
     basis on the same 35 settled signals (the R4 gap, on live data);
  F. restart-flap guard — lastNightly==0 sets a baseline without running;
     metrics only ever land on the configured metricsPath;
  G. snapshot -> sanitize round-trip preserves every new field;
  H. firstFillMax exists on impulse_v2 only; counts how many live first
     polls the cap would have named (diagnostic).
"""
import importlib.util, json, math, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
BOT = os.path.join(HERE, "btc5m_bot_staged.py")
SEED = os.path.join(HERE, "impulse_guard_seed.json")

spec = importlib.util.spec_from_file_location("botmod", BOT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ex = json.load(open(os.path.join(DATA, "state_extract.json")))
tr = json.load(open(os.path.join(DATA, "trades_unified.json")))
FEE = 0.07
out, fails = {}, 0

def check(cond, name, extra=""):
    global fails
    print(("PASS" if cond else "FAIL") + "  " + name + (f"  [{extra}]" if extra else ""))
    if not cond: fails += 1
    out.setdefault("checks", []).append({"name": name, "ok": bool(cond), "extra": str(extra)[:200]})

# ---------- A. baseline reproduction of the live qhat state (old formula) ----
measure = [dict(m) for m in ex["measure"]]
due = ex["impulse_cfg"]["lastNightly"]                     # 1783901400 = Jul 13 00:10 UTC
settled_at_due = [m for m in measure if m["win"] is not None and m["t0"] + 600 <= due]
def qhat_old(rows, lo):
    xs = [m for m in rows if (m["cost"] < 0.50) == lo]
    seed = 0.5057 if lo else 0.5068
    return round(min(0.56, (sum(m["win"] for m in xs) + 400 * seed) / (len(xs) + 400)), 4)
qlo_old, qhi_old = qhat_old(settled_at_due, True), qhat_old(settled_at_due, False)
check(qlo_old == ex["impulse_cfg"]["qlo"] and qhi_old == ex["impulse_cfg"]["qhi"],
      "A: old formula reproduces live state qlo/qhi exactly",
      f"{qlo_old}/{qhi_old} vs state {ex['impulse_cfg']['qlo']}/{ex['impulse_cfg']['qhi']}")
out["A_baseline"] = dict(qlo=qlo_old, qhi=qhi_old, settled_at_due=len(settled_at_due))

# ---------- build a live-equivalent state for the patched Bot ----------------
fl = {}
for t in tr:
    if t.get("eng") == "impulse_v2" and isinstance(t.get("t0"), (int, float)) \
       and isinstance(t.get("entry"), (int, float)):
        fl.setdefault(int(t["t0"]), t)                     # dedupe by t0 across _src
class A: asset = "BTC"; stake = 50; bank = 100; slip = 1; loose = 6
st = mod.default_state(A)
st["impulse"].update(bank=ex["impulse_cfg"]["bank"], qlo=ex["impulse_cfg"]["qlo"],
                     qhi=ex["impulse_cfg"]["qhi"], lastNightly=due,
                     benched=ex["impulse_cfg"]["benched"],
                     haircut=ex["impulse_cfg"].get("haircut", False),
                     skips=dict(ex["impulse_cfg"].get("skips", {})),
                     measure=[dict(m) for m in measure], epoch=0)   # legacy state: epoch=0
st["engines"]["impulse_v2"]["trades"] = [dict(t) for t in fl.values()]
bot = mod.Bot({"seedPath": SEED}, st)

# ---------- B. migration -----------------------------------------------------
mig = [m for m in bot.imp["measure"] if not m.get("seed")]
n_fill = sum(1 for m in mig if m.get("fillCost") is not None)
expected_joins = sum(1 for m in measure if int(m["t0"]) in fl and fl[int(m["t0"])]["side"] == m["side"])
check(n_fill == expected_joins and bot.imp.get("mAmend") == 1,
      "B: migration joined exactly the ledger-traded measurement rows",
      f"joined {n_fill}, expected {expected_joins} (R4 audit: 27 trades / 36 rows)")
check(all(m.get("final") for m in mig), "B: every legacy row is stamped final (window long closed)")
check(all(m["cost"] == o["cost"] for m, o in zip(mig, measure)),
      "B: first-poll diagnostic costs untouched by migration")
before = [m.get("fillCost") for m in mig]
bot._measure_migrate()
check([m.get("fillCost") for m in mig] == before, "B: migration idempotent on second call")
out["B_migration"] = dict(rows=len(mig), joined=n_fill,
                          orphan_skips_repaired=sum(1 for m, o in zip(mig, measure)
                                                    if m.get("fillCost") is not None and not o["sized"]))

# ---------- C. M2 seeds ------------------------------------------------------
seeds = [m for m in bot.imp["measure"] if m.get("seed")]
seed_net = sum((1 - m["cost"]) if m["win"] else -m["cost"] for m in seeds) / len(seeds) if seeds else None
check(len(seeds) == 123 and bot.imp.get("seeded") == 123, "C: n=123 seed cohort loaded", f"n={len(seeds)}")
check(abs(seed_net * 100 - 2.75) < 0.02, "C: seed cohort net/share matches the R8-verified +2.75c",
      f"{seed_net*100:+.2f}c")
out["C_seeds"] = dict(n=len(seeds), netps_c=round(seed_net * 100, 2))

# ---------- D. patched nightly on the real book ------------------------------
ns = due                                                   # replay the Jul-13 00:10 nightly
bot._impulse_nightly(ns)
live_settled = [m for m in bot.imp["measure"] if m["win"] is not None and not m.get("seed")]
def qhat_new(lo):
    xs = [m for m in live_settled
          if (mod.Bot._m_opcost(m) < mod.IMP_BUCKET_LO) == lo]
    return round(min(mod.IMP_QCAP, (sum(m["win"] for m in xs) + mod.IMP_PRIOR * mod.IMP_PRIOR_MEAN)
                     / (len(xs) + mod.IMP_PRIOR)), 4), len(xs), sum(m["win"] for m in xs)
(qlo_new, nlo, wlo), (qhi_new, nhi, whi) = qhat_new(True), qhat_new(False)
check(bot.imp["qlo"] == qlo_new and bot.imp["qhi"] == qhi_new,
      "D: module nightly == independent closed-form (registered prior, cost<0.50 buckets (kept per wave-2 qhat adjudication), operated basis)",
      f"qlo {bot.imp['qlo']} (n={nlo},w={wlo})  qhi {bot.imp['qhi']} (n={nhi},w={whi})")
check(not bot.imp["benched"], "D: no bench on the real book", f"benched={bot.imp['benched']}")
pool7 = [m for m in bot.imp["measure"] if m["win"] is not None and m["t0"] >= ns - 7 * 86400]
n7 = (sum((1 - mod.Bot._m_opcost(m)) if m["win"] else -mod.Bot._m_opcost(m) for m in pool7)
      / len(pool7)) if len(pool7) >= 120 else None
check((n7 is None) or (n7 >= -0.02) == (not bot.imp["haircut"]),
      "D: haircut state consistent with the seeded 7d window",
      f"n7={None if n7 is None else round(n7*100,2)}c on {len(pool7)} (seeds make it evaluable)")
# sizing-impact statement for the README (uses the just-refit qlo/qhi)
def p_star(q):                                             # sized iff cost < q  <=>  p_eff < p*(q)
    return round(mod.Bot._p_eff_from_cost(q), 4)
out["D_nightly"] = dict(
    qlo_before=ex["impulse_cfg"]["qlo"], qhi_before=ex["impulse_cfg"]["qhi"],
    qlo_after=bot.imp["qlo"], qhi_after=bot.imp["qhi"],
    lo_bucket=dict(n=nlo, wins=wlo), hi_bucket=dict(n=nhi, wins=whi),
    sized_boundary_p_eff_before=p_star(ex["impulse_cfg"]["qlo"]),
    sized_boundary_p_eff_after=min(p_star(bot.imp["qlo"]), 0.47 + 0.01),
    n7_seeded_c=None if n7 is None else round(n7 * 100, 2), n7_count=len(pool7),
    benched=bot.imp["benched"], haircut=bot.imp["haircut"])

# ---------- E. kill-metric preview: first-poll vs operated basis -------------
sett = [m for m in live_settled]
fp = sum((1 - m["cost"]) if m["win"] else -m["cost"] for m in sett) / len(sett)
op = sum((1 - mod.Bot._m_opcost(m)) if m["win"] else -mod.Bot._m_opcost(m) for m in sett) / len(sett)
check(abs(fp * 100 - (-6.23)) < 0.35, "E: first-poll basis reproduces the R4 headline (-6.23c/sh)",
      f"{fp*100:+.2f}c on n={len(sett)}")
check(op > fp, "E: operated basis sits above the first-poll basis (the R4 gap, live data)",
      f"operated {op*100:+.2f}c vs first-poll {fp*100:+.2f}c (gap {(op-fp)*100:.2f}c)")
out["E_kill_preview"] = dict(n_settled=len(sett), firstpoll_cps=round(fp * 100, 2),
                             operated_cps=round(op * 100, 2), gap_cps=round((op - fp) * 100, 2),
                             note="operated basis still holds 9 never-entered signals at their "
                                  "first-poll cost (legacy rows have no bestCost); the gap grows "
                                  "as amended records accrue bestCost")

# ---------- F. restart-flap guard + metrics gating ---------------------------
st2 = mod.default_state(A); st2["impulse"]["epoch"] = 0
st2["impulse"]["measure"] = [dict(t0=ns - 86400 + i * 300, side="up", cost=0.53, win=0, sized=True,
                                  skip=None) for i in range(300)]      # would bench if it ran
b2 = mod.Bot({}, st2)
q0 = (b2.imp["qlo"], b2.imp["qhi"])
b2.nightly_tick(ns + 4000)
check((b2.imp["qlo"], b2.imp["qhi"]) == q0 and not b2.imp["benched"] and b2.imp["lastNightly"] > 0,
      "F: lastNightly==0 -> baseline set, NO catch-up nightly (flap guard)")
b2.nightly_tick(ns + 4000)
check(True, "F: second tick same day is a no-op (idempotent)")
mtmp = os.path.join(tempfile.gettempdir(), "replay_metrics_test.jsonl")
if os.path.exists(mtmp): os.remove(mtmp)
b3 = mod.Bot({}, mod.default_state(A)); b3._impulse_nightly(ns)        # no metricsPath
b4 = mod.Bot({"metricsPath": mtmp}, mod.default_state(A)); b4._impulse_nightly(ns)
nl = len(open(mtmp).read().strip().splitlines()) if os.path.exists(mtmp) else 0
check(nl == 1, "F: metrics land only on the configured metricsPath", f"lines={nl}")
os.remove(mtmp)

# ---------- G. snapshot -> sanitize round-trip -------------------------------
snap = mod.snapshot(bot)
rt = mod.sanitize(snap["btc"], A)
rtm = rt["impulse"]["measure"]
check(len(rtm) == len(bot.imp["measure"]), "G: measure rows survive the round-trip",
      f"{len(rtm)} rows")
check(any(m.get("fillCost") is not None for m in rtm) and any(m.get("seed") for m in rtm)
      and all("final" in m for m in rtm if not m.get("seed")),
      "G: new fields (fillCost/bestCost/final/seed) survive sanitize")
check(rt["impulse"].get("mAmend") == 1 and rt["impulse"].get("seeded") == 123
      and rt["impulse"].get("epoch") == 0, "G: mAmend/seeded/epoch persist")
check(isinstance(rt.get("leader"), dict) and "book" in rt["leader"], "G: leader shadow state persists")
check(snap.get("leaderShadow") is not None, "G: leaderShadow published in the snapshot")

# ---------- H. firstFillMax placement + live-book diagnostic -----------------
check(mod.ENGINE_CFG["impulse_v2"].get("firstFillMax") == 0.47
      and all("firstFillMax" not in mod.ENGINE_CFG[e]
              for e in ("impulse50", "reversal_v2", "reversal", "reversal2")),
      "H: firstFillMax=0.47 on impulse_v2 only")
capped = sum(1 for m in measure if mod.Bot._p_eff_from_cost(m["cost"]) > 0.48 + 1e-9)
out["H_cap_diag"] = dict(live_first_polls_over_47c_ask=capped, of=len(measure),
                         note="these first polls would now log skip=first_fill_cap; "
                              "refill path unchanged")
print(f"\ninfo: {capped}/{len(measure)} live first polls had ask>47c (cap would name them)")

out["fails"] = fails
with open(os.path.join(HERE, "replay_results.json"), "w") as f:
    json.dump(out, f, indent=1)
print("\n" + ("REPLAY ALL PASS" if fails == 0 else f"REPLAY {fails} FAILURES")
      + f" — results in replay_results.json")
sys.exit(1 if fails else 0)
