#!/usr/bin/env python3
"""queue.py <base-branch> [--save-scope <file> | --scope <file>]

The triage pass. Every open non-draft PR against <base>, oldest first, with the
facts that decide what you do next: who is actually blocking (you or the
author), whether CI is even meaningful yet, how risky the changed paths are,
where your own review stands against the live head, and what changed since
your last saved assessment.

Run it at the start of a round with --save-scope, and again before the report
with --scope: drafts get marked ready and PRs open while you review, and the
second run names the PRs that JOINED or LEFT. Reviewing in creation order
matters -- the oldest PRs have the most accumulated review history to
reconcile, and merging them first is what stops the queue growing.
"""
import argparse, json, subprocess, sys, time
from pathlib import Path
from review_requests import collect, reconcile, effective_reviews
from ledger import assessments, handled_requests, repo_slug
from stacks import stack_of, label as stack_label, missing_members

# Two phases on purpose. Asking for `files` + `statusCheckRollup` across a
# whole PR list makes GitHub's GraphQL endpoint 504 once the queue gets big --
# so the list call stays cheap and the heavy per-PR fields are fetched one at a
# time, where a single failure degrades one row instead of the whole run.
LIST_FIELDS = ("number,title,author,createdAt,isDraft,reviewDecision,"
               "mergeable,mergeStateStatus,additions,deletions,changedFiles,"
               "autoMergeRequest,headRefOid,baseRefOid,updatedAt")
DETAIL_FIELDS = "files,statusCheckRollup"

# Risk tiers drive review depth. Classify by the *riskiest* path in the diff:
# a PR touching a migration and a stylesheet is a DATA PR, not a WEB one.
#
# These patterns are deliberately generic — they are the vocabulary most stacks
# share, not one repo's layout. Add your repo's own names (a migration prefix,
# an ORM class, a package dir) in `.pr-review-tiers.json` at the repo root:
#
#     {"DATA": ["V001__", "db/specs/"], "API": ["BaseCrud"]}
#
# The point is the OTHER count printed at the end. Tier-driven depth is this
# script's whole purpose, so a queue where most PRs land in OTHER means the
# patterns do not fit this repo and the depth column should not be trusted --
# far better to say so than to let every PR quietly read as low risk.
# Anchor every pattern that could appear inside a longer word: a bare "entity"
# matches "identity" and files an auth change as DATA. Prefer "/entities/" to
# "entity", "/seed/" to "seed".
#
# Order is load-bearing: the first match wins, so the stricter tier must come
# first. DATA before AUTH is deliberate — auth vocabulary ("secret", "token")
# appears incidentally across a large diff, while a migration path does not.
TIERS = [
    ("DATA",  ("migration", "/seed/", "schema.sql", "/store/", "store.py",
               "/mongo/", "/models/", "/entities/", "/repositories/")),
    ("AUTH",  ("auth", "jwt", "principal", "licens", "billing", "entitlement",
               "secret", "middleware", "token", "permission", "session",
               "credential")),
    ("API",   ("routers/", "/services/", "/handlers/", "/controllers/",
               "sql_quer", "/queries/", "query_builder", "/api/", "packages/",
               "/jobs/", "/dags/", "/cron")),
    ("INFRA", ("/terraform/", ".github/workflows/", "Dockerfile",
               "docker-compose", "/infra/", "/deploy", "/helm/", ".tf")),
    ("WEB",   ("/web/", "/frontend/", "/ui/", ".tsx", ".jsx", ".vue",
               ".svelte", ".css", ".scss")),
]


def load_overrides(path=".pr-review-tiers.json"):
    """Repo-supplied patterns, merged onto the generic ones. Absent is normal."""
    try:
        with open(path) as f:
            extra = json.load(f)
    except (OSError, ValueError):
        return TIERS
    merged = []
    for name, pats in TIERS:
        merged.append((name, tuple(pats) + tuple(extra.get(name) or ())))
    return merged


def tier(paths, tiers=None):
    joined = " ".join(paths).lower()
    for name, pats in (tiers or TIERS):
        if any(p.lower() in joined for p in pats):
            return name
    if paths and all(p.endswith((".md", ".json", ".html")) or "docs/" in p for p in paths):
        return "DOCS"
    return "OTHER"


def auto_of(pr):
    """AUTO means the author enabled auto-merge, so your approval is the merge
    action -- GitHub enqueues the moment the review gate clears, with no merge
    command from you. Read this column before approving, not after."""
    return "AUTO" if pr.get("autoMergeRequest") else "-"


def blocker_of(pr, red, mine=None):
    """Who has to act. This is the most useful column: a conflict or a stale
    branch is the author's problem and approving does not clear it, so those
    must never be answered with 'request changes'. An approval of yours at the
    head that leaves the PR REVIEW_REQUIRED needs someone else, not you again."""
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
    if rd == "REVIEW_REQUIRED" and mine == "approved at head":
        return "REVIEW: another approver"
    return "REVIEW: needs review"


def me():
    """The login behind `gh`; None when it cannot be read."""
    r = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True)
    return (r.stdout.strip() or None) if r.returncode == 0 else None


def my_review_of(evidence, login, head):
    """Where your own latest decisive review stands against the live head. A
    dismissed review, or one submitted against an earlier commit, no longer
    covers the code that is there."""
    if not login or "reviews" in evidence.get("failedFetches", []):
        return "?"
    review = effective_reviews(evidence["pr"].get("reviews", [])).get(login)
    if not review:
        return "none"
    if review["state"] == "DISMISSED":
        return "DISMISSED"
    where = "at head" if (review.get("commit_id") or review.get("commitOid")) == head else "at old head"
    return ("approved " if review["state"] == "APPROVED" else "changes-req ") + where


def since_last_look(saved, head, base, updated):
    """Compare the live PR with the last saved assessment, so nobody compares SHAs by hand."""
    if not saved:
        return "new"
    if saved["head"] != head:
        return "HEAD MOVED"
    if saved["base"] != base:
        return "base moved"
    return "unchanged" if saved["evidence_inputs"].get("forge") == updated else "discussion changed"


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


def request_label(state):
    active = [r for r in state["requests"] if r["outstanding"]]
    label = "Review requested again" if any(r["renewed"] for r in active) else "Review requested" if active else "No request"
    if state["coverage"] != "complete":
        return label + " · UNKNOWN" if active else "Request coverage UNKNOWN"
    return label


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base")
    scope_mode = parser.add_mutually_exclusive_group()
    scope_mode.add_argument("--save-scope", type=Path, help="write the listed PR numbers as the round's scope")
    scope_mode.add_argument("--scope", type=Path, help="name the PRs that joined or left since the saved scope")
    args = parser.parse_args()
    base = args.base
    if args.save_scope and args.save_scope.exists():
        sys.exit(f"{args.save_scope} already exists; it is the round's original scope. Compare with --scope instead of replacing it")
    scoped = None
    if args.scope:
        try:
            scoped = json.loads(args.scope.read_text())
        except (OSError, ValueError):
            scoped = None
        if not isinstance(scoped, list) or any(type(n) is not int for n in scoped):
            sys.exit(f"{args.scope} is not a readable JSON list of PR numbers; scope comparison unknown")
    listed = gh_json(["gh", "pr", "list", "--base", base, "--state", "open",
                      "--limit", "200", "--json", LIST_FIELDS])
    if listed is None or len(listed) >= 200:
        sys.exit("queue unavailable or at collection limit; coverage unknown -- check auth, network or paginate the scope")
    prs = [p for p in listed if not p["isDraft"]]
    slug = repo_slug()
    if not slug:
        sys.exit("repository unavailable; request coverage unknown")
    # Upper stack layers target the branch below them, not <base>, so the
    # listing above misses them. Add every open member of a stack rooted on <base>.
    stacks = {p["number"]: stack_of(slug, p["number"]) for p in prs}
    for number in missing_members(stacks.values(), set(stacks), base):
        extra = gh_json(["gh", "pr", "view", str(number), "--json", LIST_FIELDS])
        if not extra or extra.get("number") != number:
            sys.exit(f"stacked PR #{number} unavailable; coverage unknown")
        prs.append(extra)
        stacks[number] = stack_of(slug, number)
    prs.sort(key=lambda p: p["createdAt"])
    for p in prs:
        detail = gh_json(["gh", "pr", "view", str(p["number"]), "--json", DETAIL_FIELDS])
        p.update(detail or {"files": [], "statusCheckRollup": []})
        p["_degraded"] = detail is None

    saved = handled_requests(slug)
    assessed = assessments(slug)
    login = me()
    request_states = {}
    stale = {}
    mine = {}
    looks = {}
    for p in prs:
        evidence = collect(slug, p["number"])
        final = gh_json(["gh", "pr", "view", str(p["number"]), "--json", "headRefOid,baseRefOid,updatedAt"])
        if not final or any(p.get(k) != final.get(k) for k in ("headRefOid", "baseRefOid", "updatedAt")):
            evidence["failedFetches"].append("snapshot-consistency")
        # A saved disposition holds for its request event at the assessed head.
        head = (final or p).get("headRefOid")
        markers = [m for m in saved if m["number"] == p["number"]]
        stale[p["number"]] = [m for m in markers if m["head"] != head]
        request_states[p["number"]] = reconcile(evidence, [m for m in markers if m["head"] == head])
        mine[p["number"]] = my_review_of(evidence, login, head)
        looks[p["number"]] = since_last_look(assessed.get(p["number"]), head, (final or p).get("baseRefOid"),
                                             (final or p).get("updatedAt"))
    tiers = load_overrides()
    print(f"{len(prs)} open non-draft PR(s) targeting {base} or a stack rooted on it, oldest first\n")
    hdr = (f'{"PR":<7}{"OPENED":<12}{"AUTHOR":<18}{"RISK":<7}'
           f'{"SIZE":<13}{"BLOCKER":<26}{"CI":<9}{"AUTO":<6}{"REVIEW STATE":<20}{"MY REVIEW":<25}'
           f'{"SINCE LAST LOOK":<20}{"REQUEST STATE":<24}TITLE')
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
              f'{tier(paths, tiers):<7}{size:<13}{blocker_of(p, red, mine[p["number"]]):<26}{ci:<9}'
              f'{auto_of(p):<6}{p.get("reviewDecision") or "UNKNOWN":<20}{mine[p["number"]]:<25}'
              f'{looks[p["number"]]:<20}'
              f'{request_label(request_states[p["number"]]):<24}{p["title"][:46]}')
        stack = stacks.get(p["number"])
        if stack:
            print(f'       {stack_label(stack, p["number"])}'
                  + (' · per-PR auto-merge unavailable; land with land.py --enqueue --stack-method'
                     if stack.get("status") == "stacked" else ' -- re-read before approving or landing'))
        requests = request_states[p["number"]]
        for request in requests["requests"]:
            if request["outstanding"]:
                again = (f'; after an earlier {request["prior_state"]} review by {request["target"][5:]}'
                         if request["prior_state"] else '; requested again' if request["renewed"] else '')
                print(f'       Request {request["event_id"]}: {request["requester"] or "unknown requester"} -> '
                      f'{request["target"]} at {request["at"]}; {request["disposition"]}{again}')
        for marker in stale[p["number"]]:
            print(f'       Previously handled {marker["event_id"]} for {marker["target"]}: '
                  f'{marker["disposition"]} at {marker["at"]} on {marker["head"][:9]}; head moved, assess the request again')
        if requests["gaps"]:
            print('       Request coverage UNKNOWN: ' + ', '.join(requests["gaps"]))

    print(f'\nUnhandled review requests: {sum(s["unhandled"] for s in request_states.values())}; '
          f'unknown coverage on {sum(s["coverage"] != "complete" for s in request_states.values())} PR(s).')

    numbers = [p["number"] for p in prs]
    uncovered = ("DISMISSED", "approved at old head", "changes-req at old head")
    again = []
    for n in numbers:
        why = [w for w in (looks[n], mine[n]) if w == "HEAD MOVED" or w in uncovered]
        if why:
            again.append(f'#{n} ({", ".join(why)})')
    if again:
        print("Look again -- the head moved since your saved assessment, or your review no longer "
              "covers the head: " + ", ".join(again))
    gated = [f'#{p["number"]}' for p in prs
             if mine[p["number"]] == "approved at head" and p.get("reviewDecision") == "REVIEW_REQUIRED"]
    if gated:
        print("Approved by you at head and still REVIEW_REQUIRED -- name another approver: " + ", ".join(gated))
    if login is None:
        print("!! reviewer login unavailable (`gh api user` failed); MY REVIEW is unknown, check your reviews by hand")

    if args.save_scope:
        args.save_scope.write_text(json.dumps(numbers) + "\n")
        print(f"\nSaved the round's scope: {len(numbers)} PR(s) -> {args.save_scope}")
    if scoped is not None:
        joined = [f"#{n}" for n in numbers if n not in scoped]
        left = []
        for n in (n for n in scoped if n not in numbers):
            snap = gh_json(["gh", "pr", "view", str(n), "--json", "number,state,isDraft"])
            if not snap or snap.get("number") != n:
                why = "state unknown"
            elif snap.get("state") != "OPEN":
                why = snap["state"].lower()
            else:
                why = "draft" if snap.get("isDraft") else "open, no longer listed"
            left.append(f"#{n} ({why})")
        print(f"\nScope {args.scope}: {len(scoped)} PR(s) saved, {len(numbers)} listed now.")
        print("JOINED after the scope snapshot: " + (", ".join(joined) + " -- give each a verdict, or report it as "
              "not reviewed" if joined else "none"))
        print("LEFT the queue: " + (", ".join(left) if left else "none"))

    others = [p["number"] for p in prs
              if tier([f["path"] for f in (p.get("files") or [])], tiers) == "OTHER"]
    if others and len(others) >= max(2, len(prs) // 3):
        print(f"\n!! {len(others)} of {len(prs)} PR(s) classified OTHER: "
              f"{', '.join('#%d' % n for n in others)}")
        print("   The tier patterns do not fit this repo, so the RISK column is not a")
        print("   reliable depth signal. Add this repo's own path names to")
        print("   .pr-review-tiers.json, or choose depth by reading the diff instead.")

    print("""
RISK -> depth   DATA/AUTH  full independent trace; check migrations and reverts
                API/INFRA  verify open findings, then trace the changed logic
                WEB        verify findings, check key logic in both directions
                DOCS       check the claims actually match the diff

BLOCKER         AUTHOR:*   propose approval when CODE is ready, with a conflict
                           note. Post only with authority for each action.
                           Requesting changes for a conflict just adds noise.
MY REVIEW       Your latest approval, changes request or dismissal against the
                live head. DISMISSED and 'at old head' no longer cover this code.
SINCE LAST LOOK Compared with your last saved assessment. HEAD MOVED invalidates
                its code claims; 'discussion changed' means refresh comments,
                issue evidence and owner decisions before reusing the verdict.
AUTO            Approval or dismissal can release auto-merge, so either also
                needs merge authority. Re-read auto-merge and the verified head
                before writing. AUTO is not queue membership; confirm actual
                queue/merge state with `land.py --watch <n>`, which only polls.

STACK           Upper layers target the branch below them; review each layer's
                own diff. GitHub refuses auto-merge for stack members, and
                landing one also lands every unmerged PR below it.

CI              'N RED' is not automatically the author's fault: a failing
                review/lint job is sometimes the reviewer tooling erroring out,
                not a finding. Read the job before you attribute it.""")


if __name__ == "__main__":
    main()
