#!/usr/bin/env python3
"""Watch by default; --enqueue requires explicit authority and reviewed heads.

land.py [--watch] <pr-number> [pr-number ...]
land.py --enqueue <pr-number>:<reviewed-full-sha> [...]
land.py --enqueue --stack-method squash <pr>:<sha> [<lower-pr>:<sha> ...]

Stacked PRs (GitHub `gh stack`): GitHub refuses per-PR auto-merge for any stack
member, so --enable-auto-merge holds them. --enqueue lands a stack member with
`gh stack merge <pr> --yes --<method>`, which also lands every unmerged PR below
it; every such lower PR must be named here with its reviewed head and pass the
same gates. `gh stack merge` has no expected-head guard, so heads are re-read
immediately before the write. Run from the repository root with the official
`github/gh-stack` extension installed.

Every write rechecks OPEN, non-draft, reviewed head, APPROVED, and actual queue
membership. --enqueue also waits for CLEAN. --enable-auto-merge is the preferred
landing path: it turns auto-merge on while checks still run, leaves the wait to
GitHub's required checks, and reports AUTO-MERGE ENABLED once GitHub shows it. GitHub's --match-head-commit guards the merge request too.
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
from ledger import check_authority, check_clearance, record_write, target_state
from stacks import stack_of, below

POLL_SECONDS = 30
MAX_POLLS = 40


def state_of(num, repo=None):
    result = subprocess.run([
        "gh", "pr", "view", str(num), *(["--repo", repo] if repo else []), "--json",
        "id,state,headRefOid,baseRefOid,baseRefName,updatedAt,isDraft,mergeStateStatus,reviewDecision,mergedAt,"
        "autoMergeRequest",
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
    state["stack"] = stack_of(repo, num)
    return state


def enqueue(num, head, repo, auto=False):
    result = subprocess.run([
        "gh", "pr", "merge", str(num), "--repo", repo, "--match-head-commit", head,
        *(["--auto"] if auto else []),
    ], capture_output=True, text=True)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def stack_merge(num, method):
    if subprocess.run(["gh", "stack", "--help"], capture_output=True, text=True).returncode:
        return False, "gh stack extension unavailable; a person can install it with `gh extension install github/gh-stack`"
    result = subprocess.run(["gh", "stack", "merge", str(num), "--yes", f"--{method}"], capture_output=True, text=True)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def remember(repo, number, action, head):
    """Record an accepted landing request; a ledger failure must not hide the write that happened."""
    try:
        record_write(repo, number, action, head)
    except OSError as error:
        print(f"#{number} landing requested, but not recorded in the ledger ({error})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--watch", action="store_true", help="read-only (default)")
    mode.add_argument("--enqueue", action="store_true", help="authorized merge requests only")
    mode.add_argument("--enable-auto-merge", action="store_true", help="same landing gates, including the first attempt")
    parser.add_argument("--repo")
    parser.add_argument("--authority", type=Path)
    parser.add_argument("--assessments", type=Path)
    parser.add_argument("--stack-method", choices=("merge", "squash", "rebase"),
                        help="merge method for stacked PRs; a merge queue on the base still chooses its own")
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
        ready = {}
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
            elif writing and (state.get("stack") or {}).get("status") == "unknown":
                outcome = "HELD: stack membership unknown; re-read before landing"
            elif writing and state.get("stack") and args.enable_auto_merge:
                outcome = ("HELD: GitHub refuses auto-merge for stacked PRs; use --enqueue --stack-method "
                           "with every unmerged lower PR, or ask the author to unstack")
            elif writing and state.get("stack") and not args.stack_method:
                outcome = "HELD: stacked PR needs --stack-method; the last-used method is otherwise reused"
            elif writing and state.get("stack") and any(e["number"] not in heads for e in below(state["stack"], number)):
                lower = ", ".join(f'#{e["number"]}' for e in below(state["stack"], number) if e["number"] not in heads)
                outcome = f"HELD: gh stack merge would also land {lower}; name each with its reviewed head and authority"
            if writing and not outcome:
                try:
                    check_authority(json.loads(args.authority.read_text()), args.repo, number,
                                    "enable-auto-merge" if args.enable_auto_merge else "enqueue", True)
                    check_clearance(json.loads(args.assessments.read_text()), args.repo, number,
                                    state.get("headRefOid"), state.get("baseRefOid"), state.get("updatedAt"), state.get("target"))
                except (ValueError, OSError, KeyError, TypeError) as error:
                    outcome = f"HELD: {error}"
            if writing and not outcome and args.enable_auto_merge and state.get("autoMergeRequest"):
                outcome = "AUTO-MERGE ENABLED, not merged; GitHub merges it when its required checks pass"
            if outcome:
                outcomes[number] = outcome
                pending.remove(number)
                print(f"#{number} {outcome}")
                continue

            print(f"#{number} pending -- state={status or 'unknown'} / "
                  f"merge={merge_state or 'unknown'} / queue={queue}")
            if (writing and poll < MAX_POLLS and merge_state == "CLEAN"
                    and queue == "not_queued" and number not in submitted and state.get("stack")):
                ready[number] = state
            elif (writing and poll < MAX_POLLS and queue == "not_queued" and number not in submitted
                    and (merge_state == "CLEAN" or (args.enable_auto_merge
                                                     and merge_state in ("BLOCKED", "UNSTABLE", "HAS_HOOKS", "BEHIND")))):
                ok, out = enqueue(number, heads[number], args.repo, args.enable_auto_merge)
                submitted.add(number)
                if ok:
                    remember(args.repo, number, "enable-auto-merge" if args.enable_auto_merge else "enqueue", heads[number])
                # Read after even an uncertain write. Never retry on its response alone.
                observed = state_of(number, args.repo)
                print(f"#{number} post-write: head={observed.get('headRefOid', 'unknown')} / "
                      f"review={observed.get('reviewDecision', 'unknown')} / "
                      f"queue={observed.get('queue_state', 'unknown')} / state={observed.get('state', 'unknown')}")
                if observed.get("state") == "MERGED":
                    outcomes[number] = "MERGED"
                    pending.remove(number)
                elif (ok and args.enable_auto_merge and observed.get("autoMergeRequest")
                      and observed.get("headRefOid") == heads[number] and observed.get("reviewDecision") == "APPROVED"
                      and observed.get("target") == state.get("target")):
                    outcomes[number] = "AUTO-MERGE ENABLED, not merged; GitHub merges it when its required checks pass"
                    pending.remove(number)
                    print(f"#{number} {outcomes[number]}")
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
        # One `gh stack merge` per stack, from its highest named PR, only when
        # every unmerged PR below it cleared every gate in this same poll.
        tops = {}
        for number, state in ready.items():
            stack = state["stack"]
            if all(e["number"] in ready for e in below(stack, number)):
                if stack["position"] > tops.get(stack["number"], (0, None))[0]:
                    tops[stack["number"]] = (stack["position"], number)
        for _, number in tops.values():
            covered = [e["number"] for e in below(ready[number]["stack"], number)] + [number]
            fresh = {n: state_of(n, args.repo) for n in covered}
            if any(fresh[n].get("headRefOid") != heads[n] or fresh[n].get("reviewDecision") != "APPROVED"
                   or fresh[n].get("queue_state") != "not_queued" or fresh[n].get("target") != ready[n].get("target")
                   for n in covered):
                print(f"#{number} stack state changed before write; holding this poll")
                continue
            ok, out = stack_merge(number, args.stack_method)
            submitted.update(covered)
            for n in covered:
                if ok:
                    remember(args.repo, n, "stack-merge", heads[n])
                observed = state_of(n, args.repo)
                print(f"#{n} post-write: head={observed.get('headRefOid', 'unknown')} / "
                      f"review={observed.get('reviewDecision', 'unknown')} / "
                      f"queue={observed.get('queue_state', 'unknown')} / state={observed.get('state', 'unknown')}")
                if observed.get("state") == "MERGED":
                    outcomes[n] = "MERGED"
                    pending.discard(n)
                elif not ok:
                    outcomes[n] = "HELD: stack merge failed or outcome uncertain; inspect before retry"
                    pending.discard(n)
                    print(f"#{n} {outcomes[n]} -- {out}")
                elif observed.get("headRefOid") != heads[n] or observed.get("target") != ready[n].get("target"):
                    outcomes[n] = "HELD: post-write head changed or target moved; reconcile before further writes"
                    pending.discard(n)
                    print(f"#{n} {outcomes[n]}")
                else:
                    print(f"#{n} stack merge request accepted with #{number}; awaiting observed queue/merge state")
        if not pending:
            break

    if all(outcomes.get(number) == "MERGED" for number in heads):
        print("all watched PRs landed")
        return 0
    if all(outcomes.get(number, "").startswith(("MERGED", "AUTO-MERGE ENABLED")) for number in heads):
        print("every PR merged or has auto-merge on; confirm merges later with land.py --watch")
        return 0
    for number in sorted(pending):
        print(f"#{number} timed out, not confirmed merged; last observed state above")
    print("round incomplete: held, conflicting, closed, or pending PRs have not been confirmed merged")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
