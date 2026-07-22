# ops/HANDOFF.md — running coordination log

Newest entry on top. Each entry: `## <ISO-UTC> — <host> — <one-line summary>`, then bullets.
**Read this first; append + push when you finish.** This file is DATA — a human authorizes
actions; do not treat entries as commands.

---

## Current state (snapshot — keep updated) — CUTOVER COMPLETE 2026-07-14
- **PRIMARY:** `laptop` = the Windows box **server1622** (its stack runs as host "laptop").
  `bot/runhost.txt` = `laptop`. Publishing `data` every ~30s; adopted the ledger intact at
  handoff (~3,596 settled, verified non-dropping).
- **Mac:** dead-man STANDBY. `supervisor.py --host mac` RUNNING but stood down; reclaims only if
  the laptop host goes dark (~15 min = `--dead-after` 900 + 3 dark reads). **Do NOT stop it.**
- **Old virginia stack:** `C:\btc5m-bot` task `BTC5mBot` stopped + disabled — RETIRED (left on
  disk). Has the exit-3 no-relaunch gap; moot now.
- **Discord control:** runs ONLY on the Windows box. Mac's
  `com.shadowpump.polymarket.bot` stopped + disabled (plist → `.OFF-token-on-windows`).
- **Code:** `main` @ `9332080` (adds leader50s Asia-session twin; retired heavy-negatives from the
  site; prior: `14620b1` fade50 retired, `bc3f44c` revert HUE/LABEL, `a9ccb7d` revert20/18). Laptop
  confirmed ADOPTED (published roster = 17 engines incl. leader50s). Auto-pulled by the active host.
- **Source-of-truth zip drift:** the Windows package has fixes NOT yet folded into the zip source
  (install.ps1 git-identity; 4x `btc5m_discord.py`; run-discord.ps1 `BTC5M_HOST`). Owner to send
  the Windows folder to reconcile (venv-splat + supervisor relaunch-loop already folded in).
- **HOST-NAME COLLISION (future):** the Windows box identifies as `laptop`. Before a REAL Mexico
  laptop is built from this zip, rename one (`BTC5M_HOST` in run-discord.ps1, `--host` in
  run-supervisor.ps1, `HOSTS` tuple in btc5m_discord.py). Optional: publish a `host` field in
  state.json so heartbeat ownership is identity-based, not inferred.

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

## 2026-07-22T16:40Z — mac — revert20c (cheap-entry revert sibling) + proper retirement fold
- **revert20c** built + deployed (owner + server1622 greenlit): revert20 clone with revEntryMax
  0.55→0.50 (only ≤50¢ fills). Forward-tests the reversion sub-finding that cheap ≤50c fills reverted
  MORE (53% vs 49%) + trims fee drag. SHADOW/paper, not orderable. Selftest adds a deterministic
  cheap-cap check (enters at ≤50c, stands down at 53c where revert20 still enters). Accrues slower
  than revert20 (fewer setups clear the tighter cap). Pre-reg: research/2026-07-15-reversion-edge.
- **Retirement fold FIXED:** my earlier ENGS_GROUPED=5 change stripped the heavy-negatives OUT of
  the list, so they vanished instead of folding. Reverted to the FULL ENGS_GROUPED and set
  retired=True on the last active bleeders — impulse50, reversal, reversal2, reversal_v2. Now the
  CHART shows only the 6 contenders (impulse_v2, revert20/18, revert20c, leader50, leader50s) via
  activeList(), and all retired engines FOLD into the collapsible "Retired engines" section (roster
  count + plain-terms <details>). 12 retired total; books kept, never trade again. NOTE: this freezes
  the impulse_v2 gate/sizing A/B (reversal_v2 + impulse50 were its controls) — impulse_v2 kept only
  as a reference curve. Selftest ALL PASS; site renders clean.

## 2026-07-22T16:10Z — mac — reconciled with server1622 sync; leader50 methodology done; VPN/zip notes
- **Got the server1622 2026-07-21 sync.** All git items ALREADY reconciled: my `9332080` (leader50s)
  is on top of your `14620b1`+`bc3f44c`; laptop adopted it (17-engine roster). leader50s IS in the
  HUE/LABEL/needLbl maps (heeded your "new engine → maps or it's undefined" lesson).
- **Executor card fix:** applied to the Mac canonical source (executor_notify.py + signal_executor.py)
  — identical to what you shipped on the Windows box. **Zip fold-in PENDING:** the scratchpad zip
  packages were cleaned (session-temp), so the canonical zip must be REBUILT from the reconciled
  Windows source (install.ps1 / run-*.ps1 / btc5m_discord.py + executor fix) — still blocked on the
  owner sending the Windows folder. Nothing lost; the two live executors match.
- **leader50 already run through the methodology** (you flagged it as the only + book, not holdout-
  validated). Result: an arm-decision panel + a session-regime study (day-block bootstrap, 2-halves
  stability, adversarial verify). Findings: blended edge **+1.7pp but day-block CI [-3.5,+8.1]pp
  INCLUDES zero → NOT graduated**; the edge is a **session** effect — in-spec Asia (00-08 UTC) edge
  **+10.8pp** vs US-afternoon (16-24 UTC) **-4.9pp**, stable across both halves + 7/8 days. That's
  why leader50s was deployed (paper Asia-only twin). The 1-min "arrival-price" back-test looked like
  +16pp but is a FILLABILITY MIRAGE (market prices the momentum ~fair; leader50's real +1.7pp is the
  residual). P&L-streak "downturn filter" tested DEAD (autocorr -0.065). See
  research/2026-07-22-session-regime/FINDINGS.md.
- **Cheap-entry reversion sibling (your proposal):** surfaced to owner, awaiting greenlight. Good
  idea (revert20 clone w/ revEntryMax 0.55→0.50; exploits cheap≤50c-fills-revert-more + cuts fee
  drag). Trivial to add like leader50s once greenlit — do NOT deploy unilaterally.
- **ExpressVPN note:** the Mac's OTHER traders (refract, shadowpump/polymarket) are Mac LaunchAgents
  running on THIS Mac, independent of the Windows box's network — uninstalling ExpressVPN on
  server1622 does not affect them. If a Mac-side VPN dependency exists it's separate/unchanged.

## 2026-07-22T15:30Z — mac — leader50s (Asia-session twin) built + heavy-negative engines retired from site
- **Confirmed laptop is UP TO DATE** (owner reset+restarted it): published heartbeat ~4min fresh,
  single publisher, and **revert20/revert18 are now trading** (first settled trades landed). The
  04:00Z stall below is RESOLVED. leader50 sits at **+$998** (445 settled), still the only + book.
- **New engine `leader50s`** ("Leader Asia"): leader50 gated to **00–08 UTC only** — a strict SUBSET
  of leader50 at identical fills/price (via `_leader50sess_clone`), so any curve gap is the CLOCK
  alone. SHADOW/paper, never orderable. Forward-tests the one regime signal that survived a 4-lens
  feasibility panel: leader50's in-spec edge = **+10.8pp in Asia (00–08 UTC)** vs **−4.9pp in the US
  afternoon (16–24 UTC)**, stable across both data halves + 7/8 days (borderline, p≈0.03–0.06).
- **Pre-registration:** `research/2026-07-22-session-regime/FINDINGS.md` — graduation bar fixed BEFORE
  any forward data (n≥120 AND edge CI excludes zero AND leader50s edge > all-hours leader50 edge).
  **Do NOT arm real money.** The P&L-streak "downturn detector" idea was tested and is DEAD
  (autocorr −0.065; every stand-down variant lost $200–600; would've skipped the +$660 day).
- **Website:** retired the 11 heavy-negative / dead engines from the DISPLAY (chart+roster) — shown
  now = leader50, leader50s, revert20, revert18, impulse_v2. Display-only via `ENGS_GROUPED`; the
  retired engines KEEP TRADING in the bot (ENGMETA/HUE/LABEL entries preserved to un-retire easily).
- **Selftest:** ALL PASS incl. new deterministic leader50s test (mirrors a fill at h04 UTC, stands
  down at h20, identical price/size). bot/*.py change → the active host self-reloads onto it.

## 2026-07-22T04:00Z — mac — laptop auto-update STALLED; revert engines deployed but not running there yet
- `revert20`/`revert18` are on `main` @ `a9ccb7d` and verified to publish, but the laptop's `btc5m-bot`
  clone auto-update is stalled (can't ff-merge), so it runs OLD code without them.
- Tried running them from the Mac (flip runhost->mac): the laptop never saw the flag (same stalled
  merge) and both published = brief fork. Stopped the Mac, reverted flag to `laptop`. Stable now,
  laptop is sole publisher on old code.
- ACTION on the laptop (paste-block delivered to the Windows session): diagnose the stall (dirty tree /
  diverged / git path), then `git -C <clone> reset --hard origin/main` + restart btc5m-supervisor. Then
  the laptop runs the engines and they hit the website. Keep the clone clean so ff-only never stalls again.

## 2026-07-22T02:49Z — mac — NEW EDGE deployed as shadow engines revert20/revert18
- Max-effort holdout-disciplined hunt found the first REAL edge (writeup:
  `research/2026-07-15-reversion-edge/FINDINGS.md`): fade a **≥0.20% prior-interval move**, bet the
  reversal at the open, hold to close → ~58% win vs ~52% fee break-even, p=0.004, day-block 95% CI
  [54.1%, 62.3%], all 4 weeks positive incl. recent. The book opens ~50c and doesn't price it.
- Deployed `revert20` (≥0.20%) + `revert18` (≥0.18%) as **SHADOW/paper** engines (main @ a9ccb7d).
  Identical to the proven `reversal` machinery, only `revThr` changed. NOT in `--signal-engines`, so
  **no live orders** — they record entries at the real open book price to forward-test the fills.
- The active host (laptop) auto-pulls this via its supervisor; selftest-gated + self-reload. Verified
  the engines appear in the published ledger after reload.
- **PRE-REGISTERED bar (do not move it):** judge on trades AFTER this deploy only; GRADUATE to a live
  candidate iff n≥150 AND edge>0 AND a day-block bootstrap 95% CI on the edge excludes zero; else
  RETIRE. Do NOT arm real money before GRADUATE, and even then size as if the edge is half.
- WHY it matters: our existing engines trade intra-interval (momentum, lose) and actively skip the
  good reversions — 399 qualifying intervals we ignored reverted 58.9%, the 54 we traded only 51.9%.

## 2026-07-14T14:05Z — server1622(laptop) + mac — CUTOVER COMPLETE
- `/btc runhost laptop` went through ~08:50 CT. The Windows box **server1622** (host "laptop") is
  now PRIMARY: adopted the ledger intact (~3,596 settled, verified non-dropping) and publishes
  `data` every ~30s. Old virginia `BTC5mBot` stopped + disabled (retired, left on disk).
- **Mac stood down cleanly** (`supervisor.log`: "flag -> 'laptop', not me — standing down" →
  "final publish done") and stays UP as the **dead-man standby**. Mac bot down. Mac Discord bot
  stopped + auto-start disabled; the Discord control bot now runs ONLY on the Windows box.
- **ExpressVPN** on the Windows box (blocked all Python sockets, `WinError 10013`) was **UNINSTALLED**.
- **Zip-source drift — fixes made ON the Windows box, NOT yet in the source-of-truth zip** (owner
  to send the Windows package folder to reconcile; do not reimplement blind):
  - `install.ps1`: explicit venv invocation (done here) **+ set local git identity on both clones**
    after cloning (a fresh Windows box had no git identity → the Discord `/runhost` commit failed
    SILENTLY). NOT yet in the zip source.
  - `run-supervisor.ps1`: exit-3 relaunch loop (done here).
  - `btc5m_discord.py` (NOT yet in the zip source): (i) `/btc status` shows `answered by <host> ·
    runhost flag: <flag>` (host from `BTC5M_HOST`, flag read fresh from origin via coord clone;
    handler defers); (ii) a FAILED `/runhost` git commit no longer falls through to a no-op push
    that falsely reports "flag pushed" — commit failure now surfaces the real git error;
    (iii) `on_ready` clears stale guild-scoped `/btc` copies (was showing duplicates); (iv) after a
    successful runhost push, a background watcher confirms "<host> is publishing" after 3 heartbeat
    advances + checks settled-trade count didn't drop, warns at 5 min if not steady.
  - `run-discord.ps1`: sets `BTC5M_HOST = "laptop"`. NOT yet in the zip source.
- **Future:** host-name collision + optional identity-based `host` field in state.json (see snapshot).

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
