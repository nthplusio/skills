#!/usr/bin/env python3
"""Submit one authorized review action against a verified full head SHA.

Without --write this only reports the held action. --allow-landing additionally
asserts merge authority when approval or dismissal can release auto-merge.
Reviews carry commit_id. Comments and dismissals have no atomic head condition
in GitHub's API, so the helper checks before and after and never retries writes.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

from ledger import check_authority, check_clearance, validate_assessment
from land import state_of
from review_config import resolve as review_config


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
        if assessment["evidence_inputs"]["policy"] != review_config(".", bundle.get("review_config"))["revision"]:
            raise ValueError("review policy changed; resolve configuration and review affected checks again")
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
        if (assessment["base"] != pr["base"]["sha"] or assessment["evidence_inputs"]["forge"] != pr["updated_at"]):
            raise ValueError("assessment source or discussion changed; refresh inputs before posting")
        if args.action == "approve" and pr["user"]["login"] == login:
            raise RuntimeError("HELD: an author cannot approve their own PR")
        if args.action in ("approve", "dismiss") and not args.allow_landing:
            if "auto_merge" not in pr or pr["auto_merge"] is not None:
                raise RuntimeError("HELD: auto-merge enabled or unknown; merge authority required")
        if args.action in ("approve", "dismiss"):
            possible_landing = pr.get("auto_merge") is not None or "auto_merge" not in pr
            check_authority(authority, args.repo, args.number, args.action, possible_landing)
            check_clearance(bundle, args.repo, args.number, args.head, pr["base"]["sha"], pr["updated_at"])

        attempted = True
        if args.action == "dismiss":
            result = api(f"{pull}/reviews/{args.review_id}/dismissals", "PUT", {"message": body})
        elif args.action == "comment":
            result = api(f"repos/{args.repo}/issues/{args.number}/comments", "POST", {"body": body})
        else:
            event = "APPROVE" if args.action == "approve" else "REQUEST_CHANGES"
            result = api(f"{pull}/reviews", "POST",
                         {"event": event, "commit_id": args.head, "body": body})
        print(f"Submitted {args.action}: {result.get('html_url') or result.get('id')}")
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
        if (observed.get("headRefOid") != args.head or not observed.get("reviewDecision")
                or observed.get("queue_state", "unknown") == "unknown"):
            print("Post-write state uncertain or changed; reconcile before further writes")
            code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
