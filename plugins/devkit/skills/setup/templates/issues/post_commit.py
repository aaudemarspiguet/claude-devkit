"""Git post-commit logic for the local issues log.

Called by .git/hooks/post-commit. It never changes a status, never commits,
and always exits with 0.
    python plans-local/issues/post_commit.py [--dry-run]

Commits that change only paths under "issues": {"skip_commit_prefixes": [...]}
in .claude/devkit.json are skipped (for example bot-made log commits).
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def git(*args):
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout.strip()


def add_log_line(path, line):
    """Append a line at the end of the '## Log' section."""
    text = path.read_text(encoding="utf-8")
    if "\n## Log" not in text:
        text = text.rstrip("\n") + "\n\n## Log\n"
    start = text.index("\n## Log") + 1
    nxt = text.find("\n## ", start + 1)
    end = len(text) if nxt == -1 else nxt + 1
    section = text[start:end].rstrip("\n") + "\n" + line + "\n"
    if nxt != -1:
        section += "\n"
    path.write_text(text[:start] + section + text[end:], encoding="utf-8")


def main(dry_run):
    import sync_index

    skip = tuple(sync_index.settings().get("skip_commit_prefixes", []))
    files = [f for f in git("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", "HEAD").splitlines() if f]
    if not files or (skip and all(f.startswith(skip) for f in files)):
        print("skip: commit changes only skipped paths")
        return

    branch = git("branch", "--show-current")
    sha = git("rev-parse", "--short", "HEAD")
    subject = git("log", "-1", "--format=%s")
    line = f"- {datetime.now():%Y-%m-%d %H:%M}: commit {sha} {subject} ({len(files)} files) on `{branch}`"

    issues, _ = sync_index.load()
    matches = [i for i in issues if branch and i.get("Branch", "none") == branch]
    if not matches:
        print(f"no issue has Branch: {branch}. No Log line written.")
    else:
        if len(matches) > 1:
            names = ", ".join(i["ID"] for i in matches)
            print(f"WARNING: more than one issue has Branch: {branch} ({names}). Using {matches[0]['ID']}.")
        target = HERE / matches[0]["File"]
        if dry_run:
            print(f"dry run: would add to {target.name}:\n{line}")
        else:
            add_log_line(target, line)
            print(f"Log line added to {target.name}")

    if not dry_run:
        sync_index.main(with_mrs=False)  # no network calls in a commit hook


if __name__ == "__main__":
    try:
        main("--dry-run" in sys.argv)
    except Exception as exc:  # never break a commit
        print(f"issues post-commit: {exc}", file=sys.stderr)
    sys.exit(0)
