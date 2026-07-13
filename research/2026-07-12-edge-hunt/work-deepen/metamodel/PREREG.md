# Meta-model Phase 1 — pre-registered protocol (written BEFORE any model fit)

Date: 2026-07-13. Executor: wave-2 metamodel agent. ML-PLAN.md Phase 1, executed.

## Data
- Universe: gated signals (trigger AND gatePass) from ../dataset/signals_60d.json,
  n=2,802 (2,015 TRAIN / 787 TEST). Label: win = (label == side), contrarian.
- Ties (|ret0|<1bp, n=182) EXCLUDED from training and from primary metrics
  (PM says ties resolve ~43/57 — no binary label exists). Ties-as-loss reported
  as sensitivity on the money metric only.
- Fine-tune target: the 36-record live measure book (state_extract.json);
  32 settled records with feats.

## Model
- L2-regularized logistic regression, pure python stdlib, gradient descent
  (Barzilai-Borwein steps, best-iterate safeguard), deterministic init w=0, b=0,
  features standardized on each training fold (zero-variance columns -> std=1,
  which pins their coefficient at 0 under L2). IRLS (Newton) implemented as an
  independent cross-check optimizer; fits must agree to <=1e-5 on coefficients.
- Features (8, from the Phase-0 set; hour-cyclic counts as one feature, 2 columns;
  9 columns total): cost, pm, eff6, cnt12, hour_sin, hour_cos, vol, spread, sec.
  * cost / spread / sec have NO per-row candle values. In pretrain they are set
    CONSTANT (cost = frozen median cost anchor .507493, spread = .01, sec = 20)
    => zero variance => coefficient 0. They become learnable ONLY in the live
    fine-tune (real asks/spreads/secs). FLAGGED LIMITATION: the pretrained model
    cannot learn a price coefficient; wave-1 said price is where the signal is.
  * vol: harmonized 2x5m-candle proxy recomputed from cb5m for ALL rows (the
    shipped vol10m switches source 5m2->1m exactly at the TRAIN/TEST boundary;
    a source dummy would be an era dummy). Must reproduce the dataset's 5m2
    values exactly on vol_src=="5m2" rows before use. Dataset vol10m-as-shipped
    kept as a diagnostic variant.

## Validation (walk-forward, per ML-PLAN)
- 10d folds from May 11 12:00 UTC: fold k scored on [start+k*10d, start+(k+1)*10d),
  k=1..6 (F6 partial, ends Jul 13 03:35). Model retrains at each fold boundary on
  ALL prior gated ex-tie rows. Nothing before May 21 12:00 is ever scored.
- Lambda grid (K=8): {0.03, 0.1, 0.3, 1, 3, 10, 30, 100} on
  J = mean CE + lambda/(2n) * ||w||^2 (intercept unpenalized).
  Chosen by TRAIN-internal OOS Brier ONLY (OOS predictions with t0 < Jun 26
  00:00 UTC). Full path reported.
- PRIMARY metric window: TEST-era OOS (t0 >= Jun 26), ex-tie, n~721.
  Pooled OOS reported secondary.

## Baselines (both computed walk-forward on the same candle universe, nightly
update at 00:10 UTC, trailing 31d settled-by-then rows, cap 0.56, seeded at launch values)
- qhat-impl: bucket by cost<0.50; qhat_b = (w_b + 400*seed_b)/(n_b + 400),
  seeds lo .5057 / hi .5068.
- qhat-spec: bucket by p_eff<0.50; qhat_b = (w_b + 100)/(n_b + 200).
- Rows have no real price: bucket membership evaluated at each frozen fill
  anchor scenario p in {.45, .49, .51} (cost {.467325, .507493, .527493});
  all metrics reported per anchor. Median anchor (.49) is the headline scenario.
- Context baselines: constant 0.5; frozen seeds (no learning).

## PASS BAR (pre-registered, from ML-PLAN Phase 1)
PASS iff on TEST-era OOS ex-tie rows, at the median fill anchor, the model beats
BOTH qhat variants on BOTH Brier and log-loss with a 95% two-sided 1h-block
bootstrap CI (B=10,000, blocks = floor(t0/3600)) on the per-signal loss
difference that excludes zero. Anything less is FAIL (report closest miss).

## Money metric (reported regardless of verdict; not part of the pass bar)
Quarter-Kelly at frozen fills on the same OOS signals: f = (q_hat - c)/(1 - c);
stake = min(0.25*f*1000, 50) if f>0 (fixed bank, non-compounding); shares =
stake/c; PnL = shares*(win - c) - gas 0.004 per staked trade. Per anchor +
availability 0.55 scaling on totals. Model-q vs impl-qhat-q vs spec-qhat-q on
identical signals; 1h-block bootstrap CI on the PnL difference. Ties: excluded
primary / ties-as-loss sensitivity.

## Ablations (diagnostics at the frozen lambda; NOT used for selection; K listed)
- Drop-one over {pm, eff6, cnt12, hour, vol} (5 fits/fold)
- Single-feature over the same (5 fits/fold)
- vol-as-shipped variant (1)
K_diagnostic = 11. K_selection = 8 (lambda only).

## Fine-tune (32 settled live records)
Continue GD from pretrained coefficients; shared features keep pretrain
standardization; cost/spread/sec standardized on the live records; objective
CE + mu*||w - w_pre||^2, mu grid {0.3, 1, 3, 10} (K=4) by leave-one-out CE.
Evaluated by LOO Brier vs LOO-refit qhat variants on the same 32 records.
n=32 => declared UNPOWERED up front; result is directional only, cannot
overturn the primary verdict.
