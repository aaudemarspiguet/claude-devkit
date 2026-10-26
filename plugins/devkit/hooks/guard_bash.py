#!/usr/bin/env python3
"""
Shell-command guard (PreToolUse, matcher "Bash|PowerShell").

Opt-in: does nothing unless the repo has .claude/devkit.json. Then it blocks
force-pushes, history rewrites and commits on protected branches, pushes the
user has not approved, and shell writes to protected paths.

The PowerShell tool is matched too. Without it, Claude can run the same git and
write commands through PowerShell and skip every rule here.

Why the matcher is a bare "Bash": Claude Code issue #36389 reports that narrow
matchers like `Bash(git commit:*)` do not fire, so a `git push` to main sailed
straight through. So we match ALL shell calls and parse the command here.

Exit codes:
  0  allow
  2  block; stderr is fed back to Claude as the reason

Fails closed on parse errors.
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import devkit_config  # noqa: E402

WRITEISH = re.compile(
    r"(>>?|(?<!\w)tee(?!\w)|sed\s+-[a-zA-Z]*i|truncate|(?<!\w)rm(?!\w)|(?<!\w)mv(?!\w)|(?<!\w)cp(?!\w)"
    r"|Set-Content|Add-Content|Out-File|Clear-Content|Remove-Item|Move-Item|Rename-Item|Copy-Item"
    r"|\[IO\.File\]::(Write|Append|Delete|Move|Copy))",
    re.IGNORECASE,
)

# Redirects that throw output away. They write nothing to the repo.
DISCARD = re.compile(r"\d?>>?\s*(/dev/null|\$null|NUL\b)|\d?>&\d", re.IGNORECASE)


def block(reason: str) -> None:
    print(f"BLOCKED by guard_bash.py\n\n{reason}", file=sys.stderr)
    sys.exit(2)


def current_branch(cwd: str, protected) -> str:
    branch = devkit_config.git("branch", "--show-current", cwd=cwd)
    if not branch and protected:
        # Cannot tell which branch we are on -> assume the dangerous one.
        return protected[0]
    return branch


def git_sub(cmd: str, sub: str):
    """Match `git <sub>`, also with global options before it: git -C dir push."""
    return re.search(rf"\bgit(?:\s+(?:-[Cc]\s+\S+|--[\w-]+(?:=\S+)?))*\s+{sub}\b", cmd)


def strip_quoted(cmd: str, powershell: bool = False) -> str:
    """
    Blank out quoted regions so `echo "git push"` does not trip the guards.

    Backslash escapes are honoured inside double quotes and outside quotes.
    Single quotes are literal in POSIX shells, so backslash is NOT an escape
    inside them.

    PowerShell does not use backslash as an escape. In PowerShell mode a backslash
    is kept, so a Windows path such as .\\ci.yml stays visible.
    """
    out = []
    quote = None
    i, n = 0, len(cmd)
    while i < n:
        ch = cmd[i]
        if quote:
            if ch == "\\" and quote == '"' and not powershell and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            out.append(" ")
            if ch == quote:
                quote = None
            i += 1
        elif ch == "\\" and not powershell and i + 1 < n:
            out.append("  ")
            i += 2
        elif ch in "\"'":
            quote = ch
            out.append(" ")
            i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        block("Could not parse the hook payload. Failing closed.")

    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") or ""
    if not command.strip():
        return

    cwd = payload.get("cwd") or os.getcwd()
    try:
        root, config = devkit_config.load(cwd)
    except (OSError, ValueError) as exc:
        block(f"Could not read {devkit_config.CONFIG_REL}: {exc}. Failing closed. Ask the user to fix it.")
    if config is None:
        return

    protected_branches = config["protected_branches"]
    powershell = payload.get("tool_name") == "PowerShell"
    cmd = strip_quoted(command, powershell)
    if powershell:
        cmd = cmd.replace("\\", "/")

    # --- never rewrite history --------------------------------------------
    if config["block_force_push"] and git_sub(cmd, "push") and re.search(
        r"(--force\b|--force-with-lease\b|(?<!\w)-f(?!\w)|\s\+\S)", cmd
    ):
        block("Force-pushing is blocked in this repo (.claude/devkit.json: block_force_push).")

    if git_sub(cmd, r"(?:rebase|reset\s+--hard|filter-branch|filter-repo)"):
        branch = current_branch(cwd, protected_branches)
        if branch in protected_branches:
            block(
                f"History rewrite attempted on the protected branch `{branch}`.\n\n"
                "If the user planned this step, the user runs it in their own terminal."
            )

    # --- never push without the user's approval -----------------------------
    if config["require_push_approval"] and git_sub(cmd, "push"):
        sentinel = Path(root) / devkit_config.SENTINEL_REL
        if sentinel.exists():
            try:
                sentinel.unlink()  # one-shot: consumed by this push
            except OSError:
                pass
        else:
            block(
                "Pushing requires the user's explicit approval, every time.\n\n"
                "Ask the user, show them the branch and the diff, and only after they say "
                "yes create the one-shot sentinel at the repo root:\n"
                f"    touch {devkit_config.SENTINEL_REL}\n"
                "then retry the push. Do not create that file on your own initiative."
            )

    # --- never commit on a protected branch ----------------------------------
    if git_sub(cmd, "commit"):
        branch = current_branch(cwd, protected_branches)
        if branch in protected_branches:
            block(
                f"You are on `{branch}`, which is protected. Branch first:\n"
                "    git switch -c <descriptive-name> --no-track origin/<default branch>\n\n"
                "Note --no-track: branching WITH tracking makes a bare `git push` target "
                "the protected branch."
            )

    # --- shell writes to protected files -------------------------------------
    # The write command is found in the stripped text. The path is found in the raw
    # text, because paths are often quoted: Set-Content -Path '.ci.yml'.
    if WRITEISH.search(DISCARD.sub(" ", cmd)):
        raw_cmd = command.replace("\\", "/")
        for path, reason in config["protected_paths"].items():
            # A root-level file is matched by name; a nested one by its full path,
            # so a common name such as tsconfig.json in another folder stays free.
            if path in raw_cmd or ("/" not in path and re.search(rf"(?<![\w.-]){re.escape(path)}(?![\w.-])", raw_cmd)):
                block(
                    f"This command looks like it writes to the protected path `{path}`.\n\n{reason}\n\n"
                    "Editing it via the shell bypasses guard_files.py but breaks the same rule."
                )
        for folder, reason in config["protected_dirs"].items():
            if folder in raw_cmd:
                block(f"This command looks like it writes inside `{folder}`.\n\n{reason}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # fail closed
        print(f"BLOCKED by guard_bash.py (internal error): {exc}", file=sys.stderr)
        sys.exit(2)
