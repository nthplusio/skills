#!/usr/bin/env python3
"""Change a PR's branch at the moderate or major work level, bound to the head you reviewed.

    branch_write.py update-branch <n> --repo OWNER/REPO --head <full-sha> --authority <a.json> [--write]
    branch_write.py push-fix <n> --repo OWNER/REPO --head <full-sha> --authority <a.json> [--remote origin] [--write]

update-branch merges the base into the PR branch through GitHub, which refuses
when the head is no longer <head>. push-fix pushes the commits on the local
HEAD, which must descend from <head>, with a lease on <head>, never a force.
The moderate level caps a fix at MINOR_LINES changed lines; larger work is
major-level work for a worker. Either write makes a new head: review it again
before any approval, and a push by you means you pushed last.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

from ledger import check_authority, record_write
from review_write import api

MINOR_LINES = 50


def git(*args):
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def changed_lines(head):
    total = 0
    for line in git("diff", "--numstat", f"{head}..HEAD").splitlines():
        added, deleted, _ = line.split("\t", 2)
        total += int(added) + int(deleted) if added != "-" else MINOR_LINES + 1
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["update-branch", "push-fix"])
    parser.add_argument("number", type=int)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.head):
        parser.error("--head must be the full SHA you reviewed")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo) or args.number <= 0:
        parser.error("use OWNER/REPO and a positive PR number")
    pull = f"repos/{args.repo}/pulls/{args.number}"
    try:
        authority = json.loads(args.authority.read_text())
        check_authority(authority, args.repo, args.number, args.action)
        if args.action == "push-fix":
            local = git("rev-parse", "HEAD")
            if local == args.head or subprocess.run(["git", "merge-base", "--is-ancestor", args.head, "HEAD"]).returncode:
                raise ValueError("local HEAD must add commits on top of the reviewed head")
            size = changed_lines(args.head)
            if authority["level"] == "moderate" and size > MINOR_LINES:
                raise ValueError(f"{size} changed lines is more than a minor fix ({MINOR_LINES}); "
                                 "hand it to a worker at the major level")
            if args.repo.lower() not in git("remote", "get-url", "--push", args.remote).lower():
                raise ValueError(f"remote {args.remote} does not point at {args.repo}")
        pr = api(pull)
        if pr["head"]["sha"] != args.head or pr["state"] != "open":
            raise RuntimeError("HELD: head changed or PR closed; review current state again")
        if args.action == "push-fix" and (pr["head"].get("repo") or {}).get("full_name") != args.repo:
            raise RuntimeError("HELD: the branch lives in a fork; ask the author to apply the fix")
        if not args.write:
            print(f"HELD: {args.action} #{args.number} at {args.head}; no write authorized")
            return 0
        if args.action == "update-branch":
            api(f"{pull}/update-branch", "PUT", {"expected_head_sha": args.head})
            record_write(args.repo, args.number, args.action, args.head)
            print(f"Requested a base merge into #{args.number}. GitHub builds the new head shortly; review it again.")
            return 0
        branch = pr["head"]["ref"]
        git("push", f"--force-with-lease=refs/heads/{branch}:{args.head}", args.remote, f"HEAD:refs/heads/{branch}")
        record_write(args.repo, args.number, args.action, local)
        observed = api(pull)["head"]["sha"]
        print(f"Pushed {local[:9]} to {branch}; GitHub head is {observed[:9]}.")
        if observed != local:
            print("GitHub has not shown the pushed head yet, or someone else pushed; reconcile before further writes")
            return 1
        print("You pushed last: review the new head, and name another approver where the base requires one.")
        return 0
    except (RuntimeError, ValueError, OSError, KeyError, TypeError) as error:
        print(str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
