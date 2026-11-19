#!/usr/bin/env python3
"""Read the review rules GitHub applies to a branch, and who pushed last. Read-only.

branch_rules.py OWNER/REPO BRANCH

An approval clears the review gate only when the branch's rules are satisfied:
a code owner may have to approve, and the last push may need approval from
someone other than the person who pushed it. Without reading the rules, an
approval that leaves the PR REVIEW_REQUIRED looks like a PR nobody reviewed.

Only rulesets are readable without admin rights. Classic branch protection is
not, so an empty answer here is not proof that no review rule applies.
"""
import json
import subprocess
import sys
from urllib.parse import quote

KNOWN = {
    "require_code_owner_review": "a code owner must approve",
    "require_last_push_approval": "the last push must be approved by someone other than its pusher",
    "dismiss_stale_reviews_on_push": "a push dismisses earlier approvals",
    "required_review_thread_resolution": "review threads must be resolved",
}


def _read(path):
    result = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if result.returncode:
        return None
    try:
        return json.loads(result.stdout)
    except ValueError:
        return None


def review_rules(repo, branch):
    """Pull-request rule parameters merged across the rulesets on a branch; None when unreadable."""
    if not repo or not branch:
        return None
    rules = _read(f"repos/{repo}/rules/branches/{quote(branch, safe='')}?per_page=100")
    if not isinstance(rules, list) or len(rules) >= 100:
        return None
    merged = {}
    try:
        for rule in rules:
            if rule.get("type") != "pull_request":
                continue
            for key, value in (rule.get("parameters") or {}).items():
                if type(value) is bool:
                    merged[key] = merged.get(key, False) or value
                elif key == "required_approving_review_count" and type(value) is int:
                    merged[key] = max(merged.get(key, 0), value)
    except AttributeError:
        return None
    return merged


def describe(rules):
    """Readable lines for the rules that are switched on; an unknown flag keeps its API name."""
    if rules is None:
        return ["review rules unreadable"]
    lines = [f'{rules["required_approving_review_count"]} approval(s) required'] if rules.get("required_approving_review_count") else []
    lines += [KNOWN.get(key, key) for key, value in sorted(rules.items()) if value is True]
    return lines or ["no ruleset review rule found (classic branch protection is not readable here)"]


def last_pusher(repo, branch):
    """Login behind the most recent update of a branch; None when unreadable."""
    if not repo or not branch:
        return None
    activity = _read(f"repos/{repo}/activity?ref=refs/heads/{quote(branch, safe='/')}&per_page=1")
    try:
        return activity[0]["actor"]["login"]
    except (TypeError, KeyError, IndexError):
        return None


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    for line in describe(review_rules(sys.argv[1], sys.argv[2])):
        print(line)
