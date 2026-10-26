"""Rebuild INDEX.md from the header block of each ISS-*.md file.

The issue files are the only source of issue status. The forge is the only
source of PR/MR status: the "Open PRs" section is read live with `gh` (GitHub)
or `glab` (GitLab). The forge is detected from the `origin` remote, or set with
"issues": {"forge": "github" | "gitlab" | "none"} in .claude/workflow.json.
Run:
    python plans-local/issues/sync_index.py            # issues and open PRs/MRs
    python plans-local/issues/sync_index.py --no-mrs   # issues only (offline)
"""

import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
INDEX = HERE / "INDEX.md"
FIELDS = ("Status", "Priority", "Order", "Owner", "Tags", "Depends on", "Branch", "PR", "MR")
STATUS_ORDER = {"in-progress": 0, "blocked": 1, "open": 2, "closed": 3}
DEFAULT_ORDER_NOTE = "Work in the Order column. An issue is ready when all its dependencies are closed."


def run(*cmd, timeout=30):
    result = subprocess.run(
        list(cmd), cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"{' '.join(cmd)} failed")
    return result.stdout.strip()


def repo_root():
    try:
        return Path(run("git", "rev-parse", "--show-toplevel"))
    except (OSError, RuntimeError):
        return HERE.parents[1]


REPO = HERE  # run() needs a cwd inside the repo before the root is known
REPO = repo_root()


def settings():
    """The "issues" block of .claude/workflow.json, or {}."""
    try:
        return json.loads((REPO / ".claude" / "workflow.json").read_text(encoding="utf-8")).get("issues", {})
    except (OSError, ValueError):
        return {}


def detect_forge():
    forge = settings().get("forge", "auto")
    if forge != "auto":
        return forge
    try:
        url = run("git", "remote", "get-url", "origin")
    except (OSError, RuntimeError):
        return "none"
    host = (urlparse(url).hostname if "://" in url else url.split("@")[-1].split(":")[0]) or ""
    if host == "github.com":
        return "github"
    if "gitlab" in host:
        return "gitlab"
    try:  # self-hosted GitLab on a host without "gitlab" in its name
        run("glab", "auth", "status", "--hostname", host, timeout=15)
        return "gitlab"
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return "none"


def parse(path):
    """Return the header of one issue file as a dict, or None if it is bad."""
    lines = path.read_text(encoding="utf-8").splitlines()
    m = re.match(r"#\s*(ISS-\d{3}):\s*(.+)", lines[0]) if lines else None
    if not m:
        return None
    issue = {"ID": m.group(1), "Title": m.group(2).strip(), "File": path.name}
    for line in lines[1:]:
        if line.startswith("## "):
            break
        fm = re.match(r"-\s*([A-Za-z ]+):\s*(.*)", line)
        if fm and fm.group(1).strip() in FIELDS:
            issue[fm.group(1).strip()] = fm.group(2).strip()
    if "Status" not in issue:
        return None
    issue["Status"] = issue["Status"].lower()
    issue.setdefault("PR", issue.get("MR", "none"))
    deps = issue.get("Depends on", "none")
    issue["deps"] = [] if deps.lower() == "none" else re.findall(r"ISS-\d{3}", deps)
    return issue


def load():
    issues, bad = [], []
    for path in sorted(HERE.glob("ISS-*.md")):
        try:
            issue = parse(path)
        except (OSError, UnicodeDecodeError):
            issue = None
        if issue is None:
            bad.append(path.name)
        else:
            issues.append(issue)
    return issues, bad


def order(i):
    """Order from the Order: header. Issues without one go last."""
    try:
        return int(i.get("Order", ""))
    except ValueError:
        return 999


def row(i):
    link = f"[{i['ID']}]({i['File']})"
    deps = ", ".join(i["deps"]) or "none"
    return (
        f"| {i.get('Order', '')} | {link} | {i['Title']} | {i['Status']} | {i.get('Priority', '')} "
        f"| {i.get('Owner', '')} | {i.get('Tags', '')} | {deps} | {i.get('Branch', 'none')} |"
    )


def pr_numbers(text, sigil):
    """PR numbers in a text: "#19, #20" gives 19 and 20; "#23 to #27" gives 23 to 27."""
    s = re.escape(sigil)
    nums = {int(n) for n in re.findall(rf"{s}(\d+)", text)}
    for lo, hi in re.findall(rf"{s}(\d+)\s+to\s+{s}(\d+)", text):
        nums.update(range(int(lo), int(hi) + 1))
    return nums


def linked_issues(pr, issues, sigil):
    """Issues that name the PR in the title or PR: header, or whose Branch: is its branch."""
    return [
        i["ID"]
        for i in issues
        if pr["number"] in pr_numbers(f"{i['Title']} {i.get('PR', '')}", sigil)
        or (pr["branch"] and i.get("Branch") == pr["branch"])
    ]


def cell(s):
    return str(s).replace("|", "\\|")


# --- GitLab ----------------------------------------------------------------

def glab(path):
    """GET one GitLab API path through glab and return the parsed JSON."""
    return json.loads(run("glab", "api", path))


def gitlab_details(mr):
    """Add the pipeline, approvals, and open blockers to one MR from the list."""
    base = f"projects/:id/merge_requests/{mr['iid']}"
    full = glab(base)
    approvals = glab(f"{base}/approvals")
    try:
        blocks = glab(f"{base}/blocks")  # Premium feature; absent on free tiers
    except RuntimeError:
        blocks = []
    pipeline = full.get("head_pipeline") or {}
    on_head = pipeline.get("sha") == full.get("sha")
    return {
        "number": mr["iid"],
        "url": mr["web_url"],
        "title": mr["title"],
        "author": mr["author"]["username"],
        "branch": mr.get("source_branch", ""),
        "checks": (pipeline.get("status", "none") if on_head else "not on head") if pipeline else "none",
        "approved_by": [a["user"]["username"] for a in approvals.get("approved_by", [])],
        "state": mr["detailed_merge_status"] + (", conflict" if mr.get("has_conflicts") else ""),
        "blockers": sorted(
            b["blocking_merge_request"]["iid"]
            for b in blocks
            if b["blocking_merge_request"]["state"] != "merged"
        ),
    }


def gitlab_prs():
    mrs = glab("projects/:id/merge_requests?state=opened&per_page=100")
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(gitlab_details, mrs))


# --- GitHub ----------------------------------------------------------------

FAILED = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}


def checks_summary(rollup):
    if not rollup:
        return "none"
    states = set()
    for c in rollup:
        if c.get("__typename") == "CheckRun" and (c.get("status") or "").upper() != "COMPLETED":
            states.add("PENDING")
        else:
            states.add((c.get("conclusion") or c.get("state") or "").upper())
    if states & FAILED:
        return "failure"
    if states & {"PENDING", "EXPECTED", "QUEUED", "IN_PROGRESS", ""}:
        return "pending"
    return "success"


def github_prs():
    fields = "number,title,author,url,headRefName,isDraft,mergeStateStatus,latestReviews,statusCheckRollup"
    prs = json.loads(run("gh", "pr", "list", "--state", "open", "--limit", "100", "--json", fields))
    return [
        {
            "number": p["number"],
            "url": p["url"],
            "title": p["title"],
            "author": (p.get("author") or {}).get("login", "?"),
            "branch": p.get("headRefName", ""),
            "checks": checks_summary(p.get("statusCheckRollup")),
            "approved_by": [r["author"]["login"] for r in p.get("latestReviews", []) if r.get("state") == "APPROVED"],
            "state": ("draft, " if p.get("isDraft") else "") + (p.get("mergeStateStatus") or "unknown").lower(),
            "blockers": None,
        }
        for p in prs
    ]


FORGES = {
    # forge: (loader, sigil, noun, checks column)
    "github": (github_prs, "#", "PR", "Checks"),
    "gitlab": (gitlab_prs, "!", "MR", "Pipeline"),
}


def load_prs(forge):
    """Open PRs/MRs, oldest first. Returns (prs, None) or (None, reason)."""
    if forge not in FORGES:
        return None, f"no forge sync (forge: {forge})"
    try:
        prs = FORGES[forge][0]()
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as e:
        return None, str(e).splitlines()[0] if str(e) else type(e).__name__
    return sorted(prs, key=lambda p: p["number"]), None


def pr_table(prs, issues, forge):
    _, sigil, noun, checks = FORGES[forge]
    gitlab = forge == "gitlab"
    head = f"| {noun} | Title | Author | Approved by | {checks} | Merge state |" + (" Blocked by |" if gitlab else "") + " Issues |"
    lines = [head, "|" + "---|" * (head.count("|") - 1)]
    for p in prs:
        blocked = (" " + (", ".join(f"!{n}" for n in p["blockers"]) or "none") + " |") if gitlab else ""
        lines.append(
            f"| [{sigil}{p['number']}]({p['url']}) | {cell(p['title'])} | {p['author']} "
            f"| {', '.join(p['approved_by']) or 'none'} | {p['checks']} | {p['state']} |{blocked} "
            f"{', '.join(linked_issues(p, issues, sigil)) or 'none'} |"
        )
    return lines


def old_pr_section():
    """The "## Open PRs" section of the current INDEX.md, or None."""
    if not INDEX.exists():
        return None
    m = re.search(r"^## Open (?:PRs|MRs)\n.*?(?=^## |\Z)", INDEX.read_text(encoding="utf-8"), re.M | re.S)
    return m.group(0).rstrip("\n").split("\n") if m else None


def main(with_mrs=None):
    """with_mrs=False keeps the old PR section (the post-commit hook uses this)."""
    if with_mrs is None:
        with_mrs = "--no-mrs" not in sys.argv[1:]
    issues, bad = load()
    by_id = {i["ID"]: i for i in issues}
    unknown = [(i["ID"], d) for i in issues for d in i["deps"] if d not in by_id]
    ready = [
        i["ID"]
        for i in issues
        if i["Status"] == "open"
        and all(by_id.get(d, {}).get("Status") == "closed" for d in i["deps"])
    ]

    active = [i for i in issues if i["Status"] != "closed"]
    closed = [i for i in issues if i["Status"] == "closed"]
    active.sort(key=lambda i: (order(i), i.get("Priority", "P9"), STATUS_ORDER.get(i["Status"], 9), i["ID"]))

    head = "| Order | ID | Title | Status | Priority | Owner | Tags | Depends on | Branch |\n|---|---|---|---|---|---|---|---|---|"
    out = [
        "# Issues index",
        "",
        "Do not edit this file by hand. `sync_index.py` makes it from the issue files.",
        f"Last rebuild: {datetime.now():%Y-%m-%d %H:%M}.",
        "",
        f"Open: {len(active)}. Closed: {len(closed)}. Ready now: {', '.join(ready) or 'none'}.",
        "",
        "## Open issues",
        "",
        settings().get("order_note", DEFAULT_ORDER_NOTE),
        "",
    ]
    out += [head, *[row(i) for i in active]] if active else ["None."]
    out += ["", "## Closed issues", ""]
    out += [head, *[row(i) for i in closed]] if closed else ["None yet."]

    forge = detect_forge() if with_mrs else None
    prs, pr_error = load_prs(forge) if with_mrs else (None, "skipped")
    kept = None if with_mrs else old_pr_section()
    out.append("")
    if kept:
        out += kept
    else:
        now = f"{datetime.now():%Y-%m-%d %H:%M}"
        out += ["## Open PRs", ""]
        if prs is None:
            out.append(f"Not available at {now}: {pr_error}")
        else:
            out += [f"Read from {forge} at {now}. Run `sync_index.py` by hand to refresh.", ""]
            out += pr_table(prs, issues, forge) if prs else ["None."]

    if bad or unknown:
        out += ["", "## Problems", ""]
        out += [f"- Bad header, skipped: `{name}`" for name in bad]
        out += [f"- {iid} depends on unknown issue {dep}" for iid, dep in unknown]
    INDEX.write_text("\n".join(out) + "\n", encoding="utf-8")

    print(f"INDEX.md rebuilt: {len(active)} open, {len(closed)} closed.")
    print(f"Ready: {', '.join(ready) or 'none'}")
    if kept:
        print("Open PRs: kept the last PR section (not refreshed).")
    elif prs is None:
        print(f"Open PRs: not available ({pr_error})", file=sys.stderr)
    else:
        print(f"Open PRs ({forge}): {len(prs)}")
    for name in bad:
        print(f"WARNING: bad header, skipped {name}", file=sys.stderr)
    for iid, dep in unknown:
        print(f"WARNING: {iid} depends on unknown {dep}", file=sys.stderr)


if __name__ == "__main__":
    main()
