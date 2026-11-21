"""Which PRs in a round have to be judged against each other, not only on their own.

A PR can be correct and still be the wrong thing to merge: a newer PR replaces
it, another does the same work, or the base already landed it. `pairs` finds
the scoped PRs that share changed files or name each other; `ledger.py end`
refuses to close a round until each pair carries a relation on an assessment.
`base_overlap` names files the base changed since a PR branched, as leads for
supersession by a merged PR and for silent reverts.
"""
import json
import re
from pathlib import Path

# Files nearly every PR touches. Sharing one says nothing about the change.
IGNORED = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb", "Cargo.lock",
           "poetry.lock", "uv.lock", "go.sum", "Gemfile.lock", "composer.lock", "CHANGELOG.md")
REFERENCE = re.compile(r"(?<![\w/&])#(\d+)\b")
CLAIM = re.compile(r"\b(supersed\w*|replac\w*|in favou?r of|instead of|duplicate of|redo of|alternative to)\W+#(\d+)",
                   re.I)
PR_IN_COMMIT = re.compile(r"\(#(\d+)\)\s*$|^Merge pull request #(\d+)")


def _files(pr):
    return {path for path in pr.get("paths", []) if path.rsplit("/", 1)[-1] not in IGNORED}


def pairs(prs):
    """prs: [{"number", "paths", "text"}] -> one entry per pair that shares files or names the other."""
    by_number = {pr["number"]: pr for pr in prs}
    found = {}
    for pr in prs:
        for other in prs:
            if other["number"] <= pr["number"]:
                continue
            shared = sorted(_files(pr) & _files(other))
            if shared:
                found[(pr["number"], other["number"])] = {"prs": [pr["number"], other["number"]],
                                                          "files": shared, "mentions": []}
    for pr in prs:
        for match in REFERENCE.finditer(pr.get("text") or ""):
            other = int(match.group(1))
            if other == pr["number"] or other not in by_number:
                continue
            key = tuple(sorted((pr["number"], other)))
            entry = found.setdefault(key, {"prs": list(key), "files": [], "mentions": []})
            if f"#{pr['number']} names #{other}" not in entry["mentions"]:
                entry["mentions"].append(f"#{pr['number']} names #{other}")
    return [found[key] for key in sorted(found)]


def outside_claims(prs):
    """Supersession wording that points at a number outside the round: a closed or merged PR, or an issue."""
    scoped = {pr["number"] for pr in prs}
    return [(pr["number"], match.group(0)) for pr in prs
            for match in CLAIM.finditer(pr.get("text") or "") if int(match.group(2)) not in scoped]


def base_overlap(paths, compare):
    """compare: {"files": [...], "commits": [headline, ...], "truncated": bool} for merge-base...base."""
    changed = sorted(_files({"paths": paths}) & set(compare.get("files") or []))
    numbers = []
    for headline in compare.get("commits") or []:
        match = PR_IN_COMMIT.search(headline)
        if match:
            numbers.append(int(match.group(1) or match.group(2)))
    return {"files": changed, "prs": sorted(set(numbers)), "truncated": bool(compare.get("truncated"))}


def describe(entry):
    shown = ", ".join(entry["files"][:3]) + (f" (+{len(entry['files']) - 3})" if len(entry["files"]) > 3 else "")
    parts = ([f"shared: {shown}"] if entry["files"] else []) + entry["mentions"]
    return f'#{entry["prs"][0]} + #{entry["prs"][1]}  ' + " · ".join(parts)


def related_path(scope):
    """The pairs file that sits beside a round's scope file."""
    scope = Path(scope)
    return scope.with_name(scope.stem + ".related.json")


def save(scope, found):
    """Union with pairs already saved, so pairs a JOINED PR brings are kept with the original ones."""
    path = related_path(scope)
    try:
        known = {tuple(e["prs"]): e for e in json.loads(path.read_text())}
    except (OSError, ValueError, KeyError, TypeError):
        known = {}
    known.update({tuple(e["prs"]): e for e in found})
    path.write_text(json.dumps([known[key] for key in sorted(known)], indent=1) + "\n")
    return path
