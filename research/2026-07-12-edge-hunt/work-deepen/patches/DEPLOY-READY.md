# DEPLOY-READY — staged wave-2 patch set (2026-07-13)

**Status: verified, staged, NOT deployed. Deploy requires the owner's explicit OK.**

## What is staged

`btc5m_bot_staged.py` = `btc5m_bot_patched.py` (P1–P5, see README.md) **with the
synthesis-adjudicated P2 modification applied**: the qhat bucket boundary is KEPT at
`cost < 0.50` (dated deviation from FINAL-DESIGN §4.2's `p_eff < 0.50`, per
`IMPULSE-DEEP.md` §1/§3 — the qhat unit's both-lens-confirmed `hybrid_cost_M200`
config). All other P2 components (prior 200 @ mean 0.5, M2 seeding, single haircut
tier + hysteresis) are as shipped. Three boundary selftests reworked, two added.

## Verification evidence (this exact staged file)

- `python3 btc5m_bot_staged.py --selftest` → **105/105 PASS** (baseline was 62; the
  patch set added 41; the P2a rework net +2).
- `python3 replay_dryrun_staged.py` → **REPLAY ALL PASS** (22 checks over the REAL
  live 36-record measurement book + flagship ledger + seed cohort):
  - R4 migration joins exactly 27/36 rows, idempotent, first-poll costs untouched
  - M2 seed cohort n=123 @ +2.75c/share loads once, never feeds qhat
  - New nightly on the real book: qlo 0.4956 / qhi 0.4928 (operated basis,
    cost<0.50 buckets, prior 200) — no bench, no haircut (seeded n7 = +1.61c on 158)
  - Kill-basis preview: first-poll −6.23c/sh vs operated −2.40c/sh (the R4 gap, live)
  - Restart-flap guard: no catch-up nightly, metrics only on metricsPath
  - firstFillMax=0.47 present on impulse_v2 ONLY (controls asserted untouched)

## Deploy procedure (owner)

```bash
cd ~/btc5m-paper-trader/bot
launchctl unload ~/Library/LaunchAgents/com.btc5m.paper.plist
cp btc5m_bot.py btc5m_bot.py.bak-prewave2 && cp state.json state.json.bak-prewave2
cp ../research/2026-07-12-edge-hunt/work-deepen/patches/btc5m_bot_staged.py btc5m_bot.py
cp ../research/2026-07-12-edge-hunt/work-deepen/patches/impulse_guard_seed.json .
launchctl load ~/Library/LaunchAgents/com.btc5m.paper.plist
tail -f bot.log   # expect: gate warmed · "measurement book amended (R4): 27 legacy rows joined"
                  #         · "guard windows seeded (M2 §5.3): 123 pre-launch rows"
```

Rollback: reverse the two `cp`s from the `.bak-prewave2` files and reload the agent.

## Pre-commitment recorded (R4, before day 14)

The day-14 Phase-1 kill, the §5.2 guard windows, and the nightly qhat read the
**operated basis** (`opCost = fillCost` if filled else `bestCost`; legacy rows fall
back to first-poll cost); seed rows are excluded from kill and qhat. The first-poll
`cost` series is diagnostic only. Also recorded: **ML-PLAN Phase 1 pre-registered
STOP** — the 8-feature meta-model FAILED its OOS Brier/log-loss bar vs bucketed qhat
(`work-deepen/metamodel/results.json`); re-run only after ~400–600 settled AMENDED
measurement records, pre-registered then.
