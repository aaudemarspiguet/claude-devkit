# claude-workflow

My personal Claude Code workflow as a plugin marketplace with one plugin, `workflow`.

## Install (once per machine)

```
/plugin marketplace add aaudemarspiguet/claude-workflow
/plugin install workflow@claude-workflow
```

Restart Claude Code. The skills are then available in every project as `/workflow:<name>`.

## Set up a project (once per repo)

In the repo, run `/workflow:workflow-init`. It detects the forge, CI files and source/test
folders, confirms the settings with you, then writes:

- `.claude/workflow.json`: turns the guard hooks on for this repo and configures them
- `plans-local/issues/`: `README.md`, `TEMPLATE.md`, `sync_index.py`, `post_commit.py`, `INDEX.md`
- `.git/hooks/post-commit`: logs each commit to the issue whose `Branch:` matches
- `.claude/rules/`: `no-code-during-design`, `sycophant-challenge`, `context-sync`
- a pointer block in `CLAUDE.local.md` (local mode) or `CLAUDE.md` (tracked mode)

Local mode (the default) puts all of that in `.git/info/exclude`, so nothing reaches the shared repo.

## What's in the plugin

| Skill | Use |
|---|---|
| `workflow-init` | Scaffold a repo (above) |
| `issues` | Add, pick, start, and close issues in the local tracker |
| `context-hierarchy` | Build nested `CLAUDE.md` context files, leaves to root |
| `design-discussion` | Elephant-Goldfish phase 1: scope and discuss, no code |
| `write-spec` | Phase 2: write the agreed design to `docs/plans/<feature>.md` |
| `goldfish-test` | Phase 3: zero-context test of the spec in a fresh session |
| `mean-review` | Adversarial review of a finished implementation |
| `clear-writing` | Simplified Technical English for docs and procedures |

**Companion skill, not bundled.** Keep `unslop-text` standalone in `~/.claude/skills/unslop-text`,
so `/unslop-text` works in any project. The plugin uses it when it is there: `write-spec`
and `clear-writing` end with an unslop pass, and the `workflow-init` pointer block asks for one
on reader-facing prose. Without the skill, those steps are skipped, and `--detect` notes that.

**Hooks** (`plugins/workflow/hooks/`). They do nothing in a repo without `.claude/workflow.json`.

- `guard_files.py` (Write/Edit): blocks protected paths and folders, and blocks shrinking an append-only file.
  It always protects `.claude/workflow.json` itself.
- `guard_bash.py` (Bash/PowerShell): blocks force-push, history rewrites and commits on
  protected branches, pushes without a one-shot `.claude/.push-approved`, and shell writes to protected paths.
- `session_warnings.py` (Stop): warns about being on a protected branch, unpushed commits or no upstream,
  source changed with no tests (with a list of changed Python functions), and the open issue for this branch.

## `.claude/workflow.json`

```json
{
  "protected_branches": ["main", "master"],
  "protected_paths": { ".github/workflows/ci.yml": "CI must stay as it is." },
  "protected_dirs": { "generated/": "Built by the codegen step." },
  "append_only_files": ["tests/test_starter.py"],
  "block_force_push": true,
  "require_push_approval": true,
  "source_dirs": ["src/"],
  "test_dirs": ["tests/"],
  "function_dirs": ["src/"],
  "issues": {
    "dir": "plans-local/issues",
    "forge": "auto",
    "order_note": "Work in the Order column. An issue is ready when all its dependencies are closed.",
    "skip_commit_prefixes": []
  }
}
```

`forge` is `auto` (from the `origin` remote: github.com uses `gh`, GitLab hosts use `glab`), or
`github`, `gitlab` or `none`.

## Notes

- The hooks call `python3`. They have no `|| python` fallback on purpose: if the first run blocks
  with exit 2, a fallback would run again on an empty stdin and allow the call. Make sure `python3` is on PATH.
- A broken `workflow.json` makes the guards fail closed (they block every call) until you fix it.
- Copies in a project don't update with the plugin. The tracker scripts and rules are copied
  into each repo, so a fix here doesn't reach older projects. Re-copy by hand if you need it.
- Plugins can't ship `.claude/rules/`, so `workflow-init` copies them into each repo.

## Develop

```
python3 plugins/workflow/tests/test_guards.py   # guard cases in a throwaway repo
claude plugin validate .
```
