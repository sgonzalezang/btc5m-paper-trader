# BTC 5-Minute Paper Bot — 24/7 headless runner (macOS)

A headless Python port of the browser trader. Same strategy, two engines
(strict 10/10 + loose N/10), but it runs as a background service with **no
browser tab** — fixing the tab-throttling / must-stay-visible problem.

- **Read-only, simulated fills only.** Never signs or places a real order.
- **Pure Python 3 stdlib** — no `pip install`.
- Keeps a local `state.json` ledger that **resumes after restart**.
- Optionally publishes `state.json` to a `data` branch every ~30 min (and on
  each settled trade) so you can glance at it from `live.html` without keeping
  anything open.

## 0. Prerequisites

- macOS with Python 3 (`python3 --version` — 3.8+; macOS ships one).
- A local clone of **btc5m-paper-trader** with push access (the same clone your
  session already uses to deploy). The bot lives in its `bot/` folder.

## 1. Smoke-test that live data flows (do this first)

```bash
cd ~/btc5m-paper-trader/bot
python3 btc5m_bot.py --selftest      # offline logic — should print ALL PASS
python3 btc5m_bot.py --once          # ONE live tick, prints a data check
```

`--once` prints a **LIVE DATA CHECK** block. You want:

```
  Gamma market : OK  btc-updown-5m-1783200000
  Spot feed    : Coinbase  open=... last=...
  CLOB book Up : bid .. / ask .. / top-ask $..
  RESULT       : HEALTHY — live data is flowing.
```

If it says `NOT FOUND` for the market, just run it again — a 5-minute market
occasionally isn't listed for the first second or two of a new interval. If the
**spot feed** is NONE, your machine can't reach the exchanges (check network).

## 2. Run it by hand (foreground) to watch it work

```bash
python3 btc5m_bot.py --asset BTC --loose 6 --stake 5 --slip 1
```

Leave it a few minutes; you'll see `[LOOSE] ENTER …` lines appear (loose fires
often; strict rarely). Ctrl-C to stop. The ledger is saved in `state.json`.

Flags: `--asset {BTC,ETH,SOL,XRP,DOGE}` · `--profile {conservative,aggressive}`
· `--loose N` (loose enters at N/10) · `--stake $` · `--slip ¢` · `--bank $`.

## 3. Install as a 24/7 service (launchd)

1. Edit **run.sh** if you want different flags (asset, loose N, stake).
2. Edit **com.btc5m.paper.plist**: replace `/Users/USERNAME/btc5m-paper-trader`
   with your real clone path.
3. Install and start:

```bash
chmod +x ~/btc5m-paper-trader/bot/run.sh
cp ~/btc5m-paper-trader/bot/com.btc5m.paper.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.btc5m.paper.plist
launchctl list | grep btc5m           # a PID = running
tail -f ~/btc5m-paper-trader/bot/bot.log
```

`KeepAlive` relaunches it if it crashes; `RunAtLoad` starts it on login.
`run.sh` wraps the bot in `caffeinate -i` so the Mac won't **idle**-sleep while
it runs — but keep the Mac **plugged in** (lid-closed on battery still sleeps).

Stop / restart:

```bash
launchctl unload ~/Library/LaunchAgents/com.btc5m.paper.plist
launchctl load  -w ~/Library/LaunchAgents/com.btc5m.paper.plist
```

## 4. Publishing to the website (optional)

`run.sh` passes `--publish`, which force-updates a **`data`** branch with a
single orphan commit holding only `state.json`. This never touches `main` and
never grows history, so it won't rebuild or clutter your Pages site.

`live.html` (in the repo root) reads that branch and shows both ledgers plus a
**heartbeat age** — so you can tell at a glance whether the bot is actually
alive. Open it at your Pages URL: `…/live.html`. (Publishing needs the bot's
`--repo-dir` to be a clone whose `origin` you can push to.)

Turn publishing off by removing `--publish` from `run.sh`; the bot then just
keeps `state.json` locally.

## What it does NOT do

No real orders, no wallet, no keys. Real execution would need an authenticated
CLOB client, EIP-712 order signing, latency work, and jurisdiction checks —
out of scope until the paper ledger proves the edge (win rate must beat the
average entry price by ~5 points).
