---
name: workflow-init
description: Set up a repo for the personal workflow — guard config (.claude/workflow.json), a local issue tracker (plans-local/issues with INDEX.md, TEMPLATE.md, sync script, post-commit hook), the design rules, and a CLAUDE.md pointer. Use when the user says "init the workflow", "set up issues/tracker in this repo", "bootstrap this project", or starts a new project and wants their usual setup.
---

# Workflow Init

Scaffold this repo with the user's standard workflow. The script lives in this skill's base
directory (shown above when the skill loads; `${CLAUDE_SKILL_DIR}` if it was substituted).
Call it as `python3 "<skill dir>/scripts/init_project.py"`. On Windows, `python` works too.

It never overwrites a file that exists, so re-running it is safe.

## Procedure

1. **Detect.** Run the script with `--detect` from the repo. If it is not a git repo, stop and
   offer `git init`. If `already_initialised` is true, say so and ask whether the user wants a
   re-run (it only fills in missing pieces) or something else.
2. **Confirm the settings with the user in one message.** Show what you found and propose
   values. Ask only about what detection could not settle:
   - **Mode**: `local` (default — tracker, config and rules stay out of git via
     `.git/info/exclude`, pointer in `CLAUDE.local.md`) or `tracked` (all committed, pointer in
     `CLAUDE.md`). Local suits a team repo where the tracker is personal.
   - **Protected files**: suggest each detected CI file and anything else that must not change
     (lockfiles, generated files, course- or client-supplied docs). Each takes a reason.
   - **Protected folders** and **append-only files** (for example starter tests), if any.
   - **Source and test folders** for the end-of-session "source changed, no tests" check.
     Python folders worth a changed-function list go in `--function-dir`.
   - **Forge**: `auto` unless the remote host is unusual. Note that `gh` or `glab` must be
     logged in for the PR section.
3. **Run it** with the agreed flags (see the script's `--help`). Use `--dry-run` first if the
   user wants to see the plan.
4. **Report** what was written and skipped. If a post-commit hook already existed, show the
   line the user has to add to it by hand.
5. **Explain the lock.** After this, the plugin's guards are live in this repo, and
   `.claude/workflow.json` is protected from you. To change it, the user edits it, or you show
   them the exact edit to make.
6. **First issues.** Offer to write the first issues with the user. Follow the `issues` skill.

## What it creates

| Path | Purpose |
|---|---|
| `.claude/workflow.json` | Turns the plugin's guard hooks on for this repo and configures them |
| `<issues-dir>/README.md`, `TEMPLATE.md` | How the tracker works; the issue template |
| `<issues-dir>/sync_index.py`, `post_commit.py` | Builds `INDEX.md`; logs commits to the matching issue |
| `<issues-dir>/INDEX.md` | Generated index (empty at first) |
| `.git/hooks/post-commit` | Calls `post_commit.py` after each commit (untracked by git) |
| `.claude/rules/*.md` | `no-code-during-design`, `sycophant-challenge`, `context-sync` |
| `CLAUDE.local.md` or `CLAUDE.md` | A short pointer block so every session knows the workflow |
