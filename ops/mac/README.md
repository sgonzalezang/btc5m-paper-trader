# Mac host — supervisor setup

The Mac is the **dev machine + live-signal side**. It runs the same `supervisor.py`
as Virginia, with `--host mac`. While `bot/runhost.txt` says `virginia`, the Mac
supervisor just polls every ~30s and **stands down** (does not run the bot). It only
runs the bot after the flag flips to `mac`.

`com.btc5m.supervisor.plist` in this folder is the source of truth. It is **inert**
until you install it. Keep it installed only around the times you actually want to be
able to swap (i.e. when you're in Mexico and getting ready to trade); the dev Mac does
not need it running 24/7.

## Enable (when you're ready to be swap-capable)
```sh
cp ~/btc5m-paper-trader/ops/mac/com.btc5m.supervisor.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.btc5m.supervisor.plist
```
Verify it came up and is correctly standing down (flag is still `virginia`):
```sh
tail -f ~/btc5m-paper-trader/bot/supervisor.log
# expect: "supervisor up as 'mac'"  then each cycle it stays stood-down
python3 ~/btc5m-paper-trader/bot/supervisor.py --host mac --once   # prints would_run=False
```

## Swap the active host (Discord)
Only after the Mac supervisor is confirmed up:
```
/btc runhost mac        # Mac takes over; Virginia does a final publish and stands down
/btc runhost virginia   # hand it back
```
The winner adopts the latest ledger via `--sync-on-start`, so the P&L is continuous.
**Only one host runs at a time** — never flip the flag to `mac` unless the Mac
supervisor is actually running, or nothing picks the bot up until the dead-man's
switch fires on Virginia (~7 min).

## Disable (going back to Virginia-only)
Flip the flag to `virginia` first and wait for the Mac to stand down, then:
```sh
launchctl unload ~/Library/LaunchAgents/com.btc5m.supervisor.plist
rm ~/Library/LaunchAgents/com.btc5m.supervisor.plist
```

## Notes
- Python: `/usr/bin/python3` (3.9.6). The bot `--selftest` passes on it.
- The HMAC secret / webhook come from `bot/signal.env` (gitignored); the supervisor
  loads it automatically when it starts the bot.
- `KeepAlive` is on so the supervisor's self-reload (exit 3 on a code change) respawns
  it on the new code — the Mac equivalent of Virginia's restart-on-failure.
