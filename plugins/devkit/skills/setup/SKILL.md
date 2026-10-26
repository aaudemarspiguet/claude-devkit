---
name: setup
description: Set up a repo for the personal workflow — guard config (.claude/devkit.json), a local issue tracker (plans-local/issues with INDEX.md, TEMPLATE.md, sync script, post-commit hook), the design rules, and a CLAUDE.md pointer. Use when the user says "init the workflow", "set up issues/tracker in this repo", "bootstrap this project", or starts a new project and wants their usual setup. Also use it to elevate a local tracker to tracked, when the user says "make the issues public", "track the issues in git", "share the tracker with the team", or "elevate the issues".
---

# Devkit Setup

Scaffold this repo with the user's standard workflow. The script lives in this skill's base
directory (shown above when the skill loads; `${CLAUDE_SKILL_DIR}` if it was substituted).
Call it as `python3 "<skill dir>/scripts/init_project.py"`. On Windows, `python` works too.

It never overwrites a file that exists, so re-running it is safe.

## Procedure

1. **Detect.** Run the script with `--detect` from the repo. If it is not a git repo, stop and
   offer `git init`. If `already_initialised` is true, say so and ask whether the user wants a
   re-run (it only fills in missing pieces) or something else. If `unslop_text_installed` is
   false, note (don't block) that `unslop-text` was not found in `~/.claude/skills`, so the
   writing pass the pointer block asks for is skipped until it is installed standalone.
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
   `.claude/devkit.json` is protected from you. To change it, the user edits it, or you show
   them the exact edit to make.
6. **First issues.** Offer to write the first issues with the user. Follow the `issues` skill.

## Elevate a local tracker to tracked

Use this when a repo set up in local mode should start tracking its issues in git. Once a push
happens it can't be undone, so the user's review is the real safeguard. Never skip a step.

1. **Dry run.** Run `init_project.py --elevate --dry-run`. Add `--include rules,pointer,config`
   only if the user asked for more than the issues. It prints the files that will become
   tracked, the new folder (`plans-local/issues` becomes `plans/issues` unless `--keep-dir` or
   `--move-to DIR`), the branch, and the scan findings.
2. **Read every issue file yourself.** The scan only matches patterns. Look for what it can't
   see: remarks about named people, grades, scores, private plans, or anything written for
   the user's eyes only. Quote each one with its `file:line`.
3. **Show the user, in one message:**
   - the file list
   - the scan findings
   - your own findings
   - what each `--include` extra means for teammates: `rules` makes their Claude follow the
     rules; `config` turns the devkit guards on for anyone who has the plugin
   - that `INDEX.md` stays untracked, and that a tracked folder gets no automatic Log lines

   Ask whether to fix anything first, then get an explicit yes.
4. **Fix and re-run.** If the user wants edits, make them in the issue files, then run the dry
   run again. A `SECRET` finding blocks the run. Remove it; use `--allow-secrets` only if the
   user confirms the value is fake.
5. **Run it** without `--dry-run`. It creates the branch `chore/devkit-track-issues`, moves the
   folder and rewrites references, edits `.git/info/exclude`, stages the files, and stops. It
   needs a clean tree with no staged changes. It changes `issues.dir` in `.claude/devkit.json`
   itself, which is the one approved way that file changes.
6. **Report.** Show `git status` and the commit it suggests. Committing and pushing follow the
   normal flow, and pushing still needs the user's yes.

## What it creates

| Path | Purpose |
|---|---|
| `.claude/devkit.json` | Turns the plugin's guard hooks on for this repo and configures them |
| `<issues-dir>/README.md`, `TEMPLATE.md` | How the tracker works; the issue template |
| `<issues-dir>/sync_index.py`, `post_commit.py` | Builds `INDEX.md`; logs commits to the matching issue |
| `<issues-dir>/INDEX.md` | Generated index (empty at first) |
| `.git/hooks/post-commit` | Calls `post_commit.py` after each commit (untracked by git) |
| `.claude/rules/*.md` | `no-code-during-design`, `sycophant-challenge`, `context-sync` |
| `CLAUDE.local.md` or `CLAUDE.md` | A short pointer block so every session knows the workflow |
