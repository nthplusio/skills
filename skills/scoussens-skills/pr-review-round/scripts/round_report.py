#!/usr/bin/env python3
"""round_report.py <base-branch> [--scope scope.json] [--since ISO8601] [--me LOGIN]

The report pass. Emits one JSON record per PR touched this round, carrying the
three things a report needs and a review round reliably forgets:

  * ``url``          -- the PR link, so every row in the artifact is clickable
  * ``reviewed_at``  -- when the review was actually submitted, per PR
  * ``reviews`` /
    ``comments``     -- the full body text you posted, so the artifact can
                        expand into what was said instead of paraphrasing it

Why a script rather than recalling it: by report time the merged PRs have
dropped out of ``queue.py``'s open list, and the bodies you posted are hundreds
of lines back in the transcript. Both are exactly the things that get quietly
approximated. This reads them back from the API.

``--since`` bounds "this round". It decides which *merged* PRs are included --
open PRs against <base> are always listed -- and which reviews count as this
round's rather than a previous one's.

The default is the **previous round's end time**, read from the ledger. A fixed
clock window is wrong in both directions: too wide and it reports PRs that
landed before the round opened (and then warns you never reviewed them), too
narrow and it drops a long round's earliest merges. With no completed round it
uses the start of the round `ledger.py start` opened, and only with neither
does it fall back to 12h and say so on stderr.

``--scope`` is the file `queue.py --save-scope` wrote. With it every record
carries ``in_scope``, and the PRs that joined after that snapshot are named on
stderr. Without it a late PR cannot be told from a scoped one.

``my_review`` is your latest approval, changes request or dismissal on the PR,
with whether it is still in force at the reported head. A review GitHub
dismissed, or one made at an earlier commit, is named on stderr.

Each of your reviews and comments carries ``posted_by``: ``round`` when
`review_write.py` recorded it in the ledger, otherwise ``outside the round``.
A merged PR's ``merge_evidence`` says who merged it and whether a person's
approval stood at the merged head. Both are observed facts, named on stderr;
neither is a finding about the code.

Usage:
    python3 round_report.py <base> --scope scope.json > /tmp/round.json
    python3 round_report.py <base> --since 2026-08-21T15:00:00Z

Piping the result into the artifact build is the point; read it with jq to spot
check, e.g. `jq -r '.[] | "\\(.number) \\(.verdict) \\(.reviewed_at)"' /tmp/round.json`
"""
import json
import hashlib
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from merge_queue import queue_state
from pr_history import normalize
from review_config import resolve as review_config
from review_requests import reconcile, effective_reviews
from ledger import assessment_history, gh_said, marker_current, validate_assessment, target_state, writes as ledger_writes
from branch_rules import gate_lines
from requirements import requirement_gaps
from stacks import stack_of, missing_members


LIST_FIELDS = ("id,headRefOid,baseRefOid,updatedAt,number,title,url,author,createdAt,isDraft,reviewDecision,"
               "mergeable,mergeStateStatus,additions,deletions,state,mergedAt,headRefName,isCrossRepository")


def history_evidence(slug, pr):
    result = subprocess.run(["bash", str(Path(__file__).with_name("gather_pr.sh")),
                             slug, str(pr["number"]), "--history"], capture_output=True, text=True)
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    if result.returncode:
        return {"repository": slug, "pr": pr, "failedFetches": ["history-collection"]}
    evidence = json.loads(result.stdout)
    if evidence["pr"].get("headRefOid") != pr.get("headRefOid"):
        evidence["failedFetches"].append("queue-head-changed")
    return evidence


_gh_error = ""


def gh(args, tries=3):
    """gh with a retry -- the API 504s under load often enough that one
    transient failure should not lose the report."""
    global _gh_error
    for attempt in range(tries):
        r = subprocess.run(args, capture_output=True, text=True)
        _gh_error = r.stderr
        if r.returncode == 0:
            try:
                return json.loads(r.stdout)
            except json.JSONDecodeError:
                pass
        if attempt < tries - 1:
            time.sleep(2 * (attempt + 1))
    return None


def repo_slug():
    r = gh(["gh", "repo", "view", "--json", "nameWithOwner"])
    return r["nameWithOwner"] if r else None


def me():
    r = gh(["gh", "api", "user", "--jq", "{login: .login}"])
    return r["login"] if r else None


def verdict_of(pr):
    """The line the report groups by. Deliberately distinguishes MERGED from
    everything else and never calls a queued PR merged -- reporting a PR that
    is sitting in a merge queue as landed is the one inaccuracy that bites."""
    if pr.get("state") == "MERGED":
        return "MERGED"
    if pr.get("state") == "CLOSED":
        return "CLOSED"
    if pr.get("isDraft"):
        return "DRAFT"
    ms = pr.get("mergeStateStatus")
    rd = pr.get("reviewDecision")
    if ms in ("DIRTY", "CONFLICTING"):
        return f"{rd}_CONFLICTING" if rd in ("APPROVED", "CHANGES_REQUESTED") else "CONFLICTING"
    if rd == "CHANGES_REQUESTED":
        return "CHANGES_REQUESTED"
    if rd == "APPROVED":
        queue = pr.get("queue_state", "unknown")
        if queue == "queued":
            return "APPROVED_QUEUED"
        return "APPROVED" if queue == "not_queued" else "APPROVED_QUEUE_UNKNOWN"
    mine = pr.get("my_review") or {}
    if rd == "REVIEW_REQUIRED" and mine.get("state") == "APPROVED" and mine.get("at_head"):
        # Your approval stands at this head and GitHub still wants a review:
        # the next reviewer is someone else, so this is not NEEDS_REVIEW.
        return "APPROVED_NEEDS_ANOTHER_REVIEWER"
    return "NEEDS_REVIEW"


def my_review_of(reviews, who, head):
    """Your latest decisive review and whether it still covers the reported head."""
    review = effective_reviews(reviews).get(who) if who else None
    if not review:
        return None
    commit = review.get("commitOid") or review.get("commit_id")
    return {"state": review["state"], "commit_id": commit,
            "submitted_at": review.get("submittedAt") or review.get("submitted_at"),
            "at_head": bool(commit) and commit == head, "dismissed": review["state"] == "DISMISSED"}


def merge_evidence(pr, assessments, reviews, gaps, writes=()):
    """A missing local record is not evidence that nobody reviewed a head."""
    merged_at = pr.get("mergedAt")
    def timing(at):
        try:
            event = datetime.fromisoformat(at.replace("Z", "+00:00"))
            merge = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
            if event.tzinfo is None or merge.tzinfo is None:
                return "merge timing unknown"
            if event == merge:
                return "at recorded merge time · order unknown"
            return "before merge" if event < merge else "after merge"
        except (ValueError, AttributeError):
            return "merge timing unknown"
    head = pr.get("headRefOid")
    unknown = any(g in gaps for g in ("reviews", "history-collection"))
    # Each reviewer's latest decisive review that could have gated the merge:
    # an approval withdrawn before the merge, or given after it, did not.
    standing = [r for r in effective_reviews([r for r in reviews if timing(r.get("submittedAt")) != "after merge"]).values()
                if r.get("state") == "APPROVED" and r.get("commitOid") == head]
    merger = pr.get("mergedBy")
    return {
        "merged_by": merger.get("login") if isinstance(merger, dict) else merger,
        # None when reviews could not be read: unknown is not "nobody approved".
        "human_approval_at_head": None if unknown else any((r.get("author") or {}).get("type") == "User" for r in standing),
        "approvers_at_head": [{"actor": (r.get("author") or {}).get("login"), "actor_type": (r.get("author") or {}).get("type")}
                              for r in standing],
        "landing_requests": [{"action": w.get("action"), "at": w.get("at")} for w in writes
                             if w.get("number") == pr.get("number") and w.get("head") == head
                             and w.get("action") in ("enqueue", "enable-auto-merge", "stack-merge")],
        "local_assessments": [{"at": a["assessed_at"], "timing": timing(a["assessed_at"]),
                               "provenance": a.get("provenance") or "Saved local assessment"}
                              for a in assessments if a["head"] == head],
        "exact_head_reviews": [{"actor": (r.get("author") or {}).get("login"),
                                "actor_type": (r.get("author") or {}).get("type"),
                                "state": r["state"], "at": r.get("submittedAt"), "url": r.get("url"),
                                "timing": timing(r.get("submittedAt"))}
                               for r in reviews if r.get("commitOid") == head and r.get("state") != "PENDING"],
        "review_coverage": "unknown" if unknown else "observed",
    }


def main():
    argv = sys.argv[1:]
    if not argv:
        sys.exit("usage: round_report.py <base-branch> [--since ISO8601] [--me LOGIN]")
    base = argv[0]
    since = None
    who = None
    tickets_path = None
    scope_path = None
    config_path = None
    assessments_path = None
    for i, a in enumerate(argv):
        if a == "--since" and i + 1 < len(argv):
            since = argv[i + 1]
        if a == "--me" and i + 1 < len(argv):
            who = argv[i + 1]
        if a == "--tickets" and i + 1 < len(argv):
            tickets_path = Path(argv[i + 1])
        if a == "--scope" and i + 1 < len(argv):
            scope_path = Path(argv[i + 1])
        if a == "--assessments" and i + 1 < len(argv):
            assessments_path = Path(argv[i + 1])
        if a == "--review-config" and i + 1 < len(argv):
            config_path = argv[i + 1]
    try:
        policy = review_config(".", config_path)
    except (ValueError, OSError) as error:
        sys.exit(f"review configuration error: {error}")
    if since is None:
        prev = None
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import ledger
            prev = ledger.last_round(base)
        except Exception:
            prev = None
        try:
            started = ledger.open_round(base)
        except Exception:
            started = None
        if prev and prev.get("ended_at"):
            since = prev["ended_at"]
            print(f"[since] previous round ended {since} -- using that as the "
                  f"round boundary", file=sys.stderr)
        elif started and started.get("started_at"):
            since = started["started_at"]
            print(f"[since] no completed round in the ledger; using the start of the open "
                  f"round ({since}) as the round boundary", file=sys.stderr)
        else:
            since = (datetime.now(timezone.utc) - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"[since] no completed round in the ledger; falling back to a "
                  f"12h window ({since}). Merged PRs listed below may predate "
                  f"this round.", file=sys.stderr)
    who = who or me()
    slug = repo_slug()
    if not slug:
        sys.exit(f"could not resolve repo: {gh_said(_gh_error)} -- check auth and network")
    tickets = json.loads(tickets_path.read_text()) if tickets_path else {"repository": slug, "prs": {}}
    if tickets["repository"] != slug:
        sys.exit("tracker evidence belongs to a different repository")

    saved = assessment_history(slug)
    # Assessed in this round: recorded since the boundary, or supplied as this round's file.
    assessed_now = {a["number"] for a in saved if (a.get("recorded_at") or "") >= since}
    supplied_numbers = set()
    if assessments_path:
        supplied = json.loads(assessments_path.read_text())
        if supplied["repository"] != slug:
            sys.exit("assessments belong to a different repository")
        for assessment in supplied["assessments"]:
            validate_assessment(assessment)
        saved += supplied["assessments"]
        supplied_numbers = {a["number"] for a in supplied["assessments"]}
        assessed_now |= supplied_numbers
    saved.sort(key=lambda a: datetime.fromisoformat(a["assessed_at"].replace("Z", "+00:00")).timestamp())
    latest = {a["number"]: a for a in saved}
    recorded = ledger_writes(slug)
    # A dismissal's URL is the review it dismissed, which the helper did not post.
    posted = {w["url"] for w in recorded if w.get("url") and w.get("action") != "dismiss"}
    posted_by = lambda url: "round" if url in posted else "outside the round"
    target = target_state(slug, base)
    collected = []

    openq = gh(["gh", "pr", "list", "--base", base, "--state", "open",
                "--limit", "200", "--json", LIST_FIELDS])
    if openq is None or len(openq) >= 200:
        sys.exit("open queue unavailable or at collection limit; coverage unknown")
    # Merged PRs have already dropped out of the open list by report time. They
    # are the rows a report most wants and most often loses.
    #
    # `--search "merged:>=..."` rather than fetching a page and filtering here:
    # `gh pr list --state merged --limit N` pages by CREATION date, so a
    # long-lived PR opened months ago and merged in this round falls outside the
    # newest-N window and silently vanishes from the report. That happened on a
    # real round -- a PR open since July merged first and was the one row
    # missing. Let the server filter on merge date instead.
    mergedq = gh(["gh", "pr", "list", "--base", base, "--state", "merged",
                  "--limit", "100", "--search", f"merged:>={since}",
                  "--json", LIST_FIELDS])
    if mergedq is None or len(mergedq) >= 100:
        sys.exit("merged queue unavailable or at collection limit; coverage unknown")

    # A PR can merge between these reads. Keep the later confirmed snapshot.
    by_number = {p["number"]: p for p in openq if not p["isDraft"]}
    by_number.update((p["number"], p) for p in mergedq)
    # Persist the initial queue as a JSON list of numbers; closed PRs must not vanish.
    scope = json.loads(scope_path.read_text()) if scope_path else None
    if scope is not None and (not isinstance(scope, list) or any(type(n) is not int for n in scope)):
        sys.exit(f"{scope_path} is not a JSON list of PR numbers; coverage unknown")
    for number in scope or []:
        snapshot = gh(["gh", "pr", "view", str(number), "--repo", slug, "--json", LIST_FIELDS])
        if not snapshot or snapshot.get("number") != number:
            sys.exit(f"could not reconcile scoped PR #{number}; coverage unknown")
        by_number[number] = snapshot
    # Upper stack layers target the branch below them, so `--base` misses them.
    stacks = {n: stack_of(slug, n) for n in by_number}
    for number in missing_members(stacks.values(), set(by_number), base):
        snapshot = gh(["gh", "pr", "view", str(number), "--repo", slug, "--json", LIST_FIELDS])
        if not snapshot or snapshot.get("number") != number:
            sys.exit(f"could not collect stacked PR #{number}; coverage unknown")
        by_number[number] = snapshot
        stacks[number] = stack_of(slug, number)
    prs = sorted(by_number.values(), key=lambda p: p["createdAt"])
    stray = sorted(supplied_numbers - set(by_number))
    if stray:
        sys.exit(f"{assessments_path} holds assessments for PR(s) outside this report: "
                 + ", ".join(f"#{n}" for n in stray)
                 + f". The report covers PRs on {base}: open and not draft, merged since {since}, or listed in "
                   "--scope (which keeps a PR that closed or returned to draft). "
                   "A PR on another base belongs to a round on that base (`ledger.py start <that base>`), "
                   "with its own assessments file. Nothing reported")
    # Head branches in this repository, for the last-push check on a gated approval.
    branches = {p["number"]: p.get("headRefName") for p in prs if p.get("headRefName") and not p.get("isCrossRepository")}

    out = []
    for p in prs:
        n = p["number"]
        p["queue_state"] = (queue_state(p.get("id"), p.get("headRefOid"))
                            if p.get("state") == "OPEN" else "not_queued")
        evidence = history_evidence(slug, p)
        # Collection is later than enumeration; keep its lifecycle state too.
        for key in ("state", "mergedAt", "closedAt", "reviewDecision", "updatedAt", "headRefOid", "baseRefOid", "isDraft", "mergedBy"):
            if key in evidence.get("pr", {}):
                p[key] = evidence["pr"][key]
        if p.get("state") != "OPEN":
            p["queue_state"] = "not_queued"
        if str(n) in tickets["prs"]:
            evidence["ticketEvidence"] = tickets["prs"][str(n)]
        reviews = evidence["pr"].get("reviews", [])
        issue_comments = evidence["pr"].get("comments", [])

        mine = [r for r in reviews
                if (r.get("author") or {}).get("login") == who
                and (r.get("submittedAt") or "") >= since
                and r.get("state") != "PENDING"]
        # Latest first: the report wants this round's verdict, not the history.
        mine.sort(key=lambda r: r.get("submittedAt") or "", reverse=True)
        # Not bounded by the round: an approval from an earlier round that a push
        # dismissed is exactly the review this has to notice.
        p["my_review"] = (None if "reviews" in evidence.get("failedFetches", [])
                          else my_review_of(reviews, who, p.get("headRefOid")))

        rec = {
            "repository": slug,
            "number": n,
            "url": p["url"],
            "title": p["title"],
            "author": (p.get("author") or {}).get("login"),
            "created_at": p["createdAt"],
            "additions": p.get("additions"),
            "deletions": p.get("deletions"),
            "state": p.get("state"),
            "is_draft": bool(p.get("isDraft")),
            # None when no scope file was supplied: membership is unknown, not false.
            "in_scope": (n in scope) if scope is not None else None,
            "merged_at": p.get("mergedAt"),
            "mergeable": p.get("mergeable"),
            "merge_state": p.get("mergeStateStatus"),
            "review_decision": p.get("reviewDecision"),
            "head": p.get("headRefOid"),
            "base": p.get("baseRefOid"),
            "review_config": config_path,
            "target": target,
            "evidence_inputs": {
                "target": target,
                "forge": p.get("updatedAt"),
                "issues": hashlib.sha256(json.dumps(evidence.get("ticketEvidence", {}), sort_keys=True).encode()).hexdigest(),
                "policy": policy["revision"],
            },
            "queue_state": p["queue_state"],
            "stack": stacks.get(n),
            "verdict": verdict_of(p),
            "my_review": p["my_review"],
            # The per-PR review timestamp the report asks for. None means you
            # left a comment but no formal review -- say so rather than
            # implying a review happened.
            "reviewed_at": mine[0]["submittedAt"] if mine else None,
            "history": normalize(evidence),
            "reviews": [
                {
                    "id": r["id"],
                    "state": r["state"],
                    "commit_id": r.get("commitOid"),
                    "submitted_at": r["submittedAt"],
                    "url": r.get("url"),
                    "posted_by": posted_by(r.get("url")),
                    "body": r.get("body") or "",
                }
                for r in mine
            ],
            "comments": [
                {
                    "created_at": c["createdAt"],
                    "url": c.get("url"),
                    "posted_by": posted_by(c.get("url")),
                    "body": c.get("body") or "",
                }
                for c in issue_comments
                if (c.get("author") or {}).get("login") == who
                and (c.get("createdAt") or "") >= since
            ],
        }
        proposal = latest.get(n)
        rec["assessment"] = proposal
        rec["requirements_gaps"] = requirement_gaps(evidence.get("ticketEvidence", {}))
        rec["assessment_history"] = [a for a in saved if a["number"] == n]
        if p.get("state") == "MERGED":
            rec["merge_evidence"] = merge_evidence(p, rec["assessment_history"], reviews, evidence.get("failedFetches", []), recorded)
            rec["merge_review_gap"] = not rec["merge_evidence"]["local_assessments"]
            if rec["merge_review_gap"]:
                print(f'Merged head has no saved local assessment: #{n} {rec["head"]}; check linked assessments and exact-head reviews', file=sys.stderr)
        collected.append((rec, evidence))
        out.append(rec)

    final_target = target_state(slug, base)
    for rec, evidence in collected:
        if not target.get("sha") or final_target != target:
            evidence.setdefault("failedFetches", []).append("target-ref-changed-or-unavailable")
            rec["history"]["gaps"].append("target-ref-changed-or-unavailable")
        rec["target_final"] = final_target
        # A disposition is bound to its request event and the head it was assessed at,
        # not to the stricter inputs that keep a recommendation current.
        rec["handoffs"] = reconcile(evidence, [marker for item in rec["assessment_history"]
                                               if marker_current(item, rec["head"])
                                               for marker in item.get("request_events", [])])

    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    counts = {}
    for r in out:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    summary = " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"\n{len(out)} PR(s) in this round ({summary})", file=sys.stderr)
    print(f'Request reconciliation: {sum(r["handoffs"]["unhandled"] for r in out)} unhandled; '
          f'{sum(r["handoffs"]["coverage"] != "complete" for r in out)} PR(s) with unknown coverage. '
          'Local dispositions are not posted responses.', file=sys.stderr)
    if scope is None:
        print("NO --scope: PRs that joined after the first queue.py run cannot be told from the ones "
              "the round started with.\n  -> pass the file `queue.py <base> --save-scope` wrote.", file=sys.stderr)
    else:
        joined = [r for r in out if not r["in_scope"]]
        if joined:
            print("JOINED AFTER THE SCOPE SNAPSHOT: "
                  + ", ".join(f'#{r["number"]}' + ("" if r["state"] == "OPEN" else f' ({r["state"].lower()})')
                              for r in joined)
                  + "\n  -> give each a verdict, or report it as not reviewed in this round.", file=sys.stderr)
    lapsed = [r for r in out if r["state"] == "OPEN" and r["my_review"]
              and (r["my_review"]["dismissed"] or not r["my_review"]["at_head"])]
    if lapsed:
        def lapse(r):
            mine = r["my_review"]
            what = "DISMISSED" if mine["dismissed"] else f'{mine["state"]} at an earlier commit'
            return (f'#{r["number"]} ({what}; reviewed {(mine["commit_id"] or "unknown")[:9]}, '
                    f'head {(r["head"] or "unknown")[:9]})')
        print("YOUR REVIEW NO LONGER COVERS THE HEAD: " + ", ".join(lapse(r) for r in lapsed)
              + "\n  -> review the current head before reporting these as reviewed.", file=sys.stderr)
    gated = [r["number"] for r in out if r["verdict"] == "APPROVED_NEEDS_ANOTHER_REVIEWER"]
    if gated:
        print("APPROVED BY YOU AT HEAD AND STILL REVIEW_REQUIRED: " + ", ".join(f"#{n}" for n in gated)
              + "".join(f"\n  -> {line}" for line in gate_lines(slug, base, who, {n: branches[n] for n in gated if n in branches}))
              + "\n  -> GitHub does not report which rule holds the gate; name another eligible approver.",
              file=sys.stderr)
    unapproved = [r for r in out if (r.get("merge_evidence") or {}).get("human_approval_at_head") is False]
    if unapproved:
        def merged(r):
            found = r["merge_evidence"]
            bots = [a["actor"] or "unknown" for a in found["approvers_at_head"]]
            return (f'#{r["number"]} (merged by {found["merged_by"] or "unknown"}; GitHub reports '
                    f'{r["review_decision"] or "no review decision"}'
                    + (f'; approved at head by automation only: {", ".join(bots)}' if bots else "") + ")")
        print("MERGED WITH NO APPROVAL FROM A PERSON AT THE MERGED HEAD: " + ", ".join(merged(r) for r in unapproved)
              + "\n  -> an observed GitHub fact, not a finding: repository policy may allow it, and a review at an "
                "earlier commit or outside GitHub does not show here. Report it as observed.", file=sys.stderr)
    outside = [f'#{r["number"]} {item.get("state", "comment")} {item["url"] or "(no URL)"}'
               for r in out for item in (*r["reviews"], *r["comments"]) if item["posted_by"] != "round"]
    helper_posted = any(w.get("url") and w.get("action") != "dismiss" and (w.get("at") or "") >= since for w in recorded)
    if outside and not helper_posted:
        # Listing every item when the helper posted nothing would be a warning nobody reads.
        print(f"review_write.py RECORDED NO POST IN THIS ROUND'S WINDOW: all {len(outside)} review(s) and comment(s) from "
              f"{who} since {since} were posted some other way, or under another ledger."
              "\n  -> expected in an assessment-only round or with a new ledger; otherwise check them before "
              "reporting any as this round's review.", file=sys.stderr)
    elif outside:
        print(f"POSTED FROM {who}'S ACCOUNT IN THIS ROUND'S WINDOW, NOT RECORDED BY review_write.py: " + ", ".join(outside)
              + "\n  -> posted by hand, by another session, or under another ledger. Check each before reporting "
                "it as this round's review.", file=sys.stderr)
    unreviewed = [r["number"] for r in out if not r["reviews"] and not r["comments"]]
    if unreviewed:
        # A PR reviewed in an earlier round is a different situation from one
        # never looked at. Saying so keeps the warning worth reading -- a check
        # that fires on every round trains you to skip it.
        seen = {}
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import ledger
            seen = ledger.heads(slug, before=since)
        except Exception:
            seen = {}
        assessed = [n for n in unreviewed if n in assessed_now]
        fresh = [n for n in unreviewed if n not in assessed_now and n not in seen]
        prior = [n for n in unreviewed if n not in assessed_now and n in seen]
        live = {r["number"]: r["head"] for r in out}
        moved = lambda n, was: "head unchanged" if was == live[n] else f'HEAD MOVED to {(live[n] or "unknown")[:9]}'
        if assessed:
            print(f"ASSESSED IN THIS ROUND, NO REVIEW OR COMMENT POSTED IN IT FROM {who}: "
                  + ", ".join(f'#{n} (assessed at {latest[n]["head"][:9]}, {moved(n, latest[n]["head"])})' for n in assessed)
                  + "\n  -> a saved assessment is a local record, not a posted review. Report these as assessed "
                    "and not posted; `my_review` shows a review from an earlier round that still stands.",
                  file=sys.stderr)
        if fresh:
            print(f"NO POSTED REVIEW OR COMMENT FROM {who} IN THIS ROUND: "
                  + ", ".join(f"#{n}" for n in fresh)
                  + "\n  -> reconcile before reporting; a dropped PR is worse than an "
                    "unreviewed one, because the summary asserts the round is complete.",
                  file=sys.stderr)
        if prior:
            print("REVIEWED IN AN EARLIER ROUND, not this one: "
                  + ", ".join(f"#{n} (last head {seen[n][:9]}, {moved(n, seen[n])})" for n in prior)
                  + "\n  -> run `ledger.py open` for the findings still recorded "
                    "against these; HEAD MOVED means the saved assessment's code claims are stale.",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
