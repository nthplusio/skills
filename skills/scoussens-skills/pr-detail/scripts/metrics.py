#!/usr/bin/env python3
"""Derive the mechanical counts /pr-detail scores against, from gather_pr.sh output.

Usage: gather_pr.sh <owner/repo> <n> | metrics.py
       metrics.py <gathered.json>

Everything here is arithmetic on observed data — no judgment. The point of
computing it in a script rather than by eye is that these numbers end up in a
document about a named person's work, where a miscount is not a rounding error
but an unfair claim. Three of these were mis-derived by hand while this skill
was being built:

  * Commit churn. `gh pr view --json commits` includes commits authored by
    OTHER people when the branch absorbed upstream work. On PR #2094 that was
    8 of 11 commits — attributing all 11 to the author would have tripled the
    churn figure for someone who wrote 3.
  * Finding categories. The AI reviewer's `_(source: ...)_` tag is often
    MULTI-valued ("bug scan, framework, QA"). Grouping on the raw string
    invents categories and undercounts the real ones.
  * CI history. `statusCheckRollup` only describes the newest commit, so a PR
    that was red for a day reads as clean. Failures are counted per commit.

Emits JSON. Every field is a count or a timestamp you can point at in the
timeline; none of it is a score.
"""

import json
import re
import sys
from datetime import datetime

# `copilot-pull-request-reviewer` carries no [bot] suffix in the reviews API
# and was being counted as a human reviewer — which on PR #1215 turned 4 bot
# passes into "4 teammates reviewed this."
BOT = re.compile(r"claude|\[bot\]|dependabot|renovate|linear-code|copilot", re.I)
SOURCE_TAG = re.compile(r"_\(source:\s*([^)]+)\)_", re.I)
FAIL = {"FAILURE", "TIMED_OUT", "ERROR", "CANCELLED", "STARTUP_FAILURE"}
FIXUP = re.compile(r"^(fix(up)?!|squash!|wip\b|fix ci\b|lint\b|typo\b|address (review|comments|feedback))", re.I)


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def hours(a, b):
    return round((b - a).total_seconds() / 3600, 1) if a and b else None


def is_bot(login):
    return bool(login and BOT.search(login))


def main():
    raw = open(sys.argv[1]).read() if len(sys.argv) > 1 else sys.stdin.read()
    d = json.loads(raw)
    pr, threads, timeline, checks = d["pr"], d["threads"], d["timeline"], d["checkRuns"]

    author = (pr.get("author") or {}).get("login")
    opened, merged = ts(pr.get("createdAt")), ts(pr.get("mergedAt") or pr.get("closedAt"))

    # --- reviews -------------------------------------------------------
    # Three-way split, not two. The author's own replies land in the reviews
    # array as COMMENTED submissions, and counting them as reviews of the PR
    # is nonsense — on PR #1215 that reported 40+ "human reviews" that were
    # the author answering feedback on his own change.
    reviews = sorted(pr.get("reviews") or [], key=lambda r: r.get("submittedAt") or "")
    bot_reviews = [r for r in reviews if is_bot((r.get("author") or {}).get("login"))]
    author_replies = [r for r in reviews
                      if (r.get("author") or {}).get("login") == author]
    human_reviews = [r for r in reviews
                     if not is_bot((r.get("author") or {}).get("login"))
                     and (r.get("author") or {}).get("login") != author]
    # Each bot submission is one round. Counting timeline `review_dismissed`
    # events instead under-counts: the newest round is never dismissed, and
    # pagination can clip the tail.
    # Two different bots review here (the house panel and Copilot); one
    # combined "rounds" number hides which. Break out by login.
    rounds_by_bot = {}
    for r in bot_reviews:
        who = (r.get("author") or {}).get("login")
        rounds_by_bot[who] = rounds_by_bot.get(who, 0) + 1
    rounds = len(bot_reviews)

    first_human = next((ts(r["submittedAt"]) for r in human_reviews), None)
    first_any = next((ts(r["submittedAt"]) for r in reviews
                      if (r.get("author") or {}).get("login") != author), None)

    # The review-SLA clock starts when review is ASKED FOR, not when the branch
    # first got a PR. PR #1215 sat as a draft for 21 days; measuring from
    # createdAt reported a 355h "SLA breach" against reviewers who had not yet
    # been asked for anything.
    rfr = next((ts(e["at"]) for e in timeline if e.get("event") == "ready_for_review"), None)
    sla_start = rfr or opened

    # A review can land while the PR is still a draft (Copilot commented on
    # #1215 six days before it was marked ready), which makes a naive
    # "first review minus ready_for_review" go NEGATIVE. Zero is the honest
    # reading: the feedback was already there when review was requested.
    def response_hours(first):
        if not first:
            return None
        h = hours(sla_start, first)
        return 0.0 if h is not None and h < 0 else h

    # --- threads and their fate ----------------------------------------
    cats, thread_rows = {}, []
    for t in threads:
        nodes = (t.get("comments") or {}).get("nodes") or []
        if not nodes:
            continue
        head = nodes[0]
        body = head.get("body") or ""
        m = SOURCE_TAG.search(body)
        # Multi-valued tags ("bug scan, framework") must be split, or the
        # category histogram invents combined categories and undercounts real ones.
        tags = [s.strip().lower() for s in m.group(1).split(",")] if m else ["untagged"]
        for tag in tags:
            cats[tag] = cats.get(tag, 0) + 1
        title = re.match(r"\*\*\[(.+?)\]\*\*", body)
        thread_rows.append({
            "title": title.group(1) if title else body[:80],
            "raisedBy": (head.get("author") or {}).get("login"),
            "byBot": is_bot((head.get("author") or {}).get("login")),
            "path": head.get("path"),
            "line": head.get("line"),
            "categories": tags,
            "resolved": t.get("isResolved"),
            "outdated": t.get("isOutdated"),
            "replies": len(nodes) - 1,
            "authorReplied": any(
                (c.get("author") or {}).get("login") == author for c in nodes[1:]
            ),
        })

    # --- commits: the author's own work vs. absorbed upstream work ------
    commits = pr.get("commits") or []
    own, foreign = [], []
    for c in commits:
        who = ((c.get("authors") or [{}])[0].get("login")
               or (c.get("authors") or [{}])[0].get("name"))
        (own if who == author else foreign).append(c)
    after_first_review = [
        c for c in own if first_any and ts(c.get("committedDate")) and ts(c["committedDate"]) > first_any
    ]

    # --- CI over the whole life of the PR, not just at merge ------------
    ci_fail_commits, ci_failed_checks = 0, {}
    for entry in checks:
        bad = [r for r in entry.get("runs") or [] if (r.get("conclusion") or "").upper() in FAIL]
        if bad:
            ci_fail_commits += 1
            for r in bad:
                ci_failed_checks[r["name"]] = ci_failed_checks.get(r["name"], 0) + 1

    ev = lambda name: [e for e in timeline if e.get("event") == name]

    print(json.dumps({
        "pr": {
            "number": pr.get("number"), "title": pr.get("title"), "author": author,
            "state": pr.get("state"), "baseRef": pr.get("baseRefName"),
            "openedAt": pr.get("createdAt"), "mergedAt": pr.get("mergedAt"),
            "mergedBy": (pr.get("mergedBy") or {}).get("login"),
            "openHours": hours(opened, merged),
            "additions": pr.get("additions"), "deletions": pr.get("deletions"),
            "changedFiles": pr.get("changedFiles"),
            "labels": [l["name"] for l in pr.get("labels") or []],
        },
        "review": {
            "botRounds": rounds,
            "botReviewStates": [r.get("state") for r in bot_reviews],
            "humanReviews": [
                {"who": (r.get("author") or {}).get("login"), "state": r.get("state"),
                 "at": r.get("submittedAt")} for r in human_reviews
            ],
            "changesRequestedBy": sorted({
                (r.get("author") or {}).get("login") for r in reviews
                if r.get("state") == "CHANGES_REQUESTED"
            }),
            "authorReplyCount": len(author_replies),
            "openedAsDraft": rfr is not None,
            "readyForReviewAt": rfr.isoformat() if rfr else None,
            "draftHours": hours(opened, rfr),
            "roundsByBot": rounds_by_bot,
            "hoursToFirstReview": response_hours(first_any),
            "hoursToFirstHumanReview": response_hours(first_human),
            "reviewedWhileDraft": bool(rfr and first_any and first_any < rfr),
            "slaBreach24h": (response_hours(first_any) or 0) > 24 if first_any else None,
            "slaClockFrom": "ready_for_review" if rfr else "createdAt",
            "mergedWithNoReview": len(reviews) == 0,
        },
        "findings": {
            "total": len(thread_rows),
            "byCategory": dict(sorted(cats.items(), key=lambda kv: -kv[1])),
            "resolved": sum(1 for t in thread_rows if t["resolved"]),
            # Labelled by the PR's actual state: "unresolved at merge" is a
            # finding, "unresolved on an open PR" is just work in progress.
            ("unresolvedAtMerge" if pr.get("mergedAt") else "unresolvedStillOpen"):
                sum(1 for t in thread_rows if not t["resolved"]),
            "raisedByHuman": sum(1 for t in thread_rows
                                 if not t["byBot"] and t["raisedBy"] != author),
            "authorEngaged": sum(1 for t in thread_rows if t["authorReplied"]),
            "perKLoc": round(len(thread_rows) / max((pr.get("additions") or 0) / 1000, 0.001), 1),
            "threads": thread_rows,
        },
        "churn": {
            "commitsTotal": len(commits),
            "commitsByAuthor": len(own),
            "commitsByOthers": len(foreign),
            "otherAuthors": sorted({
                ((c.get("authors") or [{}])[0].get("login")
                 or (c.get("authors") or [{}])[0].get("name")) for c in foreign
            }),
            "authorCommitsAfterFirstReview": len(after_first_review),
            "fixupStyleCommits": sum(1 for c in own if FIXUP.match(c.get("messageHeadline") or "")),
            "forcePushes": len(ev("head_ref_force_pushed")),
            "convertedToDraft": len(ev("convert_to_draft")),
        },
        "ci": {
            "commitsWithFailingChecks": ci_fail_commits,
            "commitsChecked": len(checks),
            "failedCheckCounts": dict(sorted(ci_failed_checks.items(), key=lambda kv: -kv[1])),
        },
    }, indent=2))


if __name__ == "__main__":
    main()
