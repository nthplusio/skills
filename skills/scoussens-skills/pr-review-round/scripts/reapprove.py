#!/usr/bin/env python3
"""reapprove.py <n> --repo <owner/repo> [--carry <assessments.json>] -- read-only.

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

With `--carry`, it also prints an assessments bundle whose one assessment for this
PR is the earlier assessment at A carried to H: the new head, base, target, discussion
time and policy revision are read live, the original `assessed_at` and decisions are
kept, and `carried` plus `provenance` name the tree check and both heads. It refuses an
assessment with unresolved decisions, a changed review policy, or discussion since A
that freshness.py would not call benign. Post the re-approval with
`review_write.py reapprove`, which runs every approval guard on the carried record.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

from freshness import SHA, _api, _discussion_move
from ledger import target_state, unresolved, validate_assessment, writes
from review_config import resolve

APPROVALS = ("approve", "reapprove")
MAX_STEPS = 500


def git(*args):
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def have(sha):
    return git("cat-file", "-e", f"{sha}^{{commit}}") is not None


def base_only(approved, head, base_tip):
    """{"base_only", "reason", "steps"} for the local commits approved..head against base_tip.

    Each step is one commit on head's first-parent chain, newest first, with its second
    parent, the tree `git merge-tree --write-tree` produced (None on conflict) and its own tree.
    """
    steps = []
    verdict = lambda ok, reason: {"base_only": ok, "reason": reason, "steps": steps}
    for name, sha in (("approved head", approved), ("live head", head), ("base tip", base_tip)):
        if not have(sha):
            return verdict(False, f"{name} {sha[:9]} is not available locally")
    if approved == head:
        return verdict(False, "the head has not moved since the approval")
    if subprocess.run(["git", "merge-base", "--is-ancestor", approved, head], capture_output=True).returncode:
        return verdict(False, f"approved head {approved[:9]} is not in the live head's history (rebase or force-push)")
    commit = head
    while commit != approved:
        if len(steps) >= MAX_STEPS:
            return verdict(False, f"more than {MAX_STEPS} commits since the approval")
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
    return verdict(True, f"{len(steps)} clean base merge(s) since the approval")


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


def check(repo, number):
    """Read the PR and the ledger, fetch what git needs, and decide."""
    pr = _api(f"repos/{repo}/pulls/{number}")
    if not isinstance(pr, dict) or not SHA.fullmatch(((pr.get("head") or {}).get("sha")) or ""):
        return {"base_only": False, "reason": "the PR is unreadable", "approved": None, "head": None, "steps": []}, None
    head, ref = pr["head"]["sha"], pr["base"]["ref"]
    approved = approved_head(repo, number)
    target = target_state(repo, ref)
    result = {"approved": approved, "head": head, "base": pr["base"]["sha"], "target": target, "steps": []}
    if not approved:
        return {**result, "base_only": False, "reason": "the ledger records no approval of this PR by the round"}, pr
    if not target["sha"]:
        return {**result, "base_only": False, "reason": f"the {ref} tip is unreadable"}, pr
    subprocess.run(["git", "fetch", "-q", "origin", ref], capture_output=True)
    subprocess.run(["git", "fetch", "-q", "origin", f"pull/{number}/head"], capture_output=True)
    for sha in (approved, target["sha"]):
        if not have(sha):  # GitHub serves a dropped commit by SHA for a while
            subprocess.run(["git", "fetch", "-q", "origin", sha], capture_output=True)
    result.update(base_only(approved, head, target["sha"]))
    if result["base_only"] and mergeable(pr) is not True:
        result.update(base_only=False, reason="GitHub reports the PR conflicting" if mergeable(pr) is False
                      else "GitHub has not reported the PR mergeable yet")
    return result, pr


def carry(earlier, result, live, *, policy, discussion, at=None):
    """The earlier assessment at A carried to the base-only head H; raises when it cannot be carried."""
    validate_assessment(earlier)
    if not result["base_only"]:
        raise ValueError(f'not base-only: {result["reason"]}; review the new head')
    if earlier["head"] != result["approved"]:
        raise ValueError(f'the assessment is at {earlier["head"][:9]}, not the approved head {result["approved"][:9]}')
    blockers = unresolved(earlier)
    if blockers:
        raise ValueError("the assessment has unresolved decisions: "
                         + "; ".join(f'{d["owner"]}: {d["unblock"]}' for d in blockers))
    if earlier["evidence_inputs"]["policy"] != policy:
        raise ValueError("the review policy changed since the approval; review the new head")
    stale, benign = discussion
    if stale:
        raise ValueError("discussion since the approval needs a review: " + "; ".join(stale))
    a, h = result["approved"], result["head"]
    record = {"from_head": a, "head": h, "check": "git merge-tree --write-tree",
              "commits": [s["commit"] for s in result["steps"]],
              "at": at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    provenance = (f"Carried from the approved head {a} to {h}: {len(record['commits'])} base merge(s), each tree equal "
                  "to `git merge-tree --write-tree` of its parents. Code checks were not rerun; issue evidence is "
                  "carried from the approved assessment." + (" " + "; ".join(benign) if benign else ""))
    return {**earlier, "head": h, "base": live["base"], "carried": record, "provenance": provenance,
            "evidence_inputs": {**earlier["evidence_inputs"], "forge": live["forge"], "policy": policy,
                                "target": live["target"]}}


def describe(result):
    lines = [f'base-only: {"yes" if result["base_only"] else "no"} -- {result["reason"]}',
             f'approved head (A): {result.get("approved") or "none"}', f'live head (H):     {result.get("head") or "unknown"}']
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
    parser.add_argument("--carry", type=Path, help="assessments bundle holding the assessment at the approved head")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo) or args.number <= 0:
        parser.error("use OWNER/REPO and a positive PR number")
    result, pr = check(args.repo, args.number)
    print("\n".join(describe(result)), file=sys.stderr if args.carry else sys.stdout)
    if not args.carry:
        return 0 if result["base_only"] else 1
    try:
        bundle = json.loads(args.carry.read_text())
        if bundle.get("repository") != args.repo:
            raise ValueError("the assessments belong to a different repository")
        matches = [a for a in bundle.get("assessments", []) if a.get("number") == args.number]
        if len(matches) != 1:
            raise ValueError("one assessment of this PR required")
        live = {"base": result.get("base"), "forge": (pr or {}).get("updated_at"), "target": result.get("target")}
        discussion = _discussion_move(matches[0]["evidence_inputs"]["forge"], live["forge"], args.repo, args.number,
                                      writes(args.repo)) if live["forge"] else (["discussion time unreadable"], [])
        carried = carry(matches[0], result, live, policy=resolve(".", bundle.get("review_config"))["revision"],
                        discussion=discussion)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        print(f"not carried: {error}", file=sys.stderr)
        return 1
    print(json.dumps({**{k: v for k, v in bundle.items() if k != "assessments"}, "assessments": [carried]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
