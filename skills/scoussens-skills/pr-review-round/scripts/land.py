#!/usr/bin/env python3
"""Watch by default; --enqueue requires explicit authority and reviewed heads.

land.py [--watch] <pr-number> [pr-number ...]
land.py --enqueue <pr-number>:<reviewed-full-sha> [...]
land.py --enqueue --stack-method squash <pr>:<sha> [<lower-pr>:<sha> ...]
land.py --enable-auto-merge <pr>:<reviewed-full-sha> [...]
land.py --requeue-flake --failure-log <log> <pr>:<reviewed-full-sha>

--enable-auto-merge after this round's own approval at the reviewed head is
governed by the auto-merge-on-approval policy; on a PR someone else approved it
is the auto-merge-sweep policy. Both still need GitHub's APPROVED review decision.

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
GitHub's required checks, and reports AUTO-MERGE ENABLED once GitHub shows it, or
QUEUED once the PR is in the merge queue. GitHub's --match-head-commit guards
the merge request too.
No strategy flag: the queue owns the merge strategy. A successful request is
not proof of queue membership or landing; only subsequent reads establish it.
A PR that already has auto-merge on, or is already queued, at the reviewed head
gets no new request; the helper says so, so a re-run is safe.

A PR without GitHub's APPROVED decision that the authenticated user authored,
or last pushed under a last-push rule, cannot be approved by the round. It is
governed by the own-pr-landing policy (action land-own-pr) and lands only when
the required checks are green at the reviewed head, a review bot has reviewed
the PR, no reviewer's latest verdict requests changes, and the round's
assessment at that head has nothing unresolved. The write records each
condition. Under `ask` the hold names who can approve (approvers.py). When
GitHub refuses, for example because the base requires a human approval, the
helper prints the head-bound command a person can run. It never bypasses.

--requeue-flake puts a PR the merge queue removed for a failing check back in the
queue, under the requeue-flake policy (action requeue), with every --enqueue gate.
It goes ahead only when the failing log (`gh run view <run> --log-failed` of the
merge-group run) names a test that a line of the profile's `flakes` reference lists
beside a ticket key, and only once per PR: the ledger records the requeue, so a
second removal holds for a person.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from approvers import approvers, lines as approver_lines
from branch_rules import last_pusher, review_rules
from findings import is_bot
from merge_queue import queue_state
from review_requests import effective_reviews
from freshness import Benign, live_from_view
from ledger import check_authority, check_clearance, record_write, target_state, writes
from stacks import stack_of, below
from review_config import resolve

TICKET = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")

POLL_SECONDS = 30
MAX_POLLS = 40


def state_of(num, repo=None):
    result = subprocess.run([
        "gh", "pr", "view", str(num), *(["--repo", repo] if repo else []), "--json",
        "id,state,headRefOid,baseRefOid,baseRefName,updatedAt,isDraft,mergeable,mergeStateStatus,reviewDecision,"
        "mergedAt,autoMergeRequest,author,headRefName,headRepository,headRepositoryOwner",
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


def remember(repo, number, action, head, accepted=None, conditions=None):
    """Record an accepted landing request; a ledger failure must not hide the write that happened."""
    try:
        record_write(repo, number, action, head, accepted=accepted, conditions=conditions)
    except OSError as error:
        print(f"#{number} landing requested, but not recorded in the ledger ({error})")


def _read(command):
    result = subprocess.run(command, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except ValueError:
        return None


def own_pr(repo, state):
    """Why the authenticated user cannot approve this PR (author, or last pusher under a last-push rule), or None."""
    login = (_read(["gh", "api", "user"]) or {}).get("login")
    if not login:
        return None
    if (state.get("author") or {}).get("login") == login:
        return f"{login} authored it"
    head_repo = "/".join(filter(None, ((state.get("headRepositoryOwner") or {}).get("login"),
                                       (state.get("headRepository") or {}).get("name"))))
    if ((review_rules(repo, state.get("baseRefName")) or {}).get("require_last_push_approval")
            and last_pusher(head_repo, state.get("headRefName")) == login):
        return f"{login} pushed the last commit and the base requires another approver of the last push"
    return None


def own_conditions(repo, number, head):
    """What each own-PR landing condition observed; raises naming every condition that fails.
    The fourth, the round's assessment at the head with nothing unresolved, is clearance() and runs first."""
    failed, observed = [], {"assessment": f"saved at {head} with nothing unresolved"}
    checks = _read(["gh", "pr", "checks", str(number), "--repo", repo, "--required", "--json", "name,bucket"])
    if not isinstance(checks, list) or not checks:
        failed.append("required checks unknown or none reported at the reviewed head")
    elif any(c.get("bucket") not in ("pass", "skipping") for c in checks):
        failed.append("required checks not green: " + ", ".join(
            f'{c.get("name")} {c.get("bucket")}' for c in checks if c.get("bucket") not in ("pass", "skipping")))
    else:
        observed["checks"] = ", ".join(f'{c["name"]} {c["bucket"]}' for c in checks)
    pages = _read(["gh", "api", f"repos/{repo}/pulls/{number}/reviews?per_page=100", "--paginate", "--slurp"])
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        failed.append("reviews unreadable, so the bot review and changes requests are unknown")
    else:
        reviews = [review for page in pages for review in page]
        bots = sorted({r["user"]["login"] for r in reviews if is_bot(r.get("user"))})
        if bots:
            observed["bot_review"] = ", ".join(bots)
        else:
            failed.append("no review bot has reviewed this PR")
        blocking = sorted(login for login, r in effective_reviews(reviews).items() if r.get("state") == "CHANGES_REQUESTED")
        if blocking:
            failed.append("changes requested by " + ", ".join(blocking))
        else:
            observed["changes_requested"] = "none"
    if failed:
        raise ValueError("own PR cannot land: " + "; ".join(failed))
    return observed


def flake_ticket(log, references):
    """The ticket of the first `flakes` reference line whose backticked test name appears in the failing log."""
    for path in references:
        for line in Path(path).read_text().splitlines():
            ticket = TICKET.search(line)
            if ticket and any(test in log for test in re.findall(r"`([^`]+)`", line)):
                return ticket[0]
    return None


def landing_action(args, number, head, own=None):
    """Auto-merge after this round's own approval at the head, the sweep of a PR someone else approved,
    or the landing of a PR the round cannot approve because it is the user's own."""
    if own:
        return "land-own-pr"
    if args.requeue_flake:
        return "requeue"
    if not args.enable_auto_merge:
        return "enqueue"
    own = any(w.get("number") == number and w.get("action") in ("approve", "reapprove") and w.get("head") == head
              for w in writes(args.repo))
    return "enable-auto-merge" if own else "sweep-auto-merge"


def clearance(args, number, state):
    """The freshness verdict a landing goes ahead on; raises when it must hold."""
    return check_clearance(json.loads(args.assessments.read_text()), args.repo, number, live_from_view(state))


def drift(args, number, state):
    """Why the observed state no longer clears the assessment, or None."""
    try:
        clearance(args, number, state)
    except (ValueError, OSError, KeyError, TypeError) as error:
        return str(error)
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--watch", action="store_true", help="read-only (default)")
    mode.add_argument("--enqueue", action="store_true", help="authorized merge requests only")
    mode.add_argument("--enable-auto-merge", action="store_true", help="same landing gates, including the first attempt")
    mode.add_argument("--requeue-flake", action="store_true", help="requeue once after a removal for a known flake")
    parser.add_argument("--failure-log", type=Path, help="with --requeue-flake: the failing run's log")
    parser.add_argument("--repo")
    parser.add_argument("--authority", type=Path)
    parser.add_argument("--assessments", type=Path)
    parser.add_argument("--stack-method", choices=("merge", "squash", "rebase"),
                        help="merge method for stacked PRs; a merge queue on the base still chooses its own")
    parser.add_argument("prs", nargs="+")
    args = parser.parse_args()
    writing = args.enqueue or args.enable_auto_merge or args.requeue_flake
    if writing and not all((args.repo, args.authority, args.assessments)):
        parser.error("landing requires --repo, --authority and --assessments; flags alone grant no authority")
    if args.requeue_flake != bool(args.failure_log):
        parser.error("--requeue-flake and --failure-log go together")
    flake = None
    if args.requeue_flake:
        try:
            flake = flake_ticket(args.failure_log.read_text(), resolve(".")["references"].get("flakes", []))
        except (OSError, ValueError) as error:
            parser.error(f"could not read the failing log or the flakes reference: {error}")
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
    accepted = {}
    owned = {}  # PR -> the own-PR conditions its landing went ahead on
    # An own PR needs no APPROVED decision, only no changes request; any other PR needs APPROVED.
    cleared = lambda n, s: s.get("reviewDecision") == "APPROVED" or (
        n in owned and s.get("reviewDecision") != "CHANGES_REQUESTED")
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
            own = (own_pr(args.repo, state) if writing and status == "OPEN" and not state.get("stack")
                   and state.get("reviewDecision") != "APPROVED" else None)
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
            elif writing and state.get("reviewDecision") != "APPROVED" and not own:
                outcome = "HELD: current approval not confirmed"
            elif args.requeue_flake and any(w.get("number") == number and w.get("action") == "requeue"
                                            for w in writes(args.repo)):
                outcome = "HELD: the round already requeued this PR once after a flaky failure; a person decides now"
            elif args.requeue_flake and not flake:
                outcome = ("HELD: the failing log names no test the profile's flakes reference lists; "
                           "treat the failure as real")
            elif writing and (state.get("stack") or {}).get("status") == "unknown":
                outcome = "HELD: stack membership unknown; re-read before landing"
            elif writing and (state.get("stack") or {}).get("kind") == "branch":
                parent = state["stack"]["entries"][0]["number"]
                outcome = (f"HELD: based on #{parent}'s branch; it lands after #{parent} merges and GitHub "
                           "retargets it, then review the retargeted PR")
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
                    try:
                        check_authority(json.loads(args.authority.read_text()), args.repo, number,
                                        landing_action(args, number, heads[number], own))
                    except ValueError as error:
                        if own and "policy is ask" in str(error):
                            # Name who can approve, so the round can request their review instead.
                            raise ValueError(f"{error}\n  #{number} is your own PR ({own}); request review from:\n    "
                                             + "\n    ".join(approver_lines(approvers(args.repo, number), number)))
                        raise
                    verdict = clearance(args, number, state)
                    accepted[number] = verdict.record() if isinstance(verdict, Benign) else None
                    if accepted[number]:
                        print(f"#{number} accepted moved inputs: " + "; ".join(verdict.reasons))
                    if own:
                        owned[number] = {"own": own, **own_conditions(args.repo, number, heads[number])}
                        print(f"#{number} own PR ({own}); landing conditions hold: "
                              + "; ".join(f"{k}: {v}" for k, v in owned[number].items() if k != "own"))
                except (ValueError, OSError, KeyError, TypeError) as error:
                    outcome = f"HELD: {error}"
            if writing and not outcome and args.enable_auto_merge and state.get("autoMergeRequest"):
                outcome = ("AUTO-MERGE ENABLED, not merged; already on at the reviewed head, so no request was sent. "
                           "GitHub merges it when its required checks pass")
            elif writing and not outcome and args.enable_auto_merge and queue == "queued":
                outcome = ("QUEUED, not merged; in the merge queue at the reviewed head"
                           + ("" if number in submitted else ", so no request was sent")
                           + ". The merge queue merges it when its checks pass")
            if outcome:
                outcomes[number] = outcome
                pending.remove(number)
                print(f"#{number} {outcome}")
                continue

            print(f"#{number} pending -- state={status or 'unknown'} / "
                  f"merge={merge_state or 'unknown'} / queue={queue}")
            if writing and queue == "queued" and number not in submitted:
                print(f"#{number} already in the merge queue at the reviewed head; no merge request sent")
            if (writing and poll < MAX_POLLS and merge_state == "CLEAN"
                    and queue == "not_queued" and number not in submitted and state.get("stack")):
                ready[number] = state
            elif (writing and poll < MAX_POLLS and queue == "not_queued" and number not in submitted
                    and (merge_state == "CLEAN" or (number in owned and merge_state == "BLOCKED")
                         or (args.enable_auto_merge and merge_state in ("BLOCKED", "UNSTABLE", "HAS_HOOKS", "BEHIND")))):
                ok, out = enqueue(number, heads[number], args.repo, args.enable_auto_merge)
                submitted.add(number)
                if ok:
                    action = ("land-own-pr" if number in owned else "enable-auto-merge" if args.enable_auto_merge
                              else "requeue" if args.requeue_flake else "enqueue")
                    remember(args.repo, number, action, heads[number], accepted.get(number),
                             owned.get(number) or ({"flake": flake} if args.requeue_flake else None))
                # Read after even an uncertain write. Never retry on its response alone.
                observed = state_of(number, args.repo)
                print(f"#{number} post-write: head={observed.get('headRefOid', 'unknown')} / "
                      f"review={observed.get('reviewDecision', 'unknown')} / "
                      f"queue={observed.get('queue_state', 'unknown')} / state={observed.get('state', 'unknown')}")
                moved = None if observed.get("state") == "MERGED" else drift(args, number, observed)
                if observed.get("state") == "MERGED":
                    outcomes[number] = "MERGED"
                    pending.remove(number)
                elif (ok and args.enable_auto_merge and observed.get("queue_state") == "queued"
                      and observed.get("headRefOid") == heads[number] and cleared(number, observed) and not moved):
                    outcomes[number] = "QUEUED, not merged; the merge queue merges it when its checks pass"
                    pending.remove(number)
                    print(f"#{number} {outcomes[number]}")
                elif (ok and args.enable_auto_merge and observed.get("autoMergeRequest")
                      and observed.get("headRefOid") == heads[number] and cleared(number, observed) and not moved):
                    outcomes[number] = "AUTO-MERGE ENABLED, not merged; GitHub merges it when its required checks pass"
                    pending.remove(number)
                    print(f"#{number} {outcomes[number]}")
                elif observed.get("headRefOid") != heads[number] or not cleared(number, observed) or moved:
                    outcomes[number] = ("HELD: post-write head or approval changed, or the assessment no longer holds"
                                        + (f" ({moved})" if moved else "") + "; reconcile before further writes")
                    pending.remove(number)
                    print(f"#{number} {outcomes[number]}")
                if not ok:
                    outcomes[number] = "HELD: merge request failed or outcome uncertain; inspect before retry"
                    pending.discard(number)
                    print(f"#{number} {outcomes[number]} -- {out}")
                    if number in owned:
                        print(f"#{number} GitHub refused landing your own PR; the base may require a human approval. "
                              "After rechecking the head and approval, a person with that right can run: "
                              f"gh pr merge {number} --repo {args.repo} --match-head-commit {heads[number]}"
                              + (" --auto" if args.enable_auto_merge else ""))
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
                   or fresh[n].get("queue_state") != "not_queued" or drift(args, n, fresh[n])
                   for n in covered):
                print(f"#{number} stack state changed before write; holding this poll")
                continue
            ok, out = stack_merge(number, args.stack_method)
            submitted.update(covered)
            for n in covered:
                if ok:
                    remember(args.repo, n, "stack-merge", heads[n], accepted.get(n))
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
                elif observed.get("headRefOid") != heads[n] or drift(args, n, observed):
                    outcomes[n] = "HELD: post-write head changed or the assessment no longer holds; reconcile before further writes"
                    pending.discard(n)
                    print(f"#{n} {outcomes[n]}")
                else:
                    print(f"#{n} stack merge request accepted with #{number}; awaiting observed queue/merge state")
        if not pending:
            break

    if all(outcomes.get(number) == "MERGED" for number in heads):
        print("all watched PRs landed")
        return 0
    if all(outcomes.get(number, "").startswith(("MERGED", "AUTO-MERGE ENABLED", "QUEUED")) for number in heads):
        print("every PR merged, has auto-merge on, or is in the merge queue; confirm merges later with land.py --watch")
        return 0
    for number in sorted(pending):
        print(f"#{number} timed out, not confirmed merged; last observed state above")
    print("round incomplete: held, conflicting, closed, or pending PRs have not been confirmed merged")
    return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)  # each line as it happens, so a killed run still shows what it did
    raise SystemExit(main())
