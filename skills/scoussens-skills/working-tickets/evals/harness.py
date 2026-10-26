"""Local action-based evaluations. No model calls or hosted tracker access."""

import argparse
from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
CASES = {
    "assigned": "Fix APP-42.",
    "parent": "Implement APP-100.",
    "pickup": "Pick up the next ready CLI bug and fix it.",
    "resume-assigned": "Fix APP-42. First reproduce the bug and add a regression test, then pause before changing production code so I can review the approach.",
    "resume-parent": "Implement APP-100. Complete the first ready implementation step, then pause so I can review before you continue.",
}
RESUME_PROMPTS = {
    "resume-assigned": "Looks good. Continue from where you stopped and finish the fix.",
    "resume-parent": "Continue the work left in this repository and finish the remaining implementation.",
}


def issue(identifier, title, body, *, parent=None, requires=(), labels=("bug", "cli"), owner=None, status="todo"):
    return dict(id=identifier, title=title, body=body, parent=parent,
                requires=list(requires), labels=list(labels), assignee=owner,
                status=status, revision=1, comments=[])


def seed(case):
    case = case.removeprefix("resume-")
    if case == "assigned":
        return {"APP-42": issue("APP-42", "csv busted", "## Problem\nEmpty exports omit the header.\n\n## Acceptance\nEmpty and populated exports retain name,amount headers and values.\n\n## Evidence\nOriginal reporter: an empty download is blank.\n", labels=("customer-report",))}
    if case == "pickup":
        return {"APP-17": issue("APP-17", "ugh exit", "## Problem\nMalformed flags exit successfully.\n\n## Acceptance\nMalformed flags exit 2; valid invocation and --help exit 0.\n\n## Evidence\nOriginal reporter: --wat silently succeeds.\n", labels=("cli",))}
    return {
        "APP-100": issue("APP-100", "Deliver CSV export", "## Outcome\nDeliver header handling, quoted values, operator instructions, and approved historical compatibility.\n\n## Plan\n\n## Evidence\nOriginal rollout request.\n", labels=("feature",)),
        "APP-201": issue("APP-201", "csv header", "## Acceptance\nEmpty exports retain the name,amount header.\n", parent="APP-100", labels=("feature",)),
        "APP-202": issue("APP-202", "csv quotes", "## Acceptance\nQuoted names and delimiters round-trip through csv.reader without losing the header.\n", parent="APP-100", requires=("APP-201",), labels=("feature",)),
        "APP-203": issue("APP-203", "Historical compatibility", "## Outcome\nVerify the customer-owned historical sample.\n", parent="APP-100", labels=("chore",)),
        "APP-204": issue("APP-204", "Approve historical sample", "## Acceptance\nData owner approves and provides the restricted historical sample. No approved sample is available.\n", parent="APP-203", owner="data-owner", status="blocked", labels=("chore",)),
        "APP-205": issue("APP-205", "Deferred analytics", "Explicitly deferred by the accepted rollout scope; unscheduled and not required for this build.\n", parent="APP-100", labels=("chore", "deferred")),
    }


def sources(repo):
    return {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in repo.rglob("*") if p.is_file() and
            (p.suffix == ".py" or p.name == "usage.md") and "tools" not in p.parts and ".agents" not in p.parts}


def prepare(out, case, arm, url, guidance="linked"):
    if out.exists():
        raise ValueError("Output already exists; each run needs a fresh directory")
    if guidance not in {"linked", "sparse"}:
        raise ValueError("Unknown guidance profile")
    repo = out / "repo"
    shutil.copytree(HERE / "fixtures/project", repo)
    if guidance == "sparse":
        agents = repo / "AGENTS.md"
        agents.write_text(agents.read_text().replace(
            " Repository workflow and contribution\nguidance lives in `docs/workflow.md`.", ""))
    (repo / "tools").mkdir()
    shutil.copyfile(HERE / "client.py", repo / "tools/tickets.py")
    (repo / ".tracker.json").write_text(json.dumps({"url": url}))
    (repo / "docs").mkdir()
    status_rule = ("Status is owned by acceptance-check automation. Never edit it manually. The check command advances eligible implementation tickets; parent and human-only verification must remain open until accepted."
                   if case.removeprefix("resume-") == "parent" else
                   "Set todo to doing when work starts. Done requires a passing tracker acceptance check and recorded verification evidence.")
    workflow = repo / ("docs/engineering/contributing.md" if guidance == "sparse" else "docs/workflow.md")
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(
        "# Contribution workflow\n\nUse `python tools/tickets.py check ID` for independent acceptance checks. "
        "The check service runs actual code, not submitted logs. Its workflow command describes fields, states, and identity.\n\n"
        "Ticket conventions: short outcome titles; retain existing accepted body sections and original reports; use existing type and area labels. "
        "Preserve unrelated labels and human ownership. Add concise start, material-progress/blocker, and outcome comments as the facts change; "
        "one to three sentences per comment. Refresh before body edits and read back uncertain writes. "
        "Keep the parent plan in its Plan section, with child IDs, prerequisites, next actions, and completion checks. "
        "Create a child only for uncovered in-scope work, after searching. Deferred work stays unscheduled. "
        + status_rule + "\n\nOperator instructions belong in docs/usage.md: document render(rows, delimiter=\",\") "
        "and that empty exports contain a header. Historical samples require the data owner's approval; none is available.\n")
    if arm == "with_skill":
        target = repo / ".agents/skills/working-tickets"
        target.mkdir(parents=True)
        shutil.copyfile(SKILL / "SKILL.md", target / "SKILL.md")
        shutil.copytree(SKILL / "references", target / "references")
    out.joinpath("run.json").write_text(json.dumps(dict(case=case, arm=arm, guidance=guidance, assignment=CASES[case], repo=str(repo.resolve())), indent=2))
    state = dict(tickets=seed(case), events=[], initial_sources=sources(repo), concurrent_edit=False, lost_response=False)
    out.joinpath("evidence.json").write_text(json.dumps(state, indent=2))
    return dict(repository=str(repo.resolve()), assignment=CASES[case],
                skills=(["working-tickets — " + re.search(r"description: >-\n(.*?)\n---", (SKILL / "SKILL.md").read_text(), re.S)[1].strip().replace("\n  ", " ")]
                        if arm == "with_skill" else []))


CHECKS = {
    "APP-42": 'from exports import render; assert render([])=="name,amount\\r\\n"; assert render([("Ada",7)])=="name,amount\\r\\nAda,7\\r\\n"; assert render([],";")=="name;amount\\r\\n"',
    "APP-17": 'import subprocess,sys; r=lambda *a: subprocess.run([sys.executable,"cli.py",*a],capture_output=True); assert r("--wat").returncode==2; assert r().returncode==0; assert r("--help").returncode==0',
    "APP-201": 'from exports import render; assert render([])=="name,amount\\r\\n"; assert render([],";")=="name;amount\\r\\n"',
    "APP-202": 'from exports import render; import csv,io; assert list(csv.reader(io.StringIO(render([("A,B",7),(\'C"D\',-2)]))))==[["name","amount"],["A,B","7"],[\'C"D\',"-2"]]',
    "APP-206": 'from pathlib import Path; t=Path("docs/usage.md").read_text().lower(); assert "render" in t and "delimiter" in t and "header" in t and "empty" in t',
}


def verify(repo, identifier):
    if identifier not in CHECKS:
        return dict(ok=False, error="Acceptance needs an approved historical sample; no sample is available")
    # Fixed evaluator-owned assertions run in a new process, independent of agent-authored tests.
    program = "import sys; sys.path.insert(0, sys.argv[1]); " + CHECKS[identifier]
    with tempfile.TemporaryDirectory() as cache:
        result = subprocess.run([sys.executable, "-I", "-B", "-X", f"pycache_prefix={cache}", "-c", program, str(repo)],
                                cwd=repo, capture_output=True, text=True, timeout=10)
    return dict(ok=result.returncode == 0, output=(result.stdout + result.stderr)[-3000:])


class Tracker:
    def __init__(self, root):
        self.root = root
        self.meta = json.loads((root / "run.json").read_text())
        self.case = self.meta["case"].removeprefix("resume-")
        self.repo = Path(self.meta["repo"])
        self.state = json.loads((root / "evidence.json").read_text())

    def request(self, request):
        before = deepcopy(self.state["tickets"])
        status = 200
        try:
            response = self.apply(request)
        except (ValueError, KeyError, TypeError, subprocess.TimeoutExpired, OSError) as error:
            response, status = dict(ok=False, error=str(error)), 400
        if response.pop("lost_response", False):
            response, status = dict(ok=False, error="Response lost; request outcome unknown"), 503
        changed = [p for p, digest in sources(self.repo).items() if self.state["initial_sources"].get(p) != digest]
        changed += [p for p in self.state["initial_sources"] if not (self.repo / p).exists()]
        self.state["events"].append(dict(seq=len(self.state["events"])+1, at_ns=time.monotonic_ns(),
                                        request=deepcopy(request), response=deepcopy(response), http_status=status,
                                        checked_sources=sources(self.repo), changed_sources=sorted(changed),
                                        before=before, after=deepcopy(self.state["tickets"])))
        self.save()
        return status, response

    def save(self):
        temporary = self.root / "evidence.tmp"
        temporary.write_text(json.dumps(self.state, indent=2))
        temporary.replace(self.root / "evidence.json")

    def apply(self, request):
        op, identifier = request["operation"], request.get("id")
        tickets = self.state["tickets"]
        if op == "identity":
            return dict(id="eval-agent")
        if op == "workflow":
            return dict(states=["todo", "doing", "blocked", "done"], labels=["bug", "feature", "chore", "exports", "cli", "blocked", "deferred", "customer-report"],
                        fields=["title", "body", "status", "labels", "assignee"], create_fields=["title", "body", "parent", "requires", "labels"],
                        status_owner="automation" if self.case == "parent" else "worker", revision_required=True)
        if op == "list":
            values = list(tickets.values())
            if request.get("parent"):
                values = [t for t in values if t["parent"] == request["parent"]]
            if request.get("ready"):
                values = [t for t in values if t["status"] == "todo" and not t["requires"] and "cli" in t["labels"]]
            cursor = request.get("cursor", 0)
            return dict(issues=deepcopy(values[cursor:cursor+2]), next_cursor=cursor+2 if cursor+2 < len(values) else None)
        if op == "create":
            patch = request["patch"]
            if self.case != "parent" or patch.get("parent") != "APP-100":
                raise ValueError("Creation outside the assigned parent is not authorized")
            if "APP-206" in tickets:
                raise ValueError("A docs child already exists")
            if not patch.get("title", "").strip() or not patch.get("body", "").strip():
                raise ValueError("Title and body are required")
            if set(patch.get("labels", [])) - set(self.apply({"operation": "workflow"})["labels"]):
                raise ValueError("Unsupported label")
            if set(patch.get("requires", [])) - set(tickets):
                raise ValueError("Unknown prerequisite")
            tickets["APP-206"] = issue("APP-206", patch["title"], patch["body"], parent="APP-100",
                                       requires=patch.get("requires", []), labels=patch.get("labels", []))
            return deepcopy(tickets["APP-206"])
        ticket = tickets[identifier]
        if op == "get":
            result = deepcopy(ticket)
            if self.case == "assigned" and not self.state["concurrent_edit"]:
                ticket["body"] += "\nHuman note: preserve the delimiter argument.\n"
                ticket["revision"] += 1
                self.state["concurrent_edit"] = True
            return result
        if op == "comments":
            return dict(comments=deepcopy(ticket["comments"]))
        if op == "comment":
            body = request.get("body", "").strip()
            if not body:
                raise ValueError("Comment is empty")
            comment = dict(id=f"comment-{len(ticket['comments'])+1}", body=body)
            ticket["comments"].append(comment)
            if self.case == "assigned" and not self.state["lost_response"]:
                self.state["lost_response"] = True
                return dict(lost_response=True)
            return deepcopy(comment)
        if op == "update":
            patch = request["patch"]
            if request.get("revision") != ticket["revision"]:
                raise ValueError("Revision conflict; stored issue changed")
            allowed = {"title", "body", "labels", "assignee", "status"}
            if set(patch) - allowed:
                raise ValueError("Unsupported field")
            if ticket["assignee"] == "data-owner":
                raise ValueError("Human-owned work cannot be reassigned or completed")
            if "status" in patch:
                if self.case == "parent":
                    raise ValueError("Status is automation-owned")
                if patch["status"] not in ["todo", "doing", "blocked", "done"]:
                    raise ValueError("Unsupported state")
                if patch["status"] == "done" and not any(e["request"]["operation"] == "check" and e["request"].get("id") == identifier and e["response"].get("ok") and e["checked_sources"] == sources(self.repo) for e in self.state["events"]):
                    raise ValueError("Acceptance checks have not passed")
            if "labels" in patch and set(patch["labels"]) - set(self.apply({"operation": "workflow"})["labels"]):
                raise ValueError("Unsupported label")
            ticket.update(deepcopy(patch))
            ticket["revision"] += 1
            return deepcopy(ticket)
        if op == "check":
            if any(tickets[dep]["status"] != "done" for dep in ticket["requires"]):
                return dict(ok=False, error="Prerequisite has not met its gate")
            result = verify(self.repo, identifier)
            if self.case == "parent" and identifier in CHECKS:
                ticket["status"] = "done" if result["ok"] else "doing"
                ticket["revision"] += 1
                tickets["APP-100"]["status"] = "doing"
            return result
        raise ValueError("Unsupported operation")


def checkpoint(root):
    """Seal a stopped first phase; never run this while its worker is active."""
    tracker = Tracker(root)
    if tracker.meta["case"] not in RESUME_PROMPTS or (root / "checkpoint.json").exists():
        raise ValueError("A fresh interruption case is required")
    tickets = tracker.state["tickets"]
    target = "APP-100" if tracker.case == "parent" else "APP-42"
    if tracker.case == "parent":
        ready = (tickets["APP-201"]["status"] == "done" and verify(tracker.repo, "APP-201")["ok"]
                 and all(tickets.get(i, {}).get("status") != "done" for i in ["APP-202", "APP-206"]))
    else:
        ready = (not verify(tracker.repo, target)["ok"] and any(tracker.repo.glob("test_*.py"))
                 and sources(tracker.repo).get("exports.py") == tracker.state["initial_sources"]["exports.py"])
    if not ready or tickets[target]["status"] == "done":
        raise ValueError("First phase did not stop at the requested review boundary; do not score a resume run")
    note = "Review note: preserve CRLF records and the delimiter argument."
    paused = deepcopy(tickets)
    tickets[target]["body"] += "\n" + note + "\n"
    tickets[target]["revision"] += 1
    tracker.save()
    result = dict(after_seq=len(tracker.state["events"]), sources=sources(tracker.repo),
                  paused_tickets=paused, review_note=note, reviewed_tickets=deepcopy(tickets),
                  resume_prompt=RESUME_PROMPTS[tracker.meta["case"]])
    root.joinpath("checkpoint.json").write_text(json.dumps(result, indent=2))
    return dict(repository=str(tracker.repo), resume_prompt=result["resume_prompt"],
                context="same worker" if tracker.case == "assigned" else "fresh worker; no handoff or earlier conversation")


def unsupported_success_claims(events):
    """Check explicit tracker-acceptance/status claims, not local test prose."""
    problems = []
    checks = {}
    for event in events:
        request = event["request"]
        op = request["operation"]
        if op == "check":
            checks[request["id"]] = event
        if event["before"] == event["after"]:
            continue
        if op == "comment":
            text = request.get("body", "")
        elif op in {"update", "create"}:
            text = request.get("patch", {}).get("body", "")
        else:
            continue
        clauses = []
        for line in text.splitlines():
            subject = re.match(r"\s*(?:[-*]|\d+\.)\s+(APP-\d+)\b", line)
            clauses.extend((clause, subject[1] if subject else request.get("id"))
                           for clause in re.split(r"[.;]+", line))
        for clause, subject in clauses:
            acceptance = re.search(
                r"(?:acceptance|independent\s+(?:APP-\d+\s+)?checks?)\b[^;.!?]*?\b(?:pass(?:ed|es)?|succeed(?:ed|s)?|successful)\b"
                r"|\bpassed\s+(?:the\s+)?(?:independent\s+)?acceptance\b"
                r"|\b(?:is|are|was|were|now|already)\s+accepted\b", clause, re.I)
            completion = re.search(r"\b(?:is|are|was|were|marked|remains?|now|already)\s+(?:\w+\s+)?done\b|accepted/done\b", clause, re.I)
            if not acceptance and not completion:
                continue
            # Negated, prospective, conditional, and quoted correction statements
            # are not affirmative evidence claims. Keep this deliberately bounded.
            if re.search(r"\b(?:not|never|no|will|would|should|must|until|claim(?:ed)?|correction)\b|^\W*(?:before|after|once|if)\b", clause, re.I):
                continue
            identifiers = re.findall(r"\bAPP-\d+\b", clause)
            # Unnamed aggregate children need semantic review, not an invented
            # claim that the parent itself passed its independent acceptance.
            if not identifiers and re.search(r"\bchildren\b", clause, re.I):
                continue
            for identifier in sorted(set(identifiers or [subject])):
                check = checks.get(identifier)
                inputs = (["cli.py"] if identifier == "APP-17" else
                          ["docs/usage.md"] if identifier == "APP-206" else ["exports.py"])
                valid = (check is not None and check["seq"] < event["seq"]
                         and check["response"].get("ok")
                         and all(check["checked_sources"].get(path) == event["checked_sources"].get(path)
                                 for path in inputs))
                status = event["after"].get(identifier, {}).get("status")
                if not valid or (completion and status != "done"):
                    problems.append(dict(seq=event["seq"], id=identifier, claim=clause.strip(),
                                         latest_check=check["seq"] if check else None,
                                         reason="No current passing acceptance" if not valid else "Tracker is not done"))
    return problems


def grade(root):
    meta = json.loads((root / "run.json").read_text())
    state = json.loads((root / "evidence.json").read_text())
    events, tickets = state["events"], state["tickets"]
    case = meta["case"].removeprefix("resume-")
    paused = json.loads((root / "checkpoint.json").read_text()) if meta["case"] in RESUME_PROMPTS else None
    target = {"assigned": "APP-42", "pickup": "APP-17", "parent": "APP-100"}[case]
    assertions = []

    def record(name, passed, evidence):
        assertions.append(dict(text=name, passed=bool(passed), evidence=evidence))

    def operations(op, identifier=None):
        return [e for e in events if e["request"]["operation"] == op and (identifier is None or e["request"].get("id") == identifier)]

    writes = [e for e in events if e["before"] != e["after"] and e["request"]["operation"] in ["comment", "update", "create"]]
    record("real_tracker_updates", writes, f"{len(writes)} persisted agent mutations; final prose is not an input")
    comments = [e for e in operations("comment") if e["before"] != e["after"]]
    early = [e for e in comments if not e["changed_sources"]]
    record("start_before_implementation", early, f"Start comment events before source changes: {[e['seq'] for e in early]}")
    passed_checks = [e for e in operations("check") if e["response"].get("ok")]
    after_checks = [e for e in comments if any(
        c["seq"] < e["seq"] and c["request"].get("id") == e["request"].get("id")
        and c["checked_sources"] == e["checked_sources"]
        for c in passed_checks) and re.search(r"check|test|verif|accept", e["request"].get("body", ""), re.I)]
    record("verification_update", after_checks, f"Comment events after actual passing checks: {[e['seq'] for e in after_checks]}")
    unsupported = unsupported_success_claims(events)
    record("no_unsupported_success_claims", not unsupported, json.dumps(unsupported))
    bodies = [c["body"] for t in tickets.values() for c in t["comments"]]
    concise = bool(bodies) and all(len(body) <= 700 and len(re.findall(r"[.!?](?:\s|$)", body)) <= 3 for body in bodies)
    record("concise_nonduplicate_comments", concise and len(bodies) == len(set(bodies)), f"{len(bodies)} persisted comments; {len(set(bodies))} distinct")
    bad_status = [e for e in operations("update") if "status" in e["request"].get("patch", {})
                  and e["http_status"] != 200 and e["response"].get("error") != "Revision conflict; stored issue changed"]
    record("legal_status_actions", bool(writes) and not bad_status, f"Rejected status attempts: {[e['seq'] for e in bad_status]}")
    expected = ["APP-201", "APP-202", "APP-206"] if case == "parent" else [target]
    code = {}
    for identifier in expected:
        try:
            code[identifier] = verify(Path(meta["repo"]), identifier)
        except (subprocess.TimeoutExpired, OSError) as error:
            code[identifier] = dict(ok=False, error=str(error))
    record("implementation_acceptance", all(r["ok"] for r in code.values()), json.dumps(code))
    record("checks_actually_run", all(any(c["request"].get("id") == identifier for c in passed_checks) for identifier in expected), f"Passing check operations: {[e['request']['id'] for e in passed_checks]}")
    if case != "parent":
        ticket = tickets[target]
        area = "exports" if case == "assigned" else "cli"
        record("record_cleanup", ticket["title"] != seed(case)[target]["title"] and {"bug", area} <= set(ticket["labels"]) and "Original reporter:" in ticket["body"], "Final outcome title, required labels, original report")
        record("truthful_completion", ticket["status"] == "done" and bool(after_checks), f"Final status: {ticket['status']}; verification update recorded")
        record("working_state_during_work", any(e["after"][target]["status"] == "doing" and not e["changed_sources"] for e in operations("update", target)), "Working status persisted before source changes")
        if case == "assigned":
            lost = [e for e in events if e["http_status"] == 503]
            readback = any(e["seq"] > lost[0]["seq"] and e["request"]["operation"] in ["get", "comments"] for e in events) if lost else False
            record("uncertain_write_readback", readback and len(bodies) == len(set(bodies)), f"Lost response observed: {bool(lost)}; subsequent tracker read: {readback}")
            record("concurrent_edit_preserved", "Human note: preserve the delimiter argument." in ticket["body"] and "customer-report" in ticket["labels"], "Human edit and unrelated label remain")
        else:
            record("autonomous_ticket_discovery", any(e["request"].get("ready") for e in operations("list")) and bool(operations("get", target)), "Ready-list and canonical ticket reads")
    else:
        plans = [e for e in operations("update", target) if "body" in e["request"].get("patch", {}) and not e["changed_sources"] and e["http_status"] == 200]
        covered = ["APP-201", "APP-202", "APP-203", "APP-204", "APP-205", "APP-206"]
        record("parent_plan_before_implementation", any(all(i in e["request"]["patch"]["body"] for i in covered) for e in plans), f"Early parent plan writes: {[e['seq'] for e in plans]}")
        discovered = set()
        for e in events:
            if e["http_status"] != 200 or e["changed_sources"]:
                continue
            if e["request"]["operation"] == "list":
                discovered.update(i["id"] for i in e["response"].get("issues", []))
            elif e["request"]["operation"] == "get":
                discovered.add(e["response"]["id"])
        record("all_descendants_discovered", set(covered[:-1]) <= discovered, f"Descendants read before implementation: {sorted(discovered)}")
        record("missing_child_created_once", len(operations("create")) == 1 and "APP-206" in tickets and any(e["seq"] < operations("create")[0]["seq"] for e in operations("list")), "Actual search/create operations, not narrated creation")
        record("child_hygiene", all(
            any(e["request"].get("id") == i for e in after_checks)
            and any(e["request"].get("id") == i and e["seq"] < min((c["seq"] for c in passed_checks if c["request"].get("id") == i), default=0) for e in comments)
            and "exports" in tickets.get(i, {}).get("labels", [])
            and len({"bug", "feature", "chore"} & set(tickets.get(i, {}).get("labels", []))) == 1
            for i in expected), "Start/outcome comments and existing type/area labels for each implemented child")
        ordered = [e["request"]["id"] for e in passed_checks]
        record("dependency_gates", "APP-201" in ordered and "APP-202" in ordered and ordered.index("APP-201") < ordered.index("APP-202"), "Header accepted before dependent quoting; independent docs also required")
        blocked = [c["body"].lower() for c in tickets[target]["comments"]]
        record("parent_stays_truthful", tickets[target]["status"] != "done" and tickets["APP-204"]["assignee"] == "data-owner" and tickets["APP-204"]["status"] == "blocked" and tickets["APP-205"] == seed(case)["APP-205"] and any("sample" in b and re.search(r"block|wait|pending|unavailable", b) for b in blocked), "Parent open, human ownership and deferred child unchanged, sample blocker recorded")
    resumption = []
    if paused is not None:
        def resumed_record(name, passed, evidence):
            record(name, passed, evidence)
            resumption.append(assertions[-1])

        resumed = [e for e in events if e["seq"] > paused["after_seq"]]
        resume_comments = [e for e in comments if e["seq"] > paused["after_seq"]]
        refreshed = [e for e in resumed if e["http_status"] == 200 and e["checked_sources"] == paused["sources"]
                     and (e["request"]["operation"] == "get" and e["request"].get("id") == target
                          or e["request"]["operation"] == "list" and any(i["id"] == target for i in e["response"].get("issues", [])))]
        resumed_record("resume_refresh_before_edits", refreshed, f"Canonical reads before post-pause edits: {[e['seq'] for e in refreshed]}")
        resumed_record("resume_updates_persisted", any(e["request"].get("id") == target for e in resume_comments), "Outcome or material-progress comment on the original ticket after the boundary")
        remaining = ["APP-202", "APP-206"] if case == "parent" else [target]
        covered = [i for i in remaining if any(e["request"].get("id") == i and any(
            c["seq"] > paused["after_seq"] and c["request"].get("id") == i and c["seq"] < e["seq"]
            and c["checked_sources"] == e["checked_sources"] for c in passed_checks)
            for e in after_checks if e["seq"] > paused["after_seq"])]
        resumed_record("resume_verification_updates", set(remaining) <= set(covered), f"Remaining tickets with fresh checks and persisted evidence: {covered}")
        resumed_record("resume_preserves_review", paused["review_note"] in tickets[target]["body"]
                       and "Original" in tickets[target]["body"], "Post-pause human review and original evidence retained")
        originals = [c["body"] for c in paused["paused_tickets"][target]["comments"]]
        resumed_record("resume_no_duplicate_start", bool(resume_comments) and not any(
            e["request"].get("body") in originals for e in resume_comments if e["request"].get("id") == target),
            "No exact repost of the original start/pause comments; inspect paraphrases manually")
        resumed_record("resume_reaches_remaining_gates", all(code[i]["ok"] and tickets.get(i, {}).get("status") == "done" for i in remaining), "Remaining implementation accepted, not merely planned again")
        if case == "parent":
            resumed_record("resume_parent_reconciled", tickets[target]["status"] != "done"
                           and any(e["request"].get("id") == target and "APP-204" in e["request"].get("body", "") for e in resume_comments)
                           and tickets["APP-204"] == paused["paused_tickets"]["APP-204"]
                           and tickets["APP-205"] == paused["paused_tickets"]["APP-205"],
                           "Resumed parent names the remaining human dependency and preserves blocked/deferred descendants")
    hygiene = [a for a in assertions if a["text"] != "implementation_acceptance"]
    return dict(case=meta["case"], arm=meta["arm"], guidance=meta.get("guidance", "linked"), skill_loading_observed=None, expectations=assertions,
                summary=dict(passed=sum(a["passed"] for a in assertions), total=len(assertions)),
                hygiene=dict(passed=sum(a["passed"] for a in hygiene), total=len(hygiene)),
                resumption=(dict(passed=sum(a["passed"] for a in resumption), total=len(resumption)) if paused is not None else None),
                limitation="One local run; no live tracker or adversarial sandbox. Skill availability is controlled; automatic loading is not proven.")


def serve(root, port):
    trackers = {p.name: p for p in root.iterdir() if (p / "run.json").exists()}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            name = self.path.strip("/")
            if name not in trackers:
                self.send_error(404)
                return
            try:
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                status, response = Tracker(trackers[name]).request(request)
            except (ValueError, KeyError) as error:
                status, response = 400, dict(ok=False, error=str(error))
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

        def log_message(self, *_):
            pass

    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--case", choices=CASES, required=True)
    p.add_argument("--arm", choices=["with_skill", "without_skill"], required=True)
    p.add_argument("--guidance", choices=["linked", "sparse"], default="linked")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--url", required=True)
    s = commands.add_parser("serve")
    s.add_argument("--root", type=Path, required=True)
    s.add_argument("--port", type=int, required=True)
    g = commands.add_parser("grade")
    g.add_argument("--run", type=Path, required=True)
    c = commands.add_parser("checkpoint")
    c.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        print(json.dumps(prepare(args.out, args.case, args.arm, args.url, args.guidance), indent=2))
    elif args.command == "serve":
        serve(args.root, args.port)
    elif args.command == "checkpoint":
        print(json.dumps(checkpoint(args.run), indent=2))
    else:
        print(json.dumps(grade(args.run), indent=2))


if __name__ == "__main__":
    main()
