"""
Shared config loader for the workflow plugin hooks.

The hooks are opt-in per repo. A repo opts in by having `.claude/workflow.json`
at its git root (/workflow:workflow-init writes it). In any other repo, load()
returns None and every hook exits 0 at once.
"""

import json
import os
import subprocess

CONFIG_REL = ".claude/workflow.json"
SENTINEL_REL = ".claude/.push-approved"

DEFAULTS = {
    "protected_branches": ["main", "master"],
    # path -> reason. Repo-relative, forward slashes.
    "protected_paths": {},
    # folder prefix (ending in "/") -> reason.
    "protected_dirs": {},
    # Files that may be appended to but never shrunk (for example starter tests).
    "append_only_files": [],
    "block_force_push": True,
    "require_push_approval": True,
    # Stop-hook check: source changed with no test change.
    "source_dirs": [],
    "test_dirs": [],
    # Stop-hook check: Python folders whose changed public functions get listed.
    "function_dirs": [],
    "issues": {},
}

# Always protected once a repo opts in, so the guards cannot be switched off
# by the agent they guard.
BUILTIN_PROTECTED = {
    CONFIG_REL: "The workflow guard config. Only the user edits it.",
}


def git(*args, cwd=None, timeout=10):
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd or None, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def repo_root(cwd=None):
    root = git("rev-parse", "--show-toplevel", cwd=cwd)
    return root.replace("\\", "/") if root else None


def load(cwd=None):
    """Return (root, config) for an opted-in repo, or (root, None)."""
    root = repo_root(cwd)
    if not root:
        return None, None
    path = os.path.join(root, CONFIG_REL)
    if not os.path.isfile(path):
        return root, None
    with open(path, encoding="utf-8") as fh:
        user = json.load(fh)  # a broken config raises: the guards fail closed
    config = {**DEFAULTS, **user}
    config["protected_paths"] = {**config["protected_paths"], **BUILTIN_PROTECTED}
    return root, config
