"""Tests for INDEX.md upkeep: the reindex hook, the last-good PR table, the lock,
and the session-start refresh. Throwaway repos; parts 2 and 4 call GitHub read-only.
    python3 plugins/devkit/tests/test_reindex.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_setup as ts  # noqa: E402

HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks")
REINDEX = os.path.join(HOOKS, "reindex.py")
SESSION_SYNC = os.path.join(HOOKS, "session_sync.py")
ISSUES = "plans-local/issues"
INDEX = f"{ISSUES}/INDEX.md"
check = ts.check


def hook(script, payload):
    return subprocess.run([sys.executable, script], input=json.dumps(payload), capture_output=True, text=True)


def sync(repo, *flags):
    return ts.sh(repo, sys.executable, f"{ISSUES}/sync_index.py", *flags)


def set_config(repo, **issues):
    path = os.path.join(repo, ".claude", "devkit.json")
    with open(path, encoding="utf-8") as fh:
        config = json.load(fh)
    config["issues"].update(issues)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)


def seed_pr_section(repo, when):
    """Replace the Open PRs section with a good table read at `when`."""
    text = ts.read(repo, INDEX).split("## Open PRs")[0]
    text += (
        "## Open PRs\n\n"
        f"Read from github at {when:%Y-%m-%d %H:%M}. Run `sync_index.py` by hand to refresh.\n\n"
        "| PR | Title | Author | Approved by | Checks | Merge state | Issues |\n"
        "|---|---|---|---|---|---|---|\n"
        "| [#7](https://example.com/7) | Seeded PR | someone | none | success | clean | ISS-001 |\n"
    )
    ts.write(repo, INDEX, text)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        repo = ts.make_repo(tmp, "reindex", branch="none")
        issue = os.path.join(repo, ISSUES, "ISS-001-first.md")

        print("== 1. rebuild on edit")
        ts.write(repo, f"{ISSUES}/ISS-001-first.md", ts.read(repo, f"{ISSUES}/ISS-001-first.md").replace("Status: open", "Status: closed"))
        hook(REINDEX, {"tool_name": "Edit", "cwd": repo, "tool_input": {"file_path": issue}})
        check("Open: 0. Closed: 1." in ts.read(repo, INDEX), "Edit of an issue rebuilds INDEX.md")

        before = (ts.read(repo, INDEX), os.path.getmtime(os.path.join(repo, INDEX)))
        time.sleep(1.1)
        hook(REINDEX, {"tool_name": "Write", "cwd": repo, "tool_input": {"file_path": os.path.join(repo, "src", "app.py")}})
        after = (ts.read(repo, INDEX), os.path.getmtime(os.path.join(repo, INDEX)))
        check(before == after, "Write of a source file leaves INDEX.md alone")

        ts.write(repo, f"{ISSUES}/ISS-002-second.md", ts.ISSUE.format(branch="none", extra="").replace("ISS-001: First thing", "ISS-002: Second thing"))
        hook(REINDEX, {"tool_name": "Bash", "cwd": repo, "tool_input": {"command": f"mv /tmp/x {ISSUES}/ISS-002-second.md"}})
        check("ISS-002" in ts.read(repo, INDEX), "Bash command naming an issue file rebuilds INDEX.md")

        plain = os.path.join(tmp, "plain")
        os.makedirs(plain)
        ts.git(plain, "init", "-q")
        r = hook(REINDEX, {"tool_name": "Edit", "cwd": plain, "tool_input": {"file_path": os.path.join(plain, "ISS-001-x.md")}})
        check(r.returncode == 0 and os.listdir(plain) == [".git"], "repo without devkit.json: nothing happens")

        print("\n== 2. a failed refresh keeps the last good table")
        ts.git(repo, "remote", "set-url", "origin", "https://github.com/aaudemarspiguet/devkit-no-such-repo-0000.git")
        set_config(repo, forge="github")
        seed_pr_section(repo, datetime(2026, 1, 1, 10, 0))
        r = sync(repo)
        text = ts.read(repo, INDEX)
        check(r.returncode == 0, "sync exits 0", r.stderr)
        check("Seeded PR" in text and "Read from github at 2026-01-01 10:00" in text, "old table and read time kept", text[-600:])
        check(text.count("Refresh failed at ") == 1, "one Refresh failed note")
        sync(repo)
        text = ts.read(repo, INDEX)
        check(text.count("Refresh failed at ") == 1 and "Seeded PR" in text, "second failure: still one note, table kept")
        check("\n\n\n" not in text, "no doubled blank lines")
        sync(repo, "--no-mrs")
        check("Seeded PR" in ts.read(repo, INDEX), "--no-mrs keeps the stale section as it is")

        set_config(repo, forge="none")
        sync(repo)
        text = ts.read(repo, INDEX)
        check("Not available at" in text and "Seeded PR" not in text, "forge none: plain Not available text")

        print("\n== 3. lock")
        lock = os.path.join(repo, ISSUES, "INDEX.md.lock")
        open(lock, "w").close()
        old = time.time() - 120
        os.utime(lock, (old, old))
        r = sync(repo, "--no-mrs")
        check(r.returncode == 0 and not os.path.exists(lock), "stale lock removed, sync ran", r.stderr)
        open(lock, "w").close()
        start = time.monotonic()
        r = sync(repo, "--no-mrs")
        waited = time.monotonic() - start
        check(r.returncode == 1 and "held by another sync" in r.stderr, "fresh lock: gives up with a message", r.stderr)
        check(4.5 <= waited < 15, f"waited about 5 s ({waited:.1f} s)")
        check(os.path.exists(lock), "someone else's lock is left alone")
        os.remove(lock)
        check(not os.path.exists(os.path.join(repo, ISSUES, "INDEX.md.tmp")), "no temp file left behind")

        print("\n== 4. session-start refresh")
        set_config(repo, forge="auto")
        ts.git(repo, "remote", "set-url", "origin", "https://github.com/cli/cli.git")
        seed_pr_section(repo, datetime.now() - timedelta(minutes=2))
        r = ts.sh(repo, sys.executable, SESSION_SYNC, "--check", repo)
        check("skip: last read" in r.stdout, "read 2 min ago: skipped", r.stdout)
        seed_pr_section(repo, datetime.now() - timedelta(minutes=30))
        r = ts.sh(repo, sys.executable, SESSION_SYNC, "--check", repo)
        check("would run" in r.stdout, "read 30 min ago: runs", r.stdout)
        set_config(repo, session_sync_minutes=0)
        r = ts.sh(repo, sys.executable, SESSION_SYNC, "--check", repo)
        check("session_sync_minutes is 0" in r.stdout, "0 turns it off", r.stdout)
        set_config(repo, session_sync_minutes=10)
        start = time.monotonic()
        r = hook(SESSION_SYNC, {"cwd": repo, "hook_event_name": "SessionStart", "source": "startup"})
        returned = time.monotonic() - start
        check(r.returncode == 0 and returned < 3, f"hook returns at once ({returned:.1f} s)")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and "Seeded PR" in ts.read(repo, INDEX):
            time.sleep(1)
        time.sleep(1)  # let the detached sync release its lock
        text = ts.read(repo, INDEX)
        check(f"Read from github at {datetime.now():%Y-%m-%d}" in text and "Seeded PR" not in text,
              "detached sync refreshed the PR section from GitHub", text[-400:])

    print(f"\n{ts.total - ts.failures}/{ts.total} passed")
    sys.exit(1 if ts.failures else 0)


if __name__ == "__main__":
    main()
