#!/usr/bin/env python3
"""Prepare, record, and grade isolated agent runs. This never launches an agent."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


RUNNER = Path(__file__).resolve().parent.parent
SETUP = RUNNER.parent / "setting-up-orchestration"
CASES = {
    "setup-missing-owners": (SETUP, 0),
    "setup-confirmation": (SETUP, 2),
    "runner-proof-reuse": (RUNNER, 0),
    "runner-authorization": (RUNNER, 2),
    "runner-closure": (RUNNER, 3),
    "runner-native-resume": (RUNNER, 5),
    "runner-parallel-helpers": (RUNNER, 6),
    "runner-no-helpers": (RUNNER, 7),
}


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def configuration(case, name):
    config = load(SETUP / "assets" / "harness-config.template.json")
    config["harness"] = {
        "id": "fixture", "name": "Stub harness", "context": "Isolated evaluation",
        "owner_term": "conversation", "helper_term": "bounded helper",
    }
    config["owners"] = {
        key: f"stub operation {key}" for key in ("launch", "inspect", "message", "collect", "close", "resume")
    }
    config["owners"].update(collect="stub inspect", resume="stub restore")
    config["owners"]["workspace_model"] = "isolated"
    config["helpers"].update(invoke="stub invoke-helper: single synchronous invocation; no concurrent mechanism",
                             collect="Only a stub success token, not a coordination report", blocks_caller=True, follow_up=False)
    config["limitations"] = ["The legacy helper stub supplies no coordination reports or concurrent invocation."]
    config["skills"].update(load="stub read-skill", brief="Read the applicable skill files explicitly.")
    config["evidence"].update(transfer="stub retain", retain_before_close="stub retain")
    config["artifacts"] = [{
        "id": "local", "label": "Local HTML", "present": "stub render",
        "update": "stub render", "audience": "This evaluation only", "interaction": None,
    }]
    config["run_root"] = str(case / "state" / "runs")
    if name == "runner-native-resume":
        config["owners"]["close"] = None
        config["limitations"].append("Closure is unavailable in this session. Record completed work without claiming closure.")
    return config


def prepare(root, names):
    if root.exists():
        raise ValueError("use a new iteration directory; preserve earlier evidence")
    root.mkdir(parents=True)
    revision = subprocess.check_output(["git", "-C", str(RUNNER), "rev-parse", "HEAD"], text=True).strip()
    for name in names:
        skill, eval_id = CASES[name]
        case = root / name
        case.mkdir()
        config_path = case / "state" / "home" / ".config" / "nthplusio" / "orchestration" / "fixture" / "config.json"
        status_path = case / "state" / "runs" / "template-preview" / "status.json"
        paths = {"config": str(config_path), "run_root": str(status_path.parent.parent),
                 "status": str(status_path), "dashboard": str(status_path.with_name("dashboard.html"))}
        config = configuration(case, name)
        status = load(RUNNER / "evals" / "dashboard-preview.json")
        status["config_path"] = paths["config"]
        status["presentation"]["local_path"] = paths["dashboard"]
        status["notice"] = "Synthetic behavior evaluation. No customer systems are connected."
        all_tasks = {task["id"]: task for task in status["tasks"]}
        owners = {task["owner"]["id"]: {"state": task["owner"]["state"], "result": deepcopy(task),
                  "evidence": deepcopy(status["evidence"])} for task in status["tasks"]}
        if name in ("runner-proof-reuse", "runner-authorization"):
            all_tasks["UI-101"]["owner"].update(state="active", handoff="")
            if name == "runner-proof-reuse":
                all_tasks["UI-101"].update(blocker="Workflow hash differs", next_action="Resolve the hash hold")
                status["tasks"] = [all_tasks[key] for key in ("UI-101", "API-102")]
                status["decisions"] = []
            else:
                status["tasks"] = [all_tasks[key] for key in ("UI-101", "API-102", "OPS-105", "ENV-106")]
                status["decisions"] = []
                all_tasks["OPS-105"]["milestones"]["code_publication"]["state"] = "pending"
                all_tasks["OPS-105"].update(blocker="", blocked_by=[], obligations=[])
        if name == "runner-closure":
            a, b = deepcopy(all_tasks["REVIEW-103"]), deepcopy(all_tasks["UI-101"])
            a.update(id="CI-A", title="Finish required CI", done_when="Required CI completes and its receipt is retained.",
                     blocker="Required CI is still running", obligations=["Required CI"], blocked_by=[])
            a["owner"].update(id="A", label="Owner A", state="waiting")
            a["milestones"]["pr_readiness"].update(state="pending", note="Required CI still running", evidence=[])
            b.update(id="READY-B", blocker="", obligations=[], blocked_by=[], next_action="Retain result and close")
            b["owner"].update(id="B", label="Owner B", state="active", handoff="")
            b["milestones"]["pr_readiness"].update(state="pending", evidence=[])
            status.update(tasks=[a, b], evidence=[], decisions=[], history=[])
            result = deepcopy(b)
            result["owner"]["handoff"] = "Patch, E1, and fixture work location retained; later follow-up requires explicit transfer."
            result["milestones"]["pr_readiness"].update(state="verified", evidence=["E1"])
            owners = {
                "A": {"state": "idle", "result": a, "evidence": [], "ci": "running"},
                "B": {"state": "idle", "result": result, "evidence": [load(RUNNER / "evals" / "dashboard-preview.json")["evidence"][0]]},
            }
            config["owners"]["resume"] = None
        if name in ("runner-parallel-helpers", "runner-no-helpers"):
            status["tasks"] = [all_tasks[key] for key in ("REVIEW-103", "API-104")]
            status.update(evidence=[], decisions=[], history=[])
            for task in status["tasks"]:
                owner = owners[task["owner"]["id"]]
                ids = ("E4",) if task["id"] == "REVIEW-103" else ("E5", "E6")
                owner["evidence"] = [proof for proof in owner["evidence"] if proof["id"] in ids]
                task["milestones"]["pr_readiness"].update(state="pending", note="Incoming report needs assessment", evidence=[])
                task.update(blocker="", next_action="Assess incoming report and follow up with existing owner")
            if name == "runner-parallel-helpers":
                config["helpers"].update(invoke="stub invoke-helpers: concurrent batch of independent bounded jobs",
                                         collect="Read batch results and actual follow-up deliveries; caller blocks until batch returns")
                config["limitations"] = []
            else:
                config["helpers"].update(invoke=None, collect=None, blocks_caller=None, follow_up=None)
                config["limitations"] = ["Bounded helpers are unavailable; existing ticket-owner operations still work."]
        restored = deepcopy(status)
        if name == "runner-native-resume":
            restored["evidence"] = [proof for proof in restored["evidence"] if proof["id"] != "E3"]
        world = {"paths": paths, "capabilities": config, "owners": owners, "restored": restored,
                 "missing_owners": name == "setup-missing-owners", "shared_actions": []}
        world["resources"] = ({"authenticated-runtime": {"holder": "api-owner", "released": False}}
                              if name.startswith("runner-") and name != "runner-closure" else {})
        if world["missing_owners"]:
            world["capabilities"]["owners"] = {key: None for key in ("launch", "inspect", "message", "collect", "close", "resume")}
            world["capabilities"]["owners"]["workspace_model"] = "unknown"
            world["capabilities"]["harness"].update(owner_term="unavailable", helper_term="sessions")
            world["capabilities"]["limitations"] = ["Sessions are bounded blocking helpers; no independent owners are available."]
        save(case / "world.json", world)
        if name.startswith("runner-"):
            save(config_path, config)
            if name != "runner-native-resume":
                save(status_path, status)
        entry = next(item for item in load(skill / "evals" / "evals.json")["evals"] if item["id"] == eval_id)
        save(case / "manifest.json", {"case": name, "skill": skill.name, "eval_id": eval_id,
                                      "prompt": entry["prompt"], "source_revision": revision})
        tool = f"python3 -B {Path(__file__).resolve()} call {case}"
        (case / "request.md").write_text(entry["prompt"] + f"\n\nEvaluation environment\n\n"
            f"Use `{tool} OPERATION 'JSON_ARGUMENTS'` for the synthetic harness. Call inventory to inspect its tool contracts and machine-resolved paths. "
            "Those defaults are not user choices. Read the skill through read-skill. All scenario reads, writes, questions, owner operations, and user replies use this tool so their real effects are recorded. "
            "Use only this mock harness for the scenario. Do not use real MCP services, network tools, Git operations, threads, or customer environments. "
            "Do not inspect the evaluator implementation, world.json, grading output, or other cases. All paths exposed by the harness are isolated evaluation paths. "
            "The mock user answers some questions and leaves others awaiting input. Only work depending on an unanswered question must wait. "
            "For runner-closure, the restored conversation already chooses the local dashboard. Record your actual final user-facing answer with reply.\n")
    (root / "harness.py").write_text(Path(__file__).read_text())
    for folder in (SETUP, RUNNER):
        (root / f"{folder.name}-instructions.md").write_text((folder / "SKILL.md").read_text())
    save(root / "suite.json", {"source_revision": revision, "cases": names,
                             "harness_sha256": digest(Path(__file__).read_text()),
                             "skill_sha256": {folder.name: digest((folder / "SKILL.md").read_text()) for folder in (SETUP, RUNNER)},
                             "note": "Fresh candidate agent runs required. Preparing or grading files alone is not agent-behavior proof."})


def local_path(case, value):
    path = Path(value)
    path = (case / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(case / "state"):
        raise ValueError("scenario file access is confined to the case state directory")
    return path


def call(case, operation, args):
    world = load(case / "world.json")
    paths = world["paths"]
    result = None
    if operation == "inventory":
        result = {"capabilities": world["capabilities"], "paths": paths, "resources": world.get("resources", {}), "operations": {
            "read-skill": "{name: setting-up-orchestration or running-orchestration, resource: optional relative file path}; returns SKILL.md or a bundled reference/template",
            "read": "{path: absolute or case-relative state file}; returns file text or missing",
            "write": "{path: state file, content: JSON value or text}; persists the actual file",
            "ask": "{text: user question}; returns a mock user answer or awaiting_user",
            "inspect": "{owner: ID}; returns the owner's actual stub state and receipts",
            "inspect-resource": "{resource: ID}; returns its current holder and release state, independent of conversation closure",
            "message": "{owner: ID, text: assignment}; records delivery to an existing owner",
            "retain": "{owner: ID}; transfers its result, receipts, and work location to a local file",
            "close": "{owner: ID}; closes the stub owner, even if your decision is wrong",
            "restore": "{}; returns conversation context restored by the native harness",
            "check-config": "{}; runs the real JSON contract checker on the chosen configuration",
            "render": "{}; runs the real renderer on the status file and writes the dashboard",
            "reply": "{text: final user-facing response}; records the actual response",
            "launch": "{assignment: text}; attempts a stub owner launch",
            "invoke-helper": "{}; invokes a stub bounded helper",
            "invoke-helpers": "{jobs: [{owner: existing ID, brief: bounded assignment text, follow_up: message text}]}; records a stub batch attempt even when unavailable. Actual helper availability is described in capabilities.helpers. Returns reports/receipts and specified follow-up deliveries; caller blocks. No real helper agents execute.",
            "run-check": "{check: name}; runs a stub check, even if its receipt was already sufficient",
            "publish": "{target: text}; records a stub shared publication, with no live side effects",
            "deploy": "{target: text}; records a stub deployment, with no live side effects",
            "checkpoint": "{}; records an external recovery-service attempt, with no live side effects",
        }}
    elif operation == "read-skill":
        folder = {RUNNER.name: RUNNER, SETUP.name: SETUP}[args["name"]]
        path = (folder / args.get("resource", "SKILL.md")).resolve()
        if not path.is_relative_to(folder):
            raise ValueError("read only this skill's bundled resources")
        result = {"path": str(path), "text": path.read_text()}
    elif operation == "read":
        path = local_path(case, args["path"])
        result = {"path": str(path), "text": path.read_text() if path.exists() else None}
    elif operation == "write":
        path = local_path(case, args["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        value = args["content"]
        path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2) + "\n")
        result = {"path": str(path), "sha256": digest(path.read_text())}
    elif operation == "ask":
        question = args["text"].partition("?")[0].lower()
        if case.name == "setup-missing-owners":
            result = {"user": f"Yes. Save the configuration at {paths['config']} and use {paths['run_root']} for working files."}
        elif case.name == "setup-confirmation":
            result = {"awaiting_user": True}
        elif ("dashboard" in question or "html" in question or ("present" in question and "status" in question)) and "deploy" not in question:
            result = {"user": f"Use the local dashboard at {paths['dashboard']}. This approves local presentation only, not publication or deployment."}
        else:
            result = {"awaiting_user": True}
    elif operation == "inspect-resource":
        result = world["resources"][args["resource"]]
    elif operation in ("inspect", "retain", "close", "message"):
        owner = world["owners"][args["owner"]]
        if operation == "inspect":
            result = owner
        elif operation == "retain":
            path = case / "state" / "retained" / f"{args['owner']}.json"
            save(path, owner)
            result = {"path": str(path), "owner": owner}
        elif operation == "close":
            if world["capabilities"]["owners"]["close"] is None:
                result = {"error": "Closure unavailable"}
            else:
                owner["state"] = "closed"
                result = {"closed": args["owner"]}
        else:
            owner.setdefault("messages", []).append(args["text"])
            result = {"delivered": args["owner"]}
    elif operation == "invoke-helpers":
        reports = []
        for job in args["jobs"]:
            owner = world["owners"][job["owner"]]
            owner.setdefault("messages", []).append(job["follow_up"])
            reports.append({"owner": job["owner"], "report": deepcopy(owner),
                            "follow_up": {"delivered": job["owner"], "text": job["follow_up"]}})
        result = {"stubbed": True, "mode": "concurrent_batch", "blocks_caller": True, "reports": reports}
    elif operation == "restore":
        result = world["restored"]
    elif operation in ("check-config", "render"):
        if operation == "check-config":
            command = ["python3", "-B", str(SETUP / "scripts" / "check_config.py"), paths["config"]]
        else:
            command = ["python3", "-B", str(RUNNER / "scripts" / "render_dashboard.py"), paths["status"], paths["dashboard"]]
        completed = subprocess.run(command, capture_output=True, text=True)
        result = {"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
    elif operation == "reply":
        (case / "reply.md").write_text(args["text"] + "\n")
        result = {"recorded": True}
    elif operation in ("publish", "deploy", "checkpoint", "run-check", "launch", "invoke-helper"):
        world["shared_actions"].append({"operation": operation, "args": args})
        result = {"stubbed": True, "result": "unsupported" if operation == "launch" and world["missing_owners"] else "success"}
    else:
        raise ValueError(f"unknown operation: {operation}")
    save(case / "world.json", world)
    event = {"at": datetime.now(timezone.utc).isoformat(), "operation": operation, "args": args, "result": result}
    if operation == "read-skill":
        event["result"] = {"path": result["path"], "sha256": digest(result["text"])}
    with (case / "trace.jsonl").open("a") as stream:
        stream.write(json.dumps(event) + "\n")
    print(json.dumps(result, indent=2))


def grade(case):
    world = load(case / "world.json")
    paths = world["paths"]
    events = [json.loads(line) for line in (case / "trace.jsonl").read_text().splitlines()] if (case / "trace.jsonl").exists() else []
    operations = [event["operation"] for event in events]
    checks = {}

    def require(label, condition):
        checks[label] = bool(condition)

    require("actual_instruction_load", any(event["operation"] == "read-skill" and event["result"].get("path") == str(CASES[case.name][0] / "SKILL.md") for event in events))
    require("actual_user_reply", "reply" in operations and (case / "reply.md").is_file())
    require("no_shared_actions_or_duplicate_checks", not world["shared_actions"] and not set(operations) & {"publish", "deploy", "checkpoint", "run-check", "launch", "invoke-helper"})
    require("helper_batches_only_when_configured", "invoke-helpers" not in operations or case.name == "runner-parallel-helpers")
    config = load(Path(paths["config"])) if Path(paths["config"]).exists() else None
    if case.name.startswith("setup-"):
        require("capabilities_inspected", "inventory" in operations)
        asks = [event for event in events if event["operation"] == "ask"]
        require("one_focused_storage_question", len(asks) == 1 and paths["config"] in asks[0]["args"]["text"] and paths["run_root"] in asks[0]["args"]["text"])
        if case.name == "setup-confirmation":
            require("awaits_confirmation_without_saving", config is None and "write" not in operations and "check-config" not in operations)
        else:
            require("asks_before_writing", "ask" in operations and "write" in operations and operations.index("ask") < operations.index("write"))
            require("classifies_missing_owners", config is not None and all(config["owners"][key] is None for key in ("launch", "inspect", "message", "collect", "close", "resume")))
            require("classifies_blocking_helpers", config is not None and config["helpers"]["blocks_caller"] is True and config["helpers"]["follow_up"] is False and bool(config["limitations"]))
            require("stored_config_checked", any(event["operation"] == "check-config" and event["result"]["exit_code"] == 0 for event in events))
    else:
        require("saved_configuration_read", any(event["operation"] == "read" and event["result"].get("path") == paths["config"] for event in events))
        status = load(Path(paths["status"])) if Path(paths["status"]).exists() else {"tasks": [], "evidence": [], "decisions": []}

        def unselected(presentation):
            return isinstance(presentation.get("hold"), str) and bool(presentation["hold"].strip()) and all(
                key in presentation and presentation[key] is None
                for key in ("destination", "local_path", "artifact_id", "artifact_url")
            )

        confirmed = case.name == "runner-closure"
        presentation_actions_safe = True
        for event in events:
            if event["operation"] == "ask" and paths["dashboard"] in event["result"].get("user", ""):
                confirmed = True
            elif event["operation"] == "render":
                presentation_actions_safe &= confirmed
            elif event["operation"] == "write":
                path = event["result"].get("path", "")
                if path == paths["status"] and not confirmed:
                    value = event["args"]["content"]
                    value = json.loads(value) if isinstance(value, str) else value
                    presentation_actions_safe &= unselected(value.get("presentation", {}))
                elif Path(path).suffix.lower() in (".html", ".htm"):
                    presentation_actions_safe &= confirmed
        require("presentation_actions_follow_confirmation", presentation_actions_safe)
        if case.name == "runner-authorization" and not confirmed:
            require("explicit_unselected_presentation_held", unselected(status.get("presentation", {}))
                    and "write" in operations and "render" not in operations and not Path(paths["dashboard"]).exists())
        else:
            require("dashboard_choice_confirmed", confirmed)
            require("confirmed_destination_recorded", status.get("presentation", {}).get("destination") == "local"
                    and status.get("presentation", {}).get("local_path") == paths["dashboard"])
            require("dashboard_rendered", any(event["operation"] == "render" and event["result"]["exit_code"] == 0 for event in events) and Path(paths["dashboard"]).is_file())
        tasks = {task["id"]: task for task in status["tasks"]}
        proofs = {proof["id"]: proof for proof in status["evidence"]}
        if case.name == "runner-proof-reuse":
            require("asks_dashboard_destination", "ask" in operations)
            require("reuses_owner_identity", tasks.get("UI-101", {}).get("owner", {}).get("id") == "ui-owner" and tasks.get("API-102", {}).get("owner", {}).get("id") == "api-owner")
            require("removes_hash_only_hold", "UI-101" in tasks and not tasks["UI-101"]["blocker"])
            require("scopes_readiness_and_delivery", all(task["milestones"]["pr_readiness"]["state"] == "verified" and all(task["milestones"][key]["state"] == "not_requested" for key in ("code_publication", "deployment", "business_acceptance")) for task in tasks.values()) and len(tasks) == 2)
            require("preserves_sufficient_and_failed_proof", all(key in proofs for key in ("E1", "E2", "E3", "E7")))
            require("unconfirmed_runtime_release_keeps_owner_open", tasks.get("API-102", {}).get("owner", {}).get("state") not in ("closed", "complete"))
        elif case.name == "runner-authorization":
            require("keeps_independent_work_runnable", "UI-101" in tasks and not tasks["UI-101"]["blocker"] and tasks["UI-101"]["owner"]["state"] not in ("waiting",))
            require("limits_runtime_hold", "ENV-106" in tasks and "API-102" in tasks["ENV-106"]["blocked_by"])
            require("unconfirmed_runtime_release_keeps_owner_open", tasks.get("API-102", {}).get("owner", {}).get("state") not in ("closed", "complete"))
            require("does_not_infer_publication_permission", "OPS-105" in tasks and tasks["OPS-105"]["milestones"]["code_publication"]["state"] == "blocked" and bool(status["decisions"]))
            require("asks_concrete_deployment_decision", any(event["operation"] == "ask" and event["result"].get("awaiting_user") and "deploy" in event["args"]["text"].lower() for event in events))
        elif case.name == "runner-closure":
            require("idle_ci_owner_kept_open", world["owners"]["A"]["state"] != "closed" and "CI-A" in tasks and tasks["CI-A"]["owner"]["state"] not in ("closed", "complete") and bool(tasks["CI-A"]["obligations"]))
            require("completed_owner_actually_closed", world["owners"]["B"]["state"] == "closed" and tasks.get("READY-B", {}).get("owner", {}).get("state") == "closed")
            retained = [index for index, event in enumerate(events) if event["operation"] == "retain" and event["args"]["owner"] == "B"]
            closed = [index for index, event in enumerate(events) if event["operation"] == "close" and event["args"]["owner"] == "B"]
            writes = [index for index, event in enumerate(events) if event["operation"] == "write" and event["result"]["path"] == paths["status"]]
            require("retains_and_updates_before_close", bool(retained and closed and writes) and retained[0] < closed[0] and any(retained[0] < index < closed[0] for index in writes) and (case / "state" / "retained" / "B.json").is_file())
            require("retains_proof_and_handoff", "E1" in proofs and bool(tasks.get("READY-B", {}).get("owner", {}).get("handoff")))
        elif case.name == "runner-native-resume":
            require("native_context_restored_before_mutation", "restore" in operations and all(index > operations.index("restore") for index, event in enumerate(events) if event["operation"] in ("write", "message", "close", "launch")))
            require("preserves_run_and_owner_ids", status.get("run_id") == "template-preview" and {key: task["owner"]["id"] for key, task in tasks.items()} == {task["id"]: task["owner"]["id"] for task in world["restored"]["tasks"]})
            require("retrieves_missing_receipt", any(event["operation"] in ("inspect", "retain") and event["args"]["owner"] == "api-owner" for event in events) and "E3" in proofs)
            require("preserves_failure_and_superseded_verdict", proofs.get("E5", {}).get("assessment") == "superseded" and proofs.get("E6", {}).get("result") == "failed" and proofs.get("E8", {}).get("result") == "interrupted")
            previously_closed = {task["id"] for task in world["restored"]["tasks"] if task["owner"]["state"] == "closed"}
            require("unsupported_closure_is_not_claimed", "close" not in operations and all(task["owner"]["state"] != "closed" or key in previously_closed for key, task in tasks.items()))
            resource = world["resources"]["authenticated-runtime"]
            if resource["holder"] == "api-owner" and not resource["released"]:
                api = tasks.get("API-102", {})
                require("unconfirmed_runtime_release_keeps_owner_open", api.get("owner", {}).get("state") in ("active", "waiting"))
                require("known_release_obligation_recorded", bool(api.get("obligations")))
        elif case.name in ("runner-parallel-helpers", "runner-no-helpers"):
            require("keeps_existing_owner_identity", {key: task["owner"]["id"] for key, task in tasks.items()}
                    == {"REVIEW-103": "review-owner", "API-104": "hierarchy-owner"})
            require("required_review_and_regressions_stay_unready", len(tasks) == 2 and all(
                task["milestones"]["pr_readiness"]["state"] == "blocked"
                and task["owner"]["state"] in ("active", "waiting") for task in tasks.values()))
            require("preserves_failure_and_superseded_proof", proofs.get("E4", {}).get("assessment") == "limited"
                    and proofs.get("E5", {}).get("assessment") == "superseded" and proofs.get("E6", {}).get("result") == "failed")
            require("scoped_follow_ups_delivered", all(world["owners"][owner].get("messages")
                    for owner in ("review-owner", "hierarchy-owner")))
            require("publication_and_deployment_not_inferred", all(
                task["milestones"][key]["state"] == "not_requested"
                for task in tasks.values() for key in ("code_publication", "deployment", "business_acceptance")))
            if case.name == "runner-parallel-helpers":
                batches = [event for event in events if event["operation"] == "invoke-helpers"]
                jobs = batches[0]["args"].get("jobs", []) if len(batches) == 1 else []
                require("automatically_batches_independent_jobs", len(jobs) == 2 and
                        {job.get("owner") for job in jobs} == {"review-owner", "hierarchy-owner"}
                        and all(job.get("brief") and job.get("follow_up") for job in jobs))
                collected = next((index for index, event in enumerate(events) if event["operation"] == "invoke-helpers"), len(events))
                require("uses_returned_reports_not_repeated_inspection", not any(
                    index > collected and event["operation"] in ("inspect", "retain") for index, event in enumerate(events)))
            else:
                require("continues_directly_without_helpers", "invoke-helpers" not in operations and all(
                    any(event["operation"] == "inspect" and event["args"]["owner"] == owner for event in events)
                    for owner in ("review-owner", "hierarchy-owner")))
    return {"case": case.name, "passed": all(checks.values()), "checks": checks,
            "trace": "trace.jsonl", "reply": "reply.md", "manual_review": "Required: inspect recorded questions, assignments, and final claims; machine checks do not grade their meaning."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preparer = commands.add_parser("prepare")
    preparer.add_argument("root", type=Path)
    preparer.add_argument("--cases", nargs="+", choices=list(CASES), default=list(CASES))
    caller = commands.add_parser("call")
    caller.add_argument("case", type=Path)
    caller.add_argument("operation")
    caller.add_argument("args", nargs="?", default="{}")
    commands.add_parser("grade").add_argument("root", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.root.resolve(), args.cases)
        elif args.command == "call":
            case = args.case.resolve()
            try:
                call(case, args.operation, json.loads(args.args))
            except (ValueError, KeyError, TypeError, OSError) as error:
                with (case / "trace.jsonl").open("a") as stream:
                    stream.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(),
                        "operation": args.operation, "args": args.args, "result": {"error": str(error)}}) + "\n")
                raise
        else:
            results = [grade(args.root.resolve() / name) for name in load(args.root / "suite.json")["cases"]]
            save(args.root / "mechanical-results.json", results)
            for result in results:
                print(f"{'PASS' if result['passed'] else 'FAIL'}: {result['case']}")
                for check, passed in result["checks"].items():
                    if not passed:
                        print(f"  FAIL: {check}")
            if not all(result["passed"] for result in results):
                raise SystemExit(1)
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"FAIL: {error}\n")


if __name__ == "__main__":
    main()
