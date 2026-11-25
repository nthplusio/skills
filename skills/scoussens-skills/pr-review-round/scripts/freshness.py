#!/usr/bin/env python3
"""freshness.py -- whether a saved assessment still holds for the live PR.

Every guard asks the same question, so one classifier answers it:

    Fresh   nothing the assessment depends on moved.
    Benign  only the base or the discussion moved, and neither can change the
            verdict: the base changed no file this PR changes and GitHub still
            reports the PR mergeable; new discussion is bot comments, automated
            status events, or writes this round recorded in the ledger.
    Stale   the head or review policy changed, the base change overlaps this PR
            or conflicts, a person or a bot asking for changes spoke, or any of
            that could not be read.

Guards proceed on Fresh or Benign, record a Benign verdict's reasons, and hold
on Stale. The reviewed head always comes from the assessment, never from live
state.
"""
from dataclasses import dataclass
from datetime import datetime
import json
import re
import subprocess

SHA = re.compile(r"[0-9a-f]{40}")
# Timeline events that record state changes, not discussion a verdict depends on.
# Review requests are reconciled by the handoff ledger, not here.
AUTOMATED = frozenset({
    "labeled", "unlabeled", "assigned", "unassigned", "milestoned", "demilestoned",
    "subscribed", "unsubscribed", "mentioned", "referenced", "cross-referenced",
    "review_requested", "review_request_removed",
    "added_to_merge_queue", "removed_from_merge_queue", "auto_merge_enabled", "auto_merge_disabled",
    "auto_squash_enabled", "auto_rebase_enabled", "deployed", "deployment_environment_changed",
})
PR_FILE_LIMIT = 3000  # GitHub lists at most 3000 files for a pull request
COMPARE_FILE_LIMIT = 300  # and at most 300 for a comparison


@dataclass(frozen=True)
class Fresh:
    def record(self):
        return {"verdict": "fresh", "reasons": []}


@dataclass(frozen=True)
class Benign:
    target: dict
    base: str
    reasons: tuple

    def record(self):
        return {"verdict": "benign", "target": self.target, "base": self.base, "reasons": list(self.reasons)}


@dataclass(frozen=True)
class Stale:
    reasons: tuple

    def record(self):
        return {"verdict": "stale", "reasons": list(self.reasons)}

    def message(self):
        return "assessment no longer holds: " + "; ".join(self.reasons) + "; review again before writing"


def live_from_rest(pr, target):
    """Live inputs from a REST pull request and an independently read target ref."""
    mergeable = pr.get("mergeable")
    return {"head": pr["head"]["sha"], "base": pr["base"]["sha"], "forge": pr["updated_at"], "target": target,
            "conflicting": None if mergeable is None else (mergeable is False or pr.get("mergeable_state") == "dirty")}


def live_from_view(state):
    """Live inputs from `gh pr view` fields plus the target `land.state_of` reads."""
    mergeable, merge_state = state.get("mergeable"), state.get("mergeStateStatus")
    conflicting = (True if mergeable == "CONFLICTING" or merge_state in ("DIRTY", "CONFLICTING")
                   else False if mergeable == "MERGEABLE" else None)
    return {"head": state.get("headRefOid"), "base": state.get("baseRefOid"), "forge": state.get("updatedAt"),
            "target": state.get("target"), "conflicting": conflicting}


def classify(assessment, live, *, policy, repo, number, writes):
    """Fresh, Benign or Stale for a validated assessment against live inputs.

    `writes` are the ledger's accepted writes; the round's own posts are not new discussion.
    """
    if assessment["head"] != live["head"]:
        return Stale(("head changed",))
    if assessment["evidence_inputs"]["policy"] != policy:
        return Stale(("review policy changed; resolve configuration and review affected checks again",))
    stale, benign = [], []
    for found_stale, found_benign in (_base_move(assessment, live, repo, number),
                                      _discussion_move(assessment["evidence_inputs"]["forge"], live["forge"],
                                                       repo, number, writes)):
        stale += found_stale
        benign += found_benign
    if stale:
        return Stale(tuple(stale))
    if benign:
        return Benign(live["target"], live["base"], tuple(benign))
    return Fresh()


def _base_move(assessment, live, repo, number):
    saved, target = assessment["evidence_inputs"].get("target") or {}, live.get("target") or {}
    if not SHA.fullmatch(target.get("sha") or ""):
        return ["actual target ref unavailable"], []
    if not SHA.fullmatch(saved.get("sha") or "") or saved.get("ref") != target.get("ref"):
        return [f'assessment records no target SHA for {target.get("ref")}'], []
    moves = {(old, new) for old, new in ((saved["sha"], target["sha"]), (assessment["base"], live.get("base")))
             if old != new}
    if not moves:
        return [], []
    if live.get("conflicting") is not False:
        return ["GitHub reports the PR conflicting" if live.get("conflicting")
                else "base moved and GitHub has not reported the PR mergeable"], []
    changed = _pr_files(repo, number)
    if changed is None:
        return ["base moved and the PR's files are unreadable or truncated"], []
    touched = set()
    for old, new in sorted(moves):
        files = _base_files(repo, old, new)
        if files is None:
            return [f"base change {old[:9]}..{new[:9]} is unreadable, truncated or rewritten"], []
        touched |= files
    overlap = sorted(touched & changed)
    if overlap:
        return ["base changed files this PR changes: " + ", ".join(overlap[:5])
                + (f" and {len(overlap) - 5} more" if len(overlap) > 5 else "")], []
    return [], [f'{target["ref"]} moved {saved["sha"][:9]}..{target["sha"][:9]}: {len(touched)} file(s), '
                "none changed by this PR, and GitHub reports it mergeable"]


def _discussion_move(saved, live, repo, number, writes):
    if saved == live:
        return [], []
    since = _time(saved)
    if since is None:
        return ["saved discussion time unreadable"], []
    rows = _api(f"repos/{repo}/issues/{number}/timeline?per_page=100", paginate=True)
    if rows is None:
        return ["discussion moved and the timeline is unreadable"], []
    ours = {w["url"] for w in writes if w.get("number") == number and w.get("url")}
    dismissed = {m[1] for w in writes if w.get("number") == number and w.get("action") == "dismiss"
                 for m in [re.search(r"pullrequestreview-(\d+)$", w.get("url") or "")] if m}
    stale, benign = [], []
    for event in rows:
        kind = event.get("event") or "unknown"
        if kind == "committed":
            continue  # a commit moves the head, which is checked first
        at = _time(event.get("submitted_at") or event.get("created_at"))
        if at is None:
            stale.append(f"{kind} event without a time")
            continue
        if at <= since:
            continue
        who = event.get("user") or event.get("actor") or {}
        login = who.get("login") or "unknown"
        bot = who.get("type") == "Bot" or login.endswith("[bot]")
        state = (event.get("state") or "").upper()
        if event.get("html_url") in ours or str((event.get("dismissed_review") or {}).get("review_id")) in dismissed:
            benign.append(f"this round's {kind}")
        elif bot and (kind == "commented" or (kind == "reviewed" and state == "COMMENTED")):
            benign.append(f"{kind} by {login}")
        elif kind in AUTOMATED:
            benign.append(kind)
        else:
            stale.append(f"{kind} by {login}" + (f" ({state})" if state else "") + " since the assessment")
    return stale, ["discussion moved only by " + ", ".join(sorted(set(benign)))] if benign else []


def _pr_files(repo, number):
    rows = _api(f"repos/{repo}/pulls/{number}/files?per_page=100", paginate=True)
    if rows is None or len(rows) >= PR_FILE_LIMIT:
        return None
    return _names(rows)


def _base_files(repo, old, new):
    """Files the base changed from old to new; None unless new is old plus commits and the list is complete."""
    data = _api(f"repos/{repo}/compare/{old}...{new}")
    if not isinstance(data, dict) or data.get("status") not in ("ahead", "identical"):
        return None
    files = data.get("files")
    if not isinstance(files, list) or len(files) >= COMPARE_FILE_LIMIT:
        return None
    return frozenset(_names(files))


def _names(rows):
    return {name for row in rows for name in (row.get("filename"), row.get("previous_filename")) if name}


def _time(value):
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return moment if moment.tzinfo else None


def _api(path, paginate=False):
    """One `gh api` read; None when it fails or returns an unexpected shape."""
    try:
        result = subprocess.run(["gh", "api", path, *(["--paginate", "--slurp"] if paginate else [])],
                                capture_output=True, text=True)
        data = json.loads(result.stdout)
    except (OSError, ValueError):
        return None
    if result.returncode:
        return None
    if not paginate:
        return data
    if not isinstance(data, list) or not data or any(not isinstance(page, list) for page in data):
        return None
    return [row for page in data for row in page if isinstance(row, dict)]
