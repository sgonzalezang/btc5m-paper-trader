#!/bin/bash
# 24/7 launcher for the BTC 5-minute paper bot.
#   · caffeinate -i keeps the Mac from *idle*-sleeping while the bot runs
#     (it can still sleep if you close the lid on battery — keep it plugged in).
#   · Runs from this script's own directory; the repo root (one level up) is
#     the git clone the bot publishes state.json into (on the `data` branch).
# Edit the flags below to taste (asset, loose threshold, stake, cadence).
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd .. && pwd)"

# Optional live-signal bridge (see SIGNAL-BRIDGE.md). OFF unless bot/signal.env
# exists (untracked — never commit it). It should export:
#   SIGNAL_ENGINES=band                     # which engines emit ENTER signals
#   SIGNAL_FILE=$PWD/signal.json            # optional local drop file
#   BTC5M_SIGNAL_WEBHOOK=https://discord.com/api/webhooks/...   # keep secret
#   BTC5M_SIGNAL_SECRET=<random hex>        # HMAC key the executor verifies
[ -f signal.env ] && . ./signal.env

exec caffeinate -i /usr/bin/env python3 btc5m_bot.py \
  --asset BTC \
  --loose 7 \
  --stake 50 \
  --bank 1000 \
  --slip 1 \
  --profile conservative \
  --state "$(pwd)/state.json" \
  --publish \
  --branch data \
  --repo-dir "$REPO" \
  --publish-every 300 \
  --signal-engines "${SIGNAL_ENGINES:-}" \
  --signal-file "${SIGNAL_FILE:-}" \
  >> "$(pwd)/bot.log" 2>&1
