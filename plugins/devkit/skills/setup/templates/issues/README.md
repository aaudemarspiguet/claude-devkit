# Issues log

{{TRACKING_NOTE}}

Each `ISS-NNN-<slug>.md` file is one action item. The issue file is the only source of its status. `INDEX.md` is made from the issue files. Do not edit `INDEX.md` by hand.

The forge (GitHub or GitLab) is the only source of PR status. `sync_index.py` reads the open PRs with `gh` or `glab` and writes them to the "Open PRs" section of `INDEX.md`: approvals, checks on the head commit, merge state, and the issues that name the PR. On GitLab it also shows the "blocked by" MRs that are not merged. Do not write PR status in an issue file. The forge comes from the `origin` remote; set `"issues": {"forge": "github" | "gitlab" | "none"}` in `.claude/devkit.json` to override it. Run `python {{ISSUES_DIR}}/sync_index.py --no-mrs` to skip the forge (offline). An issue is linked to a PR by the `PR:` header (for example `#19, #20` or `#23 to #27`; GitLab uses `!19`), by its title, or by its `Branch:` header.

## Header values
- Status: `open`, `in-progress`, `blocked`, `closed`.
- Priority: `P0` (do first), `P1` (important), `P2` (other items).
- Order: a number. `INDEX.md` sorts open issues by it. Do the lowest open, ready number first.
- Owner: initials, or `Both`.
- Tags: free text (a milestone, an area, a spec section).
- Depends on: issue IDs separated by commas, or `none`.
- Branch: the git branch of the issue, or `none`.
- PR: the PR numbers of the issue, or `none`.

## Start a session on one issue
1. Run `python {{ISSUES_DIR}}/sync_index.py`. It lists the ready issues. A ready issue is open, and all its dependencies are closed.
2. Open the issue file. Read the Log. Check that the Log matches the last session.
3. If the issue needs code, write the branch name in the `Branch:` header before the first commit.
4. Set `Status:` to `in-progress`.
5. Paste the "Session prompt" of the issue into a new session.

## Open a PR
1. Merge the default branch into your branch before you push. Do not rebase a pushed branch. Do not force-push.
2. Find the PRs that this PR must merge after: the open PR of each issue in `Depends on`, and each open PR that the code needs to work.
3. Write the merge order in the PR description. On GitLab, also set each one as "blocked by" (MR edit page, "Merge request dependencies").
4. Write the `PR:` header of the issue.
5. After each merge, merge the default branch into the next branch, and check that it has no conflict.

## Close an issue
1. Check each item in "Done when".
2. Write the result in the Log.
3. Set `Status:` to `closed`.
4. Run `python {{ISSUES_DIR}}/sync_index.py`.

## Add an issue
1. Copy `TEMPLATE.md` to `ISS-NNN-<slug>.md`. Use the next free number.
2. Fill in the header and the sections.
3. Run `python {{ISSUES_DIR}}/sync_index.py`.

## The post-commit hook
The git `post-commit` hook runs `post_commit.py` after each commit. Git does not track this hook.
- It skips a commit that changes only paths listed in `"issues": {"skip_commit_prefixes": [...]}` in `.claude/devkit.json`.
- It finds the issue whose `Branch:` header is the current branch. It adds one line to the Log of that issue: date, short SHA, subject, number of files.
- In a folder tracked in git, it adds no Log line: that would leave a changed file after every commit. `git log` on the issue's branch is the record.
- It rebuilds the issue part of `INDEX.md`. It does not call the forge, so commits stay fast. It keeps the old "Open PRs" section with its old time. Run `sync_index.py` by hand to refresh it.
- It never changes the status. It never commits. It always exits with 0.
- Merges in the forge web UI do not run the hook. Write them in the Log by hand.

To test the hook without a commit: `python {{ISSUES_DIR}}/post_commit.py --dry-run`.

## Rules
- One issue gives one branch and one PR, when the issue needs code.
- The hook writes facts (commits). The session writes decisions (status, checks, notes).
- Issues owned by someone else are tracking items. Close them when that person confirms.
