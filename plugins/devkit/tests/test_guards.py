"""Run the guard hooks against a table of inputs and expected exit codes.

Builds a throwaway git repo with a .claude/devkit.json, so it runs anywhere:
    python3 plugins/devkit/tests/test_guards.py
"""

import json
import os
import subprocess
import sys
import tempfile

HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks")
GUARD_BASH = os.path.join(HOOKS, "guard_bash.py")
GUARD_FILES = os.path.join(HOOKS, "guard_files.py")

PUSH = "git" + " push"  # split so this file's own text is inert
COMMIT = "git" + " commit"

CONFIG = {
    "protected_paths": {
        ".gitlab-ci.yml": "CI file.",
        "web/tsconfig.json": "Type-check strictness.",
        "rubric.md": "Supplied doc.",
    },
    "protected_dirs": {"ai_log/": "Hook-written logs."},
    "append_only_files": ["tests/test_starter.py"],
}


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def make_repo(tmp, branch, with_config=True):
    repo = os.path.join(tmp, branch.replace("/", "_") + ("" if with_config else "_plain"))
    os.makedirs(os.path.join(repo, ".claude"))
    os.makedirs(os.path.join(repo, "tests"))
    git(repo, "init", "-q", "-b", branch)
    if with_config:
        with open(os.path.join(repo, ".claude", "devkit.json"), "w", encoding="utf-8") as fh:
            json.dump(CONFIG, fh)
    with open(os.path.join(repo, "tests", "test_starter.py"), "w", encoding="utf-8") as fh:
        fh.write("a\nb\nc\n")
    return repo


def run(script, payload):
    p = subprocess.run([sys.executable, script], input=json.dumps(payload), capture_output=True, text=True)
    return p.returncode, p.stderr.strip().splitlines()[:1]


def bash_cases(on_main):
    m = 2 if on_main else 0
    return [
        (f"{PUSH} -u origin HEAD", 2, "push needs approval"),
        (f"git -C some/dir {PUSH[4:]} origin HEAD", 2, "git -C dir push needs approval"),
        (f"{PUSH} --force origin feat/x", 2, "force push"),
        (f"{PUSH} origin +feat/x", 2, "force push via +refspec"),
        (f'echo "{PUSH}"', 0, "quoted push is inert"),
        (f'{COMMIT} -m "x"', m, "commit"),
        (f'{COMMIT} -m "fix \\"quoted\\" bug"', m, "commit w/ escaped quotes"),
        ("git reset --hard origin/main", m, "reset --hard"),
        ("sed -i s/a/b/ .gitlab-ci.yml", 2, "shell write to root CI file"),
        ("echo x > web/tsconfig.json", 2, "shell write to nested protected file"),
        ("echo x > other/tsconfig.json", 0, "same name elsewhere is free"),
        ("rm ai_log/x.md", 2, "shell delete in protected dir"),
        ("echo x >> .claude/devkit.json", 2, "config is self-protected"),
        ("cat .gitlab-ci.yml.bak > /dev/null", 0, "similar name, discard redirect"),
        ("git status --short", 0, "status"),
        ("ls ai_log", 0, "reading a protected dir is fine"),
        ("git switch -c feat/x --no-track origin/main", 0, "branching"),
        ("grep -n R10 rubric.md 2>/dev/null", 0, "discard redirect is not a write"),
        ("cat rubric.md > rubric.md", 2, "real redirect onto rubric.md"),
        ('sed -i s/a/b/ ".gitlab-ci.yml"', 2, "quoted CI path"),
    ]


PS_CASES = [
    (f"{PUSH} origin HEAD", 2, "PS: push needs approval"),
    ("Set-Content -Path .gitlab-ci.yml -Value x", 2, "PS: Set-Content on CI file"),
    ("Set-Content -Path '.gitlab-ci.yml' -Value x", 2, "PS: quoted CI path"),
    (r"Remove-Item ai_log\x.md", 2, "PS: delete in protected dir"),
    (r"Set-Content .\.gitlab-ci.yml x", 2, "PS: backslash before dot"),
    (r"Set-Content 'C:\repo\web\tsconfig.json' x", 2, "PS: quoted Windows path, nested file"),
    ("Get-Content .gitlab-ci.yml", 0, "PS: reading is fine"),
    ("Get-Content rubric.md 2>$null", 0, "PS: discard redirect"),
]


def file_cases(repo):
    j = lambda *p: os.path.join(repo, *p)  # noqa: E731
    return [
        ({"file_path": j(".gitlab-ci.yml"), "content": "x"}, 2, "Write CI file"),
        ({"file_path": j("web", "tsconfig.json"), "content": "x"}, 2, "Write nested protected file"),
        ({"file_path": j("other", "tsconfig.json"), "content": "x"}, 0, "same name elsewhere"),
        ({"file_path": j(".claude", "devkit.json"), "content": "{}"}, 2, "config is self-protected"),
        ({"file_path": j("ai_log", "s.md"), "content": "x"}, 2, "Write into protected dir"),
        ({"file_path": j("tests", "test_starter.py"), "old_string": "a\nb\n", "new_string": "a\n"}, 2, "shrink append-only (Edit)"),
        ({"file_path": j("tests", "test_starter.py"), "old_string": "a\n", "new_string": "a\nz\n"}, 0, "grow append-only (Edit)"),
        ({"file_path": j("tests", "test_starter.py"), "content": "a\n"}, 2, "shrink append-only (Write)"),
        ({"file_path": j("src", "app.py"), "content": "x"}, 0, "ordinary file"),
        ({"file_path": os.path.join(os.path.dirname(repo), "elsewhere.md"), "content": "x"}, 0, "outside the repo"),
    ]


def main():
    failures = total = 0

    def check(script, payload, want, label):
        nonlocal failures, total
        total += 1
        code, first = run(script, payload)
        ok = code == want
        failures += not ok
        print(f"{'ok  ' if ok else 'FAIL'} [{code}/{want}] {label}" + ("" if ok else f"  {first}"))

    with tempfile.TemporaryDirectory() as tmp:
        for branch in ("main", "feat/x"):
            repo = make_repo(tmp, branch)
            print(f"\n== Bash, on {branch}")
            for cmd, want, label in bash_cases(branch == "main"):
                check(GUARD_BASH, {"tool_name": "Bash", "cwd": repo, "tool_input": {"command": cmd}}, want, label)
        print("\n== PowerShell, on feat/x")
        for cmd, want, label in PS_CASES:
            check(GUARD_BASH, {"tool_name": "PowerShell", "cwd": repo, "tool_input": {"command": cmd}}, want, label)

        print("\n== push sentinel is one-shot")
        sentinel = os.path.join(repo, ".claude", ".push-approved")
        open(sentinel, "w").close()
        check(GUARD_BASH, {"tool_name": "Bash", "cwd": repo, "tool_input": {"command": f"{PUSH} origin HEAD"}}, 0, "push with sentinel")
        check(GUARD_BASH, {"tool_name": "Bash", "cwd": repo, "tool_input": {"command": f"{PUSH} origin HEAD"}}, 2, "second push without it")

        print("\n== Write/Edit")
        for tool_input, want, label in file_cases(repo):
            check(GUARD_FILES, {"tool_name": "Write", "cwd": repo, "tool_input": tool_input}, want, label)

        print("\n== repo without devkit.json: everything allowed")
        plain = make_repo(tmp, "main", with_config=False)
        check(GUARD_BASH, {"tool_name": "Bash", "cwd": plain, "tool_input": {"command": f"{PUSH} --force"}}, 0, "force push allowed")
        check(GUARD_BASH, {"tool_name": "Bash", "cwd": plain, "tool_input": {"command": f'{COMMIT} -m x'}}, 0, "commit on main allowed")
        check(GUARD_FILES, {"tool_name": "Write", "cwd": plain, "tool_input": {"file_path": os.path.join(plain, ".gitlab-ci.yml"), "content": "x"}}, 0, "write allowed")

        print("\n== broken config fails closed")
        with open(os.path.join(repo, ".claude", "devkit.json"), "w") as fh:
            fh.write("{not json")
        check(GUARD_BASH, {"tool_name": "Bash", "cwd": repo, "tool_input": {"command": "ls"}}, 2, "bash blocked")
        check(GUARD_FILES, {"tool_name": "Write", "cwd": repo, "tool_input": {"file_path": os.path.join(repo, "a.md"), "content": "x"}}, 2, "write blocked")

    print(f"\n{total - failures}/{total} passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
