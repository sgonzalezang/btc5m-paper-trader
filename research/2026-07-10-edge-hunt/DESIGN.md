# BEST MODEL v2 — DESIGN (rev 2, post 3-lens verification round)
Model Architect deliverable · 2026-07-10 · supersedes `DESIGN.md` rev 1 (07:30) and `FINAL-DESIGN.md` v2.1 (07:48)
Scope: paper-trading redesign of ~/btc5m-paper-trader (Polymarket BTC "Up or Down" 5-minute binaries).
Cost model (exact, frozen): `EV/share = q − p − 0.07·p·(1−p)`; gas $0.004/trade; fills = ask + 1c slip.
Break-evens: q*(0.4724)=0.4898 · q*(0.4861)=0.5036 · q*(0.51)=0.5275 · q*(0.53)=0.5474 · q*(0.55)=0.5673.

## What changed since v2.1 (and why this rev exists)

The earlier drafts were written while only the microstructure fill model had cleared 3-lens adversarial
verification. The verification round has since completed: **four findings now carry `survives: true`** —
fill model (3–0), regime "isolated impulse" gate (3–0), sizing/Kelly (2–1), reversal60 best-spec (2–1).
Consequences, in evidence order:

| # | v2.1 position | rev 2 position | Trigger |
|---|---|---|---|
| 1 | Ungated `reversal_v2` was flagship; gated arm shadow-only ("gate did not survive verification") | **Gated impulse engine is the flagship and only live arm**; ungated becomes the zero-stake control | Regime finding survived 3–0: walk-forward pooled OOS +2.97c/share (n=1,468), TEST +4.02c (p=0.015), gate beats ungated 5/5 OOS folds and 9/9 weeks, live gated subset +7.53c/share (n=71) vs ungated −2.79c (n=66) |
| 2 | Gate meant eff12 ≤ 0.48 (old latentfire) | Gate is **eff6 ≥ A AND cnt12 ≤ B** (deploy A=0.10, B=6); eff12≤0.48 stays on the DEAD list | Regime family: old gate is "dead weight over 60d" (+0.22c OOS vs +2.97c); new gate verified |
| 3 | Kelly design point treated as unverified | Quarter-Kelly fraction-of-bank sizing is CONFIRMED (2–1); the refuted vote attacks the (q=.56,p=.51) design point, not the ordering — every verifier agrees quarter-Kelly dominates flat $50 on risk | Sizing finding survived |
| 4 | 53c cap justified by arithmetic alone | 53c cap is part of the CONFIRMED reversal60 spec (2–1), with the cap-adverse-selection caveat pre-registered as a measured output (§6) | Reversal60 survived; both refuted votes across families flag price-informativeness |

Everything that was fixed in the v2.1 red-team pass and is orthogonal to the flagship question is
**carried forward unchanged**: the corrected qhat estimator, the measurement-book split, fee/metadata
asserts, settlement-lag handling, one-sided-book re-polling, resolution-outage rule, and the corrected
caps citation (artifacts in `work/final-design/`).

---

## 0. Evidence classes (every design choice carries a tag)

| Tag | Meaning | Allowed to buy complexity? |
|---|---|---|
| **[CONFIRMED]** | Survived 3-lens adversarial verification (4 exist: fill model, impulse gate, Kelly sizing, reversal60 spec) | Yes |
| **[PRIOR]** | Brief's validated priors (10d reversal edge, momentum fee-death, stop-neutrality, Coinbase proxy, same-feed ratios) | Yes |
| **[CANDIDATE]** | Single-source, plausible, NOT verified (e.g. the 10-day recalibration plumbing spec, rev20 gradient) | Shadow mode only |
| **[DEAD]** | Explicitly rejected/dead-end in the 60d round | Must NOT appear in the live path |

The four CONFIRMED findings, with the verifier-amended numbers this design actually uses:

1. **Fill/cost model** (3–0). 55c-capped ledger fills (n=155): p25 .47 / p50 .51 / p75 .53 / p90 .55,
   share-wtd mean **.4861** → hurdle .5036. Censored to the new 53c cap (n=123): p25 .45 / p50 .49 /
   p75 .51, share-wtd **.4724** → hurdle **.4898**. Availability: ~55% of signals fillable at ≤53c
   effective (pm-sample 27/49; 43.6% of gated triggers price >53c mid) — **unfillable signals are SKIPS,
   never 50c fills**. Winners enter fast (entrySec p50=9s, p95=37s); by ~60s the contrarian mid disperses
   violently (p25 .295 / p75 .605) — late entries inherit adverse selection. Verifier amendments honored:
   fast-entry bonus is 0 to −2c, not −2.9c; the prior-move size gradient is NOT parameterized (reverses
   across thirds); independent n is ~70 intervals, so implied CIs are ~1.5× too tight; everything rests
   on a 3-day pm window. `work/microstructure/fill_dist.json`.
2. **Isolated-impulse gate** (3–0). Fade the 12bps move only when `eff6 ≥ A AND cnt12 ≤ B` (trailing
   30 min efficient, prior hour had ≤B other 12bps events). Walk-forward pooled OOS +2.97c/share
   (n=1,468, retention .406, worst fold −3.33c); TEST +4.02c, wr .5676 (n=717, p=0.0147); TRAIN gated
   +3.20c where ungated TRAIN was −0.61c; TEST sensitivity surface is a plateau (min +2.0c over
   A∈[0.06,0.38] × B∈[1,7]). Verifier amendments honored: the +4.02c headline leans on an unconditional
   fill stat — honest central deployable estimate is **+1.5 to +3c/share** (conditional mids ~52.4c,
   decomposed EV +1.6c at mid+1c, SE 1.9c); worst-case capped-on-mids construction is ~0 to −1.6c;
   selection-corrected gate-increment p is ~0.01–0.03, borderline not overwhelming; calm-tercile gate
   effect is ~zero (the gate's value concentrates in trending regimes where ungated loses). Live
   corroboration at real CLOB asks: gated +7.53c/share (n=71, wr .577, mean entry .50).
   `work/regime/deploy_spec.json`, `work/verify-regime/verify_summary.json`.
3. **Kelly sizing** (2–1). Fee-adjusted full Kelly f*=6.88% at (q=.56, p=.51); flat $50 on a $1k bank
   ≈ 0.73× full Kelly — verified too hot (full-Kelly median terminal $1 under the TRAIN regime).
   Quarter-Kelly dominates flat on every risk metric (median DD 27.8% vs 40.9%, P(bank<$500) 0.1% vs
   4.1%) and beat flat on max-DD in 9/9 weekly folds. The refuted vote correctly shows the (q,p) design
   point is not attainable at honest fills — which strengthens, not weakens, the "size small, tie stake
   to a shrunk q estimate" recommendation the design adopts. `work/sizing/kelly_table.json`,
   `kelly_sim_results.json`.
4. **Reversal60 best spec** (2–1). Fixed 12bps buffered contrarian, hold-to-close, effective cost ≤ .53,
   no threshold adaptation, no timed exits. TEST +2.64c/share at 51c (n=1,374); full-span walk-forward
   ≈ breakeven; **TRAIN fails the fee hurdle** — the always-on rule is regime-conditional and must be
   paired with the (now-verified) gate rather than run at stake. The refuted vote's cap-adverse-selection
   evidence (cap-conditional pm fills won 45.5% while skipped expensive signals won 59.3%, small n) is
   pre-registered as a §6 measured output. `work/reversal60/best_spec.json`.

Honest status of the edge: the gated arm is the only construction that is positive on TRAIN, TEST,
pooled walk-forward OOS, and the live book simultaneously. Its honest central estimate is +1.5–3c/share
with a worst-case fill construction near zero. The design stakes it at quarter-Kelly and pre-registers
the kill thresholds (§6) instead of assuming the point estimate.

---

## 1. Engine roster (keep / kill / modify — all 9)

| Engine | Verdict | Evidence (one line) |
|---|---|---|
| **loose** | **KILL (terminal)** | Momentum is fee-dead [PRIOR#3]; live −$2,922/600; ledger autopsy: zero fees would NOT rescue it (−$3.2k of −$6.1k remains) [DEAD: microstructure]. |
| **floor** | **KILL (terminal)** | Same momentum family at 62–65c entries vs ~64.6% gross continuation → net ~0 before adverse selection; live −$1,623/531 [PRIOR#3]. |
| **band** | **KILL (terminal)** | Drift-band adds no stable structure (path-shape and seasonality families fully null); live −$1,826/504 [DEAD]. |
| **strict** | **KILL (terminal)** | n=2 fills in 3 days, momentum lineage, measures nothing; dead weight in every loop metric. |
| **value** | **KILL (terminal)** | Book is at least as informed as the FV model; "cheap vs model" = winner's curse ~5pts; entry caps made the ledger WORSE; live −$1,965/452 [DEAD: fairvalue]. |
| **fade** | **KILL (terminal)** | Contrarian mirror of loose pays double vig [PRIOR#3]; live −$1,291/480 [DEAD]. |
| **reversal** | **MODIFY → `reversal_v2` (zero-stake control)** | Spec CONFIRMED (12bps, hold-to-close, cap 53c) but TRAIN fails fees and live ungated subset ran −2.79c/share (n=66) — always-on gets no stake; it is the paired control that measures the gate increment [CONFIRMED#4 + #2]. |
| **reversal2** | **KILL (terminal)** | Gamma fallback fired 0/67 live; entries a strict subset of reversal; the fallback fill is a fiction the CONFIRMED fill model does not license [DEAD: microstructure]. |
| **latentfire** | **MODIFY → `impulse_v2` (FLAGSHIP, only live arm)** | Gate REPLACED: eff12≤0.48 is dead weight over 60d (+0.22c OOS) [DEAD: regime]; the verified isolated-impulse gate (eff6 ≥ 0.10 AND cnt12 ≤ 6) is +2.97c pooled OOS / +7.53c live gated [CONFIRMED#2]. revLoose removed. |

Shadow roster (paper books, $0 stake, same eval path — paper fills are stake-independent, so every
shadow yields exactly the ledger a live arm would have; **no engine goes live to measure what a shadow
can measure**):

- `reversal_v2` — ungated control on the identical signal stream; the day-60 gate verdict is its paired
  delta vs the flagship.
- `measure_book` — records the would-be fill for EVERY cap-compliant gated signal regardless of `f_full`
  or bank state; it is the edge-measurement instrument and qhat's data source (§4).
- `frozen_baseline` — flagship with qhat pinned at its launch value forever; measures whether adaptive
  sizing pays (§3.5).
- `gate_train_shadow` — flagship with the TRAIN-calibrated gate (A=0.32, B=6) frozen; measures whether
  the 10-day trailing recalibration (which chose A=0.10) actually pays [CANDIDATE plumbing audit].
- `cap55_shadow` — flagship with revEntryMax=0.55; settles the cap-adverse-selection question raised by
  both refuted votes with real paired books.
- `rev20_shadow` — 20bps trigger [CANDIDATE]: TEST q=.5648 but TRAIN inverts; never sized until §3
  promotion criteria pass.

Excluded machinery (so nobody re-adds it): session/hour/weekday filters, vol-scaled triggers, path-shape
features, ETH/basis/funding cross-asset signals, FV-vs-book value entries, stop-losses, hedges, timed
exits, tie-rule Up bias, favorite-longshot plays, late (>60s) entries, daily loss/trade caps,
Thompson/Hedge allocation, eff12/eff24/volratio/ATR/range-compression/time-since-event gates — every one
is on a family's [DEAD] list with TEST-side sign flips or fee-death.

---

## 2. Flagship spec — `impulse_v2`

### 2.1 Parameters (ENGINE_CFG entry)

| Param | Value | Status | Why |
|---|---|---|---|
| `revThr` | 0.12 (% of open; buffered open-to-open, Coinbase 5m, contiguous prior candle) | **FROZEN** | Fixed 12bps beats every trailing re-selection tried (walk-forward −0.44c vs +0.17c/share); 8bps fee-dead, 20/25bps TRAIN-inverted [CONFIRMED#4 + DEAD lists]. |
| side | contrarian (opposite the prior move; ties resolve Up) | **FROZEN** | [PRIOR#1]; sign memory is strictly one lag deep [DEAD: pathshape]. |
| `gateForm` | `eff6 >= gateA AND cnt12 <= gateB` | **FROZEN (form)** | [CONFIRMED#2]. eff6 = \|o[i]−o[i−6]\| / Σ\|o[j+1]−o[j]\| over the 6 open-to-open moves ending at the trigger; cnt12 = count of \|move\| ≥ 12bps among the 12 moves in the hour BEFORE the trigger (trigger excluded). Both known at t0. |
| `gateA` / `gateB` | **0.10 / 6** at launch | **REFIT (loop-managed §3)**, bounds A∈[0.06,0.38], B∈[1,7] | Deploy-calibrated trailing-20d as of 2026-07-10 (`deploy_spec.json`); bounds = the verified TEST plateau (every cell ≥ +2.0c). |
| `revEntryMax` | **0.53** (effective cost ask+slip ≤ 0.53) | **FROZEN** | [CONFIRMED#4] + arithmetic: q*(0.53)=.5474 is the last cap any measured q plausibly clears; kelly_table shows p=.55 fills −0.7c/share even at q=.56. Cap-adverse-selection risk is a §6 measured output, and `cap55_shadow` runs the counterfactual. |
| `revWinMin` | **255** (enter only in the first 45s) | **FROZEN** | [CONFIRMED#1]: winners entrySec p50=9s/p95=37s; contrarian mid disperses violently by ~60s; late entries are a [DEAD] list item. |
| exit | hold to resolution; no stop, no hedge, no timed exit | **FROZEN** | [PRIOR#4] + exits family: every overlay sign-flips TRAIN→TEST; hedge ≡ sell-out minus a second fee [DEAD]. |
| `slip` | 1c | **FROZEN** | Brief cost model; live spread p50 1c / p95 2c (n=1,482 signal quotes). |
| book | real CLOB ask only (no gamma), top ≥ $200, spread ≤ 0.02; one-sided book → re-poll inside the window, final skip only at window close | **FROZEN** | Gamma fired 0/67 [DEAD]; spread p95 2c [CONFIRMED#1]. |
| feed | Coinbase-only trigger; contiguous prior 5m candle required | **FROZEN** | Proxy 97.7% validated; same-feed ratios [PRIOR#5]; buffered construction is the methodology bar. |

`reversal_v2` (shadow control) = identical with the gate disabled. `cap55_shadow` = identical with
revEntryMax 0.55. State requirement: the bot persists `ivlHist` (bot:358/936/1020, last 20 kept); the
gate needs the last **14 five-minute opens** (13 completed moves) — extend the persisted window to 20
opens and compute eff6/cnt12 from opens exactly as the research code, not from summed returns. Cold
start / gap: rebuild from Coinbase 5m REST (deterministic public data) before the engine un-latches.

### 2.2 Eval pseudocode (style of `_reversal_eval`, bot/btc5m_bot.py:490)

```python
def _impulse_v2_eval(self, now, eid):
    cfg, prof, m, f = ENGINE_CFG[eid], self.prof(), self.mkt, self.feed
    lp  = self.loop_params(eid)              # {'qhat': .., 'gateA': .., 'gateB': ..}; all else stays in cfg
    ns  = now // 1000
    left = (m["t1"] - ns) if m else None
    pv  = self.prev_ivl                      # completed interval, Coinbase open-to-open (buffered)
    contiguous = bool(pv and m and pv.get("t0") == m["t0"] - IVL and pv.get("ret") is not None)
    prior_move = abs(pv["ret"]) * 100 if (pv and pv.get("ret") is not None) else None
    signal   = bool(contiguous and prior_move is not None and prior_move >= cfg["revThr"])   # 0.12 FROZEN
    rev_side = ("down" if pv["ret"] > 0 else "up") if signal else None
    # ---- isolated-impulse gate [CONFIRMED]: needs 14 persisted opens; latent without them
    gate_ok, eff6, cnt12 = False, None, None
    o = self.open_hist                       # last >=14 5m opens incl. current interval's open, contiguous
    if signal and len(o) >= 14 and self.opens_contiguous(o[-14:]):
        legs  = [o[k+1] - o[k] for k in range(len(o)-7, len(o)-1)]          # 6 moves ending at trigger
        denom = sum(abs(x) for x in legs)
        eff6  = (abs(o[-1] - o[-7]) / denom) if denom > 0 else 1.0
        cnt12 = sum(1 for k in range(len(o)-14, len(o)-2)
                    if abs(o[k+1] - o[k]) / o[k] >= 0.0012)                  # 12 moves BEFORE trigger
        gate_ok = (eff6 >= lp["gateA"]) and (cnt12 <= lp["gateB"])           # launch 0.10 / 6
    q = self.quote(rev_side) if rev_side else None            # REAL book only — no gamma fallback
    real_book = bool(q and q.get("src") != "gamma" and q.get("ask") is not None)
    # one-sided/absent book near the open is TRANSIENT — re-poll; skip is FINAL only at window close
    if signal and gate_ok and not real_book and left is not None and left >= cfg["revWinMin"]:
        return self._pending(eid, m["t0"], reason="one_sided_book")
    spread = (q["ask"] - q["bid"]) if (real_book and q.get("bid") is not None) else None
    slip   = 0.01
    early     = left is not None and left >= cfg["revWinMin"]                     # 255 → first 45s
    priced_ok = bool(real_book and q["ask"] + slip <= cfg["revEntryMax"] + 1e-9)  # 0.53 FROZEN
    spread_ok = spread is not None and spread <= 0.02 + 1e-9
    fresh     = bool(q and (now - q["at"]) <= prof["freshMs"]
                     and f["at"] and (now - f["at"]) <= prof["feedFreshMs"] and f["src"] == "Coinbase")
    depth_ok  = bool(real_book and q.get("top") is not None and q["top"] >= 200)
    opent, dup = self.open_trade(eid), (self.trade_for(eid, m["t0"]) if m else None)
    fam_open  = self.family_stake_this_interval(m["t0"]) if m else 0.0
    risk_ok   = ((not dup) and self.st["bank"] >= 250
                 and fam_open < 0.05 * self.st["bank"] - 1e-9)
    blocked_open = bool(opent)               # settlement lag → its own skip reason
    fillable = bool(m and m["ev"] and not m["evClosed"] and signal and gate_ok and early
                    and priced_ok and spread_ok and fresh and depth_ok)
    # ---- measurement book: record EVERY cap-compliant gated would-be fill, stake-independent (§4)
    if fillable:
        self.measure_book.record(m["t0"], rev_side, cost=q["ask"] + slip, eff6=eff6, cnt12=cnt12)
    # ---- sizing (§4): quarter-Kelly on shrunk qhat at ACTUAL total cost; f_full <= 0 is a SKIP
    cost   = (q["ask"] + slip + 0.07 * (q["ask"] + slip) * (1 - q["ask"] - slip)) if fillable else None
    f_full = (lp["qhat"] - (1 - lp["qhat"]) * cost / (1 - cost)) if fillable else None
    sized  = bool(fillable and risk_ok and not blocked_open and f_full is not None and f_full > 0
                  and not self.guard_benched())               # §5 tier-3 bench
    stake  = min(0.25 * f_full * self.st["bank"], 0.05 * self.st["bank"]) if sized else 0.0
    if signal and not sized:                                  # a skip is a decision — log WHY
        self.log_skip(eid, m["t0"], dict(gate_ok=gate_ok, eff6=eff6, cnt12=cnt12,
                       priced_ok=priced_ok, early=early, spread_ok=spread_ok, fresh=fresh,
                       depth_ok=depth_ok, risk_ok=risk_ok, missed_open_trade=blocked_open,
                       f_nonpos=(f_full is not None and f_full <= 0),
                       benched=self.guard_benched(), ask=q and q.get("ask")))
    ev = dict(t=now, side=rev_side, q=q, spread=spread, left=left, priorMove=prior_move,
              eff6=eff6, cnt12=cnt12, stake=stake, enter=sized)
    self.eng[eid]["eval"] = ev
    return ev
```

### 2.3 Expected net edge per trade (uncertainty from the verified numbers only)

At the 53c-cap fill mix (share-wtd .4724) the hurdle is q\*=.4898; at the old 55c mix (.4861) it is .5036.

| Scenario | Source | EV/share | $/trade at $50 stake (~100 sh) |
|---|---|---|---|
| Honest central (conditional mids +1c, TEST wr .5676) | verify-regime decomposition | **+1.6c** (SE 1.9c) | ≈ +$1.6 |
| Backtest at 51c fills, TEST | CONFIRMED#2 headline | +4.0c (boot p=0.015) | ≈ +$4.0 |
| Walk-forward pooled OOS at 51c | CONFIRMED#2 | +3.0c (worst fold −3.3c) | ≈ +$3.0 |
| Live gated subset, real CLOB asks | n=71, wr .577, mean entry .50 | +7.5c (small n) | ≈ +$7.5 |
| Worst-case: cap adverse-selection on mids | verify-regime / verify-reversal60 | ~0 to −1.6c | ≈ $0 to −$1.6 |
| Regime death (live last-third, n=50, CI .12–.62) | CONFIRMED#1 caveat | −12c class | the reason §5–§6 exist |

**Headline: +1.5 to +3c/share central estimate (≈ +$1.5–3 per $50 trade), with a worst-case fill
construction near zero and an unresolved regime-death tail.** Anything stronger exceeds the evidence.
Cadence: ~66 triggers/day × gate retention ~0.55 (deploy calibration ⇒ ~37 gated/day) × availability
~0.55 at the 53c cap ⇒ **~20 measurement-book fills/day**; the sized book starts at ~43–45% of that
(§4) and grows as qhat clears successive cost levels.

---

## 3. Perpetual learning loop (nightly job; rate-limited promotion)

The loop runs **nightly at 00:10 UTC** on the paper ledger + fresh Coinbase candles + Polymarket
resolutions. Nightly it does metrics, integrity asserts, qhat, and shadow bookkeeping. **Structural
parameter changes go live only at 10-day review points** — the regime family's own evidence shows
5-day refits are thrash (W20/R5 +3.15c vs W20/R10 +4.56c) and the recalibration plumbing is
single-source [CANDIDATE], so it is deliberately slow and capped. "No change" is the expected modal
outcome; that is the design working.

### 3.1 What refits vs what is FROZEN

| Class | Items | Cadence | Rule |
|---|---|---|---|
| **FROZEN** (loop may never touch; human + new verified research only) | revThr=0.12; contrarian side; hold-to-close; revEntryMax=0.53; revWinMin=255; slip=1c; fee model; gate FORM; book rules; Coinbase-only buffered signal | never | Each is verified-worse when adapted (threshold walk-forward, timed exits) or pure arithmetic (cap, fees). |
| **REFIT — gate constants** | `gateA`, `gateB` on the flagship | every **10 days**, walk-forward | Objective: net/share of gated trades over the trailing **20d** at CONFIRMED fill quantiles with >cap = skip. Min sample: **≥250 trigger signals** in window (~4d at ~66/day; else no refit). Step caps: **\|ΔA\| ≤ 0.10, \|ΔB\| ≤ 1** per refit. Hard bounds: **A∈[0.06,0.38], B∈[1,7]** (the verified TEST plateau — the loop may not leave the region where every cell was ≥ +2.0c). Plumbing per `deploy_spec.json` recalibration block [CANDIDATE — acceptable: it is rate-limiting machinery, not an edge claim, and `gate_train_shadow` audits whether it pays]. |
| **REFIT — sizing scalar** | `qhat` | nightly | `qhat = (wins + 200)/(n + 400)` (shrinkage prior: n0=400 at mean 0.5), over trailing 30d **measurement-book** settled fills, Polymarket resolutions only, hard cap 0.56. Verified anchor points: .500/.504/.510 at n=0/100/400 with 52% wins. Sizing-only — cannot change what trades, only how big. Launch seed from the gated pre-launch ledger: `(41+200)/(71+400) = .5117`. Skipped entirely on resolution outage (§3.4). |
| **Shadow params** | `cap55_shadow`, `rev20_shadow`, displaced parameterizations | every 10 days | Shadow-only; no step caps (zero-stake books cannot lose money); bounds as tagged per shadow. |
| **LIFECYCLE** | retirement / revival / promotion | 10-day review points | §3.3. |

### 3.2 Shadow evaluation before promotion (no parameter goes live raw)

A refit that wants to move a live parameter first updates a **shadow book** carrying the proposed value
on the same signal stream. Promotion to live requires ALL of, on the **common signal set** vs the
incumbent:

- shadow age ≥ 10 days AND ≥ **400 paired signals** evaluated;
- paired (shadow − incumbent) net/share: 1h-block-bootstrap **90% CI lower bound > 0**;
- shadow net/share > 0 in absolute terms;
- [CANDIDATE]-class engines/params additionally require human sign-off and enter at **half stake**.

Per-share settled-outcome SD is ~50c, so at 400 paired fills the paired-delta SE is ~2.5c — most
windows will and should resolve to "no change". Max **one promotion per engine per 30 days**. After a
promotion the displaced parameterization keeps running as a shadow for 20 days; **auto-rollback** if
the same paired-CI condition favors it. Exception for speed: a gate-constant step that stays inside the
verified plateau bounds AND within step caps may go live at the 10-day point on the weaker condition
"trailing-20d walk-forward objective improves" — the plateau is the safety net the verification bought.

### 3.3 Automatic engine retirement / revival

- **Retire (live → shadow, stake 0):** trailing 20d with ≥200 settled fills AND net/share < 0 AND 90%
  1h-block-bootstrap CI upper bound < +1c. (Both — a noisy flat book stays live.)
- **Revive (shadow → live at half stake):** via §3.2 promotion criteria only; full stake after 10
  further days re-meeting the bar. Hysteresis is deliberately asymmetric (easy to bench, hard to return).
- **Terminal kills:** loose, floor, band, strict, value, fade, reversal2 are NOT eligible for revival —
  their failure is structural (fee-death at their own entry prices), not parametric.
- If the flagship itself is retired, no arm auto-replaces it; the program returns to research. The loop
  may not promote a [CANDIDATE] into an empty flagship slot on its own.

### 3.4 Data-outage rule

If Polymarket resolution history is unavailable at job time: log `data_outage`, skip the qhat update
and all refit bookkeeping, leave every parameter untouched. The Coinbase proxy is never substituted
into the estimator (~11% sub-2bps disagreement would flow straight into sizing). Trading continues on
yesterday's qhat; **three consecutive outage nights → freeze new entries** pending human review.

### 3.5 Metrics logged nightly to judge THE LOOP ITSELF (`work/perp/loop_metrics.jsonl`)

1. **regret_vs_frozen**: cum. pnl(live params) − pnl(`frozen_baseline`). The loop must pay for itself;
   regret < −$50 at day 30 → freeze all refits (keep logging) pending review. Separately,
   pnl(flagship) − pnl(`gate_train_shadow`) audits the trailing recalibration specifically.
2. **churn**: parameter distance moved per refit; promotions proposed / accepted / rolled back.
3. **fill-model conformance** [CONFIRMED anchor]: realized fill p25/50/75 vs **.45/.49/.51** (53c-cap
   quantiles); alert \|Δp50\| > 1.5c; availability vs the Phase-0 measured value ±10pp; full skip-reason
   histogram (gated / priced_out / late / spread / depth / stale / one_sided / f_nonpos / benched /
   missed_open_trade).
4. **edge tracking**: measurement-book q with 1h-block-boot CI; net EV/share; fee share of gross;
   Polymarket resolutions only.
5. **gate diagnostics**: nightly eff6/cnt12 distributions; gated retention vs expected ~0.5–0.6;
   paired gate increment (flagship vs `reversal_v2` control) running total with CI; calm-vs-trending
   split (the gate's value should concentrate in trending stretches — if that signature disappears,
   the mechanism is drifting even if pnl hasn't yet).
6. **cap diagnostics**: cap-skipped signals' outcome q (via PM resolutions — free, no fills needed) vs
   cap-compliant fills' q; `cap55_shadow` paired delta. This is the standing test of the
   adverse-selection caveat both refuted votes raised.
7. **data health**: feed stand-downs, non-contiguous candles, one-sided books, resolution-lag
   distribution, missed intervals.
8. **integrity asserts**: fee-per-fill exact (`|feeEntry − shares·0.07·p·(1−p)| < 1e-4`; feasibility
   verified, max diff 5e-6 across 3,143 historical fills); nightly hash of market metadata (resolution
   source "Chainlink BTC/USD", tie-rule text, slug pattern, 300s cadence) vs the frozen launch hash —
   any diff freezes new entries.

---

## 4. Sizing / allocation (paper bankroll mechanics) [CONFIRMED#3]

1. **Bank** $1,000 paper. All stakes are fractions of live bank, never flat dollars — flat $50 ≈ 0.73×
   full Kelly at the design point, verified too hot (full-Kelly median terminal $1 under the TRAIN
   regime; quarter-Kelly preserved the most in every losing week, 9/9 on max-DD).
2. **Per-trade stake**: `f_full = qhat − (1−qhat)·cost/(1−cost)` with `cost = ask + slip + 0.07·p·(1−p)`
   (reproduces f*=6.88% at q=.56, p=.51 — `kelly_table.json`). If `f_full ≤ 0` → **SKIP** (logged
   `f_nonpos`; the measurement book still records the fill). Else
   `stake = min(0.25·f_full·bank, 0.05·bank)`. **No minimum-stake floor exists.** Quarter-Kelly per the
   sizing family; **half-Kelly only as the §6 SUCCESS scaling step**, never before.
3. **qhat feeds from the measurement book, not the sized book.** With f_full≤0→skip, the sized book
   self-censors to cheap fills while qhat sits near its shrunk prior (launch qhat .5117 ⇒ only fills
   with total cost < .5117, ~43–45% of cap-compliant fills, size at first). If qhat learned only from
   sized fills the estimator would starve inside its own selection loop; the measurement book (all
   cap-compliant gated fills, PM resolutions) breaks the loop, and the sized book expands mechanically
   as qhat clears successive cost levels (~79% of the censored ledger becomes tradeable once qhat >
   .5275).
4. **Concentration**: one live arm at launch, so the family cap is per-interval stake ≤ 5% of bank.
   Pre-registered rule for any future second live arm: each arm sizes quarter-Kelly on a **half-bank
   allocation**, family same-interval total ≤ 5% of bank, enforced in eval
   (`family_stake_this_interval`). Two arms never both size quarter-Kelly of the full bank on the same
   fill — that is half-Kelly on the overlap, which the sizing study rejected on drawdown.
5. **No daily loss caps, no daily trade caps** [DEAD: sizing]: on baseline mean EV $345.8 / medDD $407.4
   (`caps_livefreq2_results.json`), L150 costs $6.96 EV (2.0%) for $3.84 medDD relief (0.9%); N3 costs
   $57.24 (16.6%) for $23.80 (5.8%) — every cap's EV cost ≈ 2× its DD relief. `dayLossPct`/`maxDay`
   stay at non-binding values, deliberately, documented in ENGINE_CFG comments.
6. **Fill price is the dominant sizing lever** (verified: 2c of entry moves EV more than any Kelly
   decision): the response to a rich book is the SKIP, never "smaller size above the cap".
7. Shadows stake $0 and never touch the bank. Adaptive allocation across arms (Thompson/Hedge) stays
   dead [DEAD: sizing].

## 5. Risk controls

1. **Drawdown control = stake fraction + tiered base-rate guard + catastrophic breaker.** Fraction-of-bank
   sizing deleverages geometrically in drawdown with no cap-style EV burn. Breaker: suspend ALL entries
   if bank < $250 (ops stop, not claimed EV-neutral).
2. **Base-rate guard** (the regime-death lesson: reversal died for ~20 of 60 days and no gate rescued
   it; sizing down was the only verified-dominant response). All triggers evaluate the **measurement
   book** on PM resolutions; latencies quantified by simulation on the real 60d stream + an injected
   q=.38 episode (`work/final-design/guard_*.json`; single-path, latency-ordering evidence only):
   - **Tier 1**: trailing 15d net/share < −1c on ≥250 signals → `qhat_used = 0.5 + (qhat−0.5)/2`
     (50% edge haircut, non-compounding). Measured latency ~7d.
   - **Tier 2**: trailing 7d net/share < −2c on ≥120 signals → same haircut. Latency ~4d.
   - **Tier 3 (hard bench)**: trailing 15d < −3c (≥250) OR trailing 7d < −4c (≥120) → **stake → 0**
     until trailing 10d net/share ≥ 0 on ≥100 signals. Injected-disaster peak DD 63.5% → 31.8%.
   Honest statement: tiers 1–2 do not prevent a regime-death drawdown — most is paid before any
   trailing window can fire. What bounds loss is geometric deleveraging, tier 3, and the breaker.
   Tier 3 is an ops control; its counterfactual cost (pnl of benched would-be fills) is logged nightly.
3. **No stops, no hedges, no timed exits** [PRIOR#4 + exits family: every overlay sign-flips
   TRAIN→TEST; hedge ≡ sell-out minus a second fee]. The +EV book is held to resolution.
4. **Thin book**: real CLOB ask required (gamma removed — 0/67 live uses); top ≥ $200; spread ≤ 2c
   (live p95); one-sided book at the open → re-poll inside the 45s window, final skip at window close.
   Expected skip rate ~45–55% of gated signals; skip-rate excursion beyond the Phase-0 band ±10pp for
   3 consecutive days = fill-model-drift alarm → tier-1 haircut until conformance returns.
5. **Feed outage / staleness**: trigger requires Coinbase with a contiguous prior 5m candle; quote
   fresher than `freshMs`, feed fresher than `feedFreshMs`; any failure → stand down for that interval
   (a missed interval costs ~2c/share of unrealized EV at the central estimate; a bad-data fill at 50c
   costs 1.75c of fee before the coin flips). No Binance/Kraken failover for the SIGNAL; quotes are
   Polymarket CLOB only. Gate latches off (`gate_ok=False`) whenever the 14-open history is incomplete;
   startup rebuilds it from Coinbase REST before un-latching.
6. **Settlement lag**: hold-to-resolution + no-open-trade means a lagging resolution blanks the next
   interval(s); logged as `missed_open_trade`; Phase 0 measures the lag distribution and cadence
   numbers carry the haircut.
7. **Oracle noise**: sub-2bps outcomes carry ~11% proxy noise [PRIOR] — every estimator and metric
   scores against actual Polymarket resolutions, never the Coinbase proxy.

---

## 6. Validation plan (pre-registered; the design is not trusted until it passes)

Cadence planning: ~66 triggers/day; gate retention ~0.55 (deploy calibration, ~37 gated/day);
availability at the 53c cap **unknown between 55%** (pm-sample, unbiased, n=49) **and 79%** (censored
ledger, selection-biased) — planning uses 55% ⇒ ~20 measurement-book fills/day ⇒ day 60 ≈ **1,200**
fills, day 90 ≈ 1,800. The sized book starts at ~43–45% of measurement cadence and grows with qhat.

**Phase 0 — implementation conformance (days 1–3).** Zero gamma fills; entrySec p95 ≤ 45s; fee assert
green; metadata hash green; resolution-lag distribution logged; gate retention within [0.40, 0.70]
(walk-forward retention .406, deploy expectation ~.55 — outside band = gate-code bug). **Measured
outputs pre-registered here:** (a) availability = fillable fraction of gated signals → sets the
skip-alarm band at measured ±10pp; (b) realized wtd fill — expected ≈ .47–.48. **Power re-derivation
rule:** if realized wtd fill > .49, Phase 2's horizon extends to day 90 *before the clock starts*
(power at the old .4861 mix collapses: 45–54% at n=1,500–2,000 for q=.523). Any conformance miss =
code bug; fix before the clock starts.

**Phase 1 — survival gate (day 14, ≈ 280 measurement fills).** KILL the family (all books keep
running, stake → 0) if measurement-book net/share ≤ −2c with 90% block-boot CI excluding 0. No success
declaration is possible this early.

**Phase 2 — decision (day 60, ≈ 1,200 measurement fills), on the measurement book:**
- **SUCCESS**: net EV/share ≥ +1c AND 90% 1h-block-boot CI > 0 AND fill conformance held → trust the
  design; only then consider half-Kelly.
- **FAIL**: net/share ≤ −0.5c, OR CI upper bound < +0.5c → stake to 0; back to research (the edge, not
  the costs, was the unproven part).
- **AMBIGUOUS**: anything else → extend once to day 90 max; still ambiguous = treat as FAIL for any
  scaling decision. No second extension.

**Power at the design's own numbers** (one-sided α=.05, block-boot SE inflation bracketed [1.0, 1.15×],
hurdle .4898 at the 53c mix; `work/final-design/checks.json`):

| True q | n=1,200 (day 60) | n=1,800 (day 90) | n for 80% |
|---|---|---|---|
| .523 (live family pooled — conservative for the gated arm) | ~72/62% | ~87/78% | 1,404–1,856 |
| .533 (60d proxy all-signals) | ~90/81% | ~98/94% | ~700–950 |
| .5539+ (gated TEST class) | >97% | ~100% | <620 |

Plain statement: if the gated arm's true q is anywhere near its verified estimates, day 60 resolves it;
if the truth is the pooled-family .523, the day-90 extension exists exactly for that case; disasters
are caught by Phase 1 and the §5 guard regardless.

**Gate verdict (day 60):** flagship vs `reversal_v2` paired delta on common signals, 1h-block-boot CI —
publishes whether the CONFIRMED gate survives at live fills. Also: calm/trending split (mechanism
check), `gate_train_shadow` delta (does trailing recalibration pay), and the gate-increment CI vs the
verifier's selection-corrected expectation (+2.8pp wr class).

**Cap verdict (day 60):** cap-skipped-signal q (PM resolutions) vs filled q, plus `cap55_shadow` paired
delta → either the 53c cap stands, or the cap question goes back to research with real paired data.
The cap is NOT loop-refittable; only this pre-registered review can change it.

**Loop audit (day 30):** regret_vs_frozen ≥ −$50 or all refits freeze; promotion rollback rate < 50% or
the promotion bar tightens (CI 90% → 95%).

**Fill-model revalidation (monthly):** rerun `work/microstructure/ledger_fill.py` on the fresh ledger
against the .45/.49/.51 anchors — the CONFIRMED quantiles are the load-bearing empirical input and get
re-checked on a schedule regardless of pnl.

---

## 7. Artifacts referenced

`work/microstructure/{fill_dist.json,thinbook_spread.json,ledger_fill.py}` ·
`work/verify-microstructure/` · `work/regime/{deploy_spec.json,tournament_results.json,deepdive_results.json}` ·
`work/verify-regime/{verify_summary.json,trig_prices.json,VERDICT.md}` ·
`work/reversal60/best_spec.json` · `work/verify-reversal60/` ·
`work/sizing/{kelly_table,kelly_sim_results,caps_livefreq2_results,alloc_results,stream_stats}.json` ·
`work/verify-sizing/` · `work/final-design/{checks.json,guard_stress.json,guard_disaster.json,guard_bench.json}` ·
`data/{englist,ledger_summary,trades,pm_prices_sample,pm_res_3d,cb5m}.json` ·
bot source (read-only): `~/btc5m-paper-trader/bot/btc5m_bot.py` — `ENGINE_CFG` at line 66,
`_reversal_eval` at line 490, `ivlHist` persistence at 358/936/1020, cap-neutralization precedent 44–50.
