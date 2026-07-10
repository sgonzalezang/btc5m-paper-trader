# BEST MODEL v3 — FINAL DESIGN (rev 2 + second red-team applied)
Model Architect deliverable · 2026-07-10 · supersedes `DESIGN.md` rev 2 (09:18) and `FINAL-DESIGN.md` v2.1 (07:48)
Scope: paper-trading redesign of ~/btc5m-paper-trader (Polymarket BTC "Up or Down" 5-minute binaries).
Cost model (exact, frozen per brief): `EV/share = q − p − 0.07·p·(1−p)`; gas $0.004/trade; fills = ask + 1c slip.
Break-evens (each reproduces against the formula): q\*(0.4724)=0.4898 · q\*(0.4861)=0.5036 · q\*(0.51)=0.5275 · q\*(0.53)=0.5474 · q\*(0.55)=0.5673.

---

## 0. What the evidence actually supports (plain statement, before anything else)

Two different claims have been conflated in every prior draft. They are separated here permanently:

1. **The LEVEL of the gated arm clears fees on TEST.** Gated TEST +4.02c/share, wr .5676, n=717,
   block-boot p=0.0147 (`work/regime/deploy_spec.json`), independently reproduced at p=0.0152
   (`work/verify-regime/verify_summary.json`). This is real, TEST-side, and is what buys the arm
   its stake. Honest deployable central estimate after conditional-fill correction: **+1.5 to
   +3c/share** (conditional trigger mids ~52.4c; decomposed EV +1.6c at mid+1c, SE 1.9c).

2. **The INCREMENT of the gate over the ungated rule is NOT proven on TEST.** TEST gate-effect
   block-boot p = **0.1276** (deploy_spec), independently reproduced at **0.1263**
   (verify_summary). TEST ungated is itself +2.64c/share at 51c (n=1,374, p=0.025 vs breakeven,
   `work/reversal60/best_spec.json`) — most of the gated arm's TEST level is the period, not the
   gate. The "+2.97c pooled OOS" is the best of an **11-candidate gate tournament**
   (`work/regime/tournament_results.json`); the fold-level gate increments are +1.69, +5.23,
   +1.54, +0.80, +3.34c (n=5 folds, mean +2.52c, SD 1.78c) — nominal p≈0.03–0.04 **before** any
   correction for selecting the winner of 11 families, i.e. not significant after. The
   "~0.01–0.03 selection-corrected p" quoted in rev 2 is a **TRAIN-side circular-shift null**
   (`work/verify-regime/attack.py` §4) and is hereby re-labeled as such — it is not, and never
   was, a TEST result. A separate fixed-parameter construction (`work/verify-variant-impulse/`)
   puts the TEST gate effect at p=.033–.040 with its own ~.05–.09 multiplicity discount —
   better than .13, still short of the program's p<0.01 bar, and it shares the same 60d data.

**Consequence:** the gate increment is an **open question that the shadow architecture exists to
answer**, not an established edge. The gated flagship + `reversal_v2` zero-stake paired control +
pre-registered day-60 gate verdict (§7) is exactly the experiment that resolves it. The flagship
choice itself is defensible on the level evidence plus the live-corroboration direction (gated
positive, ungated negative on the same 3 days), but nothing in this design treats the increment
as proven, and no complexity is purchased with it.

### 0.1 Red-team resolution ledger (second round)

All six mustFix items verified correct against the artifacts and **fixed** (none rebutted).
4 of 5 shouldCut items cut, 1 restructured per the review's own alternative. All 7 missing items added.

| # | Item | Resolution | Where |
|---|---|---|---|
| MF1 | Gate-increment evidence overstated (TRAIN null quoted as TEST; best-of-11 selection; p=0.13 TEST) | **FIXED** — §0 above states level-vs-increment plainly with the artifact numbers; every downstream section treats the increment as unproven pending the day-60 paired verdict. | §0, §7 |
| MF2 | Single pooled qhat on a price-censored book while verify-regime and verify-sizing disagree on the SIGN of price-informativeness | **FIXED** — qhat is estimated and logged in two price buckets (p_eff <0.50 / ≥0.50) from day 1; sizing uses the fill's own bucket, which structurally forbids expansion into the ≥50c segment until that segment's q clears its own hurdle; pre-registered bucket-divergence alarm; the "~79% mechanically tradeable at qhat>.5275" rule is deleted. | §4 |
| MF3 | qhat launch seed .5117 triple-uses the gated n=71 live subset | **FIXED** — seeds are the neutral full-ledger values: pooled .5063 (`checks.json: seed_from_ledger_155_at_5226`), bucketed .5057 (lo, 33/63) and .5068 (hi, 48/92) from the verify-sizing ledger split. The n=71 subset seeds nothing. | §4.2 |
| MF4 | Direction flip vs PRIOR#2 (eff12≤0.48) never reconciled | **FIXED** — §1.1 gives the mechanism reconciliation (trigger-inclusive eff6 = impulse isolation; trigger-diluted eff12 = trend) and explicitly retires PRIOR#2's parameterization as a 10-day regime artifact while retaining its mechanism. | §1.1 |
| MF5 | Phase-1 kill bar effectively ~−5c, coin-flip against a q≈.45 disaster | **FIXED** — kill is now **mean ≤ −2c alone** (no CI condition); stated false-kill 11% at true +1.6c, fire probability 75% at true −4c; the q≈.45 case is explicitly assigned to the guard bench tier (7d < −4c) as first-line defense, day-14 as backstop. Kill is reversible (books keep running at stake 0). | §7 Phase 1 |
| MF6 | One-sided-book "final skip at window close" unreachable; measurement book double-counts per poll | **FIXED** — skip is final at t0+45s (= revWinMin boundary); pseudocode, skip logging (once per t0, snapshot of last in-window eval), and the availability denominator all aligned; `measure_book.record` dedupes by t0 (first fillable poll). | §3.2 |
| SC1 | Fast-track promotion exception (plateau steps skip the paired-CI bar) | **CUT** — one promotion path, paired 90%-CI bar, no exceptions. "No change" is the modal outcome by design; per-fold calibrated A wandered 0.06–0.40 inside the plateau, so the objective is flat and not stepping costs little. | §6.2 |
| SC2 | `rev20_shadow` holds a promotable slot despite TRAIN inversion | **CUT** — by the program's own DEAD standard (TRAIN→TEST sign flip is terminal) it gets no promotable book. The 20+bps split is a nightly diagnostic line computed from resolutions (free). | §6.4(5) |
| SC3 | Three guard tiers, two with identical action and overlapping windows, calibrated on one injected path | **COLLAPSED** — single haircut trigger (7d < −2c on ≥120, the faster of the two) + hard bench + $250 breaker. | §5.2 |
| SC4 | frozen_baseline and gate_train_shadow both audit "does adaptation pay"; neither resolves by day 60 | **RESTRUCTURED per review's option** — `frozen_baseline` kept (backs the regret circuit breaker); `gate_train_shadow` demoted to a deterministic nightly logged counterfactual with **no promotion/rollback machinery** and an honest ~90+ day resolution horizon stated. | §2, §6.4(1) |
| SC5 | "+7.5c live gated (n=71)" as a headline scenario row | **DE-EMPHASIZED** — removed from the scenario table; kept only as a labeled contamination footnote (same subset that motivated the gate; aggregate live per-dollar CI [−0.22, +0.29] is statistically zero). | §3.3 |
| M1 | No Coinbase-vs-Polymarket proxy-agreement monitor | **ADDED** — nightly sign-agreement on \|move\|≥4bps intervals; 2 days < 97% freezes sized entries. | §5.4 |
| M2 | Launch-time guard state undefined (week 1 unguarded) | **ADDED** — guard windows seeded from the pre-launch cap-censored live ledger (n=123, flagged `seed=True`); residual week-1 exposure pre-registered in writing. | §5.3 |
| M3 | Fill anchors/availability bands derived from a 3-day window, band ≈ its own sampling noise | **FIXED** — Phase 0 **REPLACES** the anchors (min n=100 gated signals, extend Phase 0 until reached); all ongoing alarms reference Phase-0 measured values only; pre-launch anchors demoted to a Phase-0 sanity cross-check. Text unified. | §7 Phase 0 |
| M4 | Learning-loop code paths first execute against real state | **ADDED** — mandatory replay dry-run of the full nightly job over the 60d dataset; loop may not move any live parameter until the replay artifact passes its asserts. | §6.5 |
| M5 | Refit objective scored at static unconditional quantiles forever | **FIXED** — from the first refit onward the objective uses measurement-book realized fills (>cap = skip); static quantiles only fill the pre-launch gap of the first two windows. | §6.2 |
| M6 | Metadata hash misses venue fee schedule / tick rules | **ADDED** — fee-schedule and tick/lot fields in the nightly hash, **log-and-flag** (the fee MODEL stays frozen per brief; resolution-source/tie-rule/cadence diffs still freeze entries). | §5.5 |
| M7 | Refit windows spanning outages | **ADDED** — a window with >25% of intervals under outage/stand-down does not refit even if it clears 250 signals. | §6.2 |

---

## 1. Evidence classes (tags unchanged; text corrected per MF1)

| Tag | Meaning | Allowed to buy complexity? |
|---|---|---|
| **[CONFIRMED]** | Survived 3-lens adversarial verification (fill model 3–0, impulse gate 3–0, Kelly sizing 2–1, reversal60 spec 2–1) | Yes |
| **[PRIOR]** | Brief's validated priors | Yes |
| **[CANDIDATE]** | Single-source, plausible, NOT verified | Shadow / logged-counterfactual only |
| **[DEAD]** | Explicitly rejected in the 60d round | Must NOT appear in the live path |

Correction to CONFIRMED#2's scope: "survived 3–0" means the verifiers reproduced the backtest
exactly and failed to refute the **level** of the gated book. The **increment** claim carries the
§0 caveats verbatim; a CONFIRMED tag on the family does not launder a p=0.13 sub-claim.

The four CONFIRMED findings and their verifier-amended numbers are carried unchanged from
DESIGN.md rev 2 §0 (fill model .45/.49/.51 at the 53c cap, hurdle .4898; gate level numbers as in
§0 above; quarter-Kelly dominance on risk 9/9 weeks; reversal60 spec with TRAIN fee-failure noted)
— with one addition: verify-regime and verify-sizing **disagree on price-informativeness**
(cheap-half wr .468 vs expensive-half .646, z=1.86, says expensive fills win more; ledger autopsy
says q flat across price, .5238 below 50c vs .5217 above, with all profit from cheapness; the
pm-matched sample says fillable q .4516 vs unfillable .7692). This unresolved contradiction is why
sizing is bucketed (§4) and why the cap verdict (§7) exists.

### 1.1 Reconciliation with PRIOR#2 (required by the brief's consistency mandate)

PRIOR#2 says: low eff12 (choppy) → reversal ~60%; HIGH efficiency (trending) → loses. The new
gate requires eff6 ≥ A. These are reconcilable, and the reconciliation is a mechanism fact, not a
rhetorical one:

**eff6 as computed by this gate INCLUDES the trigger leg** — the six open-to-open moves end at
the current interval's open, and the ≥12bps trigger move is the last of them (pseudocode §3.2;
convention confirmed in `work/verify-variant-impulse/`). A 12bps impulse against a quiet
background therefore produces HIGH eff6 *by construction*: the numerator is dominated by the
trigger itself. eff6 ≥ A is an **impulse-isolation** measure ("one large shock out of quiet"),
not a trend measure. The trend exclusion PRIOR#2 cared about is carried by the second conjunct:
cnt12 ≤ B kills cascades and sustained trends (≤B other 12bps moves in the prior hour), and a
quiet denominator does the rest. PRIOR#2's eff12 is **trigger-diluted** across 12 legs, so high
eff12 does mean sustained multi-interval trending — and that configuration is still excluded
here, via cnt12. The two gates agree on the mechanism (fade isolated shocks; avoid trends and
cascades) and differ on the instrument.

On the instrument, the 60d data is decisive: eff12 ≤ 0.48 as a literal filter earns +0.22c/share
OOS vs +2.97c for the impulse form (`tournament_results.json` `_latentfire_eff12le048`).
**PRIOR#2's specific parameterization is retired as a 10-day regime artifact; its mechanism is
retained.** Corroborating that raw efficiency thresholds alone are unstable: the tournament's
standalone-eff6 arm flipped its calibrated inequality direction across folds (le 0.54 / ge 0.40 /
ge 0.32 / le 0.76 / ge 0.22) — only the conjunction eff6 ≥ A ∧ cnt12 ≤ B was directionally
stable. This paragraph discharges the brief's prior-consistency requirement explicitly rather
than silently.

---

## 2. Engine roster

Terminal kills unchanged from rev 2 §1 (loose, floor, band, strict, value, fade, reversal2 — all
[DEAD] with the same one-line evidence; not eligible for revival; excluded-machinery list carried
verbatim).

| Book | Status | Stake |
|---|---|---|
| **`impulse_v2`** | **FLAGSHIP — only live arm.** 12bps buffered contrarian + isolated-impulse gate (§3). Staked on the LEVEL evidence (§0.1); the increment is on trial, not assumed. | Quarter-Kelly, bucketed qhat (§4) |
| `reversal_v2` | Shadow — ungated control on the identical signal stream. Its paired delta vs the flagship IS the day-60 gate verdict. | $0 |
| `measure_book` | Shadow — records the would-be fill ONCE per interval for every cap-compliant gated signal regardless of f_full/bank/guard. Primary measurement instrument; qhat's only data source. | $0 |
| `frozen_baseline` | Shadow — flagship with qhat_lo/qhat_hi pinned at launch seeds forever; backs the `regret_vs_frozen` circuit breaker (§6.4). | $0 |
| `cap55_shadow` | Shadow — flagship with revEntryMax=0.55; settles the cap-adverse-selection dispute with real paired books (§7 cap verdict). | $0 |

Demotions this revision (SC2/SC4): `gate_train_shadow` is no longer a shadow book — the
TRAIN-calibrated gate (A=0.32, B=6) is a **deterministic nightly logged counterfactual**
(re-score the same signal stream at those constants with measurement fills; no promotion, no
rollback, no state). Honest horizon: at ~20 fills/day and paired SE ~2.5c per 400 pairs, an
A-vs-A′ difference will not resolve before ~day 90+; it is a log line, not a decision input.
`rev20_shadow` is deleted; the ≥20bps/12–20bps split is a nightly diagnostic computed from
resolutions (§6.4(5)) — TRAIN-inverted gradients do not get promotable books.

Paper fills are stake-independent, so every shadow yields exactly the ledger a live arm would
have; no engine goes live to measure what a shadow can measure.

---

## 3. Flagship spec — `impulse_v2`

### 3.1 Parameters (ENGINE_CFG entry)

| Param | Value | Status | Why |
|---|---|---|---|
| `revThr` | 0.12 (% of open; buffered open-to-open, Coinbase 5m, contiguous prior candle) | **FROZEN** | Fixed 12bps beats trailing re-selection (walk-forward −0.44c vs +0.17c/share); 8bps fee-dead; 20/25bps TRAIN-inverted [CONFIRMED#4 + DEAD]. |
| side | contrarian; ties resolve Up | **FROZEN** | [PRIOR#1]; sign memory one lag deep [DEAD: pathshape]. |
| `gateForm` | `eff6 >= gateA AND cnt12 <= gateB` | **FROZEN (form)** | [CONFIRMED#2 level]; definitions in §3.2, trigger-leg conventions per §1.1. |
| `gateA`/`gateB` | **0.10 / 6** at launch | **REFIT (§6)**, bounds A∈[0.06,0.38], B∈[1,7] | Deploy-calibrated trailing-20d (`deploy_spec.json`); bounds = verified TEST plateau (every cell ≥ +2.0c). |
| `revEntryMax` | **0.53** effective (ask+slip) | **FROZEN** | [CONFIRMED#4] + arithmetic: q\*(0.53)=.5474 is the last cap any measured q plausibly clears. Cap dispute is a §7 measured output; `cap55_shadow` runs the counterfactual. |
| `revWinMin` | **255** (enter only in first 45s) | **FROZEN** | [CONFIRMED#1]: winners entrySec p50=9s/p95=37s; mid disperses violently by ~60s; late entries [DEAD]. |
| exit | hold to resolution; no stop/hedge/timed exit | **FROZEN** | [PRIOR#4] + exits family sign-flips [DEAD]. |
| `slip` | 1c | **FROZEN** | Brief cost model; live spread p50 1c / p95 2c (n=1,482). |
| book | real CLOB ask only (no gamma), top ≥ $200, spread ≤ 0.02; one-sided book → re-poll **within the entry window**; skip is FINAL at t0+45s | **FROZEN** | Gamma 0/67 [DEAD]; spread p95 2c [CONFIRMED#1]; MF6 fix — after t0+45s entry is impossible (`early` fails), so window-close finality was unreachable. |
| feed | Coinbase-only trigger; contiguous prior 5m candle | **FROZEN** | Proxy validated [PRIOR#5]; §5.4 monitors the proxy's continued validity. |

Loop-managed state (NOT in cfg): `gateA`, `gateB`, `qhat_lo`, `qhat_hi` (§4), guard state (§5).
State requirement: persist the last **20 five-minute opens** (extends `ivlHist`, bot:358/936/1020);
compute eff6/cnt12 from opens exactly as below. Cold start / gap: rebuild from Coinbase 5m REST
before the gate un-latches.

`reversal_v2` = identical with the gate disabled. `cap55_shadow` = identical with revEntryMax 0.55.

### 3.2 Eval pseudocode (style of `_reversal_eval`, bot/btc5m_bot.py:490)

```python
def _impulse_v2_eval(self, now, eid):
    cfg, prof, m, f = ENGINE_CFG[eid], self.prof(), self.mkt, self.feed
    lp  = self.loop_params(eid)          # {'qhat_lo','qhat_hi','gateA','gateB'}
    ns  = now // 1000
    left = (m["t1"] - ns) if m else None
    pv  = self.prev_ivl                  # completed interval, Coinbase open-to-open (buffered)
    contiguous = bool(pv and m and pv.get("t0") == m["t0"] - IVL and pv.get("ret") is not None)
    prior_move = abs(pv["ret"]) * 100 if (pv and pv.get("ret") is not None) else None
    signal   = bool(contiguous and prior_move is not None and prior_move >= cfg["revThr"])
    rev_side = ("down" if pv["ret"] > 0 else "up") if signal else None
    # ---- isolated-impulse gate; needs 14 persisted opens; latent without them
    gate_ok, eff6, cnt12 = False, None, None
    o = self.open_hist                   # last >=14 contiguous 5m opens incl. current interval's
    if signal and len(o) >= 14 and self.opens_contiguous(o[-14:]):
        legs  = [o[k+1] - o[k] for k in range(len(o)-7, len(o)-1)]   # 6 moves; trigger leg INCLUDED (§1.1)
        denom = sum(abs(x) for x in legs)
        eff6  = (abs(o[-1] - o[-7]) / denom) if denom > 0 else 1.0
        cnt12 = sum(1 for k in range(len(o)-14, len(o)-2)
                    if abs(o[k+1] - o[k]) / o[k] >= 0.0012)          # 12 moves BEFORE trigger (excluded)
        gate_ok = (eff6 >= lp["gateA"]) and (cnt12 <= lp["gateB"])
    early = left is not None and left >= cfg["revWinMin"]            # 255 -> first 45s ONLY
    q = self.quote(rev_side) if rev_side else None                   # REAL book only — no gamma
    real_book = bool(q and q.get("src") != "gamma" and q.get("ask") is not None)
    # MF6: one-sided/absent book is transient ONLY inside the entry window; skip FINAL at t0+45s
    if signal and gate_ok and not real_book and early:
        return self._pending(eid, m["t0"], reason="one_sided_book")
    spread = (q["ask"] - q["bid"]) if (real_book and q.get("bid") is not None) else None
    slip   = 0.01
    p_eff     = (q["ask"] + slip) if real_book else None
    priced_ok = bool(real_book and p_eff <= cfg["revEntryMax"] + 1e-9)      # 0.53 FROZEN
    spread_ok = spread is not None and spread <= 0.02 + 1e-9
    fresh     = bool(q and (now - q["at"]) <= prof["freshMs"]
                     and f["at"] and (now - f["at"]) <= prof["feedFreshMs"] and f["src"] == "Coinbase")
    depth_ok  = bool(real_book and q.get("top") is not None and q["top"] >= 200)
    opent, dup = self.open_trade(eid), (self.trade_for(eid, m["t0"]) if m else None)
    fam_open  = self.family_stake_this_interval(m["t0"]) if m else 0.0
    risk_ok   = ((not dup) and self.st["bank"] >= 250
                 and fam_open < 0.05 * self.st["bank"] - 1e-9)
    blocked_open = bool(opent)           # settlement lag -> its own skip reason
    fillable = bool(m and m["ev"] and not m["evClosed"] and signal and gate_ok and early
                    and priced_ok and spread_ok and fresh and depth_ok)
    # MF6: measurement book records ONCE per interval — first fillable poll (matches the
    # CONFIRMED fast-entry regime); it previously double-counted on every eval poll
    if fillable and not self.measure_book.has(m["t0"]):
        self.measure_book.record(m["t0"], rev_side, p_eff=p_eff, eff6=eff6, cnt12=cnt12)
    # ---- sizing (§4): quarter-Kelly on the fill's OWN price bucket (MF2), guard haircut applied
    cost   = (p_eff + 0.07 * p_eff * (1 - p_eff)) if fillable else None
    qb     = ((lp["qhat_lo"] if p_eff < 0.50 else lp["qhat_hi"]) if fillable else None)
    qb     = self.guard_haircut(qb)      # 0.5 + (qb-0.5)/2 while §5.2 haircut active; else identity
    f_full = (qb - (1 - qb) * cost / (1 - cost)) if fillable else None
    sized  = bool(fillable and risk_ok and not blocked_open and f_full is not None and f_full > 0
                  and not self.guard_benched())
    stake  = min(0.25 * f_full * self.st["bank"], 0.05 * self.st["bank"]) if sized else 0.0
    # MF6: skip record written ONCE per (eid, t0), at the first eval after the entry window
    # closes un-entered; flags snapshot the LAST in-window eval (cached each poll)
    if signal and not sized and not early and not self.skip_logged(eid, m["t0"]):
        self.log_skip(eid, m["t0"], self.last_inwindow_flags(eid, m["t0"], default=dict(
            gate_ok=gate_ok, eff6=eff6, cnt12=cnt12, one_sided=(not real_book),
            priced_ok=priced_ok, spread_ok=spread_ok, fresh=fresh, depth_ok=depth_ok,
            risk_ok=risk_ok, missed_open_trade=blocked_open,
            f_nonpos=(f_full is not None and f_full <= 0),
            benched=self.guard_benched(), ask=q and q.get("ask"))))
    ev = dict(t=now, side=rev_side, q=q, spread=spread, left=left, priorMove=prior_move,
              eff6=eff6, cnt12=cnt12, stake=stake, enter=sized)
    self.eng[eid]["eval"] = ev
    return ev
```

Availability definition (single, used everywhere): **availability = intervals with ≥1 fillable
in-window eval ÷ intervals where `signal AND gate_ok` held at any in-window eval.** A gated
signal whose book never went two-sided inside the 45s window counts in the denominator and logs
`one_sided`.

### 3.3 Expected net edge per trade

At the 53c-cap fill mix (share-wtd .4724) the hurdle is q\*=.4898; at the old 55c mix (.4861), .5036.

| Scenario | Source | EV/share | $/trade at ~100 sh |
|---|---|---|---|
| Honest central (conditional mids +1c, TEST wr .5676) | verify-regime decomposition | **+1.6c** (SE 1.9c) | ≈ +$1.6 |
| Backtest at 51c fills, TEST (LEVEL, not increment) | CONFIRMED#2 | +4.0c (boot p=0.015) | ≈ +$4.0 |
| Walk-forward pooled OOS at 51c (best-of-11 caveat, §0) | CONFIRMED#2 | +3.0c (worst fold −3.3c) | ≈ +$3.0 |
| Worst-case: cap adverse-selection on mids | verify-regime / verify-reversal60 | ~0 to −1.6c | ≈ $0 to −$1.6 |
| Regime death (live last-third, n=50, CI .12–.62) | CONFIRMED#1 caveat | −12c class | the reason §5/§7 exist |

Contamination footnote (SC5): the live gated subset ran +7.53c/share (n=71, 3 days). That number
is excluded from the table deliberately: it is the same subset that motivated the flagship
promotion and (formerly) seeded qhat, and the aggregate live ledger per-dollar edge is
statistically zero (95% CI [−0.22, +0.29], `work/verify-sizing/attack_summary.json`). It is
directional corroboration only (gated positive while ungated ran −2.79c on the same days) and
must never be quoted as a central estimate.

**Headline: +1.5 to +3c/share central (≈ +$1.5–3 per $50-class trade), worst-case fill
construction near zero, unresolved regime-death tail.** Cadence: ~66 triggers/day × gate
retention ~0.55 ⇒ ~37 gated/day × availability ~0.55 ⇒ **~20 measurement fills/day**; the sized
book starts at ~43% of that (§4.3) and can only expand bucket-by-bucket.

---

## 4. Sizing (paper bankroll mechanics) [CONFIRMED#3, bucketed per MF2]

### 4.1 Structure

Bank $1,000 paper. Per-trade: `f_full = qb − (1−qb)·cost/(1−cost)` with
`cost = p_eff + 0.07·p_eff·(1−p_eff)`, `p_eff = ask + slip` (reproduces f\*=6.88% at q=.56,
p=.51 — `kelly_table.json`). `f_full ≤ 0` → **SKIP** (logged `f_nonpos`; measurement book still
records). Else `stake = min(0.25·f_full·bank, 0.05·bank)`. No minimum-stake floor. Half-Kelly
only as the §7 SUCCESS scaling step. Flat-dollar staking stays dead (0.73× full Kelly, verified
too hot; quarter-Kelly won max-DD 9/9 weeks).

### 4.2 Bucketed qhat (MF2) and neutral seeds (MF3)

The program's own artifacts disagree on whether entry price predicts outcome (§1). Until the
day-60 cap verdict resolves it, a pooled qhat applied to a price-censored sized book is not
licensed. Therefore:

- **Two estimators, by effective entry price**: bucket `lo` = p_eff < 0.50, bucket `hi` =
  p_eff ∈ [0.50, 0.53]. Nightly, over trailing-30d **measurement-book** settled fills, Polymarket
  resolutions only, hard cap 0.56 each:
  `qhat_b = (wins_b + 100) / (n_b + 200)` (per-bucket shrinkage n0=200 at mean 0.5; the two
  priors sum to the old pooled n0=400).
- **Launch seeds — neutral, not the n=71 subset**: from the verify-sizing full-family ledger
  split: lo = (33+100)/(63+200) = **.5057** (n=63, q .5238); hi = (48+100)/(92+200) = **.5068**
  (n=92, q .5217). Pooled equivalent .5063 = `checks.json seed_from_ledger_155_at_5226`. The hi
  seed includes 53–55c entries the new cap forbids — acceptable: it is a prior that washes out in
  ~2 weeks, and it errs small. The formerly proposed .5117 seed is withdrawn (triple use of the
  gated n=71 live subset: gate selection, flagship promotion, and seeding).
- **Sizing uses the fill's own bucket** (pseudocode §3.2). Consequence checked at the seeds: for
  every hi-bucket cost (p_eff ∈ [.50,.53] ⇒ cost ∈ [.5175,.5474]), f_full < 0 at qhat_hi=.5068 —
  **the entire hi bucket is unsized at launch and stays unsized until its own measured q clears
  its own costs.** This replaces — and deletes — the mechanical rule "~79% becomes tradeable once
  pooled qhat > .5275". Expansion past any cost level now requires the bucket containing that
  level to earn it.
- **Pre-registered bucket-divergence alarm**: once both buckets hold ≥100 settled fills, a
  two-proportion z ≥ 2 between q_lo and q_hi (either direction) logs `bucket_divergence`, freezes
  any hi-bucket sizing regardless of qhat_hi, and feeds the day-60 cap verdict. Both buckets'
  (n, wins, qhat, mean cost, raw EV/share with 1h-block-boot CI) are §6.4 nightly lines from day 1.

### 4.3 Launch geometry (stated so Phase 0 can check it)

f_full > 0 ⟺ total cost < qhat_b. At the lo seed .5057 that is p_eff ≲ .4882; ~43% of
cap-compliant measurement fills qualify (`checks.json cap53_frac_cost_lt_5063 = .431`) ⇒ **~8–9
sized trades/day at launch** against ~20 measurement fills. qhat feeds from the measurement book,
never the sized book (self-censoring loop otherwise). Concentration: one live arm; per-interval
family stake ≤ 5% of bank; the pre-registered two-arm rule (half-bank allocations, family cap
enforced in eval) carries over unchanged. No daily loss/trade caps [DEAD: sizing — every cap's EV
cost ≈ 2× its DD relief, `caps_livefreq2_results.json`]. The response to a rich book is the SKIP,
never a smaller size above the cap. Shadows stake $0.

---

## 5. Risk controls

### 5.1 Frame

Drawdown control = fraction-of-bank sizing (geometric deleveraging) + a two-stage base-rate guard
+ catastrophic breaker (suspend ALL entries if bank < $250; ops stop, not EV-neutral). No stops,
hedges, or timed exits [PRIOR#4 + exits family]. Thin-book rules as in §3.1. Feed staleness →
stand down for the interval; gate latches off while the 14-open history is incomplete.

### 5.2 Base-rate guard (collapsed per SC3)

All triggers evaluate the **measurement book** on PM resolutions. Latency evidence is a
single-path simulation (real 60d stream + injected q=.38 episode, `work/final-design/guard_*.json`)
— ordering evidence, not calibration; three tiers were precision that evidence could not support.

- **HAIRCUT**: trailing 7d net/share < −2c on ≥120 signals → both buckets size at
  `qhat_used = 0.5 + (qhat_b − 0.5)/2` (50% edge haircut, non-compounding). Re-evaluated nightly;
  releases when the 7d window ≥ −1c (hysteresis so it does not flap). Simulated latency ~4d —
  the faster of the two former tiers; the slower 15d/−1c tier is deleted (identical action,
  overlapping window, single-path calibration).
- **BENCH**: trailing 15d < −3c (≥250) OR **7d < −4c (≥120)** → stake → 0 until trailing 10d
  net/share ≥ 0 on ≥100 signals. This is the designated first-line defense for the true-q≈.45
  disaster (EV ≈ −4c: fire probability ≈ 50% per evaluation once the window fills; injected-
  disaster peak DD 63.5% → 31.8% with bench active). Counterfactual pnl of benched would-be
  fills logged nightly.
- **BREAKER**: bank < $250 → suspend all entries.

Honest statement (unchanged): the haircut does not prevent a regime-death drawdown — most is paid
before any trailing window fires. What bounds loss is geometric deleveraging, the bench, the
breaker, and Phase 1.

### 5.3 Launch-time guard state (M2)

Guard windows are **seeded at launch** with the pre-launch cap-censored live family ledger
(n=123 fills over ~3d, PM resolutions, flagged `seed=True`). Seeds count toward the ≥120/≥250
minimums and age out of the trailing windows naturally, so a guard tier CAN be red on day 1.
Pre-registered residual, in writing: until roughly day 6 the 7d window is majority seed data
drawn from a family-wide (not flagship-only) book; during that stretch the effective defenses are
the seeded guard (approximate), the $250 breaker, and the Phase-1 kill. This exposure is known
and accepted.

### 5.4 Proxy-agreement monitor (M1)

The trigger's validity rests on the Coinbase↔Chainlink agreement stat measured once (97.7%
overall, 100% at |move| ≥ 4bps, n=260) in a benign period. Nightly, from the resolution harvest
the job already performs: sign-agreement rate between the Coinbase open-to-close direction and
the Polymarket resolution on intervals with |move| ≥ 4bps (expected ≈ 100%). Log daily.
**Two consecutive days < 97% → sized stake → 0** (`proxy_divergence` flag, human review;
measurement book keeps recording — the data remains informative about the breakage). Resume after
3 consecutive days ≥ 99%. This catches an exchange outage, a Coinbase-specific flash move, or an
oracle methodology change before pnl does.

### 5.5 Venue-rule monitoring (M6)

Nightly metadata hash, split into two severity classes:
- **Freeze class** (any diff → freeze new entries): resolution source string ("Chainlink
  BTC/USD"), tie-rule text, slug pattern, 300s cadence.
- **Flag class** (any diff → `venue_rules_changed` log + human review, no freeze): venue fee
  schedule fields as published by the public API, tick/lot rules. The 0.07·p·(1−p) MODEL stays
  frozen per the brief; a real-venue fee change must at minimum be visible, not silent.

Plus the standing integrity asserts: fee-per-fill exact (max |diff| 5e-6 across 3,143 historical
fills), settlement-lag logging (`missed_open_trade`), resolution-outage rule (§6.3).

---

## 6. Perpetual learning loop (nightly job, 00:10 UTC)

Nightly: metrics, integrity asserts, qhat (both buckets), shadow bookkeeping, counterfactual
lines. **Structural changes only at 10-day review points** (5-day refits are thrash: W20/R5
+3.15c vs W20/R10 +4.56c). "No change" is the expected modal outcome; that is the design working.

### 6.1 FROZEN vs REFIT

FROZEN (loop may never touch): revThr, side, hold-to-close, revEntryMax, revWinMin, slip, fee
model, gate FORM, book rules, Coinbase-only buffered signal. REFIT: `gateA`/`gateB` (10-day,
below); `qhat_lo`/`qhat_hi` (nightly, §4.2). Shadow params (`cap55_shadow`) refit 10-day,
shadow-only.

### 6.2 Gate-constant refits (single promotion path — SC1 applied)

- Objective: net/share of gated signals over the trailing 20d, scored on **measurement-book
  realized fills** (>cap = skip) — M5 fix: static CONFIRMED quantiles are permitted only to fill
  the pre-launch gap of the first two windows; from day 20 every window is fully
  measurement-based. Rationale: gated conditional mids run ~52.4c vs the 49.5c unconditional
  stat; a static objective would drift constants toward signal subsets the book prices out.
- Min sample: ≥250 trigger signals in the window; **and (M7) a window with >25% of its intervals
  under feed stand-down or resolution outage does not refit regardless of signal count**
  (log `window_degraded`).
- Step caps |ΔA| ≤ 0.10, |ΔB| ≤ 1 per refit; hard bounds A∈[0.06,0.38], B∈[1,7] (verified plateau).
- **Promotion path (the only one)**: proposed constants first run as a paired computation on the
  common signal stream ≥10 days and ≥400 paired signals; go live only if the paired
  (proposed − incumbent) net/share 1h-block-boot **90% CI lower bound > 0** AND proposed
  net/share > 0 absolutely. Max one promotion per 30 days; displaced values kept as a logged
  counterfactual 20 days with auto-rollback on the mirrored condition. The former fast-track
  ("plateau steps go live on trailing-objective improvement alone") is **deleted**: it was the
  largest remaining noise-chasing channel, its plateau bounds are TEST-derived (double-use of the
  last 20 days), and per-fold calibrated A wandered 0.06–0.40 inside the plateau — the objective
  is flat, so never stepping costs little. [CANDIDATE]-class changes additionally need human
  sign-off and enter at half stake.

### 6.3 Retirement / revival / outage

Retire (live → stake 0): trailing 20d, ≥200 settled fills, net/share < 0 AND 90% CI upper bound
< +1c. Revive: promotion path only, half stake, full stake after 10 further days re-meeting the
bar. Terminal kills stay terminal. If the flagship is retired, no arm auto-replaces it.
Resolution outage at job time: log `data_outage`, skip qhat and all refit bookkeeping; three
consecutive nights → freeze new entries pending human review. The Coinbase proxy never feeds any
estimator.

### 6.4 Nightly metrics (`work/perp/loop_metrics.jsonl`)

1. **regret_vs_frozen**: cum pnl(live) − pnl(`frozen_baseline`); < −$50 at day 30 → freeze all
   refits. Plus the `gate_train_counterfactual` line (deterministic A=0.32/B=6 re-score;
   ~90+ day horizon, log-only — SC4).
2. **churn**: parameter distance per refit; promotions proposed/accepted/rolled back.
3. **fill conformance**: realized fill p25/50/75 vs the **Phase-0 measured anchors** (M3 — the
   3-day pre-launch quantiles .45/.49/.51 are replaced at Phase-0 close); alert |Δp50| > 1.5c;
   availability vs Phase-0 value ±10pp (n≥100 basis); full skip-reason histogram; 3 consecutive
   days outside the availability band = fill-model-drift alarm → §5.2 haircut until conformance
   returns.
4. **edge tracking**: measurement-book q with 1h-block-boot CI; net EV/share; fee share of gross;
   **per-bucket lines: n, wins, qhat_lo/qhat_hi, mean cost, raw EV/share + CI; bucket-divergence
   z** (§4.2). PM resolutions only.
5. **gate + trigger diagnostics**: eff6/cnt12 distributions; retention vs expected 0.5–0.6;
   running paired gate increment (flagship vs `reversal_v2`) with CI — the day-60 verdict input;
   calm/trending split (mechanism signature); **prior-move split ≥20bps vs 12–20bps q from
   resolutions** (SC2 replacement for rev20_shadow — diagnostic, not promotable).
6. **cap diagnostics**: cap-skipped signals' outcome q (resolutions, free) vs filled q;
   `cap55_shadow` paired delta.
7. **proxy agreement** (§5.4) and **data health**: stand-downs, non-contiguous candles, one-sided
   finals, resolution-lag distribution, missed intervals.
8. **integrity asserts** (§5.5 both classes).

### 6.5 Loop dry-run requirement (M4 — blocking)

Before the loop may move ANY live parameter (i.e., before the first 10-day review), the full
nightly job must pass a **replay test over the 60d historical dataset** (`work/perp/replay.py` →
`work/perp/loop_replay.json`), asserting: (a) the trailing-20d gate objective reproduces
`deploy_spec.json`'s W20/R10 choice A=0.10/B=6 at asof 2026-07-10; (b) no simulated refit ever
violates bounds or step caps; (c) the nightly qhat trajectory (both buckets) matches the
closed-form shrinkage on the same fills; (d) the promotion/rollback state machine never
double-fires or acts on a degraded window. Until the artifact exists and passes, refits compute
and log proposals but change nothing. The recalibration plumbing stays [CANDIDATE] until this
replay plus the first live 10-day cycle both behave.

---

## 7. Validation plan (pre-registered)

Cadence: ~20 measurement fills/day ⇒ day 14 ≈ 280, day 60 ≈ 1,200, day 90 ≈ 1,800.

**Phase 0 — conformance + anchor REPLACEMENT (days 1–3, extend until ≥100 gated signals).**
Zero gamma fills; entrySec p95 ≤ 45s; fee assert green; metadata hash green; replay test (§6.5)
scheduled; resolution-lag distribution logged; gate retention within [0.40, 0.70] (outside =
gate-code bug); skip finality and measurement dedupe verified in logs (exactly one skip record
and ≤1 measurement record per signal interval). **Phase 0 REPLACES the pre-launch anchors** (M3):
measured fill p25/50/75, availability (per the §3.2 definition), and entrySec distribution become
the reference values; alarm bands re-derived from them (|Δp50| > 1.5c; availability ±10pp on
n≥100, SE ≤ 5pp). The 3-day pre-launch anchors (.45/.49/.51, 55%) serve only as a sanity
cross-check during Phase 0 itself: divergence > 5c on p50 or > 25pp on availability = suspect
harness bug — investigate, do not tune. Power re-derivation rule: if measured wtd fill > .49,
Phase 2's horizon extends to day 90 before the clock starts (power at the .4861 mix collapses:
45–54% at n=1,500–2,000 for q=.523). Any conformance miss = code bug; fix before the clock starts.

**Phase 1 — survival kill (day 14, ≈280 fills, min 200).** KILL the family (sized stake → 0; all
books keep running) if measurement-book net/share ≤ **−2c, mean alone — no CI condition** (MF5).
Stated properties at SE ≈ 3c: false-kill probability ≈ 11% if true EV is the central +1.6c —
accepted, this is paper, and the kill is reversible at the day-60 review because every book keeps
recording; fire probability ≈ 75% against a true q≈.45 disaster (EV ≈ −4c), whose designated
first-line defense is anyway the §5.2 bench (7d < −4c on ≥120, seeded and evaluable from week 1).
The old rule ("−2c AND 90% CI excluding 0") effectively required mean ≤ ~−5c at this n and made
day 14 a coin flip against the disaster case; it is withdrawn.

**Phase 2 — decision (day 60, ≈1,200 fills), on the measurement book:**
- SUCCESS: net EV/share ≥ +1c AND 90% 1h-block-boot CI > 0 AND fill conformance held → only then
  consider half-Kelly.
- FAIL: net/share ≤ −0.5c OR CI upper bound < +0.5c → stake 0; back to research.
- AMBIGUOUS: extend once to day 90 max; still ambiguous = FAIL for any scaling decision.

Power at the design's own numbers (one-sided α=.05, block SE inflation [1.0, 1.15×], hurdle .4898;
`work/final-design/checks.json`): true q .523 → 72/62% at n=1,200, 87/78% at 1,800; q .533 →
90/81% and 98/94%; q .5539+ → >97%. If truth is near the verified estimates day 60 resolves it;
the day-90 extension exists for the pooled-family .523 case; disasters are Phase 1 / guard.

**Gate verdict (day 60) — the increment's actual trial (MF1).** Flagship vs `reversal_v2` paired
delta on common signals, 1h-block-boot 90% CI. Pre-registered readings: CI > 0 → the increment is
real at live fills, gate stays; CI straddling 0 → increment unproven, gate stays only if its
level meets Phase-2 SUCCESS on its own (and the ungated arm's shadow level is published beside
it); CI < 0 → gate removed, `reversal_v2` inherits flagship candidacy through the §6.2 promotion
path. Also published: calm/trending mechanism split, the gate_train counterfactual line
(log-only), and the increment vs the +2.8pp-wr-class expectation.

**Cap verdict (day 60).** Cap-skipped q vs filled q (resolutions), `cap55_shadow` paired delta,
and the §4.2 bucket q's — resolving the verify-regime vs verify-sizing price-informativeness
contradiction with real paired books. The cap is not loop-refittable; only this review can change
it.

**Loop audit (day 30).** regret_vs_frozen ≥ −$50 or refits freeze; promotion rollback rate < 50%
or the promotion CI tightens to 95%.

**Fill-model revalidation (monthly).** Rerun `work/microstructure/ledger_fill.py` on the fresh
ledger vs the Phase-0 anchors.

---

## 8. Artifacts referenced

`work/regime/{deploy_spec.json,tournament_results.json,deepdive_results.json}` ·
`work/verify-regime/{verify_summary.json,attack.py,trig_prices.json}` ·
`work/reversal60/best_spec.json` · `work/verify-reversal60/` ·
`work/microstructure/{fill_dist.json,thinbook_spread.json,ledger_fill.py}` · `work/verify-microstructure/` ·
`work/sizing/{kelly_table,kelly_sim_results,caps_livefreq2_results,alloc_results,stream_stats}.json` ·
`work/verify-sizing/attack_summary.json` ·
`work/final-design/{checks.json,guard_stress.json,guard_disaster.json,guard_bench.json}` ·
`work/verify-variant-impulse/verify_results.json` (corroborating gate construction; own caveats) ·
`data/{englist,ledger_summary,trades,pm_prices_sample,pm_res_3d,cb5m}.json` ·
bot source (read-only): `~/btc5m-paper-trader/bot/btc5m_bot.py` — ENGINE_CFG:66,
`_reversal_eval`:490, ivlHist persistence 358/936/1020.

Numbers verified for this revision (reproduced from artifacts before writing): all five
break-evens vs the brief formula; TEST gate-effect p 0.1276/0.1263; fold increments
+1.69/+5.23/+1.54/+0.80/+3.34 (mean 2.52, SD 1.78, t=3.17 on 4 df); 11 tournament candidates;
neutral seeds .5063 pooled / .5057 lo / .5068 hi (integer win counts 81/33/48 confirm);
hi-bucket f_full < 0 across [.50,.53] at launch seeds; lo-bucket sized boundary p_eff ≈ .488
⇒ ~43% sized fraction (cap53_frac_cost_lt_5063 = .431); Phase-1 kill probabilities
(11.4% at +1.6c, 74.8% at −4c; old rule's effective bar −4.9c at SE 2.99c).
