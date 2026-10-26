"""End-to-end tests for setup and --elevate, in throwaway git repos:
    python3 plugins/devkit/tests/test_setup.py
"""

import os
import subprocess
import sys
import tempfile

INIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "setup", "scripts", "init_project.py")
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

ISSUE = """# ISS-001: First thing
- Status: open
- Priority: P1
- Order: 1
- Owner: A
- Tags: R1
- Depends on: none
- Branch: {branch}
- PR: none

## Session prompt
```
Work on plans-local/issues/ISS-001-first.md. {extra}
```

## Log
"""

failures = total = 0


def check(cond, label, detail=""):
    global failures, total
    total += 1
    failures += not cond
    print(f"{'ok  ' if cond else 'FAIL'} {label}" + ("" if cond else f"  {detail}"))


def sh(repo, *cmd):
    return subprocess.run(list(cmd), cwd=repo, capture_output=True, text=True, encoding="utf-8", env=ENV)


def git(repo, *args):
    return sh(repo, "git", *args)


def init(repo, *flags):
    return sh(repo, sys.executable, INIT, *flags)


def ignored(repo, path):
    return git(repo, "check-ignore", "-q", "--", path).returncode == 0


def read(repo, path):
    with open(os.path.join(repo, path), encoding="utf-8") as fh:
        return fh.read()


def write(repo, path, text):
    full = os.path.join(repo, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def make_repo(tmp, name, branch="chore/devkit-track-issues", extra="", gitignore=None):
    """A repo with a remote, set up in local mode, with one issue."""
    remote = os.path.join(tmp, name + "-remote.git")
    repo = os.path.join(tmp, name)
    os.makedirs(repo)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", remote], check=True)
    git(repo, "init", "-q", "-b", "main")
    write(repo, "src/app.py", "x = 1\n")
    if gitignore:
        write(repo, ".gitignore", gitignore)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    git(repo, "remote", "add", "origin", remote)
    git(repo, "push", "-q", "origin", "main")
    git(repo, "remote", "set-head", "origin", "main")
    r = init(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    write(repo, "plans-local/issues/ISS-001-first.md", ISSUE.format(branch=branch, extra=extra))
    sh(repo, sys.executable, "plans-local/issues/sync_index.py", "--no-mrs")
    return repo


def snapshot(repo):
    files = []
    for d, _, names in os.walk(repo):
        if ".git" in d.split(os.sep):
            continue
        files += [os.path.relpath(os.path.join(d, n), repo) for n in names]
    return sorted(files), read(repo, ".git/info/exclude"), git(repo, "status", "--porcelain").stdout, git(repo, "branch", "--show-current").stdout


def staged(repo):
    return set(git(repo, "diff", "--cached", "--name-only").stdout.split())


def main():
    with tempfile.TemporaryDirectory() as tmp:
        print("== 1. dry run changes nothing")
        repo = make_repo(tmp, "dry")
        before = snapshot(repo)
        r = init(repo, "--elevate", "--dry-run")
        check(r.returncode == 0, "dry run exits 0", r.stdout)
        check(snapshot(repo) == before, "tree, exclude, status and branch unchanged")
        check("plans/issues/ISS-001-first.md" in r.stdout, "dry run lists files at their new path")
        check("issues_tracked\": false" in init(repo, "--detect").stdout, "detect says local")

        print("\n== 2. default elevate: move to plans/issues, stage on a branch")
        r = init(repo, "--elevate")
        check(r.returncode == 0, "elevate exits 0", r.stdout + r.stderr)
        check(git(repo, "branch", "--show-current").stdout.strip() == "chore/devkit-track-issues", "on the new branch")
        check(os.path.isdir(os.path.join(repo, "plans/issues")), "folder moved")
        check(not os.path.exists(os.path.join(repo, "plans-local")), "empty plans-local/ removed")
        check(not ignored(repo, "plans/issues/ISS-001-first.md"), "issue file no longer ignored")
        check(ignored(repo, "plans/issues/INDEX.md"), "INDEX.md ignored by the tracked .gitignore")
        check("plans-local/" not in read(repo, ".git/info/exclude").split("\n"), "plans-local/ line removed")
        check(ignored(repo, ".claude/devkit.json") and ignored(repo, "CLAUDE.local.md"), "config and pointer stay local")
        check('"dir": "plans/issues"' in read(repo, ".claude/devkit.json"), "devkit.json issues.dir updated")
        check("plans/issues/post_commit.py" in read(repo, ".git/hooks/post-commit"), "hook shim updated")
        check("`plans/issues/`" in read(repo, "CLAUDE.local.md"), "pointer block updated")
        check("tracked in git" in read(repo, "plans/issues/README.md"), "README has the tracked note")
        check("plans/issues/ISS-001-first.md" in read(repo, "plans/issues/ISS-001-first.md"), "Session prompt path rewritten")
        s = staged(repo)
        check({"plans/issues/ISS-001-first.md", "plans/issues/.gitignore", "plans/issues/README.md"} <= s, "issue files staged", s)
        check("plans/issues/INDEX.md" not in s and not any(p.startswith(".claude") for p in s), "INDEX.md and .claude not staged", s)
        check("issues_tracked\": true" in init(repo, "--detect").stdout, "detect says tracked")

        print("\n== 5. commit after elevate: no Log line, clean tree")
        c = git(repo, "commit", "-qm", "Track issues")
        check(c.returncode == 0, "commit ok", c.stderr)
        check("commit " not in read(repo, "plans/issues/ISS-001-first.md").split("## Log")[1], "no Log line written")
        check(git(repo, "status", "--porcelain").stdout.strip() == "", "tree clean after commit", git(repo, "status", "--porcelain").stdout)
        r = init(repo, "--elevate")
        check(r.returncode == 0 and "already tracked" in r.stdout, "second elevate is a no-op")

        print("\n== 3. --keep-dir with a local sibling folder")
        repo = make_repo(tmp, "keep")
        write(repo, "plans-local/notes/private.md", "just mine\n")
        r = init(repo, "--elevate", "--keep-dir")
        check(r.returncode == 0, "elevate exits 0", r.stdout + r.stderr)
        check(not ignored(repo, "plans-local/issues/ISS-001-first.md"), "issues re-included")
        check(ignored(repo, "plans-local/notes/private.md"), "sibling notes stay ignored")
        check(not any("notes" in p for p in staged(repo)), "notes not staged")

        print("\n== 4. a token blocks elevation")
        repo = make_repo(tmp, "secret", extra="token ghp_" + "a" * 36)
        before = snapshot(repo)
        r = init(repo, "--elevate")
        check(r.returncode == 2 and "BLOCKED" in r.stdout, "exit 2 with BLOCKED", r.stdout)
        check(snapshot(repo) == before, "nothing changed")
        r = init(repo, "--elevate", "--allow-secrets")
        check(r.returncode == 0, "--allow-secrets goes ahead", r.stdout)

        print("\n== 6. the repo's .gitignore still hides the target")
        repo = make_repo(tmp, "hidden", gitignore="plans/\n")
        r = init(repo, "--elevate")
        check(r.returncode == 0 and "still ignored, not staged" in r.stdout, "hidden path reported", r.stdout)
        check(not staged(repo), "nothing staged")

        print("\n== 7. --include pointer moves the block to CLAUDE.md")
        repo = make_repo(tmp, "pointer")
        r = init(repo, "--elevate", "--include", "pointer")
        check(r.returncode == 0, "elevate exits 0", r.stdout + r.stderr)
        check("<!-- devkit-plugin:start -->" in read(repo, "CLAUDE.md") and "`plans/issues/`" in read(repo, "CLAUDE.md"), "CLAUDE.md has the new block")
        check(not os.path.exists(os.path.join(repo, "CLAUDE.local.md")), "empty CLAUDE.local.md removed")
        check("CLAUDE.md" in staged(repo), "CLAUDE.md staged")

        print("\n== 8. preconditions")
        repo = make_repo(tmp, "dirty")
        write(repo, "src/app.py", "x = 2\n")
        r = init(repo, "--elevate")
        check(r.returncode == 1 and "modified tracked files" in r.stdout, "modified tracked file blocks", r.stdout)

    print(f"\n{total - failures}/{total} passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
