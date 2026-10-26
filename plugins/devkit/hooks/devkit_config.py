"""
Shared config loader for the devkit plugin hooks.

The hooks are opt-in per repo. A repo opts in by having `.claude/devkit.json`
at its git root (/devkit:setup writes it). In any other repo, load()
returns None and every hook exits 0 at once.
"""

import json
import os
import subprocess

CONFIG_REL = ".claude/devkit.json"
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
    CONFIG_REL: "The devkit guard config. Only the user edits it.",
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


def repo_relative(file_path: str, root: str, cwd):
    """Repo-relative posix path, or None if the file is outside the repo."""
    if not file_path:
        return None
    norm = file_path.replace("\\", "/")
    if not os.path.isabs(norm):
        norm = os.path.join(cwd or root, norm).replace("\\", "/")
    try:
        rel = os.path.relpath(os.path.normcase(os.path.abspath(norm)), os.path.normcase(os.path.abspath(root)))
    except ValueError:  # different drive on Windows
        return None
    rel = rel.replace("\\", "/")
    if rel.startswith(".."):
        return None
    # relpath on normcased paths lowercases on Windows; rebuild the original case.
    return norm[len(norm) - len(rel):] if norm.lower().endswith(rel.lower()) else rel


def issues_dir(config):
    """The repo-relative issues folder, without a trailing slash."""
    return config["issues"].get("dir", "plans-local/issues").strip("/\\").replace("\\", "/")


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
