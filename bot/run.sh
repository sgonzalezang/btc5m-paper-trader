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

exec caffeinate -i /usr/bin/env python3 btc5m_bot.py \
  --asset BTC \
  --loose 6 \
  --stake 5 \
  --slip 1 \
  --profile conservative \
  --state "$(pwd)/state.json" \
  --publish \
  --branch data \
  --repo-dir "$REPO" \
  --publish-every 1800 \
  >> "$(pwd)/bot.log" 2>&1
