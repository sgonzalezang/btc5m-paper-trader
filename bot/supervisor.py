#!/usr/bin/env python3
"""Cross-platform supervisor for the btc5m paper bot (Mac AND Windows server).

Solves two things at once, in one loop, every ~30s:

  1. AUTO-UPDATE — fast-forward the local clone to origin/main, so both machines
     ALWAYS run the exact same latest code. A push is picked up on the next
     cycle; a change restarts the bot. If the updated code fails --selftest, the
     update is rolled back and the running bot is left alone (a bad push can't
     take down both machines).

  2. ACTIVE-HOST SWITCH (Path B) — read bot/runhost.txt (the shared flag, on
     main). If it names THIS host, ensure the bot is running; if it names the
     other host, ensure the bot is stopped. Flip the flag (e.g. from Discord)
     and the machines hand off. Ledger continuity is automatic via the bot's
     own --sync-on-start; on stop we force a final publish so the next host
     picks up the exact latest ledger.

  DEAD-MAN'S SWITCH — if the flag names the OTHER host but that host has gone
  dark (no fresh publish on the data branch for --dead-after seconds), this host
  takes over AND rewrites the flag to itself, so the bot never stays down after
  an unclean shutdown.

Run it (each machine, once, e.g. from a LaunchAgent / Scheduled Task):
    python supervisor.py --host virginia
    python supervisor.py --host mac --signal-engines "impulse_v2,leader50,..."

Only ONE host may be active at a time; the flag enforces that.
"""
import argparse, json, os, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def log(msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')}  [sup] {msg}"
    print(line, flush=True)
    try:
        with open(os.path.join(HERE, "supervisor.log"), "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def git(*a, cwd=REPO, ok=(0,)):
    r = subprocess.run(("git",) + a, cwd=cwd, capture_output=True, text=True)
    if r.returncode not in ok:
        raise RuntimeError(f"git {' '.join(a)}: {r.stderr.strip()}")
    return r.stdout.strip()


def head():
    try: return git("rev-parse", "HEAD")
    except Exception: return None


def raw_json(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "btc5m-sup/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


class Sup:
    def __init__(self, args):
        self.a = args
        self.proc = None
        self.py = args.python or sys.executable or "python"

    # ---- code auto-update -------------------------------------------------
    def update_code(self):
        """Fast-forward to origin/main. Returns True if the code changed AND the
        new code passes --selftest (so it's safe to (re)start on it). If the new
        code fails selftest, roll back and return False (keep old code)."""
        before = head()
        try:
            git("fetch", "-q", "origin", self.a.branch_code)
            target = git("rev-parse", f"origin/{self.a.branch_code}")
        except Exception as e:
            log(f"fetch skipped: {e}"); return False
        if target == before:
            return False
        try:
            # fast-forward ONLY: updates a clean clone (the server), but refuses to
            # discard local commits or uncommitted edits (the Mac dev machine) —
            # it just skips the update until the tree is clean. state.json/bot.log
            # are gitignored, so they're never touched either way.
            git("merge", "--ff-only", target)
        except Exception as e:
            log(f"update skipped (tree not fast-forwardable — keeping current code): {e}"); return False
        # gate the new code on the offline selftest
        r = subprocess.run((self.py, os.path.join(HERE, "btc5m_bot.py"), "--selftest"),
                           cwd=HERE, capture_output=True, text=True)
        if r.returncode != 0:
            log(f"NEW CODE {target[:7]} FAILED selftest — rolling back to {before[:7]}, keeping old code")
            if before: git("reset", "--hard", before)
            return False
        log(f"updated code {(before or '?')[:7]} -> {target[:7]} (selftest ok)")
        return True

    # ---- the flag ---------------------------------------------------------
    def flag(self):
        try:
            with open(os.path.join(HERE, "runhost.txt")) as f:
                return f.read().strip().lower()
        except Exception:
            return "virginia"   # safe default

    def set_flag(self, host):
        """Rewrite runhost.txt on main (used by the dead-man's switch)."""
        try:
            with open(os.path.join(HERE, "runhost.txt"), "w") as f:
                f.write(host + "\n")
            git("add", "bot/runhost.txt")
            git("commit", "-m", f"runhost: {host} (supervisor failover)", ok=(0, 1))
            git("push", "origin", f"HEAD:{self.a.branch_code}")
            log(f"flag rewritten -> {host}")
        except Exception as e:
            log(f"set_flag failed: {e}")

    def other_host_alive(self):
        """Dead-man's switch input: is the flagged (other) host still publishing?
        True if the data-branch heartbeat is fresh, else False."""
        d = raw_json(self.a.state_url)
        if not (isinstance(d, dict) and d.get("heartbeat")):
            return True   # can't tell -> assume alive (don't fight for control)
        age = time.time() - d["heartbeat"] / 1000.0
        return age < self.a.dead_after

    # ---- bot process ------------------------------------------------------
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def bot_cmd(self):
        state = os.path.join(HERE, "state.json")
        cmd = [self.py, os.path.join(HERE, "btc5m_bot.py"),
               "--asset", "BTC", "--loose", "7", "--stake", "50", "--bank", "1000",
               "--slip", "1", "--profile", "conservative", "--state", state,
               "--publish", "--branch", self.a.branch_data, "--repo-dir", REPO,
               "--publish-every", "300", "--signal-file", os.path.join(HERE, "signal.json"),
               "--sync-on-start"]
        if self.a.signal_engines:
            cmd += ["--signal-engines", self.a.signal_engines]
        return cmd

    def start(self):
        if self.running(): return
        env = dict(os.environ)
        # load signal.env for the HMAC secret / webhook if present (Mac side)
        envf = os.path.join(HERE, "signal.env")
        if os.path.exists(envf):
            for raw in open(envf):
                s = raw.strip().lstrip("export ").strip()
                if s and not s.startswith("#") and "=" in s:
                    k, v = s.split("=", 1); env[k.strip()] = v.strip()
        logf = open(os.path.join(HERE, "bot.log"), "a")
        self.proc = subprocess.Popen(self.bot_cmd(), cwd=HERE, env=env,
                                     stdout=logf, stderr=subprocess.STDOUT)
        log(f"started bot (pid {self.proc.pid})")

    def stop(self):
        if not self.running():
            self.proc = None; return
        log("stopping bot (final publish first)")
        try:
            self.proc.terminate()
            self.proc.wait(timeout=20)
        except Exception:
            try: self.proc.kill()
            except Exception: pass
        self.proc = None
        # force a final publish so the next host adopts the exact latest ledger
        try:
            sys.path.insert(0, HERE)
            import btc5m_bot as B
            B.publish(os.path.join(HERE, "state.json"), self.a.branch_data, REPO)
            log("final publish done")
        except Exception as e:
            log(f"final publish skipped: {e}")

    # ---- main loop --------------------------------------------------------
    def loop(self):
        me = self.a.host.lower()
        log(f"supervisor up as '{me}' (repo {REPO})")
        while True:
            try:
                changed = self.update_code()
                want = self.flag()
                mine = (want == me)
                if not mine and not self.other_host_alive():
                    log(f"flag says '{want}' but that host is dark — taking over")
                    self.set_flag(me); mine = True
                if mine:
                    if not self.running():
                        self.start()
                    elif changed:
                        log("code changed — restarting bot on new version")
                        self.stop(); self.start()
                else:
                    if self.running():
                        log(f"flag -> '{want}', not me — standing down")
                        self.stop()
            except Exception as e:
                log(f"loop error: {e}")
            time.sleep(self.a.poll)


def main():
    ap = argparse.ArgumentParser(description="btc5m bot supervisor (auto-update + active-host switch)")
    ap.add_argument("--host", required=True, help="this machine's name, e.g. 'mac' or 'virginia' (must match runhost.txt values)")
    ap.add_argument("--signal-engines", default="", help="engines to emit signals for (Mac/live side only; empty = none)")
    ap.add_argument("--python", default="", help="python executable to run the bot with (default: this one)")
    ap.add_argument("--branch-code", default="main")
    ap.add_argument("--branch-data", default="data")
    ap.add_argument("--poll", type=int, default=30, help="seconds between cycles")
    ap.add_argument("--dead-after", type=int, default=420, help="seconds without a published heartbeat before the flagged host is presumed dead")
    ap.add_argument("--state-url", default="https://raw.githubusercontent.com/sgonzalezang/btc5m-paper-trader/data/state.json")
    ap.add_argument("--once", action="store_true", help="run a single decision cycle and exit (for testing)")
    args = ap.parse_args()
    sup = Sup(args)
    if args.once:
        sup.update_code()
        want = sup.flag()
        print(f"[once] host={args.host} flag={want} would_run={(want==args.host.lower())}")
        return
    sup.loop()


if __name__ == "__main__":
    main()
