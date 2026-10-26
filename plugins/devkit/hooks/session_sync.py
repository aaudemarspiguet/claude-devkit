#!/usr/bin/env python3
"""
Refresh the open-PR section of INDEX.md when a session starts (SessionStart, async).

Opt-in: does nothing unless the repo has .claude/devkit.json and an issues folder
with sync_index.py. Throttled: it skips the refresh when the last good read
("Read from <forge> at YYYY-MM-DD HH:MM") is newer than
"issues": {"session_sync_minutes": N} (default 10; 0 turns it off). A failed refresh
keeps the old read time, so the next session tries again.

It starts `<issues dir>/sync_index.py` (full sync, with the forge) as a detached
process and returns at once, so the session never waits on the network and the sync
survives a session that ends first. The result, including any "Refresh failed" note,
is in INDEX.md; sync_index.py's lock keeps it safe next to the other rebuilds.

Test the throttle without a session:
    python3 session_sync.py --check <repo>
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import devkit_config  # noqa: E402

READ_LINE = re.compile(r"^Read from \S+ at (\d{4}-\d\d-\d\d \d\d:\d\d)", re.M)
DEFAULT_MINUTES = 10


def last_read(index_path):
    """Time of the last good forge read in INDEX.md, or None."""
    try:
        with open(index_path, encoding="utf-8") as fh:
            m = READ_LINE.search(fh.read())
    except OSError:
        return None
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M") if m else None


def plan(cwd):
    """(script, root) to run, or (None, reason) to skip."""
    root, config = devkit_config.load(cwd)
    if config is None:
        return None, "not a devkit repo"
    issues = devkit_config.issues_dir(config)
    script = os.path.join(root, issues, "sync_index.py")
    if not os.path.isfile(script):
        return None, f"no {issues}/sync_index.py"
    minutes = config["issues"].get("session_sync_minutes", DEFAULT_MINUTES)
    if not minutes:
        return None, "session_sync_minutes is 0"
    read = last_read(os.path.join(root, issues, "INDEX.md"))
    if read and datetime.now() - read < timedelta(minutes=minutes):
        return None, f"last read {read:%H:%M}, within {minutes} min"
    return script, root


def main() -> None:
    if len(sys.argv) > 2 and sys.argv[1] == "--check":
        script, info = plan(sys.argv[2])
        print(f"would run {script}" if script else f"skip: {info}")
        return
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    script, root = plan(payload.get("cwd"))
    if script:
        spawn_detached([sys.executable, script], root)


def spawn_detached(cmd, cwd):
    """Start the sync so it outlives this hook and the session.

    An async hook is killed when a short session exits, and its children with it, so
    the sync runs in its own process group (Windows: its own console-less process,
    out of Claude Code's job object when the job allows that).
    """
    kwargs = {"cwd": cwd, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name != "nt":
        subprocess.Popen(cmd, start_new_session=True, **kwargs)
        return
    base = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(cmd, creationflags=base | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kwargs)
    except OSError:  # the job does not allow breakaway
        subprocess.Popen(cmd, creationflags=base, **kwargs)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # advisory only -- never break the session
        print(f"[session_sync.py] {exc}", file=sys.stderr)
    sys.exit(0)
