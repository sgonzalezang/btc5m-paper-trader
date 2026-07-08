# SIGNAL-BRIDGE — wiring the Band engine to the live executor

Spec for the Discord-bot session to implement. The paper bot (this repo,
`bot/btc5m_bot.py`) is the **signal source**; the Discord bot is the
**executor**. Personal, non-commercial use by the owner only. Small-size R&D.

**Hard conditions (non-negotiable):**
- Only usable with legitimate, front-door Polymarket access (the regulated US
  venue). No VPNs, no geoblock circumvention, no borrowed accounts. If access
  requires any of those, do not build or enable this.
- The executor starts in **SHADOW mode** (logs what it *would* do, places no
  orders) and stays there until the owner explicitly flips `LIVE_ENABLED`.
- Never market orders. Never size escalation logic. The paper bot stays the
  strategy reference; the executor is a dumb, safe order hand.

## 1. Architecture — where the signal is born, and the trap to avoid

- The engine decision is computed in `evaluate()` in `bot/btc5m_bot.py` on the
  owner's Mac, every ~5s tick. When Band's gate passes (7/10 guards +
  Stable2tick + ask≤65¢ + drift 0.02–0.04%), `ev["enter"]` flips true.
- At that instant `emit_signal()` fires (one-shot per engine per interval):
  1. writes the signal JSON atomically to `SIGNAL_FILE` (same-machine option)
  2. POSTs it to a **private Discord webhook** (`BTC5M_SIGNAL_WEBHOOK`) as a
     message: human-readable line + a ```json code block.
- **The GitHub `data` branch / state.json is a dashboard mirror with up to
  ~5 minutes of lag. It must NEVER be polled for signals.** On a 5-minute
  market a GitHub-sourced signal arrives after the market closes.
- The executor listens in the private Discord channel (or watches the file if
  it runs on the same Mac), validates, and places one order via its existing
  Polymarket order machinery.
- Latency budget: webhook ~0.3s + parse + order ≈ **~1s behind the paper
  fill**. Safe because the order is a **limit at the engine's cap** — if price
  ran past 65¢, the order simply doesn't fill, which is exactly what the
  engine itself would have done (its edge dies past the cap).

## 2. Signal schema (v1)

```json
{
  "v": 1,
  "signalId": "band-1783467000",          // engine-t0 — THE idempotency key
  "engine": "band",
  "emittedAt": 1783467092431,              // ms epoch at decision time
  "asset": "BTC",
  "slug": "btc-updown-5m-1783467000",      // Polymarket market slug
  "t0": 1783467000, "t1": 1783467300,      // interval bounds (sec epoch)
  "secLeft": 208,                          // seconds to interval close at emit
  "side": "down",                          // which side the engine buys
  "tokenId": "1234…",                      // CLOB token id for that side — no
                                           //   market discovery needed
  "ask": 0.54, "bid": 0.53,                // top of book at decision time
  "limitCap": 0.65,                        // engine's hard price cap
  "driftPct": 0.0204,                      // |move| at entry, % of interval open
  "passCount": 8, "need": 7,
  "hmac": "…32 hex chars…"                 // see §3
}
```

## 3. Authenticity — reject spoofed signals

Anyone who can post in the channel could fake a signal. The executor MUST:
- Verify `hmac == hmac_sha256(BTC5M_SIGNAL_SECRET, canonical)` where
  `canonical = json.dumps(payload_without_hmac, sort_keys=True,
  separators=(",",":"))`, hex, truncated to 32 chars. Shared secret lives in
  env on both sides (`bot/signal.env` on the Mac — untracked).
- Verify the message author is the known webhook id, in the known channel.
- Drop anything that fails, and alert loudly (@owner) — a failed HMAC is an
  attack or a misconfig, both worth waking up for.

## 4. Executor validation gauntlet (all MUST pass before any order)

1. `LIVE_ENABLED` is true (else log the full decision as SHADOW and stop).
2. HMAC + author + channel verify (§3).
3. `signalId` never seen before (persist the seen-set across restarts).
4. Freshness: `now - emittedAt ≤ 10s`. Stale = skip (the moment passed).
5. Time guard: `t1 - now ≥ 60s`. Too close to the close = pin risk, skip.
6. Engine allowlist: `engine == "band"` (v1 trades Band only).
7. No open live position, and no position already taken this interval.
8. Daily rails not exhausted (§5).

## 5. Safety rails (executor-side, hard-coded, checked every order)

- `SIZE_USD` — fixed per-trade notional from config. No formula, no scaling.
  (Owner sets it. Venue minimum ~$1. Fee ≈ 7%·p·(1−p) ≈ 2.5–3% of stake per
  entry — at zero edge the expected R&D burn is ≈ (fees+spread) ≈ 3–4% of
  SIZE_USD per trade, ~40–70 Band signals/day. Do that math before sizing.)
- `MAX_TRADES_DAY` (suggest 20 to start) — then halt until local midnight.
- `MAX_DAY_LOSS_USD` — realized day loss ≥ cap → **halt + @owner alert**.
- 3 consecutive order errors → halt + alert.
- `!pause` / `!resume` Discord commands flip a kill switch instantly.
- Every decision (shadow, placed, filled, skipped + reason) posts to the
  private channel AND appends to a local `executor-ledger.jsonl`.

## 6. Order policy

- **Marketable limit**: price `min(ask + 0.01, limitCap)`, size `SIZE_USD`.
- Rest until filled or `t1 − 20s`, then cancel unfilled remainder. Partial
  fills are fine (the paper sim models partials too).
- **Never** market orders; **never** chase above `limitCap`.
- v1 holds to resolution — no exits. The paper engine's spot-retrace
  stop-loss is NOT mirrored (selling a thin 5m book near the close is usually
  worse than the stop it simulates). Consequence: live results will diverge
  from paper on 'stopped' trades — that divergence is data, not a bug; the
  reconciler (§7) measures it.

## 7. Reconciliation — the actual R&D product

Daily job (or `!recon` command): join `executor-ledger.jsonl` to the paper
bot's Band trades (`state.json` on the `data` branch — fine for THIS job,
lag is irrelevant offline) on `signalId`↔`eng+t0`:
- fill rate: % of signals that became live fills (vs paper's 100%)
- price gap: live avg fill − paper entry, in cents (slippage reality check)
- outcome gap: live P&L − paper P&L per shared interval, and where 'stopped'
  paper trades diverged
- post a one-message daily scorecard to the channel.
This comparison is the point of the whole exercise: it prices the simulator's
optimism in real cents. If live systematically underperforms paper by more
than ~1–2¢/fill, the strategy's thin edge is gone — stop and report.

## 8. Rollout ladder (do not skip rungs)

1. **Bridge on, executor SHADOW** (LIVE_ENABLED=false): ≥48h or ≥50 signals.
   Verify: every signal received once, HMAC ok, would-have prices sane.
2. **Live at minimum size** (venue minimum): ≥100 trades. Watch recon daily.
3. **Owner reviews recon**, decides size from there. (Not this doc's call.)

## 9. Enabling the source side (owner's Mac)

```bash
# create bot/signal.env (untracked; .gitignore already covers it):
SIGNAL_ENGINES=band
SIGNAL_FILE=$PWD/signal.json                       # optional, same-machine
BTC5M_SIGNAL_WEBHOOK=https://discord.com/api/webhooks/…   # private channel
BTC5M_SIGNAL_SECRET=$(openssl rand -hex 16)        # share with executor env
# then: launchctl kickstart -k gui/$UID/com.btc5m.paper
# verify: tail -f bot/bot.log  → "SIGNAL BRIDGE ON — engines=band …"
```
Kill it all: delete `bot/signal.env`, kickstart again (bridge off), and/or
`!pause` on the executor. Rotate the webhook URL + secret if ever leaked.

## 10. v1 non-goals

No stop-loss mirroring, no exits, no multi-engine, no size logic, no
re-entry, no signal replay after downtime (missed = missed), no public
sharing of the webhook/channel/secret, and no use outside the owner's own
legitimately-accessible account.
