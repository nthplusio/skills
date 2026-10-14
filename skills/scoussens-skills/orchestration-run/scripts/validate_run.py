#!/usr/bin/env python3
"""Check an orchestration run's status.json against the run lifecycle and proof rules in
references/dashboard-data.md; never renders, invokes owners or runs checks.

  validate_run.py <status.json>    prints every finding and exits 1 when any rule fails
  validate_run.py --skill-version  prints this skill's version and exits

The dashboard skill's renderer checks the record's shape. This script checks what the values
mean for a coordinated run: proof behind verified stages and delivered work, settled scope before
resolution or closure, publication scope, approval expiry, runtime release, idle scans, history
length and closed-run cleanliness. Run it before rendering.
"""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re


SKILL_DIR = Path(__file__).resolve().parent.parent
# Business stage keys from the dashboard skill's status contract (assets/stages.json), read from a
# sibling skill in the pack or in a skills repository; the literal list is the fallback when the
# dashboard skill is not installed beside this one.
STAGE_FALLBACK = ("defined", "researched", "pr_readiness", "code_publication", "review", "verification",
                  "deployment", "business_acceptance")


def stage_keys():
    """Stage keys from the dashboard skill installed beside this one, in a pack or a flat skills
    directory alike. A missing or malformed file falls back to the literal so a broken sibling never
    stops this script."""
    contract = SKILL_DIR.parent / "dashboard" / "assets" / "stages.json"
    try:
        return tuple(item["key"] for item in json.loads(contract.read_text()))
    except (OSError, ValueError, KeyError, TypeError):
        return STAGE_FALLBACK


STAGES = stage_keys()
RESOLVED = ("delivered", "no_change_needed", "cancelled", "deferred")
WORK_STATES = ("needs_decision", "blocked", "waiting", "unknown", "working", "ready", "awaiting_acceptance") + RESOLVED
WAITING_ON_PEOPLE = ("needs_decision", "waiting", "awaiting_acceptance")
OPEN_OWNER_STATES = ("active", "waiting", "blocked", "unreachable")
FINISHED_OWNER_STATES = ("complete", "closed")
PUBLICATION_SCOPES = ("none", "draft", "ready", "merge")
APPROVAL_STATES = ("active", "consumed", "expired", "revoked")
CODE_KINDS = ("pushed_branch", "bundle", "patch")
HISTORY_LIMIT = 800


def skill_version():
    """Digest of the files a coordinator follows: instructions, references and scripts."""
    digest = hashlib.sha256()
    for path in sorted(SKILL_DIR.rglob("*")):
        relative = path.relative_to(SKILL_DIR)
        if path.is_file() and relative.parts[0] != "evals" and "__pycache__" not in relative.parts:
            digest.update(str(relative).encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()[:12]


def moment(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} needs an ISO 8601 timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} needs a timezone")
    return parsed


def nonempty(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be nonempty text")


def indexed(records):
    result = {}
    for record in records:
        key = record["id"]
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", key):
            raise ValueError("IDs must start with a letter/number and contain only letters, numbers, _ or -")
        if key in result:
            raise ValueError(f"duplicate ID: {key}")
        result[key] = record
    return result


def work_status(task):
    """The row's work status, or the display fallback the renderer uses for records without one."""
    if "work" in task:
        return task["work"]
    state = {"active": "working", "waiting": "waiting", "blocked": "blocked"}.get(task["owner"]["state"], "unknown")
    return {"state": state, "reason": "inferred from owner activity"}


def accepted(evidence, proof_ids):
    return bool(proof_ids) and all(
        proof_id in evidence and evidence[proof_id]["assessment"] == "accepted"
        and evidence[proof_id]["result"] not in ("failed", "interrupted") for proof_id in proof_ids)


def check_task_proof(task, evidence, decisions):
    """One row's proof and scope rules: verified stages and delivered work cite accepted proof, resolved
    and finished rows have nothing left open, and attention states name what holds them."""
    key, owner = task["id"], task["owner"]
    phases = task.get("milestones") or {}
    if owner["state"] == "blocked" and not task.get("blocker", "").strip():
        raise ValueError(f"{key}: blocked owner needs an actionable blocker")
    for stage, phase in phases.items():
        for proof_id in phase["evidence"]:
            if proof_id not in evidence:
                raise ValueError(f"{key}: missing proof {proof_id}")
        if phase["state"] == "verified" and not accepted(evidence, phase["evidence"]):
            raise ValueError(f"{key}: verified stage needs accepted supporting proof")
    unfinished = any(phase["state"] in ("pending", "blocked") for phase in phases.values())
    if owner["state"] in FINISHED_OWNER_STATES:
        if task.get("obligations") or task.get("blocker") or not owner.get("handoff", "").strip():
            raise ValueError(f"{key}: completed owner needs a handoff and settled obligations")
        if unfinished:
            raise ValueError(f"{key}: unfinished stage prevents owner completion")
    work = work_status(task)
    if work.get("state") not in WORK_STATES:
        raise ValueError(f"{key}: invalid work state")
    if not isinstance(work.get("reason"), str) or not work["reason"].strip():
        raise ValueError(f"{key}: work needs a reason")
    proof_ids = work.get("evidence", [])
    if work["state"] in RESOLVED:
        if task.get("obligations") or task.get("blocker"):
            raise ValueError(f"{key}: resolved work needs settled obligations and no blocker")
        if unfinished:
            raise ValueError(f"{key}: unfinished stage prevents work resolution")
    elif "work" in task and work["state"] != "unknown" and owner["state"] in FINISHED_OWNER_STATES:
        raise ValueError(f"{key}: unfinished work prevents owner completion")
    if work["state"] in ("delivered", "no_change_needed") and not accepted(evidence, proof_ids):
        raise ValueError(f"{key}: work outcome needs accepted supporting proof")
    if work["state"] in ("cancelled", "deferred") and (not isinstance(work.get("receipt"), str) or not work["receipt"].strip()):
        raise ValueError(f"{key}: cancellation or deferral needs a decision receipt")
    if work["state"] == "deferred" and (not isinstance(work.get("revisit"), str) or not work["revisit"].strip()):
        raise ValueError(f"{key}: deferred work needs a revisit trigger")
    if work["state"] == "blocked" and not task.get("blocker", "").strip():
        raise ValueError(f"{key}: blocked work needs an actionable blocker")
    if work["state"] == "needs_decision" and not any(key in item.get("task_ids", []) for item in decisions.values()):
        raise ValueError(f"{key}: needs_decision work needs a pending decision naming this task")


def check_run_choices(data):
    choices = data["run_choices"]
    if choices.get("target_stage") not in STAGES:
        raise ValueError("run_choices.target_stage must name a business stage")
    if choices.get("publication_scope") not in PUBLICATION_SCOPES:
        raise ValueError(f"run_choices.publication_scope must be one of {', '.join(PUBLICATION_SCOPES)}")
    nonempty(choices.get("confirmed_from"), "run_choices.confirmed_from")
    limit = choices.get("idle_scan_limit")
    if type(limit) is not int or limit < 1:
        raise ValueError("run_choices.idle_scan_limit must be a positive integer")
    return limit


def check_monitoring(data, tasks, limit):
    monitoring = data["monitoring"]
    unchanged = monitoring.get("unchanged_scans")
    if type(unchanged) is not int or unchanged < 0:
        raise ValueError("monitoring.unchanged_scans must be a nonnegative integer")
    open_work = [task for task in tasks.values() if work_status(task)["state"] not in RESOLVED]
    if (limit is not None and unchanged >= limit and monitoring.get("next_check_at") and open_work
            and all(work_status(task)["state"] in WAITING_ON_PEOPLE for task in open_work)):
        raise ValueError(f"{unchanged} unchanged scans with only people-gated work left: "
                         "stop scheduled checks, set next_check_at to null and record the hold")


def check_skill_version(data):
    nonempty(data.get("skill_version"), "skill_version")


def notes(data):
    """Observations that do not fail the record. A version mismatch is one: the old renderer printed
    it on the page, and a producer that wants it shown copies it into the record's notice."""
    found = []
    if data.get("skill_version") and data["skill_version"] != skill_version():
        found.append(f"this record was written for orchestration-run {data['skill_version']}; the current version is "
                     f"{skill_version()}. Read what changed, migrate the record and save the new version")
    return found


def check_history(data):
    long = [index for index, item in enumerate(data["history"]) if len(item) > HISTORY_LIMIT]
    if long:
        raise ValueError(f"history entries {long} exceed {HISTORY_LIMIT} characters; keep the detail in proof and summarise the change")


def check_follow_ups(follow_ups, tasks):
    for item in follow_ups.values():
        nonempty(item.get("text"), f"{item['id']}.text")
        if item.get("from_task") not in tasks:
            raise ValueError(f"{item['id']}: follow-up needs the assigned task it came from")
        if item.get("owner") is not None:
            nonempty(item["owner"], f"{item['id']}.owner")


def check_approvals(approvals, tasks, updated):
    for item in approvals.values():
        for field in ("scope", "receipt", "side_effects"):
            nonempty(item.get(field), f"{item['id']}.{field}")
        if item.get("state") not in APPROVAL_STATES:
            raise ValueError(f"{item['id']}: invalid approval state")
        if any(key not in tasks for key in item.get("task_ids", [])):
            raise ValueError(f"{item['id']}: approval names an unknown task")
        moment(item.get("granted_at"), f"{item['id']}.granted_at")
        if item.get("expires_at") is not None and item["state"] == "active" \
                and moment(item["expires_at"], f"{item['id']}.expires_at") <= updated:
            raise ValueError(f"{item['id']}: approval expired; mark it expired and ask again before acting")


def check_task_lifecycle(task, scope):
    """Schema 2 rules for one row: runtime settled before finishing, unpublished code kept, publication
    inside the run's scope, and a named sign-off for requested acceptance."""
    key, owner = task["id"], task["owner"]
    finished = owner["state"] in FINISHED_OWNER_STATES or work_status(task)["state"] in RESOLVED
    held = [entry["id"] for entry in task["runtime"] if entry["state"] == "held"]
    if finished and held:
        raise ValueError(f"{key}: release or retain runtime {', '.join(held)} with a reason and date before finishing")
    phases = task["milestones"]
    unpublished = phases["pr_readiness"]["state"] == "verified" and phases["code_publication"]["state"] != "verified"
    if owner["state"] in FINISHED_OWNER_STATES and unpublished:
        code = owner.get("retained_code")
        if not isinstance(code, dict) or code.get("kind") not in CODE_KINDS:
            raise ValueError(f"{key}: unpublished code must be kept outside the owner's workspace "
                             f"({', '.join(CODE_KINDS)}) before the owner finishes")
        nonempty(code.get("ref"), f"{key}.owner.retained_code.ref")
        if code["kind"] != "pushed_branch":
            nonempty(code.get("checksum"), f"{key}.owner.retained_code.checksum")
    if scope == "none" and phases["code_publication"]["state"] in ("pending", "blocked"):
        raise ValueError(f"{key}: code publication is requested but this run's publication scope is none")
    acceptance = phases["business_acceptance"]
    if acceptance["state"] in ("pending", "blocked"):
        nonempty(acceptance.get("accountable"), f"{key}.business_acceptance.accountable")
        nonempty(acceptance.get("revisit"), f"{key}.business_acceptance.revisit")


def check_closed(data, tasks, follow_ups):
    if data.get("closed_at") is None:
        return
    moment(data["closed_at"], "closed_at")
    still_open = [task["id"] for task in tasks.values() if task["owner"]["state"] in OPEN_OWNER_STATES]
    held = [task["id"] for task in tasks.values() if any(entry["state"] == "held" for entry in task["runtime"])]
    unowned = [item["id"] for item in follow_ups.values() if not item.get("owner")]
    problems = ([f"open owner {key}" for key in still_open] + [f"held runtime on {key}" for key in held]
                + [f"unowned follow-up {key}" for key in unowned]
                + (["pending decisions"] if data["decisions"] else [])
                + (["a scheduled check"] if data["monitoring"].get("next_check_at") else []))
    if problems:
        raise ValueError(f"a closed run cannot keep {', '.join(problems)}")


def findings(data):
    """Every rule the record breaks, one line each. Independent rule groups report separately so one
    fix does not hide the next finding."""
    found = []

    def attempt(check, *args):
        try:
            return check(*args)
        except (ValueError, KeyError, TypeError) as error:
            found.append(f"missing field {error}" if isinstance(error, KeyError) else str(error))
            return None

    def required(field):
        nonempty(data.get(field), field)

    attempt(required, "run_id")
    attempt(required, "config_path")
    updated = attempt(moment, data.get("updated_at"), "updated_at")
    try:
        evidence, tasks, decisions = indexed(data["evidence"]), indexed(data["tasks"]), indexed(data["decisions"])
    except (ValueError, KeyError, TypeError) as error:
        found.append(f"missing field {error}" if isinstance(error, KeyError) else str(error))
        return found
    for task in tasks.values():
        attempt(check_task_proof, task, evidence, decisions)
    if data.get("schema_version", 2) < 2:
        return found
    limit = attempt(check_run_choices, data)
    attempt(check_monitoring, data, tasks, limit)
    attempt(check_skill_version, data)
    attempt(check_history, data)
    follow_ups = attempt(lambda: indexed(data.get("follow_ups", []))) or {}
    attempt(check_follow_ups, follow_ups, tasks)
    approvals = attempt(lambda: indexed(data["approvals"])) or {}
    if updated is not None:
        attempt(check_approvals, approvals, tasks, updated)
    scope = data.get("run_choices", {}).get("publication_scope")
    for task in tasks.values():
        attempt(check_task_lifecycle, task, scope)
    attempt(check_closed, data, tasks, follow_ups)
    return found


def validate(data):
    """Raise ValueError listing every finding, one per line. Returns nothing when the record follows the rules."""
    found = findings(data)
    if found:
        raise ValueError("\n".join(found))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("status", type=Path, nargs="?")
    parser.add_argument("--skill-version", action="store_true", help="print this skill's version and exit")
    args = parser.parse_args()
    if args.skill_version:
        print(skill_version())
        return
    if args.status is None:
        parser.error("status is required")
    try:
        found = findings(json.loads(args.status.read_text()))
    except (OSError, ValueError) as error:
        parser.exit(1, f"FAIL: {error}\n")
    for note in notes(json.loads(args.status.read_text())):
        print(f"NOTE: {note}")
    if found:
        parser.exit(1, "".join(f"FAIL: {line}\n" for line in found))
    print(f"PASS: {args.status} follows the run lifecycle")


if __name__ == "__main__":
    main()
