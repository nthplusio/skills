#!/usr/bin/env python3
"""Render one status file that follows references/status-contract.md as a self-contained HTML page.

The renderer checks the shape of the record: known top-level keys, value sets, well-formed IDs
and references that resolve. It does not judge whether the record is true or whether the
producer followed its own lifecycle rules; a producer with such rules checks them before
rendering. It never invokes owners or checks.
"""

import argparse
from datetime import datetime
from html import escape
from ipaddress import ip_address
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


# The contract this renderer and references/status-contract.md describe. Bump it when a field,
# value set or default changes; producers compare it with the version they wrote against.
CONTRACT_VERSION = "2"
ASSETS = Path(__file__).resolve().parent.parent / "assets"
# Business stages in delivery order, from the contract's machine-readable list. The first two and
# review/verification are optional so older records still render.
STAGE_LIST = json.loads((ASSETS / "stages.json").read_text())
STAGES = {item["key"]: (item["label"], item["technical_label"], item["description"]) for item in STAGE_LIST}
REQUIRED_STAGES = tuple(item["key"] for item in STAGE_LIST if item["required"])
NOT_RECORDED = {"state": "not_requested", "note": "Not recorded in this status record.", "evidence": []}
# Status of the agent that owns the row.
OWNER_STATES = {
    "active": "Working",
    "waiting": "Waiting",
    "blocked": "Blocked",
    "unreachable": "Not responding",
    "complete": "Finished",
    "closed": "Closed",
}
STATES = {
    "verified": ("Done", "✓"),
    "pending": ("In progress", "…"),
    "blocked": ("Blocked", "!"),
    "not_requested": ("Not in scope", "—"),
}
WORK_STATES = {
    "needs_decision": ("Needs a decision", "attention"),
    "blocked": ("Blocked", "attention"),
    "waiting": ("On hold", "attention"),
    "unknown": ("Confirming status", "attention"),
    "working": ("In progress", "moving"),
    "ready": ("Ready to start", "moving"),
    "awaiting_acceptance": ("Ready for sign-off", "moving"),
    "delivered": ("Done", "resolved"),
    "no_change_needed": ("No change needed", "resolved"),
    "cancelled": ("Cancelled", "resolved"),
    "deferred": ("Postponed", "resolved"),
}
GROUPS = {"attention": "Needs attention", "moving": "In progress", "resolved": "Wrapped up"}
# Schema 2 fixes the set of top-level keys; schema 1 records keep rendering with extra keys ignored.
SCHEMA_VERSIONS = (1, 2)
V2_FIELDS = {"schema_version", "run_id", "title", "goal", "updated_at", "config_path", "harness_name",
             "notice", "run_choices", "monitoring", "presentation", "decisions", "tasks", "evidence",
             "history", "approvals", "contract_version", "follow_ups", "closed_at"}
APPROVAL_STATES = {"active": "Active", "consumed": "Used", "expired": "Expired", "revoked": "Revoked"}
RUNTIME_STATES = {"held": "In use", "released": "Released", "retained": "Kept on purpose"}
CODE_KINDS = {"pushed_branch": "Pushed branch", "bundle": "Git bundle", "patch": "Patch file"}
# Row fields a producer may leave out; the page shows these values in their place.
TASK_DEFAULTS = {"blocker": "", "next_action": "", "done_when": "", "resources": [], "blocked_by": [],
                 "obligations": [], "runtime": []}


def friendly_time(moment):
    offset = moment.strftime("%z")
    zone = "UTC" if offset == "+0000" else f"UTC{offset[:3]}:{offset[3:]}"
    hour = moment.hour % 12 or 12
    return f"{moment:%b} {moment.day}, {moment.year}, {hour}:{moment:%M} {'AM' if moment.hour < 12 else 'PM'} ({zone})"


def friendly_interval(seconds):
    if seconds % 3600 == 0:
        count, unit = seconds // 3600, "hour"
    elif seconds % 60 == 0:
        count, unit = seconds // 60, "minute"
    else:
        count, unit = seconds, "second"
    return f"{count} {unit}{'' if count == 1 else 's'}"


def work_status(task):
    if "work" in task:
        return task["work"]
    owner_state = task["owner"]["state"]
    state = {"active": "working", "waiting": "waiting", "blocked": "blocked"}.get(owner_state, "unknown")
    if state == "unknown":
        return {"state": state, "summary": "We're confirming how this item ended.",
                "reason": "Outcome not recorded; inspect the retained result before classifying."}
    return {"state": state, "reason": "Work status inferred from owner activity; confirm at the next scan."}


def stages(task):
    """Every stage in order; a stage the record leaves out shows as not recorded."""
    recorded = task.get("milestones") or {}
    return {key: recorded.get(key, NOT_RECORDED) for key in STAGES}


def unsubmitted(task):
    """Delivered implementation that was never published, so readers do not mistake it for shipped work."""
    phases = stages(task)
    return (work_status(task)["state"] == "delivered" and phases["pr_readiness"]["state"] == "verified"
            and phases["code_publication"]["state"] != "verified")


def work_label(task):
    state = work_status(task)["state"]
    return "Done, not submitted" if unsubmitted(task) else WORK_STATES[state][0]


def stage_position(task):
    """Return (current, target): the first unfinished requested stage and the last requested one."""
    phases = stages(task)
    requested = [key for key in STAGES if phases[key]["state"] != "not_requested"]
    if not requested:
        return None, None
    return next((key for key in requested if phases[key]["state"] != "verified"), None), requested[-1]


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


def link(href, hosted):
    if not href:
        return ""
    url = urlsplit(href)
    if url.scheme.lower() not in ("", "http", "https", "file"):
        raise ValueError(f"unsupported link scheme: {url.scheme}")
    if hosted and not href.startswith("#"):
        if url.scheme not in ("http", "https") or not url.hostname:
            raise ValueError("hosted dashboard needs accessible links, not local paths")
        host = url.hostname.lower()
        if host == "localhost" or host.endswith((".localhost", ".local")):
            raise ValueError("hosted dashboard cannot link to a local host")
        try:
            address = ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("hosted dashboard cannot link to a private or loopback address")
    return escape(href, quote=True)


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


def with_defaults(task):
    """A copy of the row with the contract's defaults filled in, so the page never reads a missing field."""
    task, owner = dict(task), dict(task["owner"])
    for field, default in TASK_DEFAULTS.items():
        task.setdefault(field, list(default) if isinstance(default, list) else default)
    for field in ("location", "handoff"):
        owner.setdefault(field, "")
    task["owner"] = owner
    return task


def check_shape(data, tasks, evidence, decisions):
    """Value sets, well-formed IDs and references that resolve. Rules about what the values mean stay
    with the producer."""
    if data["schema_version"] >= 2:
        unknown = set(data) - V2_FIELDS
        if unknown:
            raise ValueError(f"unknown top-level field {', '.join(sorted(unknown))}; extend the contract or keep it in history")
    for item in evidence.values():
        if item["result"] not in ("passed", "failed", "interrupted", "observed"):
            raise ValueError(f"{item['id']}: invalid evidence result")
        if item["assessment"] not in ("accepted", "limited", "superseded"):
            raise ValueError(f"{item['id']}: invalid evidence assessment")
        if not item.get("href") and not item.get("output", "").strip():
            raise ValueError(f"{item['id']}: proof needs an artifact link or literal output")
    owners = set()
    for task in tasks.values():
        key, owner = task["id"], task["owner"]
        nonempty(owner.get("id"), f"{key}: owner needs its actual harness ID; owner.id")
        if owner["state"] not in OWNER_STATES:
            raise ValueError(f"{key}: invalid owner state")
        activity = owner.get("activity")
        if activity is not None and (not isinstance(activity, str) or not activity.strip()):
            raise ValueError(f"{key}: owner activity must be nonempty text when present")
        if owner["id"] in owners:
            raise ValueError(f"{key}: owner {owner['id']} is already bound to another ticket; use that ticket's owner or a separate owner")
        owners.add(owner["id"])
        code = owner.get("retained_code")
        if code is not None and (not isinstance(code, dict) or code.get("kind") not in CODE_KINDS):
            raise ValueError(f"{key}: retained_code.kind must be one of {', '.join(CODE_KINDS)}")
        recorded = task.get("milestones")
        if recorded is not None:
            unknown = set(recorded) - set(STAGES)
            if unknown:
                raise ValueError(f"{key}: unknown stage {', '.join(sorted(unknown))}")
            missing = [stage for stage in REQUIRED_STAGES if stage not in recorded]
            if missing:
                raise ValueError(f"{key}: missing stage {missing[0]}")
            for stage, phase in recorded.items():
                if phase["state"] not in STATES:
                    raise ValueError(f"{key}: invalid stage state")
                for proof_id in phase["evidence"]:
                    if proof_id not in evidence:
                        raise ValueError(f"{key}: missing proof {proof_id}")
        work = work_status(task)
        if not isinstance(work, dict) or work.get("state") not in WORK_STATES:
            raise ValueError(f"{key}: invalid work state")
        nonempty(work.get("reason"), f"{key}: work needs a reason; work.reason")
        if "summary" in work and (not isinstance(work["summary"], str) or not work["summary"].strip()):
            raise ValueError(f"{key}: work summary must be nonempty text when present")
        proof_ids = work.get("evidence", [])
        if not isinstance(proof_ids, list) or any(proof_id not in evidence for proof_id in proof_ids):
            raise ValueError(f"{key}: work evidence must name retained proof")
        for entry in indexed(task["runtime"]).values():
            nonempty(entry.get("kind"), f"{key}.runtime.{entry['id']}.kind")
            nonempty(entry.get("ref"), f"{key}.runtime.{entry['id']}.ref")
            if entry.get("state") not in RUNTIME_STATES:
                raise ValueError(f"{key}: invalid runtime state for {entry['id']}")
            if entry["state"] == "retained":
                nonempty(entry.get("reason"), f"{key}.runtime.{entry['id']}.reason")
                moment(entry.get("until"), f"{key}.runtime.{entry['id']}.until")
    for item in decisions.values():
        affected = item.get("task_ids", [])
        if not isinstance(affected, list) or any(key not in tasks for key in affected):
            raise ValueError(f"{item['id']}: unknown affected task; task_ids must name assigned rows in tasks. Name unassigned tickets in the decision text and leave task_ids empty.")
        discussion = item.get("discussion", {})
        if not isinstance(discussion, dict) or (discussion and any(
            not isinstance(discussion.get(key), str) or not discussion[key].strip() for key in ("owner_id", "label")
        )):
            raise ValueError(f"{item['id']}: discussion needs an owner_id and label")
        if "requires_human" in discussion:
            raise ValueError(f"{item['id']}: requires_human belongs on the decision, alongside discussion")
        human = item.get("requires_human", False)
        if not isinstance(human, bool):
            raise ValueError(f"{item['id']}: requires_human must be boolean")
        if human and not discussion:
            raise ValueError(f"{item['id']}: human-only gate needs a discussion owner")


def render(data, hosted=False):
    if data["schema_version"] not in SCHEMA_VERSIONS:
        raise ValueError("unsupported dashboard schema_version")
    nonempty(data["run_id"], "run_id")
    updated = moment(data["updated_at"], "updated_at") if data.get("updated_at") is not None else None
    auto_refresh = data["presentation"].get("auto_refresh", False)
    if type(auto_refresh) is not bool:
        raise ValueError("presentation.auto_refresh must be boolean")
    refresh_meta = ""
    refresh_status = "This page is a snapshot. It changes when the coordinator posts an update."
    if auto_refresh:
        interval = data.get("monitoring", {}).get("interval_seconds")
        if type(interval) is not int or interval < 1:
            raise ValueError("automatic refresh needs a positive integer monitoring.interval_seconds")
        refresh_meta = f'<meta http-equiv="refresh" content="{interval}">'
        refresh_status = f"This page reloads every {friendly_interval(interval)} to show the coordinator's latest update."
    evidence = indexed(data.get("evidence", []))
    tasks = indexed(with_defaults(task) for task in data["tasks"])
    decisions = indexed(data.get("decisions", []))
    check_shape(data, tasks, evidence, decisions)
    # Approvals and follow-ups arrived with schema 2; a schema 1 record never carried them.
    schema_2 = data["schema_version"] >= 2
    approvals = indexed(data.get("approvals", [])) if schema_2 else {}
    for item in approvals.values():
        if item.get("state") not in APPROVAL_STATES:
            raise ValueError(f"{item['id']}: invalid approval state")
    follow_ups = indexed(data.get("follow_ups", [])) if schema_2 else {}
    for item in follow_ups.values():
        nonempty(item.get("text"), f"{item['id']}.text")
        if item.get("from_task") not in tasks:
            raise ValueError(f"{item['id']}: follow-up needs the assigned task it came from")
    overdue = [(task["id"], entry) for task in tasks.values() for entry in task["runtime"]
               if entry["state"] == "retained" and updated is not None and moment(entry["until"], "until") <= updated]

    def anchor(href, label):
        return f'<a href="{link(href, hosted)}">{escape(label)}</a>' if href else escape(label)

    def proof_links(ids):
        return " ".join(anchor(f"#proof-{key}", key) for key in ids)

    def context_packet(task_ids, decision=None):
        packet = {
            "run_id": data["run_id"], "snapshot_time": data.get("updated_at"), "goal": data.get("goal", ""),
            "approval_constraints": "This context grants no approval. Use only explicitly authorized scope from the originating conversation.",
            "tasks": [{key: tasks[task_id].get(key, {}) for key in
                       ("id", "title", "owner", "blocker", "next_action", "obligations", "milestones")}
                      for task_id in task_ids],
        }
        for task in packet["tasks"]:
            task["work"] = work_status(tasks[task["id"]])
        if decision is not None:
            packet["decision"] = decision
            packet["answer_route"] = decision.get("discussion") or {
                "label": "Coordinator", "href": data["presentation"].get("coordinator_href", "")}
        elif task_ids:
            owner = tasks[task_ids[0]]["owner"]
            packet["answer_route"] = {"owner_id": owner["id"], "label": owner["label"], "href": owner.get("href", "")}
        return escape(json.dumps(packet, indent=2, ensure_ascii=False), quote=True)

    def runtime_list(entries):
        return "<br>".join(
            f'{RUNTIME_STATES[entry["state"]]} · {escape(entry["kind"])} <code>{escape(entry["ref"])}</code>'
            + (f' · until {escape(entry["until"])} · {escape(entry["reason"])}' if entry["state"] == "retained" else "")
            for entry in entries)

    def plain(work):
        return work.get("summary") or work["reason"]

    def task_proof_ids(task):
        return list(dict.fromkeys([key for phase in stages(task).values() for key in phase["evidence"]]
                                  + work_status(task).get("evidence", [])))

    def stage_text(task):
        current, target = stage_position(task)
        if target is None:
            return "No stages requested", ""
        if work_status(task)["state"] in ("cancelled", "deferred"):
            reached = [key for key, phase in stages(task).items() if phase["state"] == "verified"]
            return (f"Stopped after {STAGES[reached[-1]][0]}" if reached else "Stopped before starting"), ""
        if current is None:
            return f"{STAGES[target][0]} ✓", "Reached this run's target"
        state = "blocked" if stages(task)[current]["state"] == "blocked" else "in progress"
        return f"{STAGES[current][0]} — {state}", f"Target: {STAGES[target][0]}"

    def stepper(task):
        phases = stages(task)
        current, _ = stage_position(task)
        steps = []
        for key, (plain_label, _, _) in STAGES.items():
            state = phases[key]["state"]
            state_label = STATES[state][0]
            steps.append(f'<span class="step {state}{" current" if key == current else ""}" role="img" '
                         f'aria-label="{plain_label}: {state_label}" title="{plain_label}: {state_label}"></span>')
        return f'<span class="stepper">{"".join(steps)}</span>'

    def issue_data(task):
        work = work_status(task)
        stage, target = stage_text(task)
        return (f'<section class="issue-data"><h3>{task["id"]} · {escape(task["title"])}</h3><dl>'
                f'<dt>Status</dt><dd>{work_label(task)} · {escape(plain(work))}</dd>'
                f'<dt>Stage</dt><dd>{escape(stage)}{" · " + escape(target) if target else ""}</dd>'
                f'<dt>Agent</dt><dd>{escape(task["owner"]["label"])} · {OWNER_STATES[task["owner"]["state"]]}</dd>'
                f'<dt>Holding it up</dt><dd>{escape(task["blocker"] or "Nothing")}</dd>'
                f'<dt>Next action</dt><dd>{escape(task["next_action"] or "Not recorded")}</dd>'
                f'<dt>Evidence</dt><dd>{proof_links(task_proof_ids(task)) or "None retained"}</dd></dl></section>')

    def question(task, subject):
        if subject == "proof":
            text = f"What does retained proof {', '.join(task_proof_ids(task)) or 'for this task'} establish, and what remains unverified?"
        else:
            text = "What is the blocker and next action, and does anything need my decision?"
        return f"In orchestration run {data['run_id']}, task {task['id']}: {text}"

    def signal(state):
        label, symbol = STATES[state]
        return f'<span class="signal {state}" aria-hidden="true">{symbol}</span>'

    first = next((task["id"] for task in tasks.values() if task["blocker"]), next(iter(tasks), ""))
    rows, details = {group: [] for group in GROUPS}, []
    counts = dict.fromkeys(WORK_STATES, 0)
    for task in tasks.values():
        key = task["id"]
        owner = task["owner"]
        agent = OWNER_STATES[owner["state"]]
        work = work_status(task)
        label, group = work_label(task), WORK_STATES[work["state"]][1]
        counts[work["state"]] += 1
        work_badge = f'<span class="work-status work-{work["state"]}">{label}</span>'
        agent_badge = f'<span class="agent-status agent-{owner["state"]}">{agent}</span>'
        related = [item for item in decisions.values() if key in item.get("task_ids", [])]
        decision_links = " · ".join(anchor(f'#decision-{item["id"]}', item["id"]) for item in related)
        story = escape(plain(work))
        if work.get("revisit"):
            story += f'<small class="revisit">We\'ll revisit: {escape(work["revisit"])}</small>'
        if related:
            story += f'<small class="row-decisions">Waiting on your decision: {decision_links}</small>'
        stage, target = stage_text(task)
        current, _ = stage_position(task)
        plain_steps, technical_steps = [], []
        for phase_key, (plain_label, technical_label, help_text) in STAGES.items():
            phase = stages(task)[phase_key]
            plain_steps.append(f'<li class="{phase["state"]}{" current" if phase_key == current else ""}">{signal(phase["state"])}<div><b>{plain_label}</b>'
                               f'<span>{STATES[phase["state"]][0]}</span><small>{help_text}</small></div></li>')
            if phase["state"] == "not_requested" and not phase["note"].strip():
                continue
            technical_steps.append(
                f'<div class="phase">{signal(phase["state"])}<div><b>{technical_label}</b> <code>{phase_key}</code><span><code>{phase["state"]}</code></span>'
                f'<small>{escape(phase["note"]) or "No note."} {proof_links(phase["evidence"])}'
                + (f' Sign-off by {escape(phase["accountable"])}; revisit {escape(phase["revisit"])}.' if phase.get("accountable") else "")
                + '</small></div></div>')
        rows[group].append(
            f'<tr id="row-{key}" data-work-state="{work["state"]}" data-owner-state="{owner["state"]}"><td class="task-cell" data-label="Item">'
            f'<button class="task-picker" data-task="{key}" aria-pressed="false" aria-haspopup="dialog">'
            f'<span>{escape(task["title"])}</span><small>{key}</small></button></td>'
            f'<td data-label="Stage" class="stage-cell">{stepper(task)}<b>{escape(stage)}</b>'
            + (f'<small>{escape(target)}</small>' if target else "") + '</td>'
            f'<td data-label="Status">{work_badge}</td>'
            f'<td data-label="What\'s happening" class="reason-cell">{story}</td>'
            f'<td data-label="Agent" class="agent-cell">{agent_badge}</td></tr>'
        )
        lifecycle = "Complete, closure pending / unavailable" if owner["state"] == "complete" else agent
        checked = owner.get("last_checked_at")
        resources = ", ".join(task["resources"]) or "None shared"
        dependencies = ", ".join(task["blocked_by"]) or "None"
        obligations = "; ".join(task["obligations"]) or "None outstanding"
        orchestration = (
            f'<dt>Status</dt><dd>{agent_badge} <code>{owner["state"]}</code>'
            + (f' · {escape(lifecycle)}' if owner["state"] == "complete" else "") + '</dd>'
            + (f'<dt>Doing now</dt><dd>{escape(owner["activity"])}</dd>' if owner.get("activity") else "")
            + f'<dt>Agent</dt><dd>{anchor(owner.get("href"), owner["label"])} <code>{escape(owner["id"])}</code></dd>'
            f'<dt>Last checked</dt><dd>{escape(checked or "Check time not recorded")}</dd>'
            f'<dt>Work location</dt><dd>{escape(owner["location"] or "Not recorded")}</dd>'
            f'<dt>Retained handoff</dt><dd>{escape(owner["handoff"] or "Not complete")}</dd>'
            + (f'<dt>Retained code</dt><dd>{CODE_KINDS[owner["retained_code"]["kind"]]} '
               f'<code>{escape(owner["retained_code"]["ref"])}</code>'
               + (f' · checksum <code>{escape(owner["retained_code"]["checksum"])}</code>' if owner["retained_code"].get("checksum") else "")
               + '</dd>' if owner.get("retained_code") else "")
            + (f'<dt>Runtime</dt><dd>{runtime_list(task["runtime"])}</dd>' if task.get("runtime") else "")
        )
        technical = (
            f'<dt>Work state</dt><dd><code>{work["state"]}</code> · {escape(work["reason"])}</dd>'
            f'<dt>Blocker</dt><dd>{escape(task["blocker"] or "None")}</dd>'
            f'<dt>Next action</dt><dd>{escape(task["next_action"] or "Not recorded")}</dd>'
            f'<dt>Done when</dt><dd>{escape(task["done_when"] or "Not recorded")}</dd>'
            + (f'<dt>Decision receipt</dt><dd>{escape(work["receipt"])}</dd>' if work.get("receipt") else "")
            + (f'<dt>Outcome proof</dt><dd>{proof_links(work["evidence"])}</dd>' if work.get("evidence") else "")
            + f'<dt>Resources</dt><dd>{escape(resources)}</dd><dt>Dependencies</dt><dd>{escape(dependencies)}</dd>'
            f'<dt>Obligations</dt><dd>{escape(obligations)}</dd>'
        )
        details.append(
            f'<details class="task-detail" id="task-{key}"{" open" if key == first else ""}><summary>{escape(task["title"])} <small>{key}</small></summary>'
            f'<section class="plain-view"><div class="work-outcome">{work_badge}<p>{escape(plain(work))}</p>'
            + (f'<p><b>We\'ll revisit:</b> {escape(work["revisit"])}</p>' if work.get("revisit") else "")
            + (f'<p><b>Waiting on your decision:</b> {decision_links}</p>' if related else "")
            + f'</div><h3>Business progress <small>{escape(stage)}{" · " + escape(target) if target else ""}</small></h3>'
            f'<ol class="steps" aria-label="Business progress">{"".join(plain_steps)}</ol></section>'
            f'<section class="technical"><h3>Agent (orchestration)</h3><dl class="tech-grid">{orchestration}</dl></section>'
            f'<section class="technical"><h3>Technical details</h3><dl class="tech-grid">{technical}</dl>'
            f'<h4>Stages and evidence</h4>{"".join(technical_steps) or "<p class=muted>No stages requested.</p>"}</section>'
            f'<section class="agent-tools"><div class="detail-heading"><h3>Ask about this item</h3>'
            f'<button class="quiet" data-copy-id="{key}">Copy ID</button></div>'
            f'<div class="question-options"><button data-question="{escape(question(task, "status"), quote=True)}">Prepare status question</button>'
            f'<button data-question="{escape(question(task, "proof"), quote=True)}">Prepare evidence question</button></div>'
            f'<div class="share-actions"><button data-discussion-owner="{escape(owner["id"], quote=True)}" '
            f'data-discussion-label="{escape(owner["label"], quote=True)}" data-discussion-href="{link(owner.get("href", ""), hosted)}" '
            f'data-context="{context_packet([key])}">Copy context for agent</button>'
            f'{anchor(owner.get("href"), "Open work owner conversation") if owner.get("href") else escape(owner["label"] + " (" + owner["id"] + ")")}'
            '<small>Copy, then paste into this owner\'s existing conversation. Copy does not send anything.'
            + (' No direct link is configured.' if not owner.get("href") else "")
            + '</small><p class="share-feedback" role="status" aria-live="polite"></p></div></section>'
            '</details>'
        )
    proofs = []
    for item in evidence.values():
        proofs.append(
            f'<details class="receipt" id="proof-{item["id"]}"><summary><b>{item["id"]}</b> {escape(item["label"])}'
            f'<span>{item["result"]} · {item["assessment"]}</span></summary>'
            f'<p><b>Scope</b> {escape(item["scope"])}</p><p>{escape(item["note"])}</p>'
            f'{anchor(item.get("href"), "Open retained artifact") if item.get("href") else ""}'
            f'{"<pre>" + escape(item["output"]) + "</pre>" if item.get("output") else ""}</details>'
        )
    decision_html = []
    for item in decisions.values():
        affected = item.get("task_ids", [])
        if not isinstance(affected, list) or any(key not in tasks for key in affected):
            raise ValueError(f"{item['id']}: unknown affected task; task_ids must name assigned rows in tasks. Name unassigned tickets in the decision text and leave task_ids empty.")
        discussion = item.get("discussion", {})
        if not isinstance(discussion, dict) or (discussion and any(
            not isinstance(discussion.get(key), str) or not discussion[key].strip() for key in ("owner_id", "label")
        )):
            raise ValueError(f"{item['id']}: discussion needs an owner_id and label")
        if "requires_human" in discussion:
            raise ValueError(f"{item['id']}: requires_human belongs on the decision, alongside discussion")
        human = item.get("requires_human", False)
        if not isinstance(human, bool):
            raise ValueError(f"{item['id']}: requires_human must be boolean")
        if human and not discussion:
            raise ValueError(f"{item['id']}: human-only gate needs a discussion owner")
        href = discussion.get("href", "")
        if discussion:
            route = (anchor(href, "Answer in conversation" if human else "Open discussion") if href
                     else escape(f"Discuss with {discussion['label']} ({discussion['owner_id']})"))
        else:
            route = anchor(data["presentation"].get("coordinator_href"), "Open coordinator")
        attributes = (f'data-discussion-owner="{escape(discussion.get("owner_id", ""), quote=True)}" '
                      f'data-discussion-label="{escape(discussion.get("label", "coordinator"), quote=True)}" '
                      f'data-discussion-href="{link(href, hosted)}" data-requires-human="{str(human).lower()}"')
        prompt = f"In orchestration run {data['run_id']}, decision {item['id']}: {item['text']} Explain the recommendation and the consequence of each option."
        affected_links = " · ".join(anchor(f"#task-{key}", key) for key in affected)
        unblocks = escape(item.get("unblocks") or "Discuss the pending choice")
        answer_with = escape(discussion.get("label", "Coordinator"))
        decision_html.append(
            f'<article class="decision" id="decision-{item["id"]}"><div class="decision-preview">'
            f'<button class="decision-picker" data-decision="{item["id"]}" aria-haspopup="dialog" aria-controls="decision-dialog">'
            f'<b>{item["id"]}</b><span>{escape(item["text"])}</span></button>'
            f'<small>{"Affects " + affected_links + " · " if affected else ""}Answering unlocks: {unblocks}'
            f' · Answer with: {answer_with}{" · You must answer this yourself" if human else ""}</small></div>'
            f'<button class="quiet" {attributes} data-decision="{item["id"]}" data-copy-id="{item["id"]}">Copy {item["id"]}</button>'
            f'<div class="decision-detail" data-decision="{item["id"]}" hidden><div class="context-columns"><section><p class="decision-question">{escape(item["text"])}</p>'
            f'<dl><dt>Our recommendation</dt><dd>{escape(item["recommendation"])}</dd>'
            f'<dt>Affects</dt><dd>{affected_links or "The whole run"}</dd>'
            f'<dt>Answering unlocks</dt><dd>{unblocks}</dd>'
            f'<dt>Where to answer</dt><dd>{answer_with}</dd></dl>'
            + ('<p class="human-warning">You need to answer this yourself in the linked conversation. '
               'A forwarded or copied message cannot answer it.</p>' if human else "")
            + '</section><section><h3 class="column-heading">Technical context</h3>' + "".join(issue_data(tasks[key]) for key in affected) + '</section></div>'
            + f'<div class="share-actions"><button {attributes} data-context="{context_packet(affected, item)}">Copy context for agent</button>{route}'
            + ('<small>Copying prepares context only. Answer the existing dialog yourself.</small>' if human else
               '<small>Copy, then open the conversation and paste. Neither action sends a message.</small>')
            + '<p class="share-feedback" role="status" aria-live="polite"></p></div>'
              f'<div class="decision-actions"><button class="quiet" {attributes} data-copy-id="{item["id"]}">Copy ID</button>'
              f'<button class="quiet" {attributes} data-question="{escape(prompt, quote=True)}">Prepare {item["id"]} question</button></div></div></article>'
        )
    approval_html = "".join(
        f'<li id="approval-{item["id"]}"><b>{item["id"]}</b> {APPROVAL_STATES[item["state"]]} · {escape(item["scope"])}'
        f'<small>Side effects: {escape(item["side_effects"])} · Granted {escape(item["granted_at"])}'
        f' · {"Expires " + escape(item["expires_at"]) if item.get("expires_at") else "No expiry"}'
        f' · Source: {escape(item["receipt"])}</small></li>' for item in approvals.values())
    held = [(task["id"], entry) for task in tasks.values() for entry in task["runtime"] if entry["state"] != "released"]
    overdue_ids = {(key, entry["id"]) for key, entry in overdue}
    runtime_html = "".join(
        f'<li><b>{key}</b> {RUNTIME_STATES[entry["state"]]} · {escape(entry["kind"])} <code>{escape(entry["ref"])}</code>'
        + (f'<small>{"Cleanup overdue since" if (key, entry["id"]) in overdue_ids else "Kept until"} '
           f'{escape(entry["until"])} · {escape(entry["reason"])}</small>' if entry["state"] == "retained" else "")
        + '</li>' for key, entry in held)
    follow_up_html = "".join(
        f'<li id="follow-up-{item["id"]}"><b>{item["id"]}</b> {escape(item["text"])}'
        f'<small>From {anchor("#task-" + item["from_task"], item["from_task"])} · '
        f'{"Owned by " + escape(item["owner"]) if item.get("owner") else "Needs an owner"}'
        f'{" · " + escape(item["trigger"]) if item.get("trigger") else ""}</small></li>' for item in follow_ups.values())
    unowned = sum(1 for item in follow_ups.values() if not item.get("owner"))
    notice = data.get("notice", "")
    if data.get("closed_at"):
        notice = (notice + " " if notice else "") + f"This run closed at {data['closed_at']}. The page no longer changes."
    total = len(tasks)
    done = counts["delivered"]
    closed_other = len(rows["resolved"]) - done
    not_submitted = sum(1 for task in tasks.values() if unsubmitted(task))
    segments = [("done", "Done", done), ("closed", "Wrapped up without delivery", closed_other),
                ("moving", "In progress", len(rows["moving"])), ("attention", "Needs attention", len(rows["attention"]))]
    meter = "".join(f'<span class="segment segment-{name}" style="flex-grow:{count}" title="{label}: {count}"></span>'
                    for name, label, count in segments if count)
    meter_legend = "".join(f'<li><i class="swatch segment-{name}" aria-hidden="true"></i><b>{count}</b> {label}</li>'
                           for name, label, count in segments if count)
    if total:
        headline = (f'<b>{len(rows["resolved"])} of {total}</b> items wrapped up'
                    f' <span class="headline-detail">· {done} done'
                    + (f' ({not_submitted} not submitted)' if not_submitted else "")
                    + f' · {len(rows["moving"])} in progress · {len(rows["attention"])} need attention</span>')
    else:
        headline = "No items are assigned yet."
    callout = (f'<a class="callout" href="#decisions">{len(decisions)} decision{"s" if len(decisions) != 1 else ""} '
               f'need{"s" if len(decisions) == 1 else ""} your input →</a>' if decisions else "")
    if unowned:
        callout += (f'<a class="callout" href="#follow-ups">{unowned} follow-up{"s need" if unowned != 1 else " needs"} an owner →</a>')
    if overdue:
        callout += (f'<a class="callout" href="#runtime">{len(overdue)} kept resource'
                    f'{"s are" if len(overdue) != 1 else " is"} past {"their" if len(overdue) != 1 else "its"} cleanup date →</a>')
    replacements = {
        "TITLE": escape(data["title"]), "RUN_ID": escape(data["run_id"]),
        "GOAL": escape(data.get("goal", "")), "UPDATED": escape(data.get("updated_at") or ""),
        "UPDATED_FRIENDLY": escape(friendly_time(updated) if updated else "Snapshot time not recorded"),
        "CONTRACT_VERSION": CONTRACT_VERSION,
        "REFRESH_META": refresh_meta, "REFRESH_STATUS": refresh_status,
        "NOTICE": escape(notice),
        "FOLLOW_UPS": follow_up_html or '<li class="muted">No follow-up work recorded.</li>', "TASK_COUNT": str(total),
        "HEADLINE": headline, "CALLOUT": callout,
        "METER": meter or '<span class="segment segment-empty" style="flex-grow:1"></span>',
        "METER_LABEL": escape(", ".join(f"{count} {label.lower()}" for _, label, count in segments if count) or "No items"),
        "METER_LEGEND": meter_legend,
        "AGENT_COUNTS": "".join(f'<span class="agent-status agent-{state}"><b>{count}</b> {label}</span>'
                                 for state, label in OWNER_STATES.items()
                                 if (count := sum(task["owner"]["state"] == state for task in tasks.values())))
                        or '<span class="muted">No agents assigned yet.</span>',
        "WORK_COUNTS": "".join(f'<span class="work-status work-{state}"><b>{count}</b> {WORK_STATES[state][0]}</span>'
                                for state, count in counts.items() if count),
        "ROWS": "".join(f'<tbody class="group-{group}"><tr class="group-heading"><th scope="rowgroup" colspan="5">{label} ({len(rows[group])})</th></tr>'
                        + "".join(rows[group]) + '</tbody>' for group, label in GROUPS.items() if rows[group])
                or '<tbody><tr><td colspan="5">No items are assigned yet.</td></tr></tbody>',
        "STAGE_KEY": "".join(f'<li><b>{plain_label}</b> {help_text}</li>' for plain_label, _, help_text in STAGES.values()),
        "DECISION_COUNT": str(len(decisions)),
        "DETAILS": "".join(details) or '<p>Select an item after one is assigned.</p>',
        "DECISIONS": "".join(decision_html) or '<p class="muted">Nothing needs your decision right now.</p>',
        "PROOFS": "".join(proofs) or '<p class="muted">No evidence retained yet.</p>',
        "APPROVALS": approval_html or '<li class="muted">No approvals recorded.</li>',
        "RUNTIME": runtime_html or '<li class="muted">Nothing is running or kept for this run.</li>',
        "HISTORY": "".join(f'<li>{escape(item)}</li>' for item in data.get("history", [])) or '<li>No material changes recorded.</li>',
        "QUESTION": escape(question(tasks[first], "status") if first else f"In orchestration run {data['run_id']}: what work is assigned?"),
        "COORDINATOR": anchor(data["presentation"].get("coordinator_href"), "Open coordinator") if data["presentation"].get("coordinator_href") else "Paste into your coordinator conversation.",
        "INTERACTION": escape(data["presentation"].get("interaction", "")),
        "FIRST_TASK": first,
    }
    template = (ASSETS / "dashboard-template.html").read_text()
    return re.sub(r"\{\{([A-Z_]+)\}\}", lambda match: replacements[match[1]], template)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("status", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--hosted", action="store_true")
    parser.add_argument("--contract-version", action="store_true", help="print the status contract version and exit")
    args = parser.parse_args()
    if args.contract_version:
        print(CONTRACT_VERSION)
        return
    if args.status is None or args.output is None:
        parser.error("status and output are required")
    try:
        html = render(json.loads(args.status.read_text()), args.hosted)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(args.output.name + ".tmp")
        temporary.write_text(html)
        temporary.replace(args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"FAIL: {error}\n")
    print(f"PASS: rendered {args.output}")


if __name__ == "__main__":
    main()
