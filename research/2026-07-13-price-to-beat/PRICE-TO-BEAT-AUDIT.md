# Price-to-Beat Audit — Coinbase display vs Chainlink settlement

**Date:** 2026-07-13  **Scope:** btc5m paper trader (`live.html` display + Discord pings) vs Polymarket "Bitcoin Up or Down" 5-minute settlement truth.
**Work dir:** `/Users/sgonzalez/btc5m-paper-trader/research/2026-07-13-price-to-beat/work/`

---

## 1. Verdict (3 sentences)

The displayed "price to beat" is derived from **Coinbase**, while Polymarket settles on the **Chainlink BTC/USD data stream** — so the printed reference number is off by a small cross-source basis (Pyth-vs-Coinbase median **$3.68**, max **~$8**), and the live "▲ Up leads / ▼ Down leads" ticker shows a **confidently wrong** leader on **2.2% of intervals** (19/863), rising to **27% when BTC is within 1 bp of the line**. The error is entirely a near-flat phenomenon: **100% of disagreements are under 3 bps** and there are **zero disagreements above 3 bps** across 662 intervals. **The money is safe** — booked trade P&L already reconciles to the Polymarket oracle (`settledBy="polymarket"` on 3490/3576 trades; only 5 interim provisional), so no settled result depends on the Coinbase reference; this is a **display-truth** bug, not a settlement bug.

---

## 2. The mismatch

| | Polymarket settlement (truth) | Our display |
|---|---|---|
| **Source** | Chainlink BTC/USD data stream (`data.chain.link/streams/btc-usd`) | Coinbase 1-min candle open |
| **Reference** | Chainlink price at **t0** (window start) | Coinbase 1m open at t0 (`strikeOf`, live.html:790) |
| **Settle** | Chainlink price at **exactly t0+300** (`endDate`) | Coinbase 1m open at t0+300 |
| **Rule** | Up iff `end >= start` → **TIE resolves UP** | `verdictOf` uses `d>0` (tie→down), guarded by margin band |

**Exact rule** (single verbatim description across **106 distinct markets** audited — prior 67 plus 39 independently re-fetched, Jul 7–13 UTC, 21+ hours, 100% Chainlink, 0 mention Coinbase):

> "resolve to 'Up' if the Bitcoin price at the end of the time range … is **greater than or equal to** the price at the beginning … Otherwise … 'Down'. … the price according to Chainlink data stream BTC/USD, **not according to other sources or spot markets**."

**Boundary timing** (n=67): `secondsDelay=None` for all; `endDate − t0 = 300` exactly for all; `umaEndDate − t0 ≈ 316–385s` is a post-window UMA posting buffer (not a price shift); `startDate` is the ~24h-prior listing time, **not** the price-window start (the window start comes from the slug/title t0). Ground truth independently re-verified: gamma `outcomePrices` match `pm_res_3d` on **25/25** spot checks, 0 mismatches.

**Tie convention note:** the `>` vs `>=` difference is **measure-zero in practice** — there are **0 exact ties** in the 863-interval sample (Chainlink's 8-decimal stream essentially never ties), so `d>0` and `d>=0` give identical agreement (844). Fixing only the tie operator would change nothing; the real exposure is the Coinbase-vs-Chainlink *reference basis*, of which an exact tie is only the center.

---

## 3. Quantified divergence

**Coinbase-derived leader vs Chainlink oracle, n=863** (`work/source/divergence.py`, `work/source/results.json` — independently reproduced by two verifiers):

- **Overall agreement: 97.80%** (844/863). Disagreement **2.20%** (19/863).
- Oracle up-rate 50.75%, Coinbase up-rate 50.9% — no directional bias.

**Disagreement by move size** (100% of errors < 3 bps; zero above):

| |move| (bps) | n | wrong | rate |
|---|---|---|---|---|
| [0,1) | 63 | 17 | **27.0%** |
| [1,2) | 73 | 1 | 1.4% |
| [2,3) | 65 | 1 | 1.5% |
| **≥3** | **662** | **0** | **0.0%** |

(Coarser bucketing in `work/proxy/results.json` agrees: 0–2 bps 18/136 = 13.2%, 2–5 bps 1/193 = 0.5%, everything ≥5 bps = 0/574.) Max disagreeing move = **2.22 bps ($14.07)** — right against the 3-bp boundary.

**Times the site would CONFIDENTLY show the wrong leader:**

- **Live "Up leads / Down leads" ticker** (`drawBtcBar`, live.html:838–841) — **no margin guard**: wrong on **19/863 = 2.2%** of intervals (measured at the settle instant; a conservative floor for "wrong at some point intraday").
- **Closed-window verdict** (`verdictOf` + `clearMargin`, live.html:806–810) — **0 wrong** out of 662 hard calls (100% agree). Its `max($15, 0.03%)≈$19≈3 bp` defer band catches **all 19/19** disagreements; 201/863 (23.3%) defer to "too close → oracle decides," and the naive Coinbase sign would have been wrong on **19/201 = 9.5%** of those.
- **Discord pings** carry **no price-to-beat**; leader/settle/would-be pings all report **oracle-confirmed** result + P&L, and signals gate on ≥4 bp / ≥12 bp moves (past the disagreement zone, 0% wrong there). No cross-source leader error ships to Discord.

---

## 4. Best fetchable fix source

| Source | Fetchable (stdlib, no key)? | Closeness to Chainlink | Verdict |
|---|---|---|---|
| **Pyth Hermes** `hermes.pyth.network/v2/updates/price/<ts>?ids[]=e62df6…415b43` | **Yes** — live + historical, `publish_time == requested second` on **497/497** boundaries | Best available: agrees with oracle **98.76%** vs Coinbase 95.27% on the near-flat-enriched set; fixes **16/19** Coinbase errors (head-to-head oracle backs Pyth 16/18 = 89%) | **Recommended proxy** |
| **Chainlink Data Streams** (actual truth) | **No** — `data.chain.link` returns HTTP 429 "Vercel Security Checkpoint"; the REST/WS gateway needs an issued API key + HMAC | Exact | Not usable server-side |
| **Chainlink on-chain push feed** (`latestRoundData`) | Yes via public RPC | Wrong product | Read **$62265.87 unchanged over 20+ min** while spot moved ~$80 — updates only on 0.5% deviation / 1h heartbeat → zero move on most 5-min windows. Unusable |
| **Coinbase + wider band** | Yes (current) | Basis median ~$3–4 vs Pyth | Cheapest; the existing band already quarantines every error |

**Tradeoff:** Pyth shrinks the displayed-number gap from ~$3.68 (Coinbase-vs-oracle basis) to near-zero and fixes 16/19 boundary calls, **but cannot reach 100%** — it is a different oracle than Chainlink and still missed 3/19 (all sub-$3 moves). The residual sub-2-bp zone is oracle-timing noise **no spot/oracle feed can resolve against Chainlink**, so a "too close → oracle decides" band must remain regardless of source. Pyth's ~1 req/s limit is a non-issue at 1 fetch per 5-min interval.

---

## 5. Recommended fix (ranked)

**Settlement is already oracle-correct — P&L history is NOT affected.** `settle_pending` tries the Polymarket/Chainlink oracle FIRST for every trade (bot line ~1635, `winner_of` on gamma `outcomePrices≥0.99`); Coinbase `btcOpen/btcClose` only feed an *interim* provisional settle that a reconciliation pass corrects (203 trades `settledBy="polymarket (corrected)"`, only 5 still provisional at snapshot). Everything below is **display-only**.

### Rank 1 — Guard the live leader line (do now, ~10 lines, zero runtime risk)
`drawBtcBar` (live.html:838–841) renders `▲ Up leads / ▼ Down leads` for any nonzero `d = px − open` with **no dead-zone**. Wrap it in the existing `clearMargin`, mirroring `verdictOf`: when `|d| < clearMargin(open)` show **"… too close to call → oracle decides"** instead of a confident direction.
- **Removes 19/19 = 100% of wrong-confident displays.** This is also the internal-consistency fix — the live line currently picks a side the site's own closed logic (a few lines up) declines.

### Rank 2 — Relabel the displayed number + optionally switch source to Pyth
The number at live.html:844 says "price to beat" with no caveat but is the Coinbase open, off from the Chainlink reference by the live basis (~$5–20). Either relabel to **"≈ Coinbase proxy"** or source `strikeOf` from **Pyth-at-t0** (historical Hermes endpoint), keeping the too-close band.
- Switching to Pyth is **cosmetic for direction** (max observed divergence 2.22 bp is fully inside the band) but makes the *printed number* honest and fixes 16/19 boundary calls if you ever tighten the band. Adds a live dependency — lower priority than Rank 1.

### Rank 3 — Align tie operator for consistency (optional, cosmetic)
Set `verdictOf` (live.html:810) and bot provisional (line ~1645) to `>=`→Up to match Polymarket. **Changes nothing empirically** (0 exact ties in sample) but removes a latent inconsistency.

### Skip
Do **not** invest in a live Chainlink Data Streams integration for display — not anonymously fetchable, and the residual after Pyth is sub-2-bp noise the band already handles. Widening the band 3→5 bp adds tail headroom above the 2.22-bp p99 at ~0 cost.

**Residual error after Rank 1:** the confident-wrong live-leader rate drops to **0%**; sub-3-bp intervals correctly show "too close → oracle decides." After an optional Pyth switch, the displayed *number* basis drops from median ~$3.68 to ~$0, but ~1.2% of near-flat calls remain unknowable against Chainlink by design.

---

### Number → artifact cross-check

| Number | Artifact |
|---|---|
| 106 markets 100% Chainlink; verbatim rule; 300s boundary | `work/source/results.json`, `work/source/meta_rows.json` |
| 97.80% agree, 19 disagree, bps buckets | `work/source/divergence.py`, `work/source/results.json`, `work/proxy/results.json` |
| 662 hard calls 0 wrong; 201 deferred; 19/201 = 9.5% | `work/source/results.json`, `work/codefix/results.json` |
| Pyth 98.76% vs Coinbase 95.27%; fixes 16/19; basis p50 $3.68/$2.41 | `work/proxy/results.json`, `work/divergence/pyth_gaps.json` |
| Chainlink 429, on-chain feed stale $62265.87 | `work/proxy/cl_probe.txt`, `work/proxy/results.json` |
| Oracle-first settle; 3490 oracle / 5 provisional | `bot/btc5m_bot.py` L1635-1665; `trades_unified.json` settledBy counts |
| Code touch points | `live.html` L790/806/810/838-844; `work/codefix/live.html.leaderbar.patched.js` |
