# leader50 entry-clock leak — pre-registration for `leader50t`

2026-07-29. Source: EV decomposition of leader50's n=600 settled fills (state.json book).

## The finding

leader50's edge is thin in aggregate: **60.8% win at a 58.4¢ average entry**. Since entry price
*is* the break-even win rate on a binary market, that is only **+2.4pp** of real edge (+$939,
EV/$ +0.018).

Slicing by **entrySec** (seconds into the 5-minute interval at fill) against session:

| entrySec | NIGHT (22–05 ET) | DAY (06–21 ET) |
|---|---|---|
| 0–30s   | n=13  66.2%* +$244 | n=64  62.5%  +$342 |
| **31–60s** | n=36  66.7%  +$200 | **n=119  51.3%  −$905** |
| 61–120s | n=43  76.7%  +$683 | n=125  56.0%  −$405 |
| >120s   | n=65  66.2%  +$438 | n=135  61.5%  +$341 |

\* night 0–30s is 84.6% on n=13 — too small to lean on.

**The daytime 31–60s bucket is the single worst population in the book**: 51.3% win while paying
~58¢, i.e. below its own break-even, for −$905 — most of leader50's entire daytime deficit (−$626
net). The same window **at night runs 66.7%**, so this is not the `leader50s` session effect
repackaged.

## Why it is believable (not just mined)

A minute into a *daytime* interval, the qualifying drift is already public and the book has
adjusted; a taker arriving then is the slow side of an informed market. This is the same family as
the already-validated runaway lesson (R3 / `leader50z`): **the states where you are last to know
are the states that lose**. Nights have thinner, less informed flow, and the window is fine there.

## Stability (split-half)

| | H1 (first 300) | H2 (last 300) |
|---|---|---|
| dropped bucket | n=61 50.8% −$482 | n=58 51.7% −$423 |
| twin (kept) | n=239 64.0% +$1,096 | n=242 62.4% +$748 |

Sign holds in both halves on both sides of the split.

## What was REJECTED

- **Entry-price caps.** `entry>=60c` looked strong overall (+0.041 EV/$) but **flips sign across
  halves** (+0.041 → −0.046). Classic overfit; not deployed.
- **Chasing cheaper entries.** Price is informative: 50–54¢ fills win 52.2%, 60–64¢ fills win
  65.8%. Buying cheaper mostly means buying worse. Do not target low entry price as a goal.

## The twin

`leader50t` ("Leader Clock") mirrors every leader50 fill **except** daytime (06–21 ET) fills with
`30 < entrySec <= 60`. Identical signal, identical booked price/size/fees — a strict SUBSET, so any
curve gap between the twins is pure entry-TIMING selection.

In-sample: **twin +$1,844 / 63.2% (n=481)** vs parent **+$939 / 60.8% (n=600)**.

**Bar:** judged after **n>=150 twin fills**; the parent-minus-twin gap must keep the same sign in
both halves of the forward sample. In-sample numbers are the hypothesis, not the result — the
rule was found by slicing data already looked at, so only the forward sample counts.

Paper/shadow, never orderable.
