#!/usr/bin/env python3
"""Submit one authorized review action against a verified full head SHA.

Without --write this only reports the held action. An authority "with approvals"
covers an approval that releases auto-merge. --allow-landing asserts merge
authority for a dismissal that can release auto-merge.
Reviews carry commit_id. Comments and dismissals have no atomic head condition
in GitHub's API, so the helper checks before and after and never retries writes.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

from ledger import (approvals_granted, check_authority, current_assessment, record_write, require_resolved,
                    target_state, validate_assessment)
from freshness import Benign, live_from_rest, live_from_view
from land import state_of
from branch_rules import review_rules, describe, last_pusher


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["approve", "request-changes", "comment", "dismiss"])
    parser.add_argument("number", type=int)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--body-file", required=True, type=Path)
    parser.add_argument("--review-id", type=int)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--allow-landing", action="store_true")
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
        check_authority(authority, args.repo, args.number, args.action)
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
        if args.action == "request-changes":
            code_decisions = [d for d in assessment["decisions"] if d["kind"] == "code" and d["severity"] == "blocking"]
            if not code_decisions:
                raise ValueError("request-changes requires a verified code decision; use a comment for evidence/owner requests")
            body += "\n\n## Unblock\n" + "\n".join(
                f'- {d["owner"]}: {d["unblock"]} · {d["effort"]}' for d in code_decisions)
        # Read identity first so the head check is the last read before a write.
        login = api("user")["login"] if args.action == "approve" else None
        pr = api(pull)
        if pr["head"]["sha"] != args.head or pr["state"] != "open" or pr["draft"] is not False:
            raise RuntimeError("HELD: head changed, PR closed, or draft; review current state again")
        target = target_state(args.repo, pr["base"].get("ref"))
        # A moved base or discussion holds only when it could change the verdict; see freshness.py.
        _, verdict = current_assessment(bundle, args.repo, args.number, live_from_rest(pr, target))
        accepted = verdict.record() if isinstance(verdict, Benign) else None
        if accepted:
            print("Accepted moved inputs: " + "; ".join(accepted["reasons"]))
        if args.action == "approve" and pr["user"]["login"] == login:
            raise RuntimeError("HELD: an author cannot approve their own PR")
        if args.action == "approve":
            # Your approval cannot clear a last-push rule on a commit you pushed.
            rules = review_rules(args.repo, pr["base"].get("ref"))
            if (rules or {}).get("require_last_push_approval") and login and last_pusher(
                    (pr["head"].get("repo") or {}).get("full_name"), pr["head"].get("ref")) == login:
                raise RuntimeError(f'HELD: you pushed the last commit, and {pr["base"].get("ref")} requires approval '
                                   "of the last push by someone else; name another approver")
        # Approving to merge covers auto-merge; dismissing someone else's review still needs --allow-landing.
        lands_with_approval = args.action == "approve" and approvals_granted(authority)
        if args.action in ("approve", "dismiss") and not args.allow_landing and not lands_with_approval:
            if "auto_merge" not in pr or pr["auto_merge"] is not None:
                raise RuntimeError("HELD: auto-merge enabled or unknown; merge authority required")
        if args.action in ("approve", "dismiss"):
            possible_landing = pr.get("auto_merge") is not None or "auto_merge" not in pr
            check_authority(authority, args.repo, args.number, args.action, possible_landing)
            require_resolved(assessment)

        attempted = True
        if args.action == "dismiss":
            result = api(f"{pull}/reviews/{args.review_id}/dismissals", "PUT", {"message": body})
        elif args.action == "comment":
            result = api(f"repos/{args.repo}/issues/{args.number}/comments", "POST", {"body": body})
        else:
            event = "APPROVE" if args.action == "approve" else "REQUEST_CHANGES"
            result = api(f"{pull}/reviews", "POST",
                         {"event": event, "commit_id": args.head, "body": body})
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
        if (args.action == "approve" and submitted and observed.get("state") == "OPEN"
                and observed.get("reviewDecision") not in (None, "", "APPROVED")):
            print(f'APPROVAL POSTED BUT THE REVIEW GATE DID NOT CLEAR: GitHub reports {observed["reviewDecision"]}. '
                  "The approval exists; do not post it again.")
            print(f'Review rules on {observed.get("baseRefName") or "the base"}: ' + "; ".join(describe(rules)))
            print("Name another eligible approver, or the reviewer whose changes request is still in force.")
            code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
