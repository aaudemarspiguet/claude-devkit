#!/usr/bin/env python3
"""
End-of-session advisory checks (Stop hook).

Opt-in: does nothing unless the repo has .claude/workflow.json. Purely
informational -- never blocks, never writes.

  1. Sitting on a protected branch.
  2. Commits on this branch that are not on origin/<default branch>, and no upstream.
  3. A `source_dirs` file changed on this branch with no `test_dirs` change.
  4. Which public Python functions in `function_dirs` changed (ast, compared with
     origin/<default branch>), so the right tests get written.
  5. The issue whose Branch: header is this branch, as a reminder to update its Log.

Test check 4 without a branch:
    python3 session_warnings.py --functions <path> [<path> ...]
"""

import ast
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workflow_config  # noqa: E402
from workflow_config import git  # noqa: E402


def default_branch(cwd, protected):
    """origin/HEAD if known, else the first protected branch that exists on origin."""
    head = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=cwd)
    if head:
        return head
    for name in protected:
        if git("rev-parse", "--verify", "--quiet", f"origin/{name}", cwd=cwd):
            return f"origin/{name}"
    return ""


def function_hashes(source: str) -> dict:
    """Map qualified name -> hash of the body (docstring removed)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    found = {}

    def visit(nodes, prefix=""):
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                visit(node.body, f"{prefix}{node.name}.")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                body = node.body
                if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
                    body = body[1:]
                dump = "".join(ast.dump(b) for b in body) + ast.dump(node.args)
                dump += "".join(ast.dump(d) for d in node.decorator_list)
                found[prefix + node.name] = hashlib.sha256(dump.encode()).hexdigest()[:16]

    visit(tree.body)
    return found


def changed_functions(path: str, base: str, cwd=None) -> list:
    """New or changed public functions in path, compared with base."""
    try:
        with open(path if cwd is None else f"{cwd}/{path}", encoding="utf-8") as fh:
            now = function_hashes(fh.read())
    except OSError:
        return []
    before = function_hashes(git("show", f"{base}:{path}", cwd=cwd)) if base else {}
    return sorted(name for name, h in now.items() if before.get(name) != h)


def changed_files(base: str, cwd=None) -> list:
    committed = git("diff", "--name-only", f"{base}...HEAD", cwd=cwd).splitlines() if base else []
    working = git("diff", "--name-only", "HEAD", cwd=cwd).splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard", cwd=cwd).splitlines()
    return sorted({f for f in committed + working + untracked if f})


def function_report(paths, base="", cwd=None) -> list:
    lines = []
    for path in paths:
        names = changed_functions(path, base, cwd)
        if names:
            lines.append(f"    {path}: " + ", ".join(names[:12]) + (" ..." if len(names) > 12 else ""))
    return lines


def branch_issue(root, config, branch):
    """ID and status of the issue whose Branch: header is this branch."""
    folder = os.path.join(root, config["issues"].get("dir", "plans-local/issues"))
    if not branch or not os.path.isdir(folder):
        return None
    for name in sorted(os.listdir(folder)):
        if not re.match(r"ISS-\d{3}.*\.md$", name):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                head = fh.read(2000)
        except OSError:
            continue
        if re.search(rf"^-\s*Branch:\s*{re.escape(branch)}\s*$", head, re.M):
            status = re.search(r"^-\s*Status:\s*(\S+)", head, re.M)
            return name[:7], status.group(1) if status else "?"
    return None


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    root, config = workflow_config.load(payload.get("cwd") or None)
    if config is None:
        return
    cwd = root
    protected = config["protected_branches"]
    warnings = []

    # 1. On a protected branch.
    branch = git("branch", "--show-current", cwd=cwd)
    if branch in protected:
        warnings.append(f"You are on the protected branch `{branch}`. Switch to a branch before committing.")

    # 2. Unpushed work relative to the default branch.
    base = default_branch(cwd, protected)
    ahead = git("log", "--oneline", f"{base}..HEAD", cwd=cwd) if base else ""
    if ahead and branch not in protected:
        lines = ahead.splitlines()
        upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", cwd=cwd)
        detail = f"{len(lines)} commit(s) ahead of {base}"
        if not upstream:
            detail += ". This branch has NO upstream, so `git push` has nowhere to go"
        warnings.append(f"{detail}.\n  Check with: git log {base}..HEAD")

    # 3 and 4. Source touched without tests.
    sources = tuple(config["source_dirs"])
    test_dirs = tuple(config["test_dirs"])
    if sources and test_dirs:
        files = changed_files(base, cwd)
        src = [f for f in files if f.startswith(sources) and not f.startswith(test_dirs)]
        tests = [f for f in files if f.startswith(test_dirs)]
        if src and not tests:
            msg = (
                f"{len(src)} source file(s) changed on this branch with no test change:\n"
                + "".join(f"    {f}\n" for f in src[:8])
            )
            fdirs = tuple(config["function_dirs"])
            py = [f for f in src if fdirs and f.endswith(".py") and f.startswith(fdirs)]
            report = function_report(py, base, cwd)
            if report:
                msg += "  Changed public functions:\n" + "\n".join(report) + "\n"
            msg += f"  Add or update tests in {', '.join(test_dirs)} for these changes."
            warnings.append(msg)

    # 5. Issue reminder.
    issue = branch_issue(root, config, branch)
    if issue and issue[1] != "closed":
        warnings.append(
            f"This branch belongs to {issue[0]} (status: {issue[1]}). Before you stop, update its "
            "Status, its Done when list, and its Log."
        )

    if not warnings:
        return

    body = "\n\n".join(f"{i}. {w}" for i, w in enumerate(warnings, 1))
    print(json.dumps({"systemMessage": f"Session checks: {len(warnings)} warning(s)\n\n{body}"}))


if __name__ == "__main__":
    try:
        if len(sys.argv) > 2 and sys.argv[1] == "--functions":
            print("\n".join(function_report(sys.argv[2:])) or "no changed public functions")
        else:
            main()
    except Exception as exc:  # advisory only -- never break the session
        print(f"[session_warnings.py] {exc}", file=sys.stderr)
