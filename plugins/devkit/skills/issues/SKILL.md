---
name: issues
description: Work with the repo's local issue tracker (plans-local/issues/ISS-NNN-*.md and its generated INDEX.md) — add an issue, pick the next ready one, start a session on one, update its Log, or close it. Use when the user says "add an issue", "what's next", "what's ready", "close ISS-012", "update the index", "make issues for this plan", or names an ISS- ID.
---

# Issues

The tracker's own `README.md` (in the issues folder, default `plans-local/issues/`; the
`issues.dir` value in `.claude/devkit.json` overrides it) is the source of truth for the
procedures. Read it first, every time, then follow it. This skill adds only the habits
around it.

If the repo has no issues folder, offer `/devkit:setup` instead.

## Habits

- **Never edit `INDEX.md`.** Change the issue files, then run `sync_index.py`. Use `--no-mrs`
  when offline or when the forge CLI isn't logged in.
- **What's next** = run `sync_index.py`, then name the lowest-Order ready issue and why it is
  ready (its dependencies are closed). Don't pick by gut.
- **Adding issues from a plan or spec**: one issue per branch-and-PR-sized piece. Fill
  `Depends on` honestly — that's what makes "ready" mean something. Give each a "Done when"
  list someone else could check, and a "Session prompt" that a fresh session can run with no
  other context.
- **Starting work**: set `Status: in-progress` and `Branch:` before the first commit, so the
  post-commit hook logs commits to the right issue.
- **Closing**: tick every "Done when" item or say in the Log why one is dropped. Write the
  result in the Log. Only then set `Status: closed`.
- **The hook writes facts, the session writes decisions.** Don't hand-write commit lines the
  hook already adds. Do write decisions, blockers and review outcomes in the Log.
- Before you stop on an issue, update its Status, its "Done when" list and its Log.
