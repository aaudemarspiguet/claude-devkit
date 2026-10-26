#!/usr/bin/env python3
"""
Scaffold the workflow into a git repo: guard config, local issue tracker, rules,
post-commit hook, and a CLAUDE.md pointer. Safe to re-run: it never overwrites a
file that already exists, and reports what it skipped.

    init_project.py --detect                      # print what it found, write nothing
    init_project.py [options]                     # scaffold
    init_project.py --dry-run [options]           # print the plan, write nothing

Options (repeatable where it makes sense):
    --repo PATH                 repo to set up (default: the git root of the cwd)
    --mode local|tracked        local (default): plans-local/, the config and the rules are
                                in .git/info/exclude, the pointer goes in CLAUDE.local.md.
                                tracked: all of it is committed, the pointer goes in CLAUDE.md.
    --issues-dir DIR            default plans-local/issues
    --protect PATH[=REASON]     a file Claude must not edit
    --protect-dir DIR[=REASON]  a folder Claude must not write into
    --append-only PATH          a file that may grow but never shrink
    --source-dir DIR            source folders (session check: source changed, no tests)
    --test-dir DIR              test folders
    --function-dir DIR          Python folders whose changed public functions get listed
    --branch NAME               protected branches (default: the default branch + main/master)
    --forge auto|github|gitlab|none
    --skip-commit-prefix DIR    commits touching only these paths get no issue Log line
"""

import argparse
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
TEMPLATES = SKILL / "templates"
MARK_START = "<!-- workflow-plugin:start -->"
MARK_END = "<!-- workflow-plugin:end -->"
HOOK_MARK = "workflow-plugin"

CI_CANDIDATES = (".gitlab-ci.yml", ".travis.yml", "azure-pipelines.yml", "Jenkinsfile", ".circleci/config.yml")
SOURCE_CANDIDATES = ("src", "app", "lib", "backend", "frontend", "packages", "server", "client", "pkg", "cmd")
TEST_CANDIDATES = ("tests", "test", "__tests__", "spec", "e2e")


def git(root, *args):
    out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8")
    return out.stdout.strip() if out.returncode == 0 else ""


def find_root(start):
    root = git(start, "rev-parse", "--show-toplevel")
    if not root:
        sys.exit(f"Not a git repository: {start}. Run `git init` first.")
    return Path(root)


def default_branch(root):
    head = git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head:
        return head.split("/", 1)[-1]
    return git(root, "branch", "--show-current") or "main"


def detect(root):
    ci = [p for p in CI_CANDIDATES if (root / p).is_file()]
    wf = root / ".github" / "workflows"
    if wf.is_dir():
        ci += sorted(f".github/workflows/{f.name}" for f in wf.iterdir() if f.suffix in (".yml", ".yaml"))
    remote = git(root, "remote", "get-url", "origin")
    forge = "github" if "github.com" in remote else "gitlab" if "gitlab" in remote else ("unknown" if remote else "none")
    return {
        "repo": str(root).replace("\\", "/"),
        "default_branch": default_branch(root),
        "current_branch": git(root, "branch", "--show-current"),
        "remote": remote or None,
        "forge_guess": forge,
        "ci_files": ci,
        "source_dir_candidates": [d + "/" for d in SOURCE_CANDIDATES if (root / d).is_dir()],
        "test_dir_candidates": [d + "/" for d in TEST_CANDIDATES if (root / d).is_dir()],
        "already_initialised": (root / ".claude" / "workflow.json").is_file(),
        "existing_post_commit_hook": hook_path(root).is_file(),
        # Companion skill, not bundled. Only the standalone copy has a fixed path to check.
        "unslop_text_installed": (Path.home() / ".claude" / "skills" / "unslop-text" / "SKILL.md").is_file(),
    }


def hook_path(root):
    hooks = git(root, "rev-parse", "--git-path", "hooks") or ".git/hooks"
    return (root / hooks if not os.path.isabs(hooks) else Path(hooks)) / "post-commit"


def split_reason(value, default):
    path, _, reason = value.partition("=")
    return path.strip().replace("\\", "/"), (reason.strip() or default)


def slash(d):
    d = d.strip().replace("\\", "/")
    return d if d.endswith("/") else d + "/"


class Plan:
    def __init__(self, dry_run):
        self.dry_run = dry_run
        self.done, self.skipped = [], []

    def write(self, path: Path, text: str, root: Path, executable=False):
        rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
        if path.exists():
            self.skipped.append(f"{rel} (exists)")
            return False
        if not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            if executable:
                path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.done.append(f"wrote {rel}")
        return True


def build_config(args, root):
    base = default_branch(root)
    branches = args.branch or list(dict.fromkeys([base, "main", "master"]))
    return {
        "protected_branches": branches,
        "protected_paths": dict(split_reason(p, "Protected by .claude/workflow.json. Ask the user first.") for p in args.protect),
        "protected_dirs": {slash(k): v for k, v in (split_reason(p, "Protected folder. Ask the user first.") for p in args.protect_dir)},
        "append_only_files": [p.replace("\\", "/") for p in args.append_only],
        "block_force_push": True,
        "require_push_approval": True,
        "source_dirs": [slash(d) for d in args.source_dir],
        "test_dirs": [slash(d) for d in args.test_dir],
        "function_dirs": [slash(d) for d in args.function_dir],
        "issues": {
            "dir": args.issues_dir,
            "forge": args.forge,
            "order_note": "Work in the Order column. An issue is ready when all its dependencies are closed.",
            "skip_commit_prefixes": [slash(d) for d in args.skip_commit_prefix],
        },
    }


def pointer_block(issues_dir):
    return f"""{MARK_START}
## Workflow (claude-workflow plugin)

- Issues live in `{issues_dir}/`. Read its `README.md` before you start, add, or close an issue.
  `INDEX.md` there is generated: never edit it by hand, run `python {issues_dir}/sync_index.py`.
- `.claude/workflow.json` configures the plugin's guard hooks. Do not edit it; ask the user.
- Pushing needs the user's yes every time. After the yes: `touch .claude/.push-approved`, then push.
- Design work follows Elephant-Goldfish: `/workflow:design-discussion` -> `/workflow:write-spec`
  -> `/workflow:goldfish-test` (fresh session) -> build -> `/workflow:mean-review`.
- Prose for a reader (READMEs, PR/MR descriptions, specs, docs, write-ups) gets a final pass with
  the `unslop-text` skill when it is installed. Not for commit messages, issue Logs, or chat.
{MARK_END}
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.getcwd())
    ap.add_argument("--detect", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--mode", choices=("local", "tracked"), default="local")
    ap.add_argument("--issues-dir", default="plans-local/issues")
    ap.add_argument("--protect", action="append", default=[])
    ap.add_argument("--protect-dir", action="append", default=[])
    ap.add_argument("--append-only", action="append", default=[])
    ap.add_argument("--source-dir", action="append", default=[])
    ap.add_argument("--test-dir", action="append", default=[])
    ap.add_argument("--function-dir", action="append", default=[])
    ap.add_argument("--branch", action="append", default=[])
    ap.add_argument("--forge", choices=("auto", "github", "gitlab", "none"), default="auto")
    ap.add_argument("--skip-commit-prefix", action="append", default=[])
    args = ap.parse_args()

    root = find_root(args.repo)
    if args.detect:
        print(json.dumps(detect(root), indent=2))
        return

    args.issues_dir = args.issues_dir.strip("/\\").replace("\\", "/")
    plan = Plan(args.dry_run)
    issues = root / args.issues_dir

    # 1. Guard config (the opt-in marker for the plugin hooks).
    config = build_config(args, root)
    plan.write(root / ".claude" / "workflow.json", json.dumps(config, indent=2) + "\n", root)

    # 2. Issue tracker.
    note = (
        "This folder is in `.git/info/exclude`. Git does not track it. Do not push it."
        if args.mode == "local"
        else "This folder is tracked in git. Commit issue changes with the work they describe."
    )
    for name in ("README.md", "TEMPLATE.md", "sync_index.py", "post_commit.py"):
        text = (TEMPLATES / "issues" / name).read_text(encoding="utf-8")
        text = text.replace("{{ISSUES_DIR}}", args.issues_dir).replace("{{TRACKING_NOTE}}", note)
        plan.write(issues / name, text, root)

    # 3. Rules.
    globs = config["source_dirs"]
    paths = ("paths:\n" + "".join(f'  - "{d}**"\n' for d in globs)) if globs else ""
    for src in sorted((TEMPLATES / "rules").glob("*.md")):
        text = src.read_text(encoding="utf-8").replace("{{PATHS}}", paths)
        plan.write(root / ".claude" / "rules" / src.name, text, root)

    # 4. Git post-commit hook.
    hook = hook_path(root)
    text = (TEMPLATES / "git-hooks" / "post-commit").read_text(encoding="utf-8").replace("{{ISSUES_DIR}}", args.issues_dir)
    if hook.exists() and HOOK_MARK not in hook.read_text(encoding="utf-8", errors="replace"):
        plan.skipped.append(
            f"{hook.name} hook (another post-commit hook exists; add this line to it by hand: "
            f"python3 {args.issues_dir}/post_commit.py)"
        )
    else:
        plan.write(hook, text, root, executable=True)

    # 5. CLAUDE.md pointer.
    target = root / ("CLAUDE.local.md" if args.mode == "local" else "CLAUDE.md")
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    if MARK_START in existing:
        plan.skipped.append(f"{target.name} pointer (already there)")
    else:
        if not args.dry_run:
            sep = "\n" if existing and not existing.endswith("\n\n") else ""
            target.write_text(existing + sep + pointer_block(args.issues_dir), encoding="utf-8", newline="\n")
        plan.done.append(f"added the workflow pointer to {target.name}")

    # 6. Keep local files out of git.
    exclude_file = root / (git(root, "rev-parse", "--git-path", "info/exclude") or ".git/info/exclude")
    wanted = [".claude/.push-approved"]
    if args.mode == "local":
        wanted += [
            args.issues_dir.split("/")[0] + "/",
            ".claude/workflow.json",
            "CLAUDE.local.md",
            *(f".claude/rules/{p.name}" for p in sorted((TEMPLATES / "rules").glob("*.md"))),
        ]
    current = exclude_file.read_text(encoding="utf-8").splitlines() if exclude_file.exists() else []
    missing = [w for w in wanted if w not in current]
    if missing:
        if not args.dry_run:
            exclude_file.parent.mkdir(parents=True, exist_ok=True)
            with exclude_file.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(("\n" if current and current[-1] else "") + "# workflow plugin (local only)\n" + "\n".join(missing) + "\n")
        plan.done.append(f"added {len(missing)} line(s) to .git/info/exclude")

    # 7. First INDEX.md.
    if not args.dry_run and (issues / "sync_index.py").exists():
        subprocess.run([sys.executable, str(issues / "sync_index.py"), "--no-mrs"], cwd=root, capture_output=True)
        plan.done.append(f"built {args.issues_dir}/INDEX.md")

    print(("DRY RUN, nothing written.\n" if args.dry_run else "") + f"Repo: {root}  (mode: {args.mode})")
    for line in plan.done:
        print(f"  + {line}")
    for line in plan.skipped:
        print(f"  = skipped {line}")


if __name__ == "__main__":
    main()
