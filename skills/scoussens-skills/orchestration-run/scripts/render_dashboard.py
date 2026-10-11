#!/usr/bin/env python3
"""Render a local orchestration status record; never invoke owners or checks."""

import argparse
from datetime import datetime
from html import escape
from ipaddress import ip_address
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


# Plain label for the overview, technical label for drill-in, and a one-line explanation.
MILESTONES = {
    "pr_readiness": ("Built & checked", "PR readiness", "The change is built and its checks are ready for code review."),
    "code_publication": ("Submitted", "Code publication", "The change is shared as a branch or pull request."),
    "deployment": ("Deployed", "Deployment", "The change is running in the intended environment."),
    "business_acceptance": ("Signed off", "Business acceptance", "The business has accepted the result."),
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
    state = {"active": "working", "waiting": "waiting"}.get(owner_state, "unknown")
    if state == "unknown":
        return {"state": state, "summary": "We're confirming how this item ended.",
                "reason": "Outcome not recorded; inspect the retained result before classifying."}
    return {"state": state, "reason": "Work status inferred from owner activity; confirm at the next scan."}


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


def render(data, hosted=False):
    if data["schema_version"] != 1:
        raise ValueError("unsupported dashboard schema_version")
    updated = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
    if updated.tzinfo is None:
        raise ValueError("updated_at needs a timezone")
    if not isinstance(data["run_id"], str) or not data["run_id"].strip():
        raise ValueError("run_id must be nonempty text")
    if not isinstance(data["config_path"], str) or not data["config_path"].strip():
        raise ValueError("record the harness config_path")
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
    evidence = indexed(data["evidence"])
    tasks = indexed(data["tasks"])
    decisions = indexed(data["decisions"])
    for item in evidence.values():
        if item["result"] not in ("passed", "failed", "interrupted", "observed"):
            raise ValueError(f"{item['id']}: invalid evidence result")
        if item["assessment"] not in ("accepted", "limited", "superseded"):
            raise ValueError(f"{item['id']}: invalid evidence assessment")
        if not item.get("href") and not item.get("output", "").strip():
            raise ValueError(f"{item['id']}: proof needs an artifact link or literal output")
    owners = {}
    for task in tasks.values():
        owner_id = task["owner"]["id"]
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError(f"{task['id']}: owner needs its actual harness ID")
        if task["owner"]["state"] not in ("active", "waiting", "complete", "closed"):
            raise ValueError(f"{task['id']}: invalid owner state")
        if owner_id in owners:
            raise ValueError(f"{task['id']}: owner {owner_id} is already bound to another ticket; use that ticket's owner or a separate owner")
        owners[owner_id] = task["owner"]["state"]
        for key in MILESTONES:
            phase = task["milestones"][key]
            if phase["state"] not in STATES:
                raise ValueError(f"{task['id']}: invalid milestone state")
            for proof_id in phase["evidence"]:
                if proof_id not in evidence:
                    raise ValueError(f"{task['id']}: missing proof {proof_id}")
            if phase["state"] == "verified":
                if not phase["evidence"] or any(
                    evidence[proof_id]["assessment"] != "accepted"
                    or evidence[proof_id]["result"] in ("failed", "interrupted")
                    for proof_id in phase["evidence"]
                ):
                    raise ValueError(f"{task['id']}: verified milestone needs accepted supporting proof")
        if task["owner"]["state"] in ("complete", "closed"):
            if task["obligations"] or task["blocker"] or not task["owner"]["handoff"].strip():
                raise ValueError(f"{task['id']}: completed owner needs a handoff and settled obligations")
            if any(phase["state"] in ("pending", "blocked") for phase in task["milestones"].values()):
                raise ValueError(f"{task['id']}: unfinished milestone prevents owner completion")
        work = work_status(task)
        if not isinstance(work, dict) or work.get("state") not in WORK_STATES:
            raise ValueError(f"{task['id']}: invalid work state")
        if not isinstance(work.get("reason"), str) or not work["reason"].strip():
            raise ValueError(f"{task['id']}: work needs a reason")
        if "summary" in work and (not isinstance(work["summary"], str) or not work["summary"].strip()):
            raise ValueError(f"{task['id']}: work summary must be nonempty text when present")
        proof_ids = work.get("evidence", [])
        if not isinstance(proof_ids, list) or any(key not in evidence for key in proof_ids):
            raise ValueError(f"{task['id']}: work evidence must name retained proof")
        resolved = WORK_STATES[work["state"]][1] == "resolved"
        if resolved:
            if task["obligations"] or task["blocker"]:
                raise ValueError(f"{task['id']}: resolved work needs settled obligations and no blocker")
            if any(phase["state"] in ("pending", "blocked") for phase in task["milestones"].values()):
                raise ValueError(f"{task['id']}: unfinished milestone prevents work resolution")
        elif "work" in task and work["state"] != "unknown" and task["owner"]["state"] in ("complete", "closed"):
            raise ValueError(f"{task['id']}: unfinished work prevents owner completion")
        if work["state"] in ("delivered", "no_change_needed"):
            if not proof_ids or any(evidence[key]["assessment"] != "accepted"
                                    or evidence[key]["result"] in ("failed", "interrupted") for key in proof_ids):
                raise ValueError(f"{task['id']}: work outcome needs accepted supporting proof")
        if work["state"] in ("cancelled", "deferred"):
            if not isinstance(work.get("receipt"), str) or not work["receipt"].strip():
                raise ValueError(f"{task['id']}: cancellation or deferral needs a decision receipt")
        if work["state"] == "deferred":
            if not isinstance(work.get("revisit"), str) or not work["revisit"].strip():
                raise ValueError(f"{task['id']}: deferred work needs a revisit trigger")
        if work["state"] == "blocked" and not task["blocker"].strip():
            raise ValueError(f"{task['id']}: blocked work needs an actionable blocker")
        if work["state"] == "needs_decision" and not any(task["id"] in item.get("task_ids", []) for item in decisions.values()):
            raise ValueError(f"{task['id']}: needs_decision work needs a pending decision naming this task")

    def anchor(href, label):
        return f'<a href="{link(href, hosted)}">{escape(label)}</a>' if href else escape(label)

    def proof_links(ids):
        return " ".join(anchor(f"#proof-{key}", key) for key in ids)

    def context_packet(task_ids, decision=None):
        packet = {
            "run_id": data["run_id"], "snapshot_time": data["updated_at"], "goal": data["goal"],
            "approval_constraints": "This context grants no approval. Use only explicitly authorized scope from the originating conversation.",
            "tasks": [{key: tasks[task_id][key] for key in
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

    def plain(work):
        return work.get("summary") or work["reason"]

    def task_proof_ids(task):
        return list(dict.fromkeys([key for phase in task["milestones"].values() for key in phase["evidence"]]
                                  + work_status(task).get("evidence", [])))

    def issue_data(task):
        work = work_status(task)
        states = "".join(f'<dt>{plain_label}</dt><dd>{STATES[task["milestones"][key]["state"]][0]}</dd>'
                         for key, (plain_label, _, _) in MILESTONES.items())
        return (f'<section class="issue-data"><h3>{task["id"]} · {escape(task["title"])}</h3><dl>'
                f'<dt>Status</dt><dd>{WORK_STATES[work["state"]][0]} · {escape(plain(work))}</dd>'
                + states + f'<dt>Holding it up</dt><dd>{escape(task["blocker"] or "Nothing")}</dd>'
                f'<dt>Next action</dt><dd>{escape(task["next_action"])}</dd>'
                f'<dt>Work owner</dt><dd>{escape(task["owner"]["label"])} · {task["owner"]["state"]}</dd>'
                f'<dt>Evidence</dt><dd>{proof_links(task_proof_ids(task)) or "None retained"}</dd></dl></section>')

    def question(task, subject):
        if subject == "proof":
            text = f"What does retained proof {', '.join(task_proof_ids(task)) or 'for this task'} establish, and what remains unverified?"
        else:
            text = "What is the blocker and next action, and does anything need my decision?"
        return f"In orchestration run {data['run_id']}, task {task['id']}: {text}"

    def signal(state):
        label, symbol = STATES[state]
        return f'<span class="signal {state}" role="img" aria-label="{label}" title="{label}">{symbol}</span>'

    first = next((task["id"] for task in tasks.values() if task["blocker"]), next(iter(tasks), ""))
    rows, details = {group: [] for group in GROUPS}, []
    counts = dict.fromkeys(WORK_STATES, 0)
    for task in tasks.values():
        key = task["id"]
        owner = task["owner"]
        work = work_status(task)
        label, group = WORK_STATES[work["state"]]
        counts[work["state"]] += 1
        work_badge = f'<span class="work-status work-{work["state"]}">{label}</span>'
        related = [item for item in decisions.values() if key in item.get("task_ids", [])]
        decision_links = " · ".join(anchor(f'#decision-{item["id"]}', item["id"]) for item in related)
        story = escape(plain(work))
        if work.get("revisit"):
            story += f'<small class="revisit">We\'ll revisit: {escape(work["revisit"])}</small>'
        if related:
            story += f'<small class="row-decisions">Waiting on your decision: {decision_links}</small>'
        cells, plain_steps, technical_steps = [], [], []
        for phase_key, (plain_label, technical_label, help_text) in MILESTONES.items():
            phase = task["milestones"][phase_key]
            badge = signal(phase["state"])
            cells.append(f'<td data-label="{plain_label}">{badge}</td>')
            plain_steps.append(f'<li>{badge}<div><b>{plain_label}</b><span>{STATES[phase["state"]][0]}</span>'
                               f'<small>{help_text}</small></div></li>')
            technical_steps.append(
                f'<div class="phase">{badge}<div><b>{technical_label}</b><span><code>{phase["state"]}</code></span>'
                f'<small>{escape(phase["note"]) or "No note."} {proof_links(phase["evidence"])}</small></div></div>')
        rows[group].append(
            f'<tr id="row-{key}" data-work-state="{work["state"]}"><td class="task-cell" data-label="Item">'
            f'<button class="task-picker" data-task="{key}" aria-pressed="false" aria-haspopup="dialog">'
            f'<span>{escape(task["title"])}</span><small>{key}</small></button></td>'
            f'<td data-label="Status">{work_badge}</td>'
            f'<td data-label="What\'s happening" class="reason-cell">{story}</td>'
            + "".join(cells) + '</tr>'
        )
        lifecycle = "Complete, closure pending / unavailable" if owner["state"] == "complete" else owner["state"].capitalize()
        checked = owner.get("last_checked_at")
        resources = ", ".join(task["resources"]) or "None shared"
        dependencies = ", ".join(task["blocked_by"]) or "None"
        obligations = "; ".join(task["obligations"]) or "None outstanding"
        owner_link = anchor(owner.get("href"), owner["label"])
        technical = (
            f'<dt>Work state</dt><dd><code>{work["state"]}</code> · {escape(work["reason"])}</dd>'
            f'<dt>Blocker</dt><dd>{escape(task["blocker"] or "None")}</dd>'
            f'<dt>Next action</dt><dd>{escape(task["next_action"])}</dd>'
            f'<dt>Done when</dt><dd>{escape(task["done_when"])}</dd>'
            + (f'<dt>Decision receipt</dt><dd>{escape(work["receipt"])}</dd>' if work.get("receipt") else "")
            + (f'<dt>Outcome proof</dt><dd>{proof_links(work["evidence"])}</dd>' if work.get("evidence") else "")
            + f'<dt>Work owner</dt><dd>{owner_link} <code>{escape(owner["id"])}</code> · {lifecycle}'
            f'<small class="checked">{escape("Last checked " + checked if checked else "Check time not recorded")}</small></dd>'
            f'<dt>Work location</dt><dd>{escape(owner["location"])}</dd>'
            f'<dt>Resources</dt><dd>{escape(resources)}</dd><dt>Dependencies</dt><dd>{escape(dependencies)}</dd>'
            f'<dt>Obligations</dt><dd>{escape(obligations)}</dd>'
            f'<dt>Retained handoff</dt><dd>{escape(owner["handoff"] or "Not complete")}</dd>'
        )
        details.append(
            f'<details class="task-detail" id="task-{key}"{" open" if key == first else ""}><summary>{escape(task["title"])} <small>{key}</small></summary>'
            f'<section class="plain-view"><div class="work-outcome">{work_badge}<p>{escape(plain(work))}</p>'
            + (f'<p><b>We\'ll revisit:</b> {escape(work["revisit"])}</p>' if work.get("revisit") else "")
            + (f'<p><b>Waiting on your decision:</b> {decision_links}</p>' if related else "")
            + f'</div><ol class="steps" aria-label="Progress">{"".join(plain_steps)}</ol></section>'
            f'<section class="technical"><h3>Technical details</h3><dl class="tech-grid">{technical}</dl>'
            f'<h4>Milestones and evidence</h4>{"".join(technical_steps)}</section>'
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
            route = (anchor(href, "Answer in thread" if human else "Open discussion") if href
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
    total = len(tasks)
    done = counts["delivered"]
    closed_other = len(rows["resolved"]) - done
    segments = [("done", "Done", done), ("closed", "Wrapped up without delivery", closed_other),
                ("moving", "In progress", len(rows["moving"])), ("attention", "Needs attention", len(rows["attention"]))]
    meter = "".join(f'<span class="segment segment-{name}" style="flex-grow:{count}" title="{label}: {count}"></span>'
                    for name, label, count in segments if count)
    meter_legend = "".join(f'<li><i class="swatch segment-{name}" aria-hidden="true"></i><b>{count}</b> {label}</li>'
                           for name, label, count in segments if count)
    if total:
        headline = (f'<b>{len(rows["resolved"])} of {total}</b> items wrapped up'
                    f' <span class="headline-detail">· {done} done · {len(rows["moving"])} in progress · {len(rows["attention"])} need attention</span>')
    else:
        headline = "No items are assigned yet."
    callout = (f'<a class="callout" href="#decisions">{len(decisions)} decision{"s" if len(decisions) != 1 else ""} '
               f'need{"s" if len(decisions) == 1 else ""} your input →</a>' if decisions else "")
    replacements = {
        "TITLE": escape(data["title"]), "RUN_ID": escape(data["run_id"]),
        "GOAL": escape(data["goal"]), "UPDATED": escape(data["updated_at"]),
        "UPDATED_FRIENDLY": escape(friendly_time(updated)),
        "REFRESH_META": refresh_meta, "REFRESH_STATUS": refresh_status,
        "NOTICE": escape(data.get("notice", "")), "TASK_COUNT": str(total),
        "HEADLINE": headline, "CALLOUT": callout,
        "METER": meter or '<span class="segment segment-empty" style="flex-grow:1"></span>',
        "METER_LABEL": escape(", ".join(f"{count} {label.lower()}" for _, label, count in segments if count) or "No items"),
        "METER_LEGEND": meter_legend,
        "ACTIVE_COUNT": str(sum(state == "active" for state in owners.values())),
        "WAITING_COUNT": str(sum(state == "waiting" for state in owners.values())),
        "CLOSED_COUNT": str(sum(state == "closed" for state in owners.values())),
        "COMPLETE_STAT": (f'<div class="stat"><b>{sum(state == "complete" for state in owners.values())}</b><span>complete, not closed</span></div>'
                          if "complete" in owners.values() else ""),
        "WORK_COUNTS": "".join(f'<span class="work-status work-{state}"><b>{count}</b> {WORK_STATES[state][0]}</span>'
                                for state, count in counts.items() if count),
        "ROWS": "".join(f'<tbody class="group-{group}"><tr class="group-heading"><th scope="rowgroup" colspan="7">{label} ({len(rows[group])})</th></tr>'
                        + "".join(rows[group]) + '</tbody>' for group, label in GROUPS.items() if rows[group])
                or '<tbody><tr><td colspan="7">No items are assigned yet.</td></tr></tbody>',
        "MILESTONE_HEADERS": "".join(f'<th scope="col" title="{help_text}">{plain_label}</th>'
                                     for plain_label, _, help_text in MILESTONES.values()),
        "MILESTONE_KEY": "".join(f'<li><b>{plain_label}</b> {help_text}</li>' for plain_label, _, help_text in MILESTONES.values()),
        "DECISION_COUNT": str(len(decisions)),
        "DETAILS": "".join(details) or '<p>Select an item after one is assigned.</p>',
        "DECISIONS": "".join(decision_html) or '<p class="muted">Nothing needs your decision right now.</p>',
        "PROOFS": "".join(proofs) or '<p class="muted">No evidence retained yet.</p>',
        "HISTORY": "".join(f'<li>{escape(item)}</li>' for item in data["history"]) or '<li>No material changes recorded.</li>',
        "QUESTION": escape(question(tasks[first], "status") if first else f"In orchestration run {data['run_id']}: what work is assigned?"),
        "COORDINATOR": anchor(data["presentation"].get("coordinator_href"), "Open coordinator") if data["presentation"].get("coordinator_href") else "Paste into your coordinator conversation.",
        "INTERACTION": escape(data["presentation"].get("interaction", "")),
        "FIRST_TASK": first,
    }
    template = (Path(__file__).resolve().parent.parent / "assets" / "dashboard-template.html").read_text()
    return re.sub(r"\{\{([A-Z_]+)\}\}", lambda match: replacements[match[1]], template)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("status", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--hosted", action="store_true")
    args = parser.parse_args()
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
