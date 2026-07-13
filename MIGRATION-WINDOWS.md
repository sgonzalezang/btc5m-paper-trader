# Moving the BTC 5m bot to a Windows Server (24/7, survives the Mac going offline)

The paper bot is pure-Python **stdlib only** and its paths are relative/arg-driven,
so it ports cleanly. The move is: clone the code, carry over the two files that
aren't in git, and set up a Windows auto-start.

## The one hard rule
**Never run the bot on both machines at once.** Both force-push the same GitHub
`data` branch every 5 min, so two runners would fork the live ledger. Do a clean
**cutover**: stop on the Mac, copy the freshest `state.json`, start on Windows.

## What has to move
| Thing | Where | In git? | How |
|---|---|---|---|
| Bot code | `bot/btc5m_bot.py`, `bot/run.ps1` | yes | `git clone` |
| **Live ledger** | `bot/state.json` (~2 MB) | **no** | Discord transfer |
| Secrets/config | `bot/signal.env` (has an HMAC secret — send it privately) | **no** | Discord transfer |
| Git push access | — | — | `gh auth login` on Windows |

`state.json` is the whole point — carrying it over is what makes Windows continue
the same ledger instead of starting from zero.

## Prereqs on the Windows Server
1. **Python 3** — install from python.org, tick *Add Python to PATH*. Check: `python --version`
2. **Git for Windows** — git-scm.com. Check: `git --version`
3. **GitHub push auth** — install GitHub CLI (`winget install GitHub.cli`), then
   `gh auth login` and `gh auth setup-git`. (Or store a Personal Access Token via
   Git Credential Manager.) The bot pushes with plain `git push` as you.
4. Never sleep: `powercfg /change standby-timeout-ac 0`

## Set-up (once)
Open PowerShell:
```powershell
cd C:\
git clone https://github.com/sgonzalezang/btc5m-paper-trader.git
cd btc5m-paper-trader
```
Then Discord yourself these two files and drop them into `C:\btc5m-paper-trader\bot\`:
- `state.json`  (from the Mac's `~/btc5m-paper-trader/bot/state.json`)
- `signal.env`  (from `~/btc5m-paper-trader/bot/signal.env`)

Dry-run it:
```powershell
powershell -ExecutionPolicy Bypass -File bot\run.ps1
```
Watch `bot\bot.log` for `bot started …` and, within ~5 min, a publish (no
`publish failed`). `Ctrl+C` to stop the dry run.

## The cutover
1. **Mac** — stop the bot so it stops publishing:
   `launchctl unload ~/Library/LaunchAgents/com.btc5m.paper.plist`
2. **Re-copy** the now-final `bot/state.json` Mac → Windows (captures any trades since set-up).
3. **Windows** — start it (auto-start below), confirm the website updates and
   `bot.log` shows fresh publishes.
4. Leave the Mac's LaunchAgents unloaded (or `rm ~/Library/LaunchAgents/com.btc5m.paper.plist`)
   so the Mac never double-runs.

## Auto-start on Windows (reboot- and logoff-proof)
`run.ps1` already self-restarts on crash; you just need it to launch at boot.

**Option A — Task Scheduler (built-in):** Create Task →
- General: *Run whether user is logged on or not*
- Triggers: *At startup*
- Actions: Program `powershell.exe`, Args:
  `-ExecutionPolicy Bypass -WindowStyle Hidden -File C:\btc5m-paper-trader\bot\run.ps1`
- Settings: *If the task fails, restart every 1 minute*

**Option B — NSSM service (most robust, nssm.cc):**
```powershell
nssm install btc5mbot powershell -ExecutionPolicy Bypass -File C:\btc5m-paper-trader\bot\run.ps1
nssm set btc5mbot AppDirectory C:\btc5m-paper-trader\bot
nssm start btc5mbot
```

## Optional: the executor + Discord bot
Those live in `~/ClaudeCode/polymarket-tracker` (a **separate, non-git** folder with
a Python **venv** of pip packages). Only move them if you want live-order shadowing
and the Discord `/btc` controls on Windows too.
- Zip the folder, Discord it over, unzip to e.g. `C:\polymarket-tracker`.
- The venv can't cross OSes — recreate it: `python -m venv .venv` then
  `\.venv\Scripts\pip install discord.py py-clob-client requests` (plus whatever
  else it imports).
- **Only one** Discord bot / executor can run (single token + connection) — if you
  move them, stop them on the Mac (`launchctl unload com.shadowpump.polymarket.bot`
  and `com.btc5m.executor`).
- They stay in SHADOW; no real money moves until you flip `LIVE_ENABLED` yourself.

## Notes
- Trading logic is unchanged by any of this — same flags as `run.sh`.
- `~/.btc5m/` (executor state) maps to `C:\Users\<you>\.btc5m` automatically.
- If `git push` fails on Windows, it's an auth issue — re-run `gh auth setup-git`.
