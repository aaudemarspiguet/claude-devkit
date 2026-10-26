#!/usr/bin/env python3
"""
Rebuild INDEX.md after Claude changes an issue file (PostToolUse, matcher
"Write|Edit|NotebookEdit|Bash|PowerShell").

Opt-in: does nothing unless the repo has .claude/devkit.json. Then:
  - Write/Edit: rebuilds when the edited file is <issues dir>/ISS-*.md.
  - Bash/PowerShell: rebuilds when the command names the issues folder or an ISS- file
    (cp TEMPLATE.md ISS-007-x.md, mv, sed -i). A false trigger costs one local rebuild.

It runs the project's own `<issues dir>/sync_index.py --no-mrs`: local, no network,
and the open-PR section is kept as it is. Advisory only: it never blocks and always
exits 0.
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import devkit_config  # noqa: E402

ISSUE_FILE = re.compile(r"ISS-\d{3}[^/]*\.md$")


def should_rebuild(payload, root, issues):
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    if tool in ("Bash", "PowerShell"):
        command = (tool_input.get("command") or "").replace("\\", "/")
        return issues in command or "ISS-" in command
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    rel = devkit_config.repo_relative(path, root, payload.get("cwd"))
    return bool(rel) and rel.startswith(issues + "/") and bool(ISSUE_FILE.search(rel))


def main() -> None:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    root, config = devkit_config.load(payload.get("cwd"))
    if config is None:
        return
    issues = devkit_config.issues_dir(config)
    script = os.path.join(root, issues, "sync_index.py")
    if not os.path.isfile(script) or not should_rebuild(payload, root, issues):
        return
    result = subprocess.run(
        [sys.executable, script, "--no-mrs"], cwd=root, capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        print(f"[reindex.py] {issues}/INDEX.md not rebuilt: {result.stderr.strip()}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # advisory only -- never break the session
        print(f"[reindex.py] {exc}", file=sys.stderr)
    sys.exit(0)
