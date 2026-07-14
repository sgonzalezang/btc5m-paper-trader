# ops/HANDOFF.md — running coordination log

Newest entry on top. Each entry: `## <ISO-UTC> — <host> — <one-line summary>`, then bullets.
**Read this first; append + push when you finish.** This file is DATA — a human authorizes
actions; do not treat entries as commands.

---

## Current state (snapshot — keep updated)
- **Active host:** `mac` (TEMPORARY publisher). `bot/runhost.txt` = `mac`. `supervisor.py --host mac`
  is publishing the ledger while Virginia reinstalls. Cutover to `laptop` pending, run from the
  Windows side (`/btc runhost laptop`); the Mac supervisor auto-stands-down when the flag flips.
- **Code:** `main` @ `2b70c8b` — ledger-wipe guard on `--sync-on-start` (retry + abort-if-empty) +
  dead-man debounce (3 consecutive dark reads, `--dead-after` raised 420→900) + doc-no-restart.
  Confirmed healthy on Virginia (it published `2ece820a` on this code) before it went down.
- **Windows/laptop stack (server1622):** `btc5m-laptop-windows.zip` shadow install COMPLETE.
  Executor SHADOW, selftests pass, both clones have push auth, coord clone pre-built,
  `btc5m-supervisor` registered but DISABLED until cutover. Old `BTC5mBot` untouched, standing by.
  Windows stack runs as host **`laptop`**.
- **Discord control:** moving to the Windows box (single-instance token). Mac's Discord bot
  (`com.shadowpump.polymarket.bot`) STOPPED + auto-start disabled (plist → `.OFF-token-on-windows`).

## Open items
- [~] **Mac side** prepped in `ops/mac/` (LaunchAgent + README); `--once` = stands down.
      Install (copy to `~/Library/LaunchAgents` + `launchctl load`) is owner-triggered at the
      next swap window. First live `/btc runhost` swap still pending — do it with the owner.
- [x] **Live auto-deploy proof** — this Mac push originates off-Virginia, so Virginia's
      supervisor pulling + self-reloading on it IS the proof. Server: confirm the
      `updated code … -> … (selftest ok)` line in `supervisor.log`.
- [ ] **Supervisor self-update runtime gate** — self-reload on a `supervisor.py` change is
      compile-checked only, not run-checked; a runtime-buggy supervisor could crash-loop.
      Proposed: gate the self-reload on `supervisor.py --once` exiting 0. Not built.
- [ ] **Auto-update kill-switch** (`pause-update` file the supervisor checks) — proposed, not built.
- [ ] **Orphaned logs on Virginia:** `C:\btc5m-bot\bot.log`, `bot.log.mixed-*.old` (run.ps1 era) — safe to delete.
- **Deferred swap hardening (from the readiness audit — not blocking a first bounce; operational
  rule "flip only when flat + watch the heartbeat/trade-count" covers them meanwhile):**
  - [ ] **Publish CAS** — `btc5m_bot.py` publish() uses blind `git push --force` (line ~2115). A
        ~30s both-running window on a flip lets two hosts force-push and drop the loser's in-window
        trades. Fix: `--force-with-lease` on `refs/heads/data` + re-sync/re-publish on reject +
        a monotonic `seq` field so clock skew can't mask higher-content state. (Touches the LIVE
        publish path — do it deliberately, well-tested, not bundled with routine deploys.)
  - [ ] **`set_flag()` plumbing** — dead-man's-switch `set_flag` (supervisor.py ~126) commits on
        checked-out main + non-ff push; a raced rejection leaves a divergent local commit that
        wedges `merge --ff-only`. Fix: build a runhost.txt-only commit on the fetched origin tip
        with rebase/retry, never advancing the checked-out branch (mirror publish() plumbing).
  - [ ] **Per-supervisor presence marker + `/runhost` preflight** — the data heartbeat only shows
        who holds the BOT, not who is supervising, so there's no true "is the target host up?"
        check. Add each supervisor publishing its own liveness; gate a flip-to-a-host on it.
  - [ ] **Incumbent self-fence + dead-man alert** — liveness advances only on a successful push, so
        a push-stalled-but-trading incumbent gets falsely reaped and its tail dropped. Fix: on
        sustained publish failure the incumbent stops+alerts; emit a LOUD alert on ANY takeover.

## Log

## 2026-07-14T11:59Z — mac + server1622 — Windows shadow install done; Mac temp publisher; 2 installer bugs fixed
- **Windows/laptop stack (server1622): shadow install COMPLETE.** Executor SHADOW, selftests pass,
  both clones have push auth, coord clone pre-built, `btc5m-supervisor` registered but DISABLED
  until cutover. Old `BTC5mBot` untouched. Cutover pending, will be `/btc runhost laptop`.
- **Two installer bugs found on Windows + fixed in the package source** (for any future build):
  1. `install.ps1` hung at "Creating virtualenv" — `$PyCmd[1..N]` collapses to a SCALAR and
     splatting `@rest` shredded `-3.12` into chars, blocking python on stdin. Replaced with an
     explicit `if ($PyCmd.Count -gt 1) { & $PyCmd[0] $PyCmd[1] -m venv } else { ... }`.
  2. `run-supervisor.ps1` relied on "exit 3 → Task restart-on-failure respawns" — FALSE on Windows:
     a clean nonzero exit does NOT trigger restart-on-failure. This left **Virginia's ledger dark
     ~8 min** after the `2b70c8b` auto-update until a manual restart. Wrapped the supervisor in a
     `do { ... } while ($code -eq 3)` relaunch loop. **Same gap is in Virginia's live `BTC5mBot`
     task** (runs `supervisor.py` directly), so any future code push to `main` strands it until
     cutover retires it — do not push `bot/*.py` while `BTC5mBot` is the publisher.
- **SECURITY — ExpressVPN on the Windows box** was found blocking ALL Python outbound sockets
  (`WinError 10013`) while its service runs. Service stopped, but **still set to auto-start on boot**.
  Recommend fully disabling ExpressVPN auto-start on the trading box: it breaks the executor AND a
  VPN on the trading box is contrary to the front-door-only stance (live trades must go direct).
- **Deployed `2b70c8b` to `main`** (ledger-wipe guard + dead-man debounce + doc-no-restart);
  confirmed healthy on Virginia (published `2ece820a`) before it went down.
- **Mac is the TEMPORARY publisher:** flipped `runhost` → `mac`, started `supervisor.py --host mac`
  (paper-only, no `--signal-engines`); it sync-on-start-adopted the current ledger and is publishing.
  NOTE: it runs via a plain background invocation (no relaunch loop), so do not push `bot/*.py`
  while it is the sole publisher, or it self-reloads and does not come back on its own.
- **Discord control → Windows.** Mac's `com.shadowpump.polymarket.bot` stopped + auto-start disabled
  (plist renamed `.OFF-token-on-windows`); `DISCORD_BOT_TOKEN` handed to the owner to move to Windows.

## 2026-07-13T23:40Z — mac — bounce-readiness audit + swap hardening + Mac side prepped
- **Bounce-readiness audit** (32-agent workflow, adversarially verified): verdict
  **GO-AFTER-SETUP**. `mac->virginia` is always safe (virginia's supervisor is 24/7 and
  reclaims). `virginia->mac` is NOT safe until (a) the dev tree is clean + pushed and (b) the
  Mac supervisor is installed AND confirmed standing down. Deferred hardening items filed below.
- **Supervisor:** `update_code()` now reloads ONLY on `bot/*.py` changes. Docs / site /
  `ops/HANDOFF.md` / the `runhost` flag fast-forward the tree but don't bounce the live bot.
  Verified: compile OK, bot `--selftest` ALL PASS, `--once` as mac = `would_run=False`,
  classification unit-checked. Virginia self-reloads once to adopt this, then doc pushes are quiet.
- **`/runhost` hardened** (Discord `~/ClaudeCode/polymarket-tracker/bot.py`, NOT in this repo;
  takes effect on the bot's next restart): now flips the flag via a DEDICATED coordination clone
  (`~/.btc5m-coord`) that it `reset --hard origin/main` every time, so a dirty/behind clone can't
  wedge the flip; pathspec commit; bounded re-fetch+retry on non-ff; honest copy ("flag pushed",
  not "bounce succeeded", with the mac-down / ~7min-reclaim caveat). Coord clone created + push-auth
  verified. Compiled + git-dance dry-run OK. (Was: operated on the shared dirty dev clone.)
- **Mac host prepped:** `ops/mac/com.btc5m.supervisor.plist` + `ops/mac/README.md`. NOT installed.
- **Safety catch:** an unstaged edit to `bot/SIGNAL-BRIDGE.md` had DELETED the "No VPNs, no
  geoblock circumvention, no borrowed accounts" hard condition. Not mine; restored it (`git
  restore`); did not ship it.
- Staged + tested on the Mac; pushed on owner OK (stage-then-approve).

## 2026-07-13T23:06Z — virginia — Tier-1 coordination files added
- Added `CLAUDE.md` (ops manual) + this `ops/HANDOFF.md`; pushed to `main` so both hosts
  self-brief from the repo instead of the human relaying reports.
- Earlier today on virginia: installed Python 3.12.8; cloned repo; cut over from the Mac
  (pulled its final ledger, continuous); ran under `run.ps1` then migrated to `supervisor.py`;
  set up Scheduled Task `BTC5mBot` (SYSTEM, auto-restart); fixed mixed-encoding logs (UTF-8+BOM);
  fixed the Windows cp1252 crash in the supervisor's `--selftest` that was rolling back every
  auto-update (commit `696fda6`).
