#!/usr/bin/env python3
"""approvers.py <pr-number> --repo OWNER/REPO -- who can approve a PR. Read-only.

Reads the CODEOWNERS file GitHub uses at the base ref (.github/CODEOWNERS, then
CODEOWNERS, then docs/CODEOWNERS) for the PR's changed files, and the base's
review rules. Prints the code owners who can approve, leaving out the PR's
author and, when the base requires the last push to be approved by someone
else, its last pusher. A team stays listed: its other members can approve.

An input it cannot read prints as unknown, never as an empty list, and the
command exits 1. Without a CODEOWNERS file, any collaborator with write access
can approve, and it says so.
"""
import argparse
import base64
import json
import re
import subprocess
from urllib.parse import quote

from branch_rules import describe, last_pusher, review_rules

LOCATIONS = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")


def _get(path, paginate=False):
    """(data, None) on success, (None, "missing") on a 404, (None, reason) otherwise."""
    result = subprocess.run(["gh", "api", path, *(["--paginate", "--slurp"] if paginate else [])],
                            capture_output=True, text=True)
    if result.returncode:
        return None, "missing" if "HTTP 404" in result.stderr else (result.stderr.strip() or "read failed")
    try:
        return json.loads(result.stdout), None
    except ValueError:
        return None, "unreadable response"


def pattern(text):
    """A CODEOWNERS pattern as a regex over repository paths, with gitignore's rules as GitHub applies them."""
    anchored = "/" in text.rstrip("/")
    body = text.strip("/")
    regex, i = "", 0
    while i < len(body):
        if body.startswith("**/", i):
            regex, i = regex + "(?:.*/)?", i + 3
        elif body.startswith("**", i):
            regex, i = regex + ".*", i + 2
        elif body[i] == "*":
            regex, i = regex + "[^/]*", i + 1
        elif body[i] == "?":
            regex, i = regex + "[^/]", i + 1
        else:
            regex, i = regex + re.escape(body[i]), i + 1
    # A pattern owns what it names and everything under it, except `dir/*`, which owns only direct children.
    below = "" if body.endswith("*") and not body.endswith("**") else "(?:/.*)?"
    if text.endswith("/"):
        below = "/.*"
    return re.compile(("" if anchored else "(?:.*/)?") + regex + below + r"\Z")


def parse(text):
    """[(regex, owners)] in file order; the last matching line wins."""
    rules = []
    for line in text.splitlines():
        tokens = line.split()
        if not tokens or tokens[0].startswith("#"):
            continue
        owners = []
        for token in tokens[1:]:
            if token.startswith("#"):
                break
            owners.append(token)
        rules.append((pattern(tokens[0]), owners))
    return rules


def owners_of(rules, path):
    matched = [owners for regex, owners in rules if regex.match(path)]
    return matched[-1] if matched else []


def codeowners(repo, ref):
    """(location, rules) for the file GitHub uses at ref; (None, []) when there is none. Raises when unreadable."""
    for location in LOCATIONS:
        data, error = _get(f"repos/{repo}/contents/{location}?ref={quote(ref, safe='')}")
        if error == "missing":
            continue
        if error:
            raise ValueError(f"CODEOWNERS unreadable at {location}: {error}")
        try:
            return location, parse(base64.b64decode(data["content"]).decode())
        except (KeyError, TypeError, ValueError) as reason:
            raise ValueError(f"CODEOWNERS unreadable at {location}: {reason}")
    return None, []


def approvers(repo, number):
    """Who can approve PR `number`. `owners` maps each eligible owner to the files it owns; None when unknown."""
    result = {"author": None, "base": None, "rules": None, "last_pusher": None, "left_out": {},
              "codeowners": None, "owners": None, "unowned": [], "unknown": []}
    pr, error = _get(f"repos/{repo}/pulls/{number}")
    if error:
        result["unknown"].append(f"PR unreadable: {error}")
        return result
    result["author"], result["base"] = pr["user"]["login"], pr["base"]["ref"]
    result["left_out"][result["author"].lower()] = "author"
    rules = result["rules"] = review_rules(repo, result["base"])
    if rules is None or rules.get("require_last_push_approval"):
        pusher = result["last_pusher"] = last_pusher((pr["head"].get("repo") or {}).get("full_name"), pr["head"]["ref"])
        why = (f'{result["base"]} requires approval of the last push by someone else' if rules is not None
               else "review rules unreadable, so the last-push rule may apply")
        if pusher:
            result["left_out"].setdefault(pusher.lower(), f"last pusher; {why}")
        else:
            result["unknown"].append(f"last pusher unreadable; {why}")
    pages, error = _get(f"repos/{repo}/pulls/{number}/files?per_page=100", paginate=True)
    if error or not isinstance(pages, list):
        result["unknown"].append(f"changed files unreadable: {error}")
        return result
    files = [f["filename"] for page in pages for f in page]
    try:
        result["codeowners"], owner_rules = codeowners(repo, result["base"])
    except ValueError as reason:
        result["unknown"].append(str(reason))
        return result
    owners = {}
    for path in files:
        named = owners_of(owner_rules, path)
        if not named:
            result["unowned"].append(path)
        for owner in named:
            if owner.lstrip("@").lower() not in result["left_out"]:
                owners.setdefault(owner, []).append(path)
    result["owners"] = owners
    return result


def lines(result, number):
    out = [f'#{number} by {result["author"] or "unknown"} into {result["base"] or "unknown"}']
    if result["base"]:
        out.append(f'review rules on {result["base"]}: ' + "; ".join(describe(result["rules"])))
    out += [f"left out @{login}: {why}" for login, why in result["left_out"].items()]
    if result["owners"] is None:
        out.append("approvers: unknown (" + "; ".join(result["unknown"]) + ")")
        return out
    out += [f"unknown: {reason}" for reason in result["unknown"]]
    if not result["codeowners"]:
        out.append(f'approvers: no CODEOWNERS file at {result["base"]}; any other collaborator with write access')
        return out
    out.append(f'CODEOWNERS: {result["codeowners"]} at {result["base"]}')
    if result["owners"]:
        out.append("approvers:")
        out += [f'  {owner}  owns {", ".join(paths)}' for owner, paths in result["owners"].items()]
    else:
        out.append("approvers: none of the changed files' code owners is eligible")
    if result["unowned"]:
        out.append("files without a code owner: " + ", ".join(result["unowned"]))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("number", type=int)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    result = approvers(args.repo, args.number)
    print("\n".join(lines(result, args.number)))
    return 1 if result["unknown"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
