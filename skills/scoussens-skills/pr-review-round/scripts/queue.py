#!/usr/bin/env python3
"""queue.py <base-branch>

The triage pass. Every open non-draft PR against <base>, oldest first, with the
three facts that decide what you do next: who is actually blocking (you or the
author), whether CI is even meaningful yet, and how risky the changed paths are.

Run this once at the start of a round. Reviewing in creation order matters --
the oldest PRs have the most accumulated review history to reconcile, and
merging them first is what stops the queue growing.
"""
import json, subprocess, sys, time

# Two phases on purpose. Asking for `files` + `statusCheckRollup` across a
# whole PR list makes GitHub's GraphQL endpoint 504 once the queue gets big --
# so the list call stays cheap and the heavy per-PR fields are fetched one at a
# time, where a single failure degrades one row instead of the whole run.
LIST_FIELDS = ("number,title,author,createdAt,isDraft,reviewDecision,"
               "mergeable,mergeStateStatus,additions,deletions,changedFiles,"
               "autoMergeRequest")
DETAIL_FIELDS = "files,statusCheckRollup"

# Risk tiers drive review depth. Classify by the *riskiest* path in the diff:
# a PR touching a migration and a stylesheet is a DATA PR, not a WEB one.
TIERS = [
    ("DATA",  ("migrations/", "/seed/", "schema.sql", "V001", "il_specs",
               "customer-upgrades", "/store/", "store.py", "_specs.py", "/mongo/")),
    ("AUTH",  ("auth", "jwt", "principal", "licens", "secret", "middleware",
               "ws_tickets", "token", "permission")),
    ("API",   ("routers/", "/services/", "sql_queries/", "ILCrud", "/api/",
               "packages/", "/dags/")),
    ("INFRA", ("/terraform/", ".github/workflows/", "Dockerfile",
               "docker-compose", "/infra/")),
    ("WEB",   ("apps/web/", ".tsx", ".jsx", ".css")),
]


def tier(paths):
    joined = " ".join(paths)
    for name, pats in TIERS:
        if any(p in joined for p in pats):
            return name
    if paths and all(p.endswith((".md", ".json", ".html")) or "docs/" in p for p in paths):
        return "DOCS"
    return "OTHER"


def auto_of(pr):
    """AUTO means the author enabled auto-merge, so your approval is the merge
    action -- GitHub enqueues the moment the review gate clears, with no merge
    command from you. Read this column before approving, not after."""
    return "AUTO" if pr.get("autoMergeRequest") else "-"


def blocker_of(pr, red):
    """Who has to act. This is the most useful column: a conflict or a stale
    branch is the author's problem and approving does not clear it, so those
    must never be answered with 'request changes'."""
    ms, rd = pr["mergeStateStatus"], pr.get("reviewDecision")
    if ms in ("DIRTY", "CONFLICTING"):
        return "AUTHOR: conflicts"
    if ms == "BEHIND":
        return "AUTHOR: behind base"
    if red:
        return "AUTHOR: red CI"
    if rd == "CHANGES_REQUESTED":
        return "REVIEW: changes-req"
    if rd == "APPROVED" and ms == "CLEAN":
        return "-> MERGEABLE NOW"
    return "REVIEW: needs review"


def gh_json(args, tries=3):
    """gh with a retry. The API 504s under load often enough that a single
    transient failure should not abort a review round."""
    for attempt in range(tries):
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode == 0:
            try:
                return json.loads(r.stdout)
            except json.JSONDecodeError:
                pass
        if attempt < tries - 1:
            time.sleep(2 * (attempt + 1))
    return None


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: queue.py <base-branch>")
    base = sys.argv[1]
    listed = gh_json(["gh", "pr", "list", "--base", base, "--state", "open",
                      "--limit", "200", "--json", LIST_FIELDS])
    if listed is None:
        sys.exit("could not list PRs (gh failed after retries) -- check auth and network")
    prs = [p for p in listed if not p["isDraft"]]
    prs.sort(key=lambda p: p["createdAt"])
    for p in prs:
        detail = gh_json(["gh", "pr", "view", str(p["number"]), "--json", DETAIL_FIELDS])
        p.update(detail or {"files": [], "statusCheckRollup": []})
        p["_degraded"] = detail is None

    print(f"{len(prs)} open non-draft PR(s) targeting {base}, oldest first\n")
    hdr = (f'{"PR":<7}{"OPENED":<12}{"AUTHOR":<18}{"RISK":<7}'
           f'{"SIZE":<13}{"BLOCKER":<22}{"CI":<9}{"AUTO":<6}TITLE')
    print(hdr)
    print("-" * len(hdr))
    for p in prs:
        paths = [f["path"] for f in (p.get("files") or [])]
        checks = p.get("statusCheckRollup") or []
        state = lambda c: c.get("conclusion") or c.get("state")
        red = [c for c in checks if state(c) in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT")]
        pend = [c for c in checks if state(c) in ("PENDING", "IN_PROGRESS", "QUEUED", None, "")]
        if p.get("_degraded"):
            ci = "?"          # detail fetch failed; re-check this row by hand
        else:
            ci = f"{len(red)} RED" if red else (f"{len(pend)} pend" if pend else "green")
        size = f'+{p["additions"]}/-{p["deletions"]}'
        print(f'#{p["number"]:<6}{p["createdAt"][:10]:<12}{p["author"]["login"][:17]:<18}'
              f'{tier(paths):<7}{size:<13}{blocker_of(p, red):<22}{ci:<9}'
              f'{auto_of(p):<6}{p["title"][:46]}')

    print("""
RISK -> depth   DATA/AUTH  full independent trace; check migrations and reverts
                API/INFRA  verify open findings, then trace the changed logic
                WEB        verify findings, check key logic in both directions
                DOCS       check the claims actually match the diff

BLOCKER         AUTHOR:*   approve anyway when the CODE is ready -- that clears
                           the review gate -- then comment about the conflict.
                           Requesting changes for a conflict just adds noise.
AUTO            The author enabled auto-merge, so APPROVING IS LANDING: GitHub
                enqueues as soon as the review gate clears and no merge command
                is needed. Check this column before you approve. Confirm the
                landing with `land.py --watch <n>`, which only polls.

CI              'N RED' is not automatically the author's fault: a failing
                review/lint job is sometimes the reviewer tooling erroring out,
                not a finding. Read the job before you attribute it.""")


if __name__ == "__main__":
    main()
