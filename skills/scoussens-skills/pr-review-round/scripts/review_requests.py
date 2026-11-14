#!/usr/bin/env python3
"""Collect and reconcile reviewer handoffs, independently of CI and merge state.

Canonical source in pr-detail; bundled with pr-review-round.
Usage: review_requests.py OWNER/REPO NUMBER [--requests-only]
"""
import argparse
import json
import subprocess


DISPOSITIONS = ("assessed-locally", "awaiting-owner-decision", "reviewer-incomplete")


def effective_reviews(reviews):
    """Latest decisive submission per reviewer. Comments do not erase a verdict."""
    latest = {}
    for review in sorted(reviews, key=lambda r: (r.get("submittedAt") or r.get("submitted_at") or "", str(r.get("id", "")))):
        actor = (review.get("author") or review.get("user") or {}).get("login")
        if actor and review.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[actor] = review
    return latest


def target_of(event):
    user = event.get("requestedReviewer") or event.get("requested_reviewer")
    team = event.get("requestedTeam") or event.get("requested_team")
    if user:
        return "user:" + (user if isinstance(user, str) else user["login"])
    if team:
        return "team:" + (team if isinstance(team, str) else team["slug"])
    return None


def _api(args):
    result = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "forge read failed")
    data = json.loads(result.stdout)
    if isinstance(data, dict) and data.get("errors"):
        raise ValueError("GraphQL errors in response")
    return data


def collect_requests(repo, number):
    """REST avoids requestedReviewer permission gaps. GraphQL is a fallback."""
    attempts = []
    try:
        pages = _api([f"repos/{repo}/pulls/{number}/requested_reviewers?per_page=100", "--paginate", "--slurp"])
        if not isinstance(pages, list) or not pages or any(
                not isinstance(p, dict) or not isinstance(p.get("users"), list) or not isinstance(p.get("teams"), list) for p in pages):
            raise ValueError("invalid requested-reviewer pages")
        targets = ["user:" + u["login"] for p in pages for u in p["users"]]
        targets += ["team:" + t["slug"] for p in pages for t in p["teams"]]
        return dict(requestedReviewers=sorted(set(targets)), failedFetches=[], requestFetchAttempts=attempts)
    except (ValueError, KeyError, TypeError) as error:
        attempts.append({"source": "requests-rest", "error": str(error)})
    try:
        owner, name = repo.split("/")
        query = '''query($o:String!,$r:String!,$n:Int!,$endCursor:String){
          repository(owner:$o,name:$r){pullRequest(number:$n){reviewRequests(first:100,after:$endCursor){
            pageInfo{hasNextPage endCursor} nodes{requestedReviewer{__typename ... on User{login} ... on Team{slug}}}
          }}}}'''
        pages = _api(["graphql", "-f", "query=" + query, "-f", "o=" + owner, "-f", "r=" + name,
                      "-F", "n=" + str(number), "--paginate", "--slurp"])
        if not isinstance(pages, list) or not pages:
            raise ValueError("missing request pages")
        targets = []
        for index, page in enumerate(pages):
            if page.get("errors"):
                raise ValueError("GraphQL permission or collection error")
            connection = page["data"]["repository"]["pullRequest"]["reviewRequests"]
            more = connection["pageInfo"]["hasNextPage"]
            if more != (index < len(pages) - 1):
                raise ValueError("request pagination incomplete")
            for node in connection["nodes"]:
                target = node["requestedReviewer"]
                if target["__typename"] not in ("User", "Team"):
                    raise ValueError("unknown request target")
                targets.append(("user:" + target["login"]) if target["__typename"] == "User" else "team:" + target["slug"])
        return dict(requestedReviewers=sorted(set(targets)), failedFetches=[], requestFetchAttempts=attempts)
    except (ValueError, KeyError, TypeError) as error:
        attempts.append({"source": "requests-graphql", "error": str(error)})
        return dict(requestedReviewers=None, failedFetches=["review-requests"], requestFetchAttempts=attempts)


def collect(repo, number):
    evidence = collect_requests(repo, number)
    evidence.update(timeline=[], pr={"number": number, "reviews": []})
    for source, endpoint in (("reviews", f"pulls/{number}/reviews"), ("timeline", f"issues/{number}/timeline")):
        try:
            pages = _api([f"repos/{repo}/{endpoint}?per_page=100", "--paginate", "--slurp"])
            if not isinstance(pages, list) or not pages or any(not isinstance(p, list) for p in pages):
                raise ValueError("invalid event pages")
            rows = [row for page in pages for row in page]
            if source == "reviews":
                evidence["pr"]["reviews"] = rows
            else:
                evidence["timeline"] = rows
        except (ValueError, KeyError, TypeError):
            evidence["failedFetches"].append(source)
    return evidence


def reconcile(evidence, handled=()):
    """Every observed request keeps its own disposition; duplicate IDs collapse.

    Local markers cannot claim a forge response. Team membership is never inferred.
    """
    gaps = list(evidence.get("failedFetches", [])) + list(evidence.get("truncatedSources", []))
    outstanding = evidence.get("requestedReviewers")
    if outstanding is None:
        gaps.append("review-requests")
    reviews = evidence["pr"].get("reviews", [])
    markers = {(str(m["event_id"]), m["target"]): m for m in handled}
    events = {}
    for event in evidence.get("timeline", []):
        if event.get("event") not in ("review_requested", "review_request_removed"):
            continue
        target = target_of(event)
        at = event.get("at") or event.get("created_at")
        if event.get("id") is None or not target or not at:
            gaps.append("request-event-identity")
            continue
        events[str(event["id"])] = {**event, "target": target, "at": at}
    ordered = sorted(events.values(), key=lambda e: (e["at"], str(e["id"])))
    result = []
    for index, event in enumerate(ordered):
        if event["event"] != "review_requested":
            continue
        target = event["target"]
        later = [e for e in ordered[index + 1:] if e["target"] == target]
        responses = [r for r in reviews if target == "user:" + (r.get("author") or r.get("user") or {}).get("login", "")
                     and (r.get("submittedAt") or r.get("submitted_at") or "") > event["at"]
                     and r.get("state") in ("APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED")]
        marker = markers.get((str(event["id"]), target))
        if later:
            disposition = "superseded" if later[0]["event"] == "review_requested" else "removed"
        elif outstanding is not None and target not in outstanding:
            disposition = "answered" if responses else "removed"
        elif marker and marker["at"] >= event["at"]:
            disposition = marker["disposition"]
        else:
            disposition = "unhandled"
        # Outstanding requests remain work even if a later review is visible.
        prior = effective_reviews([r for r in reviews if
                                   (r.get("submittedAt") or r.get("submitted_at") or "") < event["at"]])
        renewed = target.startswith("user:") and prior.get(target[5:], {}).get("state") == "CHANGES_REQUESTED"
        actor = event.get("actor")
        result.append(dict(event_id=str(event["id"]), target=target,
                           requester=actor.get("login") if isinstance(actor, dict) else actor,
                           at=event["at"], renewed=renewed, disposition=disposition,
                           response_urls=[r.get("url") or r.get("html_url") for r in responses],
                           local=marker, outstanding=outstanding is not None and target in outstanding and not later))
    known = {r["target"] for r in result if r["outstanding"]}
    for target in outstanding or []:
        if target not in known:
            gaps.append("request-event-missing:" + target)
    return dict(coverage="unknown" if gaps else "complete", gaps=sorted(set(gaps)), requests=result,
                outstanding=outstanding,
                unhandled=sum(r["disposition"] == "unhandled" for r in result),
                effectiveReviews={who: r["state"] for who, r in effective_reviews(reviews).items()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository")
    parser.add_argument("number", type=int)
    parser.add_argument("--requests-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps((collect_requests if args.requests_only else collect)(args.repository, args.number)))
