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


MILESTONES = {
    "pr_readiness": "PR readiness",
    "code_publication": "Code publication",
    "deployment": "Deployment",
    "business_acceptance": "Business acceptance",
}
STATES = {
    "verified": ("Verified", "✓"),
    "pending": ("Pending", "…"),
    "blocked": ("Blocked", "!"),
    "not_requested": ("Not requested", "—"),
}


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
        if decision is not None:
            packet["decision"] = decision
            packet["answer_route"] = decision.get("discussion") or {
                "label": "Coordinator", "href": data["presentation"].get("coordinator_href", "")}
        elif task_ids:
            owner = tasks[task_ids[0]]["owner"]
            packet["answer_route"] = {"owner_id": owner["id"], "label": owner["label"], "href": owner.get("href", "")}
        return escape(json.dumps(packet, indent=2, ensure_ascii=False), quote=True)

    def issue_data(task):
        states = "".join(f'<dt>{label}</dt><dd>{STATES[task["milestones"][key]["state"]][0]}</dd>'
                         for key, label in MILESTONES.items())
        ids = dict.fromkeys(key for phase in task["milestones"].values() for key in phase["evidence"])
        return (f'<section class="issue-data"><h3>{task["id"]} · {escape(task["title"])}</h3><dl>'
                f'<dt>Work owner</dt><dd>{escape(task["owner"]["label"])} · {task["owner"]["state"]}</dd>'
                + states + f'<dt>Blocker</dt><dd>{escape(task["blocker"] or "None")}</dd>'
                f'<dt>Next action</dt><dd>{escape(task["next_action"])}</dd>'
                f'<dt>Retained proof</dt><dd>{proof_links(ids) or "None retained"}</dd></dl></section>')

    def question(task, subject):
        if subject == "proof":
            ids = dict.fromkeys(key for phase in task["milestones"].values() for key in phase["evidence"])
            text = f"What does retained proof {', '.join(ids) or 'for this task'} establish, and what remains unverified?"
        else:
            text = "What is the blocker and next action, and does anything need my decision?"
        return f"In orchestration run {data['run_id']}, task {task['id']}: {text}"

    first = next((task["id"] for task in tasks.values() if task["blocker"]), next(iter(tasks), ""))
    rows, details = [], []
    for task in tasks.values():
        key = task["id"]
        owner = task["owner"]
        cells, phases = [], []
        for phase_key, label in MILESTONES.items():
            phase = task["milestones"][phase_key]
            state, symbol = STATES[phase["state"]]
            badge = f'<span class="signal {phase["state"]}" role="img" aria-label="{state}" title="{state}">{symbol}</span>'
            cells.append(f'<td data-label="{label}">{badge}</td>')
            phases.append(f'<div class="phase">{badge}<div><b>{label}</b><span>{state}</span><small>{escape(phase["note"])} {proof_links(phase["evidence"])}</small></div></div>')
        rows.append(
            f'<tr id="row-{key}"><td class="task-cell" data-label="Task"><button class="task-picker" data-task="{key}" aria-pressed="false">'
            f'<b>{key}</b><span>{escape(task["title"])}</span></button></td>'
            f'<td data-label="Owner">{anchor(owner.get("href"), owner["label"])}<small class="lifecycle">{owner["state"].capitalize()}</small></td>'
            + "".join(cells) + '</tr>'
        )
        resources = ", ".join(task["resources"]) or "None shared"
        dependencies = ", ".join(task["blocked_by"]) or "None"
        obligations = "; ".join(task["obligations"]) or "None outstanding"
        details.append(
            f'<details class="task-detail" id="task-{key}"{" open" if key == first else ""}><summary>{key} · {escape(task["title"])}</summary>'
            f'<div class="detail-heading"><span>{escape(owner["label"])} · {owner["state"].capitalize()}</span>'
            f'<button class="quiet" data-copy-id="{key}">Copy ID</button></div>'
            f'<div class="question-options"><button data-question="{escape(question(task, "status"), quote=True)}">Prepare status question</button>'
            f'<button data-question="{escape(question(task, "proof"), quote=True)}">Prepare proof question</button></div>'
            f'<div class="blocker"><b>Blocker</b><p>{escape(task["blocker"] or "None")}</p></div>'
            f'<div class="next"><b>Next action</b><p>{escape(task["next_action"])}</p></div>'
            + "".join(phases)
            + f'<details class="assignment"><summary>Assignment and resources</summary><dl><dt>Done when</dt><dd>{escape(task["done_when"])}</dd>'
            f'<dt>Work location</dt><dd>{escape(owner["location"])}</dd><dt>Resources</dt><dd>{escape(resources)}</dd>'
            f'<dt>Dependencies</dt><dd>{escape(dependencies)}</dd><dt>Obligations</dt><dd>{escape(obligations)}</dd>'
            f'<dt>Retained handoff</dt><dd>{escape(owner["handoff"] or "Not complete")}</dd></dl></details>'
            f'<div class="share-actions"><button data-discussion-owner="{escape(owner["id"], quote=True)}" '
            f'data-discussion-label="{escape(owner["label"], quote=True)}" data-discussion-href="{link(owner.get("href", ""), hosted)}" '
            f'data-context="{context_packet([key])}">Copy context for agent</button>'
            f'{anchor(owner.get("href"), "Open work owner conversation") if owner.get("href") else escape(owner["label"] + " (" + owner["id"] + ")")}'
            '<small>Copy, then paste into this owner\'s existing conversation. Copy does not send.'
            + (' No direct link is configured.' if not owner.get("href") else "")
            + '</small><p class="share-feedback" role="status" aria-live="polite"></p></div>'
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
            raise ValueError(f"{item['id']}: unknown affected task")
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
        decision_html.append(
            f'<article class="decision" id="decision-{item["id"]}"><div class="decision-preview">'
            f'<button class="decision-picker" data-decision="{item["id"]}" aria-haspopup="dialog" aria-controls="decision-dialog">'
            f'<b>{item["id"]}</b><span>{escape(item["text"])}</span></button>'
            f'<small>{affected_links}{" · " if affected else ""}Unblocks: {escape(item.get("unblocks") or "Discuss the pending choice")}'
            f' · {escape(discussion.get("label", "Coordinator"))}{" · Human only" if human else ""}</small></div>'
            f'<button class="quiet" {attributes} data-decision="{item["id"]}" data-copy-id="{item["id"]}">Copy {item["id"]}</button>'
            f'<div class="decision-detail" data-decision="{item["id"]}" hidden><div class="context-columns"><section><p class="decision-question">{escape(item["text"])}</p>'
            f'<dl><dt>Recommendation</dt><dd>{escape(item["recommendation"])}</dd>'
            f'<dt>Affected tasks</dt><dd>{affected_links or "Run-level decision"}</dd>'
            f'<dt>An answer unblocks</dt><dd>{escape(item.get("unblocks") or "Discuss the pending choice")}</dd>'
            f'<dt>Answer destination</dt><dd>{escape(discussion.get("label", "Coordinator"))}</dd></dl>'
            + ('<p class="human-warning">Human-only gate. A forwarded message cannot answer it. '
               'You must answer the existing dialog yourself; copying cannot unlock it.</p>' if human else "")
            + '</section><section>' + "".join(issue_data(tasks[key]) for key in affected) + '</section></div>'
            + f'<div class="share-actions"><button {attributes} data-context="{context_packet(affected, item)}">Copy context for agent</button>{route}'
            + ('<small>Copying prepares context only. Answer the existing human-only dialog yourself.</small>' if human else
               '<small>Copy, then open the conversation and paste. Neither action sends a message.</small>')
            + '<p class="share-feedback" role="status" aria-live="polite"></p></div>'
              f'<div class="decision-actions"><button class="quiet" {attributes} data-copy-id="{item["id"]}">Copy ID</button>'
              f'<button class="quiet" {attributes} data-question="{escape(prompt, quote=True)}">Prepare {item["id"]} question</button></div></div></article>'
        )
    replacements = {
        "TITLE": escape(data["title"]), "RUN_ID": escape(data["run_id"]),
        "GOAL": escape(data["goal"]), "UPDATED": escape(data["updated_at"]),
        "NOTICE": escape(data.get("notice", "")), "TASK_COUNT": str(len(tasks)),
        "ACTIVE_COUNT": str(sum(state == "active" for state in owners.values())),
        "WAITING_COUNT": str(sum(state == "waiting" for state in owners.values())),
        "CLOSED_COUNT": str(sum(state == "closed" for state in owners.values())),
        "COMPLETE_STAT": (f'<div class="stat"><b>{sum(state == "complete" for state in owners.values())}</b><span>complete, not closed</span></div>'
                          if "complete" in owners.values() else ""),
        "ROWS": "".join(rows) or '<tr><td colspan="6">No assigned tasks.</td></tr>',
        "DETAILS": "".join(details) or '<p>Select a task after one is assigned.</p>',
        "DECISIONS": "".join(decision_html) or '<p class="muted">Nothing needs your decision.</p>',
        "PROOFS": "".join(proofs) or '<p class="muted">No retained proof yet.</p>',
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
