#!/usr/bin/env python3
"""Submit one authorized review action against a verified full head SHA.

Without --write this only reports the held action. The authority file from
authority.py decides each write: approvals cover an approval that releases
auto-merge, the reapprove-base-only policy covers `reapprove` (an approval on an
assessment `reapprove.py --carry` built from the round's approval; `approve` takes
one carried from an assessment the round never approved), and a dismissal follows the
dismiss-bot-review or dismiss-human-review policy (or a one-PR grant), chosen by
what GitHub says about the review's author. A bot's review is dismissed only
when the assessment at the head records each of its inline findings as fixed or
overstated (`verified_findings`); the message lists them with file and line.
Approvals, change requests and comments are pull request reviews (a comment is a
COMMENT review), so each carries commit_id and shows in GitHub's review list. A
review this login already posted at the same head is not posted again.
Dismissals have no atomic head condition in GitHub's API, so the helper checks
before and after. It never retries a write.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

from ledger import (check_authority, current_assessment, record_write, require_resolved, target_state,
                    validate_assessment)
from freshness import Benign, live_from_rest, live_from_view
from land import state_of
from branch_rules import review_rules, describe, last_pusher
from reapprove import approved_head
from findings import inline_comments, is_bot, line_of, review_findings

# Each review action: the event GitHub takes and the state the posted review shows.
REVIEWS = {"approve": ("APPROVE", "APPROVED"), "reapprove": ("APPROVE", "APPROVED"),
           "request-changes": ("REQUEST_CHANGES", "CHANGES_REQUESTED"),
           "comment": ("COMMENT", "COMMENTED")}


def api(path, method="GET", payload=None):
    command = ["gh", "api", path, "--method", method]
    if payload is not None:
        command += ["--input", "-"]
    result = subprocess.run(command, input=json.dumps(payload) if payload else None,
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{method} failed; inspect remote state before retry: {result.stderr.strip()}")
    try:
        data = json.loads(result.stdout)
    except ValueError as error:
        raise RuntimeError(f"{method} returned unreadable data; inspect remote state before retry") from error
    if not isinstance(data, dict):
        raise RuntimeError(f"{method} returned unexpected data; inspect remote state before retry")
    return data


def verified_bot_findings(repo, number, review_id, assessment, granted):
    """The dismissal's evidence: each inline finding of the bot's review with the fixed or overstated record
    the assessment at the reviewed head keeps for it. Raises naming every finding without one."""
    comments = inline_comments(repo, number)
    if comments is None:
        raise RuntimeError(f"HELD: could not read review {review_id}'s inline findings; coverage unknown")
    found = review_findings(comments, review_id)
    if not found and not granted:
        raise RuntimeError(f"HELD: bot review {review_id} has no inline findings for the round to record as verified; "
                           "dismissing it needs a one-PR grant")
    records = {r["comment"]: r for r in assessment.get("verified_findings", [])}
    missing = [f'{c["path"]}:{line_of(c)} (comment {c["id"]})' for c in found if c["id"] not in records]
    if missing:
        raise RuntimeError(f'HELD: the assessment at {assessment["head"]} has no fixed or overstated record for '
                           + "; ".join(missing) + ". Verify each at the head and add it to verified_findings")
    lines = [f'\n\n## Findings verified at `{assessment["head"]}`']
    for comment in found:
        record = records[comment["id"]]
        lines.append(f'- `{comment["path"]}:{line_of(comment)}` (comment {comment["id"]}): {record["status"]}, '
                     f'checked at `{record["file"]}:{record["line"]}`. {record["observation"]}')
    return "\n".join(lines)


def existing_review(pull, login, head, state, body):
    """The review this action would post, if you already posted it at this head: any
    COMMENTED review with the same body, or your latest verdict when it has `state`.
    A comment does not replace a verdict, and a review at an older head does not count."""
    result = subprocess.run(["gh", "api", f"{pull}/reviews?per_page=100", "--paginate", "--slurp"],
                            capture_output=True, text=True)
    try:
        if result.returncode:
            raise ValueError(result.stderr.strip())
        reviews = [review for page in json.loads(result.stdout) for review in page]
        mine = [r for r in reviews if (r.get("user") or {}).get("login") == login and r.get("commit_id") == head]
        if state == "COMMENTED":
            return next((r for r in mine if r.get("state") == state
                         and (r.get("body") or "").replace("\r\n", "\n").strip() == body), None)
        # GitHub lists reviews in chronological order.
        verdicts = [r for r in mine if r.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED")]
    except (ValueError, TypeError, AttributeError) as error:
        raise RuntimeError(f"HELD: could not read your existing reviews ({error}); nothing posted") from error
    return verdicts[-1] if verdicts and verdicts[-1]["state"] == state else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["approve", "reapprove", "request-changes", "comment", "dismiss"])
    parser.add_argument("number", type=int)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--body-file", required=True, type=Path)
    parser.add_argument("--review-id", type=int)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--authority", type=Path)
    parser.add_argument("--assessments", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.head):
        parser.error("--head must be the full SHA whose code and findings you verified")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo) or args.number <= 0:
        parser.error("use OWNER/REPO and a positive PR number")
    if args.action == "dismiss" and (not args.review_id or args.review_id <= 0):
        parser.error("dismiss requires a positive --review-id")
    if not args.write:
        print(f"HELD: {args.action} #{args.number} at {args.head}; no write authorized")
        return 0
    if not args.authority or not args.assessments:
        parser.error("writes require --authority and --assessments; flags alone grant no authority")

    body = args.body_file.read_text().strip()
    if not body:
        parser.error("--body-file must contain the evidence for this action")
    body = f"Reviewed head: `{args.head}`\n\n{body}"
    pull = f"repos/{args.repo}/pulls/{args.number}"
    attempted = False
    submitted = False
    rules = None
    code = 0
    try:
        authority = json.loads(args.authority.read_text())
        write = args.action
        if args.action == "dismiss":
            # Bots and people are separate policies, so whose review this is comes from GitHub.
            try:
                dismissed = api(f"{pull}/reviews/{args.review_id}")
            except RuntimeError as error:
                raise RuntimeError(f"HELD: could not read review {args.review_id} to tell a bot from a person ({error})")
            write = "dismiss-bot" if is_bot(dismissed.get("user")) else "dismiss-human"
        check_authority(authority, args.repo, args.number, write)
        bundle = json.loads(args.assessments.read_text())
        if bundle.get("repository") != args.repo:
            raise ValueError("assessment belongs to a different repository")
        matches = [a for a in bundle.get("assessments", []) if a.get("number") == args.number]
        if len(matches) != 1:
            raise ValueError("one assessment required for this PR")
        assessment = matches[0]
        validate_assessment(assessment)
        if assessment["head"] != args.head:
            raise ValueError("assessment head differs from reviewed head")
        # A re-approval stands on an assessment reapprove.py carried from the round's own approval; a fresh
        # approval stands on a review of this head. Keeping them apart is what lets reapprove-base-only be never.
        carried = assessment.get("carried")
        approved = approved_head(args.repo, args.number) if carried or args.action == "reapprove" else None
        if args.action == "approve" and carried and carried["from_head"] == approved:
            raise ValueError("this assessment was carried from the round's approval; post it with reapprove, "
                             "or review the head")
        if args.action == "reapprove":
            if not carried or carried["from_head"] != approved:
                raise ValueError("reapprove needs an assessment reapprove.py --carry built from the round's last approval"
                                 + (f" at {approved[:9]}" if approved else "; the ledger records none"))
        if args.action == "request-changes":
            code_decisions = [d for d in assessment["decisions"] if d["kind"] == "code" and d["severity"] == "blocking"]
            if not code_decisions:
                raise ValueError("request-changes requires a verified code decision; use a comment for evidence/owner requests")
            body += "\n\n## Unblock\n" + "\n".join(
                f'- {d["owner"]}: {d["unblock"]} · {d["effort"]}' for d in code_decisions)
        # Read identity first; after the head check, only the existing-review lookup precedes a write.
        login = api("user")["login"] if args.action != "dismiss" else None
        pr = api(pull)
        if pr["head"]["sha"] != args.head or pr["state"] != "open" or pr["draft"] is not False:
            raise RuntimeError("HELD: head changed, PR closed, or draft; review current state again")
        target = target_state(args.repo, pr["base"].get("ref"))
        # A moved base or discussion holds only when it could change the verdict; see freshness.py.
        _, verdict = current_assessment(bundle, args.repo, args.number, live_from_rest(pr, target))
        accepted = verdict.record() if isinstance(verdict, Benign) else None
        if accepted:
            print("Accepted moved inputs: " + "; ".join(accepted["reasons"]))
        if args.action in ("approve", "reapprove") and pr["user"]["login"] == login:
            raise RuntimeError("HELD: an author cannot approve their own PR")
        if args.action in ("approve", "reapprove"):
            # Your approval cannot clear a last-push rule on a commit you pushed.
            rules = review_rules(args.repo, pr["base"].get("ref"))
            if (rules or {}).get("require_last_push_approval") and login and last_pusher(
                    (pr["head"].get("repo") or {}).get("full_name"), pr["head"].get("ref")) == login:
                raise RuntimeError(f'HELD: you pushed the last commit, and {pr["base"].get("ref")} requires approval '
                                   "of the last push by someone else; name another approver")
        # check_authority above covered the landing either write can release: approvals, or the
        # dismiss policy or grant whose question names it.
        if args.action in ("approve", "reapprove", "dismiss"):
            require_resolved(assessment)
        if write == "dismiss-bot":
            granted = any(g.get("pr") == args.number and g.get("action") == write for g in authority.get("grants", []))
            body += verified_bot_findings(args.repo, args.number, args.review_id, assessment, granted)

        # Every check above still runs on a retry; only then does an existing review end it.
        if args.action in REVIEWS:
            event, state = REVIEWS[args.action]
            existing = existing_review(pull, login, args.head, state, body)
            if existing:
                print(f"{args.action} already exists at {args.head}: {existing.get('html_url') or existing.get('id')}; "
                      "nothing posted")
                return 0
        attempted = True
        if args.action == "dismiss":
            result = api(f"{pull}/reviews/{args.review_id}/dismissals", "PUT", {"message": body})
        else:
            try:
                result = api(f"{pull}/reviews", "POST", {"event": event, "commit_id": args.head, "body": body})
            except RuntimeError as error:
                # An error or timeout can follow an accepted review. Read back once; never post again.
                try:
                    result = existing_review(pull, login, args.head, state, body)
                except RuntimeError:
                    result = None
                if not result:
                    raise error
                print(f"The write returned an error, but reading back found your {args.action} at {args.head}")
        submitted = True
        print(f"Submitted {args.action}: {result.get('html_url') or result.get('id')}")
        try:
            record_write(args.repo, args.number, args.action, args.head, result.get("html_url"), accepted)
        except OSError as error:
            print(f"Posted, but not recorded in the ledger ({error}); round_report.py will list it as posted outside the round")
        if api(pull)["head"]["sha"] != args.head:
            raise RuntimeError("HEAD MOVED during write; action may already exist. Reconcile before further writes")
    except (RuntimeError, ValueError, OSError, KeyError, TypeError) as error:
        print(str(error))
        code = 1
    if attempted:
        observed = state_of(args.number, args.repo)
        print(f"Post-write: head={observed.get('headRefOid', 'unknown')} / "
              f"review={observed.get('reviewDecision', 'unknown')} / "
              f"queue={observed.get('queue_state', 'unknown')} / state={observed.get('state', 'unknown')}")
        drift = None
        if observed.get("state") != "MERGED":
            try:
                current_assessment(bundle, args.repo, args.number, live_from_view(observed))
            except ValueError as error:
                drift = str(error)
        if (observed.get("headRefOid") != args.head or not observed.get("reviewDecision")
                or observed.get("queue_state", "unknown") == "unknown" or drift):
            print("Post-write state uncertain or changed; reconcile before further writes"
                  + (f" ({drift})" if drift else ""))
            code = 1
        if (args.action in ("approve", "reapprove") and submitted and observed.get("state") == "OPEN"
                and observed.get("reviewDecision") not in (None, "", "APPROVED")):
            print(f'APPROVAL POSTED BUT THE REVIEW GATE DID NOT CLEAR: GitHub reports {observed["reviewDecision"]}. '
                  "The approval exists; do not post it again.")
            print(f'Review rules on {observed.get("baseRefName") or "the base"}: ' + "; ".join(describe(rules)))
            print("Name another eligible approver, or the reviewer whose changes request is still in force.")
            code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
