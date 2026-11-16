#!/usr/bin/env python3
"""GitHub-native stacked PRs (`gh stack`): read stack membership and order.

stacks.py <pr-number> [--repo OWNER/REPO]   # print one PR's stack as JSON

A stack is an ordered chain of PRs. Only the bottom PR targets the stack's base
branch; each higher PR targets the branch below it until that PR merges and
GitHub retargets it. So `gh pr list --base <base>` misses upper layers, a
child's diff is against its parent branch, GitHub refuses per-PR auto-merge for
any stack member, and `gh stack merge <pr>` lands that PR plus every unmerged
PR below it. Read-only: this module never changes a stack.
"""
import argparse
import json
import subprocess

QUERY = ("query($owner: String!, $name: String!, $number: Int!) { repository(owner: $owner, name: $name) {"
         " pullRequest(number: $number) { stackEntry { position stack { number size baseRefName"
         " entries(first: 50) { totalCount nodes { position pullRequest {"
         " number state isDraft baseRefName headRefName headRefOid } } } } } } } }")
UNKNOWN = {"status": "unknown"}


def stack_of(repo, number):
    """None when not stacked; {"status": "unknown"} when membership could not be read."""
    if not repo or "/" not in repo or not number:
        return dict(UNKNOWN)
    owner, name = repo.split("/", 1)
    result = subprocess.run(["gh", "api", "graphql", "-f", f"query={QUERY}", "-f", f"owner={owner}",
                             "-f", f"name={name}", "-F", f"number={number}"], capture_output=True, text=True)
    try:
        data = json.loads(result.stdout)
    except ValueError:
        return dict(UNKNOWN)
    errors = data.get("errors") or []
    # A forge without the stack schema cannot have stacked PRs.
    if errors and all((e.get("extensions") or {}).get("code") == "undefinedField"
                      and (e.get("extensions") or {}).get("fieldName") == "stackEntry" for e in errors):
        return None
    try:
        if result.returncode or errors:
            return dict(UNKNOWN)
        entry = data["data"]["repository"]["pullRequest"]["stackEntry"]
        if entry is None:
            return None
        stack, connection = entry["stack"], entry["stack"]["entries"]
        entries = sorted(({"position": n["position"], "number": n["pullRequest"]["number"],
                           "state": n["pullRequest"]["state"], "isDraft": n["pullRequest"]["isDraft"],
                           "base": n["pullRequest"]["baseRefName"], "head": n["pullRequest"]["headRefName"],
                           "headOid": n["pullRequest"]["headRefOid"]}
                          for n in connection["nodes"]), key=lambda e: e["position"])
        if connection["totalCount"] != len(entries) or number not in [e["number"] for e in entries]:
            return dict(UNKNOWN)
        return {"status": "stacked", "number": stack["number"], "base": stack["baseRefName"],
                "size": stack["size"], "position": entry["position"], "entries": entries}
    except (KeyError, TypeError):
        return dict(UNKNOWN)


def below(stack, number):
    """Unmerged PRs a `gh stack merge <number>` would also land, bottom first."""
    position = next(e["position"] for e in stack["entries"] if e["number"] == number)
    return [e for e in stack["entries"] if e["position"] < position and e["state"] != "MERGED"]


def label(stack, number):
    """One readable line, such as 'Stack #7 · 2 of 3 · on #41 (open) · under #43'."""
    if not stack:
        return ""
    if stack.get("status") != "stacked":
        return "Stack membership unknown"
    entries = stack["entries"]
    index = next(i for i, e in enumerate(entries) if e["number"] == number)
    parts = [f'Stack #{stack["number"]} · {stack["position"]} of {stack["size"]} on {stack["base"]}']
    lower = below(stack, number)
    if lower:
        parts.append("lands with " + ", ".join(f'#{e["number"]}' for e in lower) + " below")
    if index + 1 < len(entries):
        parts.append("under " + ", ".join(f'#{e["number"]}' for e in entries[index + 1:]))
    return " · ".join(parts)


def missing_members(stacks, listed, base):
    """Open non-draft stack members rooted on base but absent from a `--base` listing."""
    found = {}
    for stack in stacks:
        if (stack or {}).get("status") != "stacked" or stack["base"] != base:
            continue
        for entry in stack["entries"]:
            if entry["state"] == "OPEN" and not entry["isDraft"] and entry["number"] not in listed:
                found[entry["number"]] = stack["number"]
    return found


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("number", type=int)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    print(json.dumps(stack_of(args.repo, args.number), indent=2))
