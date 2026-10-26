"""
Elevate a local devkit issue tracker to tracked in git.

Called as `init_project.py --elevate [--dry-run] ...`. In order, it:
  1. checks the preconditions (devkit set up, tracker still ignored, no staged or
     modified tracked files, the target folder free);
  2. scans every file that will become tracked for secrets and private remarks;
  3. switches to a new branch off the default branch;
  4. moves the issues folder (plans-local/issues -> plans/issues by default);
  5. rewrites every reference to the old folder;
  6. takes the devkit lines out of .git/info/exclude;
  7. git-ignores the generated INDEX.md;
  8. checks that the repo's own .gitignore does not still hide anything;
  9. stages the files and stops. It never commits or pushes.

--include rules,pointer,config elevates more than the issues. --dry-run prints
the plan and the scan, and changes nothing.

Exit codes: 0 done (or nothing to do), 1 a precondition failed, 2 the scan found secrets.
"""

import json
import os
import re
import subprocess
from pathlib import Path

import init_project as ip

SECRETS = [
    (re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "GitHub fine-grained token"),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}"), "GitLab token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"\bxox[bpas]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
]
WARNINGS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "email address"),
    (re.compile(r"[A-Za-z]:[\\/]Users[\\/][^\\/\s]+|/Users/[^/\s]+|/home/[^/\s]+"), "home path"),
    (re.compile(r"(?i)\b(cannot see|can't see|private|confidential|do not push|don't share|do not share)\b"), "private remark"),
]
EXTRA_SCOPES = ("rules", "pointer", "config")


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8")


def rel(root, path):
    return Path(path).relative_to(root).as_posix()


def tracked_files(folder):
    """Every file in the issues folder that should be committed."""
    return sorted(
        p for p in folder.rglob("*")
        if p.is_file() and p.name != "INDEX.md" and "__pycache__" not in p.parts and p.suffix != ".pyc"
    )


def scan(root, paths, pointer_text=None):
    """[(severity, where, label, snippet)] for each hit."""
    hits = []
    # The README's local-mode note is replaced during elevation, so it is not a finding.
    sources = [(rel(root, p), p.read_text(encoding="utf-8", errors="replace").replace(ip.LOCAL_NOTE, "")) for p in paths]
    if pointer_text is not None:
        sources.append(("CLAUDE.md (pointer block)", pointer_text))
    for where, text in sources:
        for n, line in enumerate(text.splitlines(), 1):
            for severity, patterns in (("SECRET", SECRETS), ("warn", WARNINGS)):
                for pattern, label in patterns:
                    m = pattern.search(line)
                    if m:
                        hits.append((severity, f"{where}:{n}", label, line.strip()[:100]))
    return hits


def negation_lines(rel_dir):
    """Exclude patterns that hide everything under the top folder except rel_dir.

    Git cannot re-include a path whose parent folder is excluded, so each level is
    opened with `parent/*` and the next level re-included with `!parent/child/`.
    """
    parts = rel_dir.split("/")
    lines = []
    for i in range(1, len(parts)):
        lines += ["/".join(parts[:i]) + "/*", "!" + "/".join(parts[: i + 1]) + "/"]
    return lines


def replace_block(text, new_block):
    start, end = text.index(ip.MARK_START), text.index(ip.MARK_END) + len(ip.MARK_END)
    return text[:start] + new_block.rstrip("\n") + text[end:]


def remove_block(text):
    start, end = text.index(ip.MARK_START), text.index(ip.MARK_END) + len(ip.MARK_END)
    return (text[:start].rstrip("\n") + "\n" + text[end:].lstrip("\n")).strip("\n")


def run(root, args):
    dry = args.dry_run
    out = []  # the plan, printed at the end
    include = {s.strip() for s in args.include.split(",") if s.strip()}
    unknown = include - set(EXTRA_SCOPES)
    if unknown:
        print(f"Unknown --include value(s): {', '.join(sorted(unknown))}. Use {', '.join(EXTRA_SCOPES)}.")
        return 1

    # 1. Preconditions.
    config_path = root / ".claude" / "devkit.json"
    if not config_path.is_file():
        print("No .claude/devkit.json here. Run setup first.")
        return 1
    old = ip.issues_dir_of(root)
    old_dir = root / old
    if not old_dir.is_dir():
        print(f"No issues folder at {old}/.")
        return 1
    elevate_issues = ip.is_ignored(root, old + "/")
    if not elevate_issues and not include:
        print(f"{old}/ is already tracked. Nothing to do. (Use --include to elevate rules, pointer or config.)")
        return 0
    if git(root, "diff", "--cached", "--quiet").returncode != 0:
        print("There are staged changes. Commit or unstage them first, so only the tracker gets staged.")
        return 1
    if git(root, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        print("There are modified tracked files. Commit or stash them first: elevate switches branch.")
        return 1

    if not elevate_issues or args.keep_dir:
        new = old
    elif args.move_to:
        new = args.move_to.strip("/\\").replace("\\", "/")
    elif old.startswith("plans-local/"):
        new = "plans/" + old[len("plans-local/"):]
    else:
        new = old
    new_dir = root / new
    moving = new != old
    if moving and new_dir.exists():
        print(f"{new}/ already exists. Pick another folder with --move-to, or --keep-dir.")
        return 1

    # Files that will become tracked, at their final paths.
    issue_files = tracked_files(old_dir) if elevate_issues else []
    rule_files = sorted((root / ".claude" / "rules").glob("*.md")) if "rules" in include else []
    pointer_src = root / "CLAUDE.local.md"
    pointer_text = None
    if "pointer" in include:
        text = pointer_src.read_text(encoding="utf-8") if pointer_src.exists() else ""
        if ip.MARK_START in text:
            pointer_text = text[text.index(ip.MARK_START): text.index(ip.MARK_END) + len(ip.MARK_END)]
        else:
            out.append("  ! no devkit pointer block in CLAUDE.local.md; --include pointer does nothing")
    config_files = [config_path] if "config" in include else []

    # 2. Scan.
    hits = scan(root, issue_files + rule_files + config_files, pointer_text)
    secrets = [h for h in hits if h[0] == "SECRET"]

    # Outdated script copies (older projects keep the scripts they were set up with).
    stale = [
        name for name in ("post_commit.py", "sync_index.py")
        if elevate_issues and (old_dir / name).exists()
        and (old_dir / name).read_text(encoding="utf-8") != ip.issue_template(name, old, ip.TRACKED_NOTE)
    ]

    print(("DRY RUN, nothing changed.\n" if dry else "") + f"Repo: {root}")
    print(f"Elevating: {', '.join((['issues'] if elevate_issues else []) + sorted(include))}")
    if elevate_issues:
        print(f"Issues folder: {old}/" + (f" -> {new}/" if moving else " (kept)"))
        print(f"Files to track ({len(issue_files)}):")
        for p in issue_files:
            print(f"    {new}/{p.relative_to(old_dir).as_posix()}")
        print(f"    {new}/.gitignore  (new: ignores the generated INDEX.md)")
    for p in rule_files + config_files:
        print(f"    {rel(root, p)}")
    if pointer_text:
        print("    CLAUDE.md  (the devkit pointer block moves here from CLAUDE.local.md)")
    if "config" in include:
        print("  ! Tracking .claude/devkit.json turns the guards on for every teammate who has the devkit plugin.")
    if "rules" in include:
        print("  ! Tracking the rules makes every teammate's Claude sessions follow them.")
    print(f"Scan: {len(secrets)} secret(s), {len(hits) - len(secrets)} warning(s)")
    for severity, where, label, snippet in hits:
        print(f"  [{severity}] {where}  {label}: {snippet}")
    for name in stale:
        verb = "will be replaced (--refresh-scripts)" if args.refresh_scripts else "differs from the current template; pass --refresh-scripts to replace it"
        print(f"  ! {old}/{name} {verb}")
    if secrets and not args.allow_secrets:
        print("BLOCKED: the scan found token or key patterns. Remove them, or pass --allow-secrets if they are fake.")
        return 2

    base_ref = f"origin/{ip.default_branch(root)}"
    has_base = git(root, "rev-parse", "--verify", "--quiet", base_ref).returncode == 0
    print(f"Branch: {args.elevate_branch} from {base_ref if has_base else 'HEAD'}")
    if dry:
        for line in out:
            print(line)
        return 0

    # 3. Branch.
    if git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{args.elevate_branch}").returncode == 0:
        print(f"Branch {args.elevate_branch} already exists. Delete it or pass --elevate-branch.")
        return 1
    switch = git(root, "switch", "-c", args.elevate_branch, *([base_ref] if has_base else []))
    if switch.returncode != 0:
        print(f"git switch failed, nothing moved:\n{switch.stderr.strip()}")
        return 1
    out.append(f"  + switched to new branch {args.elevate_branch}")

    to_add = []
    exclude_file = ip.exclude_path(root)
    lines = exclude_file.read_text(encoding="utf-8").splitlines() if exclude_file.exists() else []

    if elevate_issues:
        # 4. Move (one rename: atomic on one volume).
        top = old.split("/")[0]
        if moving:
            new_dir.parent.mkdir(parents=True, exist_ok=True)
            os.rename(old_dir, new_dir)
            out.append(f"  + moved {old}/ to {new}/")
            top_dir = root / top
            if top_dir.is_dir() and not any(top_dir.iterdir()):
                top_dir.rmdir()

        # 5. References.
        if moving:
            changed = 0
            for p in tracked_files(new_dir):
                if p.suffix in (".md", ".py"):
                    text = p.read_text(encoding="utf-8")
                    if old in text:
                        p.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
                        changed += 1
            out.append(f"  + rewrote {old} -> {new} in {changed} file(s)")
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config.setdefault("issues", {})["dir"] = new
            config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8", newline="\n")
            out.append("  + set issues.dir in .claude/devkit.json")
            hook = ip.hook_path(root)
            if hook.exists() and ip.HOOK_MARK in hook.read_text(encoding="utf-8", errors="replace"):
                hook.write_text(ip.hook_template(new), encoding="utf-8", newline="\n")
                out.append("  + updated .git/hooks/post-commit")
            elif hook.exists():
                out.append(f"  ! .git/hooks/post-commit is not devkit's: change {old}/post_commit.py to {new}/post_commit.py in it by hand")
            if pointer_src.exists():
                text = pointer_src.read_text(encoding="utf-8")
                if ip.MARK_START in text:
                    pointer_src.write_text(replace_block(text, ip.pointer_block(new)), encoding="utf-8", newline="\n")
                    if pointer_text:
                        pointer_text = ip.pointer_block(new).rstrip("\n")
                    out.append("  + updated the pointer block in CLAUDE.local.md")
        readme = new_dir / "README.md"
        if readme.exists():
            text = readme.read_text(encoding="utf-8")
            if ip.LOCAL_NOTE in text:
                readme.write_text(text.replace(ip.LOCAL_NOTE, ip.TRACKED_NOTE), encoding="utf-8", newline="\n")
                out.append("  + README.md now says the folder is tracked")
            else:
                out.append("  ! README.md has no local-mode note to replace; check its first paragraph by hand")
        if args.refresh_scripts:
            for name in stale:
                (new_dir / name).write_text(ip.issue_template(name, new, ip.TRACKED_NOTE), encoding="utf-8", newline="\n")
                out.append(f"  + replaced {new}/{name} with the current template")

        # 6. Exclude lines. Keep the top folder excluded while anything else is left in it.
        top_line = top + "/"
        if top_line in lines:
            if moving and (root / top).is_dir():
                out.append(f"  = kept {top_line} in .git/info/exclude (it still holds local files)")
            elif moving or "/" not in old:
                lines.remove(top_line)
                out.append(f"  + .git/info/exclude: removed {top_line}")
            else:
                # Kept in place under a local top folder: hide the rest, re-include the issues.
                i = lines.index(top_line)
                lines[i:i + 1] = negation_lines(old)
                out.append(f"  + .git/info/exclude: {top_line} now re-includes {old}/")

        # 7. INDEX.md is generated: ignore it in the tracked folder.
        gitignore = new_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(ip.ISSUES_GITIGNORE, encoding="utf-8", newline="\n")
        to_add += tracked_files(new_dir)

    if "rules" in include:
        for p in rule_files:
            line = rel(root, p)
            if line in lines:
                lines.remove(line)
        to_add += rule_files
        out.append("  + .git/info/exclude: removed the rule files")
    if "config" in include:
        if ".claude/devkit.json" in lines:
            lines.remove(".claude/devkit.json")
        to_add.append(config_path)
        out.append("  + .git/info/exclude: removed .claude/devkit.json")
    exclude_file.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    if pointer_text:
        target = root / "CLAUDE.md"
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        if ip.MARK_START not in existing:
            sep = "\n" if existing and not existing.endswith("\n\n") else ""
            target.write_text(existing + sep + pointer_text + "\n", encoding="utf-8", newline="\n")
        rest = remove_block(pointer_src.read_text(encoding="utf-8"))
        if rest.strip():
            pointer_src.write_text(rest + "\n", encoding="utf-8", newline="\n")
        else:
            pointer_src.unlink()
        to_add.append(target)
        out.append("  + moved the pointer block to CLAUDE.md")

    # 8. Anything the repo's own .gitignore still hides is left out and reported.
    stage, hidden = [], []
    for p in to_add:
        r = rel(root, p)
        check = git(root, "check-ignore", "-v", "--", r)
        (hidden if check.returncode == 0 else stage).append((r, check.stdout.strip()))
    for r, why in hidden:
        out.append(f"  ! still ignored, not staged: {r}  ({why.split(chr(9))[0]})")

    # 9. Stage and stop.
    if stage:
        add = git(root, "add", "--", *[r for r, _ in stage])
        if add.returncode != 0:
            out.append(f"  ! git add failed: {add.stderr.strip()}")
        else:
            out.append(f"  + staged {len(stage)} file(s)")
    for line in out:
        print(line)
    print("\n" + git(root, "status", "--short").stdout.rstrip())
    print(
        "\nNext: review the staged diff (git diff --cached), then commit, for example\n"
        f'    git commit -m "Track the issue log in {new if elevate_issues else "git"}"\n'
        "and push and open a PR the usual way (pushing still needs your approval)."
    )
    return 0
