#!/usr/bin/env python3
"""
File-edit guard (PreToolUse, matcher Write|Edit|NotebookEdit).

Opt-in: does nothing unless the repo has .claude/workflow.json. Then it blocks
writes to `protected_paths` and into `protected_dirs`, and blocks edits that
would shrink an `append_only_files` entry.

Exit codes:
  0  allow
  2  block; stderr is fed back to Claude as the reason

Fails closed: if the payload or the config cannot be parsed, the call is blocked.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workflow_config  # noqa: E402


def block(reason: str) -> None:
    print(f"BLOCKED by guard_files.py\n\n{reason}", file=sys.stderr)
    sys.exit(2)


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


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        block("Could not parse the hook payload. Failing closed.")

    cwd = payload.get("cwd")
    try:
        root, config = workflow_config.load(cwd)
    except (OSError, ValueError) as exc:
        block(f"Could not read {workflow_config.CONFIG_REL}: {exc}. Failing closed. Ask the user to fix it.")
    if config is None:
        return

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or tool_input.get("path") or ""
    rel = repo_relative(file_path, root, cwd)
    if rel is None:
        return

    if rel in config["protected_paths"]:
        block(
            f"`{rel}` is protected.\n\n{config['protected_paths'][rel]}\n\n"
            "If this edit is genuinely required, raise it with the user first -- "
            "do not work around this guard."
        )

    for prefix, reason in config["protected_dirs"].items():
        if rel.startswith(prefix):
            block(f"`{rel}` is inside the protected folder `{prefix}`.\n\n{reason}")

    if rel in config["append_only_files"]:
        old = tool_input.get("old_string")
        new = tool_input.get("new_string")
        if old is not None and new is not None:
            if new.count("\n") < old.count("\n"):
                block(
                    f"`{rel}` is append-only and this edit removes lines.\n\n"
                    "Add to it instead of removing from it. If a removal is truly needed, ask the user."
                )
        elif "content" in tool_input:
            try:
                with open(os.path.join(root, rel), "r", encoding="utf-8") as fh:
                    existing = fh.read()
            except OSError:
                existing = ""
            if existing and tool_input["content"].count("\n") < existing.count("\n"):
                block(
                    f"`{rel}` is append-only and this overwrite is shorter than the current file.\n\n"
                    "Use Edit to append, not Write to replace."
                )


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # fail closed
        print(f"BLOCKED by guard_files.py (internal error): {exc}", file=sys.stderr)
        sys.exit(2)
