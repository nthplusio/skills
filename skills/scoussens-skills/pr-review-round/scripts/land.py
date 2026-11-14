#!/usr/bin/env python3
"""Watch by default; --enqueue requires explicit authority and reviewed heads.

land.py [--watch] <pr-number> [pr-number ...]
land.py --enqueue <pr-number>:<reviewed-full-sha> [...]

Every write rechecks OPEN, non-draft, reviewed head, APPROVED, CLEAN, and actual
queue membership. GitHub's --match-head-commit guards the merge request too.
No strategy flag: the queue owns the merge strategy. A successful request is
not proof of queue membership or landing; only subsequent reads establish it.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time

from merge_queue import queue_state
from ledger import check_authority, check_clearance, target_state

POLL_SECONDS = 30
MAX_POLLS = 40


def state_of(num, repo=None):
    result = subprocess.run([
        "gh", "pr", "view", str(num), *(["--repo", repo] if repo else []), "--json",
        "id,state,headRefOid,baseRefOid,baseRefName,updatedAt,isDraft,mergeStateStatus,reviewDecision,mergedAt",
    ], capture_output=True, text=True)
    if result.returncode:
        return {}
    try:
        state = json.loads(result.stdout)
        if not isinstance(state, dict):
            return {}
    except ValueError:
        return {}
    state["queue_state"] = queue_state(state.get("id"), state.get("headRefOid"))
    state["target"] = target_state(repo, state.get("baseRefName"))
    return state


def enqueue(num, head, repo, auto=False):
    result = subprocess.run([
        "gh", "pr", "merge", str(num), "--repo", repo, "--match-head-commit", head,
        *(["--auto"] if auto else []),
    ], capture_output=True, text=True)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--watch", action="store_true", help="read-only (default)")
    mode.add_argument("--enqueue", action="store_true", help="authorized merge requests only")
    mode.add_argument("--enable-auto-merge", action="store_true", help="same landing gates, including the first attempt")
    parser.add_argument("--repo")
    parser.add_argument("--authority", type=Path)
    parser.add_argument("--assessments", type=Path)
    parser.add_argument("prs", nargs="+")
    args = parser.parse_args()
    writing = args.enqueue or args.enable_auto_merge
    if writing and not all((args.repo, args.authority, args.assessments)):
        parser.error("landing requires --repo, --authority and --assessments; flags alone grant no authority")
    heads = {}
    for value in args.prs:
        pattern = r"([1-9][0-9]*):([0-9a-f]{40})" if writing else r"([1-9][0-9]*)"
        match = re.fullmatch(pattern, value)
        if not match:
            parser.error("use NUMBER:REVIEWED_FULL_SHA with --enqueue; otherwise use NUMBER")
        number = int(match[1])
        head = match[2] if writing else None
        if number in heads and heads[number] != head:
            parser.error(f"conflicting reviewed heads for #{number}")
        heads[number] = head

    pending = set(heads)
    outcomes = {}
    submitted = set()
    for poll in range(MAX_POLLS + 1):
        if poll:
            time.sleep(POLL_SECONDS)
        for number in sorted(pending):
            state = state_of(number, args.repo)
            status = state.get("state")
            merge_state = state.get("mergeStateStatus")
            queue = state.get("queue_state", "unknown")
            outcome = None
            if status == "MERGED":
                outcome = "MERGED"
            elif status == "CLOSED":
                outcome = "CLOSED, not merged"
            elif merge_state in ("DIRTY", "CONFLICTING"):
                outcome = "CONFLICTING, author action"
            elif writing and state.get("headRefOid") != heads[number]:
                outcome = "HELD: reviewed head changed or unavailable; review again"
            elif writing and (status != "OPEN" or state.get("isDraft") is not False):
                outcome = "HELD: open non-draft state not confirmed"
            elif writing and state.get("reviewDecision") != "APPROVED":
                outcome = "HELD: current approval not confirmed"
            if writing and not outcome:
                try:
                    check_authority(json.loads(args.authority.read_text()), args.repo, number,
                                    "enable-auto-merge" if args.enable_auto_merge else "enqueue", True)
                    check_clearance(json.loads(args.assessments.read_text()), args.repo, number,
                                    state.get("headRefOid"), state.get("baseRefOid"), state.get("updatedAt"), state.get("target"))
                except (ValueError, OSError, KeyError, TypeError) as error:
                    outcome = f"HELD: {error}"
            if outcome:
                outcomes[number] = outcome
                pending.remove(number)
                print(f"#{number} {outcome}")
                continue

            print(f"#{number} pending -- state={status or 'unknown'} / "
                  f"merge={merge_state or 'unknown'} / queue={queue}")
            if (writing and poll < MAX_POLLS and merge_state == "CLEAN"
                    and queue == "not_queued" and number not in submitted):
                ok, out = enqueue(number, heads[number], args.repo, args.enable_auto_merge)
                submitted.add(number)
                # Read after even an uncertain write. Never retry on its response alone.
                observed = state_of(number, args.repo)
                print(f"#{number} post-write: head={observed.get('headRefOid', 'unknown')} / "
                      f"review={observed.get('reviewDecision', 'unknown')} / "
                      f"queue={observed.get('queue_state', 'unknown')} / state={observed.get('state', 'unknown')}")
                if observed.get("state") == "MERGED":
                    outcomes[number] = "MERGED"
                    pending.remove(number)
                elif (observed.get("headRefOid") != heads[number] or observed.get("reviewDecision") != "APPROVED"
                      or observed.get("target") != state.get("target")):
                    outcomes[number] = "HELD: post-write head or approval changed, or target moved; reconcile before further writes"
                    pending.remove(number)
                    print(f"#{number} {outcomes[number]}")
                if not ok:
                    outcomes[number] = "HELD: merge request failed or outcome uncertain; inspect before retry"
                    pending.discard(number)
                    print(f"#{number} {outcomes[number]} -- {out}")
                elif number in pending:
                    print(f"#{number} merge request accepted; awaiting observed queue/merge state")
        if not pending:
            break

    if all(outcomes.get(number) == "MERGED" for number in heads):
        print("all watched PRs landed")
        return 0
    for number in sorted(pending):
        print(f"#{number} timed out, not confirmed merged; last observed state above")
    print("round incomplete: held, conflicting, closed, or pending PRs have not been confirmed merged")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
