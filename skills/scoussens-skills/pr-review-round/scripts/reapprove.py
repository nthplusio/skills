#!/usr/bin/env python3
"""reapprove.py <n> --repo <owner/repo> [--carry <assessments.json>] -- read-only on the forge.

Whether a PR the round approved earlier has changed only by clean base merges since
that approval, so the `reapprove-base-only` policy can approve it again without a
new review. Run it from the repository root.

The approved head A is the round's last `approve` or `reapprove` write in the ledger;
approvals posted outside the round do not count. The live head H is base-only when:

  - A is an ancestor of H (no rebase, no force-push that dropped A);
  - every commit on H's first-parent chain back to A is a two-parent merge whose
    second parent is reachable from the live base branch tip;
  - each merge's tree equals `git merge-tree --write-tree <first> <second>`, which
    must merge cleanly (no conflict resolved by hand, no change slipped into a merge);
  - GitHub reports the PR mergeable.

Anything unreadable is not base-only. Output: the verdict, its reason, A, H and the
merge-tree result per commit.

With `--carry`, A is the head of the PR's saved assessment instead, whether or not
the round approved it, and the script replaces this PR's assessment in the round's
assessments file, in place, with that assessment carried to H, keeping every other
PR's entry; `ledger.py record` then saves it. In the carried record the new head,
base, target, discussion time and policy revision are read live, the original `assessed_at` and
decisions are kept, and `carried` plus `provenance` record the tree check, both heads
and why the review still holds. H may equal A when only the base or the discussion
moved. It refuses a changed review policy, a base move freshness.py would not call
benign, and a head that changed code: it names the files changed beyond the base, so
a test-only push gets a short review of those files. Discussion since A that
freshness.py would not call benign needs `--read "<why the review still holds>"`,
which the round passes only after reading every new event. When A is the round's
approval, post the re-approval with `review_write.py reapprove`; otherwise approve
with `review_write.py approve`. Both run every approval guard on the carried record.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

from freshness import SHA, _api, _base_move, _discussion_move
from ledger import target_state, validate_assessment, writes
from review_config import resolve

APPROVALS = ("approve", "reapprove")
MAX_STEPS = 500


def git(*args):
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def have(sha):
    return git("cat-file", "-e", f"{sha}^{{commit}}") is not None


def base_only(approved, head, base_tip, anchor="the approval"):
    """{"base_only", "reason", "steps"} for the local commits approved..head against base_tip.
    `anchor` names what the approved head is in the reason: the round's approval or a saved assessment.

    Each step is one commit on head's first-parent chain, newest first, with its second
    parent, the tree `git merge-tree --write-tree` produced (None on conflict) and its own tree.
    """
    steps = []
    verdict = lambda ok, reason: {"base_only": ok, "reason": reason, "steps": steps}
    for name, sha in (("approved head", approved), ("live head", head), ("base tip", base_tip)):
        if not have(sha):
            return verdict(False, f"{name} {sha[:9]} is not available locally")
    refused = verdict
    verdict = lambda ok, reason: {**refused(ok, reason), **({} if ok else {"files": pushed(approved, head, base_tip)})}
    if approved == head:
        return verdict(False, f"the head has not moved since {anchor}")
    if subprocess.run(["git", "merge-base", "--is-ancestor", approved, head], capture_output=True).returncode:
        return verdict(False, f"approved head {approved[:9]} is not in the live head's history (rebase or force-push)")
    commit = head
    while commit != approved:
        if len(steps) >= MAX_STEPS:
            return verdict(False, f"more than {MAX_STEPS} commits since {anchor}")
        parents = (git("rev-list", "--parents", "-n", "1", commit) or "").split()[1:]
        if len(parents) != 2:
            steps.append({"commit": commit, "parents": len(parents)})
            return verdict(False, f"{commit[:9]} is not a two-parent merge"
                           + (" (an author commit)" if len(parents) == 1 else ""))
        first, second = parents
        step = {"commit": commit, "second_parent": second}
        steps.append(step)
        if subprocess.run(["git", "merge-base", "--is-ancestor", second, base_tip], capture_output=True).returncode:
            return verdict(False, f"{commit[:9]} merges {second[:9]}, which is not on the base branch")
        merged = subprocess.run(["git", "merge-tree", "--write-tree", first, second], capture_output=True, text=True)
        tree = git("rev-parse", f"{commit}^{{tree}}")
        step.update(merge_tree=merged.stdout.split("\n", 1)[0] if merged.returncode == 0 else None, tree=tree)
        if merged.returncode:
            return verdict(False, f"{commit[:9]}: the base merge conflicts, so someone resolved it by hand")
        if step["merge_tree"] != tree:
            return verdict(False, f"{commit[:9]}: the merge's tree differs from a clean merge of its parents")
        commit = first
    return verdict(True, f"{len(steps)} clean base merge(s) since {anchor}")


def pushed(approved, head, base_tip):
    """Files the head changes since `approved` other than by taking the base tip's version; None when unreadable."""
    changed = git("diff", "--name-only", approved, head)
    fork = git("merge-base", approved, base_tip)
    if changed is None or not fork:
        return None
    from_base = set((git("diff", "--name-only", fork, base_tip) or "").splitlines())
    return [f for f in changed.splitlines()
            if f not in from_base or git("rev-parse", f"{head}:{f}") != git("rev-parse", f"{base_tip}:{f}")]


def approved_head(repo, number):
    """The head of the round's last approval of this PR, from the ledger; None when there is none."""
    mine = [w for w in writes(repo) if w.get("number") == number and w.get("action") in APPROVALS
            and SHA.fullmatch(w.get("head") or "")]
    return max(mine, key=lambda w: w.get("at") or "")["head"] if mine else None


def mergeable(pr):
    """True, False, or None while GitHub has not computed it."""
    if pr.get("mergeable") is None:
        return None
    return pr["mergeable"] is True and pr.get("mergeable_state") != "dirty"


def check(repo, number, since=None):
    """Read the PR and the ledger, fetch what git needs, and decide. `since` replaces the round's approved head."""
    pr = _api(f"repos/{repo}/pulls/{number}")
    if not isinstance(pr, dict) or not SHA.fullmatch(((pr.get("head") or {}).get("sha")) or ""):
        return {"base_only": False, "reason": "the PR is unreadable", "approved": None, "head": None, "steps": []}, None
    head, ref = pr["head"]["sha"], pr["base"]["ref"]
    approved = since or approved_head(repo, number)
    target = target_state(repo, ref)
    anchor = "the saved assessment" if since else "the approval"
    result = {"approved": approved, "anchor": anchor, "head": head, "base": pr["base"]["sha"], "target": target,
              "steps": []}
    if not approved:
        return {**result, "base_only": False, "reason": "the ledger records no approval of this PR by the round"}, pr
    if not target["sha"]:
        return {**result, "base_only": False, "reason": f"the {ref} tip is unreadable"}, pr
    subprocess.run(["git", "fetch", "-q", "origin", ref], capture_output=True)
    subprocess.run(["git", "fetch", "-q", "origin", f"pull/{number}/head"], capture_output=True)
    for sha in (approved, target["sha"]):
        if not have(sha):  # GitHub serves a dropped commit by SHA for a while
            subprocess.run(["git", "fetch", "-q", "origin", sha], capture_output=True)
    result.update(base_only(approved, head, target["sha"], anchor))
    if result["base_only"] and mergeable(pr) is not True:
        result.update(base_only=False, reason="GitHub reports the PR conflicting" if mergeable(pr) is False
                      else "GitHub has not reported the PR mergeable yet")
    return result, pr


def carry(earlier, result, live, *, policy, discussion, base=([], []), read=None, at=None):
    """The earlier assessment at A carried to the live head H; raises when the review may no longer hold.

    `discussion` and `base` are freshness.py's (stale, benign) reasons since A; `read` is the round's
    statement that it read the stale discussion and why the review still holds."""
    validate_assessment(earlier)
    a, h = result["approved"], result["head"]
    if earlier["head"] != a:
        raise ValueError(f'the assessment is at {earlier["head"][:9]}, not the carried-from head {a[:9]}')
    if a != h and not result["base_only"]:
        files = result.get("files")
        raise ValueError(f'not base-only: {result["reason"]}; review the new head'
                         + (f'. Changed beyond the base: {", ".join(files)}' if files else ""))
    if earlier["evidence_inputs"]["policy"] != policy:
        raise ValueError("the review policy changed since the assessment; review the new head")
    if base[0]:
        raise ValueError("the base moved in a way that needs a review: " + "; ".join(base[0]))
    stale, benign = discussion
    if stale and not read:
        raise ValueError("discussion since the assessment needs a review: " + "; ".join(stale)
                         + '. After reading it, carry with --read "<why the review still holds>"')
    reasons = ([f'{len(result["steps"])} base merge(s), each tree equal to `git merge-tree --write-tree` of its '
                "parents"] if a != h else []) + list(base[1]) + list(benign)
    if stale:
        reasons.append("read by the round: " + "; ".join(stale) + f". {read}")
    record = {"from_head": a, "head": h, "check": "git merge-tree --write-tree",
              "commits": [s["commit"] for s in result["steps"]] if a != h else [], "reason": "; ".join(reasons),
              "at": at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    provenance = (f"Carried from {a} to {h}: {record['reason'] or 'nothing moved'}. Code checks were not rerun; "
                  "issue evidence is carried from the earlier assessment.")
    return {**earlier, "head": h, "base": live["base"], "carried": record, "provenance": provenance,
            "evidence_inputs": {**earlier["evidence_inputs"], "forge": live["forge"], "policy": policy,
                                "target": live["target"]}}


def describe(result):
    lines = [f'base-only: {"yes" if result["base_only"] else "no"} -- {result["reason"]}',
             f'head at {result.get("anchor", "the approval")} (A): {result.get("approved") or "none"}',
             f'live head (H): {result.get("head") or "unknown"}']
    for step in result["steps"]:
        if "second_parent" not in step:
            lines.append(f'  {step["commit"][:9]}  {step["parents"]} parent(s): not a base merge')
        elif "tree" not in step:
            lines.append(f'  {step["commit"][:9]}  merges {step["second_parent"][:9]}: not on the base branch')
        else:
            same = "clean, tree matches" if step["merge_tree"] == step["tree"] else (
                "conflict" if step["merge_tree"] is None else f'tree {step["tree"][:9]} != merge-tree {step["merge_tree"][:9]}')
            lines.append(f'  {step["commit"][:9]}  merges {step["second_parent"][:9]}: {same}')
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("number", type=int)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--carry", type=Path, help="the round's assessments file; carry updates this PR's entry in place")
    parser.add_argument("--read", help="with --carry: why the review holds after the round read the new discussion")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo) or args.number <= 0:
        parser.error("use OWNER/REPO and a positive PR number")
    if not args.carry:
        result, _ = check(args.repo, args.number)
        print("\n".join(describe(result)))
        return 0 if result["base_only"] else 1
    try:
        bundle = json.loads(args.carry.read_text())
        if bundle.get("repository") != args.repo:
            raise ValueError("the assessments belong to a different repository")
        matches = [a for a in bundle.get("assessments", []) if a.get("number") == args.number]
        if len(matches) != 1:
            raise ValueError("one assessment of this PR required")
        earlier = matches[0]
        validate_assessment(earlier)
        result, pr = check(args.repo, args.number, since=earlier["head"])
        print("\n".join(describe(result)), file=sys.stderr)
        if not pr:
            raise ValueError(result["reason"])
        live = {"head": result["head"], "base": result.get("base"), "forge": pr.get("updated_at"),
                "target": result.get("target"), "conflicting": None if mergeable(pr) is None else not mergeable(pr)}
        discussion = _discussion_move(earlier["evidence_inputs"]["forge"], live["forge"], args.repo, args.number,
                                      writes(args.repo)) if live["forge"] else (["discussion time unreadable"], [])
        # A moved head is judged by the base-merge check; an unmoved head with a moved base, by freshness.py.
        base = _base_move(earlier, live, args.repo, args.number) if result["head"] == earlier["head"] else ([], [])
        carried = carry(earlier, result, live, policy=resolve(".", bundle.get("review_config"))["revision"],
                        discussion=discussion, base=base, read=args.read)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        print(f"not carried: {error}", file=sys.stderr)
        return 1
    # Replace this PR's entry in the round's file in place, as `ledger.py decide` does; other PRs' entries stay.
    bundle["assessments"] = [carried if a.get("number") == args.number else a for a in bundle["assessments"]]
    args.carry.write_text(json.dumps(bundle, indent=2))
    print(f'#{args.number} carried from {carried["carried"]["from_head"][:9]} to {carried["head"][:9]} in {args.carry}: '
          + (carried["carried"]["reason"] or "nothing moved"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
