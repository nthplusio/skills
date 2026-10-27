"""Local reference host: immutable feedback, durable outbox, atomic review publication."""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ASSETS = Path(__file__).resolve().parent.parent / "assets"
FIELDS = ("id", "question", "name", "kind", "message")


class DecisionConflict(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def questions(model):
    return {q["id"]: q for r in model["requirements"] for q in r["questions"]}


def pending_proposals(question, feedback, reviewed):
    acceptance = next((f for f in feedback if f["id"] == question.get("answer", {}).get("acceptance_id")), None)
    denied = {f.get("context", {}).get("proposal_id") for f in feedback if f["kind"] == "deny" and f["id"] in reviewed}
    return [f for f in feedback if f["question"] == question["id"] and f["kind"] in ("propose", "adopt")
            and f["id"] not in question.get("proposal_outcomes", {})
            and f["id"] not in denied and (not acceptance or f["created_at"] > acceptance["created_at"])]


def planning(requirement, feedback, reviewed):
    ids = {q["id"] for q in requirement["questions"]}
    open_ids = [q["id"] for q in requirement["questions"] if q["status"] == "open"]
    deferred_ids = [q["id"] for q in requirement["questions"] if q["status"] == "deferred"]
    pending_ids = [f["id"] for f in feedback if f["question"] in ids and f["id"] not in reviewed]
    proposal_ids = [f["id"] for q in requirement["questions"] for f in pending_proposals(q, feedback, reviewed)]
    return {
        "status": "needs_review" if pending_ids or proposal_ids else "needs_answers" if open_ids else "deferred" if deferred_ids else "ready_for_breakdown",
        "open_question_ids": open_ids, "deferred_question_ids": deferred_ids, "pending_feedback_ids": pending_ids,
        "pending_proposal_ids": proposal_ids,
    }


def validate(model, previous, feedback, *, check_review_times=True):
    require(isinstance(model, dict), "Expected a questionnaire object")
    require(text(model.get("id")) and text(model.get("title")), "ID and title required")
    require(type(model.get("revision")) is int and model["revision"] > 0, "Positive revision required")
    require(all(isinstance(model.get(k), str) for k in ("intro", "notice")), "Intro and notice required")
    require(model.get("state", "open") in ("open", "closed"), "Questionnaire state must be open or closed")
    if model.get("state") == "closed":
        closure = model.get("closure")
        require(isinstance(closure, dict) and text(closure.get("reason")) and text(closure.get("closed_at")), "Closure needs reason and time")
        require(datetime.fromisoformat(closure["closed_at"]).tzinfo is not None, "Closure time needs timezone")
    else:
        require("closure" not in model, "An open questionnaire cannot have a closure")
    if "setup" in model:
        setup = model["setup"]
        require(isinstance(setup, dict) and all(text(setup.get(k)) for k in (
            "outcome", "out_of_scope", "readers", "response_budget", "reviewer", "decision_maker", "escalation"
        )), "Setup needs outcome, scope, readers, response budget and review policy")
    roles = model.get("roles", [])
    require(isinstance(roles, list), "Roles must be a list")
    for role in roles:
        require(isinstance(role, dict) and re.fullmatch(r"[a-z][a-z0-9-]*", role.get("id", "")), "Role needs a slug ID")
        require(text(role.get("name")) and text(role.get("knows")), "Role needs a name and what it knows")
        require(isinstance(role.get("held_by"), list) and all(text(p) for p in role["held_by"]), "Role holders must be names")
    role_ids = [role["id"] for role in roles]
    require(len(set(role_ids)) == len(role_ids), "Duplicate role ID")
    glossary = model.get("glossary", [])
    require(isinstance(glossary, list) and all(isinstance(g, dict) and text(g.get("term")) and text(g.get("definition")) for g in glossary), "Glossary entries need a term and definition")
    require(len({g["term"].casefold() for g in glossary}) == len(glossary), "Duplicate glossary term")
    require(isinstance(model.get("requirements"), list) and model["requirements"], "Requirements required")
    ids = set()
    for item in [model] + model["requirements"]:
        require(isinstance(item, dict), "Requirement must be an object")
        require(re.fullmatch(r"[a-z][a-z0-9-]*", item.get("id", "")) and item["id"] not in ids, "Invalid or duplicate ID")
        ids.add(item["id"])
    for r in model["requirements"]:
        require(all(text(r.get(k)) for k in ("title", "text", "priority")), "Requirement needs title, text and priority")
        require(isinstance(r.get("details", ""), str), "Details must be text")
        require(isinstance(r.get("questions"), list) and r["questions"], "Named questions required")
        for q in r["questions"]:
            require(isinstance(q, dict), "Question must be an object")
            require(re.fullmatch(r"[a-z][a-z0-9-]*", q.get("id", "")) and q["id"] not in ids, "Invalid or duplicate question ID")
            ids.add(q["id"])
            require(all(text(q.get(k)) for k in ("title", "prompt")), "Question needs title and prompt")
            if "role" in q:
                require(q["role"] in role_ids and "people" not in q, "Question role must name a declared role; its holders replace people")
            else:
                require(isinstance(q.get("people"), list) and all(text(p) for p in q["people"]), "People must be respondent names")
            require(q.get("status") in ("open", "answered", "deferred"), "Question must be open, answered or deferred")
            if q["status"] == "deferred":
                require(model.get("state") == "closed" and text(q.get("deferral")), "Deferred questions need a closed questionnaire and reason")
            else:
                require("deferral" not in q, "Only deferred questions carry a deferral reason")
            require(model.get("state") != "closed" or q["status"] != "open", "Close by answering or explicitly deferring each open question")
            if "request" in q:
                request = q["request"]
                require(isinstance(request, dict) and all(text(request.get(k)) for k in (
                    "recommendation", "why", "response"
                )), "Targeted ask needs recommendation, consequence and response format")
                if "options" in request:
                    options = request["options"]
                    require(isinstance(options, list) and len(options) >= 2 and all(text(o) for o in options), "Options need at least two choices")
                    require(len({o.strip().casefold() for o in options}) == len(options), "Duplicate option")
            if "attention" in q:
                attention = q["attention"]
                require(q["status"] != "answered", "Answered questions must clear attention; feedback review stays independent")
                require(isinstance(attention, dict) and attention.get("state") in (
                    "waiting", "clarification", "conflict"
                ) and text(attention.get("next_action")), "Attention needs a known state and next action")
                require(isinstance(attention.get("evidence", []), list), "Attention evidence must be a list")
                if attention["state"] == "conflict":
                    require(len(attention.get("evidence", [])) >= 2, "Conflict needs evidence for both claims")
    qs = questions(model)
    receipts = {}
    previous_receipts = {r["feedback_id"]: r for r in previous["reviews"]} if previous else {}
    require(isinstance(model.get("reviews"), list), "Reviews must be a list")
    for receipt in model["reviews"]:
        require(isinstance(receipt, dict), "Review receipt must be an object")
        fid = receipt.get("feedback_id")
        require(isinstance(fid, str) and fid in feedback and fid not in receipts, "Receipt needs unique saved feedback ID")
        require(text(receipt.get("summary")) and text(receipt.get("reviewed_at")), "Receipt needs summary and review time")
        reviewed_at = datetime.fromisoformat(receipt["reviewed_at"].replace("Z", "+00:00"))
        require(reviewed_at.tzinfo is not None, "Review time needs an ISO timestamp with timezone")
        if check_review_times and fid not in previous_receipts:
            created_at = datetime.fromisoformat(feedback[fid]["created_at"])
            require(created_at <= reviewed_at <= datetime.now(timezone.utc), "Review time must fall between submission and publication; omit reviewed_at to use the host clock")
        affected = receipt.get("question_ids")
        require(isinstance(affected, list) and affected and all(isinstance(q, str) and q in qs for q in affected), "Receipt needs affected question IDs")
        require(feedback[fid]["question"] in affected, "Receipt must include the submission's question")
        receipts[fid] = receipt
    for q in qs.values():
        outcomes = q.get("proposal_outcomes", {})
        require(isinstance(outcomes, dict), "Proposal outcomes must be an object")
        for pid, outcome in outcomes.items():
            proposal = feedback.get(pid)
            require(proposal is not None and proposal["kind"] in ("propose", "adopt") and proposal["question"] == q["id"], "Outcome needs its original proposal")
            require(isinstance(outcome, dict) and outcome.get("state") in ("accepted", "denied", "not_selected"), "Unknown proposal outcome")
            decision = feedback.get(outcome.get("decision_id"))
            require(decision is not None and decision["question"] == q["id"] and decision["id"] in receipts, "Outcome needs its recorded decision")
            require(decision["kind"] in (("deny",) if outcome["state"] == "denied" else ("accept", "correct")), "Outcome must match its decision")
            if outcome["state"] != "not_selected":
                require(decision.get("context", {}).get("proposal_id") == pid, "Outcome must name the decided proposal")
            else:
                require(decision.get("context", {}).get("proposal_id") != pid, "Not-selected outcome needs a competing proposal")
        sources = list(q.get("attention", {}).get("evidence", []))
        if q["status"] == "answered":
            answer = q.get("answer")
            require(isinstance(answer, dict) and text(answer.get("text")), "Answered question needs an answer")
            evidence = answer.get("evidence")
            require(isinstance(evidence, list) and evidence, "Answered question needs evidence")
            if "proposal_id" in answer or "acceptance_id" in answer:
                proposal = feedback.get(answer.get("proposal_id"))
                acceptance = feedback.get(answer.get("acceptance_id"))
                require(proposal is not None and proposal["kind"] in ("propose", "adopt") and proposal["question"] == q["id"], "Answer needs its original proposal")
                require(not any(f["kind"] == "deny" and f.get("context", {}).get("proposal_id") == proposal["id"] and f["id"] in receipts for f in feedback.values()), "A denied proposal cannot become the accepted answer")
                require(acceptance is not None and acceptance["kind"] in ("accept", "correct") and acceptance["question"] == q["id"]
                        and acceptance.get("context", {}).get("proposal_id") == proposal["id"], "Answer needs acceptance of this proposal")
                require(answer["text"] == acceptance["message"], "Accepted answer must preserve the accepted wording")
                require(all(fid in receipts and q["id"] in receipts[fid]["question_ids"] for fid in (proposal["id"], acceptance["id"])), "Review both proposal and acceptance")
                require({"#feedback-" + proposal["id"], "#feedback-" + acceptance["id"]} <= {e.get("href") for e in evidence}, "Cite both proposal and acceptance")
            sources.extend(evidence)
        else:
            require("answer" not in q, "Reopened questions must remove the current answer; history keeps it")
        for source in sources:
            require(isinstance(source, dict) and text(source.get("label")), "Evidence needs a label")
            href = source.get("href", "")
            require(isinstance(href, str), "Evidence link must be text")
            if href.startswith("#feedback-"):
                fid = href.removeprefix("#feedback-")
                require(fid in receipts and q["id"] in receipts[fid]["question_ids"], "Feedback evidence must be reviewed for this question")
                require(q["status"] != "answered" or feedback[fid]["kind"] != "deny", "A denial does not answer the question")
                if q["status"] == "answered" and feedback[fid]["kind"] in ("propose", "adopt", "accept", "correct"):
                    require("acceptance_id" in q["answer"], "A proposal is not an answer; record its explicit acceptance")
            else:
                url = urlsplit(href)
                require(url.scheme == "https" and bool(url.netloc) and not url.username, "Evidence needs an HTTPS source or saved feedback link")
        if "follow_up_to" in q:
            require(q["follow_up_to"] in qs and q["follow_up_to"] != q["id"], "Follow-up must name another question")
        depends = q.get("depends_on", [])
        require(isinstance(depends, list) and len(set(depends)) == len(depends) and all(d in qs and d != q["id"] for d in depends), "depends_on must list other question IDs once each")
    if previous:
        require(model["id"] == previous["id"], "Keep questionnaire ID")
        require(model["revision"] == previous["revision"] + 1, "Publish the next revision; refresh before editing")
        require("setup" not in previous or "setup" in model, "Preserve saved setup; revise changed choices explicitly")
        require({r["id"] for r in previous.get("roles", [])} <= set(role_ids), "Preserve role IDs; change who holds a role instead")
        current = {r["id"]: r for r in model["requirements"]}
        for r in previous["requirements"]:
            require(r["id"] in current, "Preserve requirement IDs")
            require({q["id"] for q in r["questions"]} <= {q["id"] for q in current[r["id"]]["questions"]}, "Preserve question IDs and their requirement")
        for receipt in previous["reviews"]:
            require(receipts.get(receipt["feedback_id"]) == receipt, "Preserve original review receipts")
        for qid, old in questions(previous).items():
            for pid, outcome in old.get("proposal_outcomes", {}).items():
                require(qs[qid].get("proposal_outcomes", {}).get(pid) == outcome, "Preserve original proposal outcomes")


def respondents(model, question):
    if "role" in question:
        return next(r["held_by"] for r in model["roles"] if r["id"] == question["role"])
    return question["people"]


HIDDEN_REFERENCES = [
    (re.compile(r"\b[\w./-]+\.(?:py|m?js|tsx?|jsx|css|html|sql|go|rs|java|kt|rb|cs|ya?ml|json)(?::\d+)?\b"), "names a source file the reader cannot open"),
    (re.compile(r"\b(?!(?:UTF|ISO|SHA)-)[A-Z][A-Z0-9]{1,9}-\d+\b|(?<![\w&])#\d{2,}\b"), "cites a ticket or PR number; say what it decided"),
    (re.compile(r"\bQ\d+\b"), "refers to a question number; link the question by title or say what it decided"),
    (re.compile(r"`|=>|</?[a-z]+[ >]|\{[^}]*:[^}]*;[^}]*\}|\b[a-z]+-[a-z-]+\s*:\s*[^;\n]+;|\b[a-zA-Z_]\w*\.[a-zA-Z_]\w*\("), "quotes code; describe the behavior the reader would see"),
]
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}\b")
MEETING = re.compile(r"\b(?:meeting|call|sync|standup)\b", re.IGNORECASE)
COMMON_ACRONYMS = {"API", "CSV", "FAQ", "HTML", "HTTP", "HTTPS", "ID", "IDS", "JSON", "OK", "PDF", "PR", "SME", "UI", "URL", "UTF"}


def lint(model):
    """Heuristic self-containment warnings. Advisory: a clean result does not prove a reader can answer."""
    warnings = []
    glossary = {g["term"].casefold() for g in model.get("glossary", [])}
    roles = model.get("roles", [])
    intro = model["intro"]
    if len(intro.split()) > 60:
        warnings.append("intro: over 60 words; open with the page's purpose and move process text into setup")
    if re.search(r"\b\d+\s+(?:open\s+)?questions\b", intro):
        warnings.append("intro: hard-coded question count goes stale; the page shows live counts")
    for role in roles:
        if not role["held_by"]:
            warnings.append(f"role {role['id']}: nobody holds this role yet")
    for kind, items in (("requirement", model["requirements"]), ("question", list(questions(model).values()))):
        seen = {}
        for item in items:
            title = item["title"].strip().casefold()
            if title in seen:
                warnings.append(f"{item['id']}: same {kind} title as {seen[title]}; readers cannot tell them apart")
            seen.setdefault(title, item["id"])
    qs = questions(model)
    for q in qs.values():
        if q["status"] != "open":
            continue
        request = q.get("request", {})
        fields = {"title": q["title"], "prompt": q["prompt"], **{f"request.{k}": v for k, v in request.items() if isinstance(v, str)}}
        options = request.get("options", [])
        if options:
            fields["request.options"] = " · ".join(options)
        if q.get("attention"):
            fields["next_action"] = q["attention"]["next_action"]
        for field, value in fields.items():
            for pattern, message in HIDDEN_REFERENCES:
                match = pattern.search(value)
                if match:
                    warnings.append(f"{q['id']} {field}: '{match.group(0)}' {message}")
            if DATE.search(value) and MEETING.search(value):
                warnings.append(f"{q['id']} {field}: cites a meeting the reader may not have attended; state what it decided")
            for acronym in sorted(set(re.findall(r"\b[A-Z][A-Z0-9]{1,}\b", value)) - COMMON_ACRONYMS):
                if acronym.casefold() not in glossary and not re.fullmatch(r"Q\d+", acronym):
                    warnings.append(f"{q['id']} {field}: define '{acronym}' in the glossary")
        if q["prompt"].count("?") > 1:
            warnings.append(f"{q['id']} prompt: asks more than one question; split it or ask the one decision")
        if roles and "role" not in q:
            warnings.append(f"{q['id']}: no role; name the role this question is for")
        mentions = lambda option, value: re.search(r"(?<!\w)" + re.escape(option.strip()) + r"(?!\w)", value, re.IGNORECASE)
        named = [o for o in options if mentions(o, request.get("recommendation", ""))]
        if options and len(named) != 1:
            warnings.append(f"{q['id']} request.recommendation: names {len(named)} of the options; recommend exactly one listed option")
        for a in options:
            for b in options:
                if a != b and mentions(a, b):
                    warnings.append(f"{q['id']} request.options: '{a}' overlaps '{b}'; make options mutually exclusive")
        for child in qs.values():
            if child.get("follow_up_to") == q["id"] and child["status"] == "answered":
                warnings.append(f"{q['id']}: follow-up {child['id']} is answered; restate what it settled and ask only what remains")
    return warnings


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS publication (revision INTEGER PRIMARY KEY, model TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS feedback (
                    id TEXT PRIMARY KEY, question TEXT NOT NULL, name TEXT NOT NULL,
                    kind TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS delivery (
                    feedback_id TEXT PRIMARY KEY REFERENCES feedback(id), attempts INTEGER NOT NULL DEFAULT 0,
                    attempted_at REAL, receipt TEXT, delivered_at TEXT);
                CREATE TRIGGER IF NOT EXISTS immutable_feedback_update BEFORE UPDATE ON feedback
                    BEGIN SELECT RAISE(ABORT, 'feedback is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_feedback_delete BEFORE DELETE ON feedback
                    BEGIN SELECT RAISE(ABORT, 'feedback is immutable'); END;
            """)
            if "context" not in {row["name"] for row in db.execute("PRAGMA table_info(feedback)")}:
                db.execute("ALTER TABLE feedback ADD COLUMN context TEXT NOT NULL DEFAULT '{}'")
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def model(self, db=None):
        if db is None:
            with self.connect() as conn:
                return self.model(conn)
        row = db.execute("SELECT model FROM publication ORDER BY revision DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None

    def publish(self, model):
        model = deepcopy(model)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self.model(db)
            previous_receipts = {r["feedback_id"]: r for r in previous["reviews"]} if previous else {}
            if isinstance(model, dict) and isinstance(model.get("reviews"), list):
                for receipt in model["reviews"]:
                    if isinstance(receipt, dict) and isinstance(receipt.get("feedback_id"), str) and "reviewed_at" not in receipt:
                        old = previous_receipts.get(receipt["feedback_id"])
                        receipt["reviewed_at"] = old["reviewed_at"] if old else now()
            if model == previous:
                return  # Retry after an uncertain commit.
            rows = {r["id"]: {**dict(r), "context": json.loads(r["context"])} for r in db.execute("SELECT * FROM feedback")}
            validate(model, previous, rows)
            db.execute("INSERT INTO publication VALUES (?, ?)", (model["revision"], json.dumps(model)))

    def close(self, defer_reason=None):
        model = self.model()
        require(model is not None, "Publish a questionnaire before closing it")
        if model.get("state") == "closed":
            return
        unanswered = [q for q in questions(model).values() if q["status"] == "open"]
        require(not unanswered or text(defer_reason), "Unanswered questions remain; use --defer-unanswered REASON to close with deferrals")
        for question in unanswered:
            question.update(status="deferred", deferral=defer_reason)
        model.update(state="closed", closure={"reason": defer_reason or "Review complete.", "closed_at": now()}, revision=model["revision"] + 1)
        self.publish(model)

    def submit(self, data):
        require(isinstance(data, dict) and set(FIELDS) <= set(data) <= set(FIELDS) | {"context"}, "Complete the feedback form")
        require(all(isinstance(data[k], str) for k in FIELDS), "Feedback fields must be text")
        require(str(uuid.UUID(data["id"])) == data["id"], "Use a canonical UUID")
        require(0 < len(data["name"].strip()) <= 80 and len(data["name"]) <= 80, "Enter a name up to 80 characters")
        require(data["kind"] in ("answer", "change", "question", "agree", "propose", "adopt", "accept", "correct", "deny"), "Choose a response type")
        require(len(data["message"]) <= 3000 and (data["kind"] in ("agree", "deny") or text(data["message"])), "Enter feedback up to 3000 characters")
        context = data.get("context", {})
        require(isinstance(context, dict), "Submission context must be an object")
        decision = data["kind"] in ("accept", "correct", "deny")
        required = {"revision", "proposal_id"} if decision else {"revision"} if data["kind"] in ("propose", "adopt") else set()
        require(set(context) == required or (data["kind"] in ("accept", "correct") and set(context) == required | {"replace"} and context["replace"] is True), "Include the displayed revision and proposal when required")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            model = self.model(db)
            require(data["question"] in questions(model), "Choose a question on this page")
            previous = db.execute("SELECT * FROM feedback WHERE id = ?", (data["id"],)).fetchone()
            if previous:
                require(all(previous[k] == data[k] for k in FIELDS) and json.loads(previous["context"]) == context, "Submission ID already saved with different content")
            else:
                require(model.get("state") != "closed", "Questionnaire is closed; ask the owner to reopen it")
                if required:
                    if type(context.get("revision")) is not int or context["revision"] != model["revision"]:
                        raise DecisionConflict("Review changed; load the updated review before submitting")
                if data["kind"] == "adopt":
                    require(data["message"] == questions(model)[data["question"]].get("request", {}).get("recommendation"), "Recommendation changed; load the updated review")
                if decision:
                    rows = [{**dict(r), "context": json.loads(r["context"])} for r in db.execute("SELECT * FROM feedback")]
                    reviewed = {r["feedback_id"] for r in model["reviews"]}
                    question = questions(model)[data["question"]]
                    candidates = pending_proposals(question, rows, reviewed)
                    proposal = next((f for f in candidates if f["id"] == context["proposal_id"]), None)
                    require(proposal is not None, "Proposal is no longer awaiting a decision; load the updated review")
                    require(not any(f["kind"] in ("accept", "correct", "deny") and f.get("context", {}).get("proposal_id") == proposal["id"] and f["id"] not in reviewed for f in rows), "A decision is already awaiting review for this proposal")
                    if data["kind"] != "deny":
                        require(not any(f["question"] == question["id"] and f["kind"] in ("accept", "correct", "deny") and f["id"] not in reviewed for f in rows), "The reviewer must reconcile earlier decisions on this question before accepting another proposal")
                    if data["kind"] != "deny" and question["status"] == "answered" and not context.get("replace"):
                        raise DecisionConflict("Confirm replacement of the current answer before accepting this proposal")
                    if data["kind"] == "accept":
                        require(data["message"] == proposal["message"], "Accept the exact proposal or use the correction editor")
                db.execute("INSERT INTO feedback (id, question, name, kind, message, created_at, context) VALUES (?, ?, ?, ?, ?, ?, ?)", (*[data[k] for k in FIELDS], now(), json.dumps(context)))
                db.execute("INSERT INTO delivery (feedback_id) VALUES (?)", (data["id"],))
                if decision:
                    updated = deepcopy(model)
                    question = questions(updated)[data["question"]]
                    outcomes = question.setdefault("proposal_outcomes", {})
                    outcomes[proposal["id"]] = {"state": "denied" if data["kind"] == "deny" else "accepted", "decision_id": data["id"]}
                    if data["kind"] != "deny":
                        for candidate in candidates:
                            if candidate["id"] != proposal["id"]:
                                outcomes[candidate["id"]] = {"state": "not_selected", "decision_id": data["id"]}
                        question.pop("attention", None)
                        question.update(status="answered", answer={
                            "text": data["message"], "proposal_id": proposal["id"], "acceptance_id": data["id"],
                            "evidence": [{"label": label, "href": "#feedback-" + fid} for label, fid in (
                                ("Original proposal", proposal["id"]), ("SME correction" if data["kind"] == "correct" else "SME acceptance", data["id"]))],
                        })
                    applied = [(proposal["id"], "Original proposal preserved."), (data["id"], "Proposal denied." if data["kind"] == "deny" else "Corrected answer accepted." if data["kind"] == "correct" else "Answer accepted.")]
                    if data["kind"] != "deny":
                        applied.extend((c["id"], "Another proposal accepted; this candidate was not selected.") for c in candidates if c["id"] != proposal["id"])
                    for fid, summary in applied:
                        if fid not in reviewed:
                            updated["reviews"].append({"feedback_id": fid, "question_ids": [question["id"]], "summary": summary, "reviewed_at": now(), "method": "host_recorded"})
                    updated["revision"] += 1
                    saved = {r["id"]: {**dict(r), "context": json.loads(r["context"])} for r in db.execute("SELECT * FROM feedback")}
                    validate(updated, model, saved)
                    db.execute("INSERT INTO publication VALUES (?, ?)", (updated["revision"], json.dumps(updated)))
        return data["id"]

    def feedback(self, db=None):
        if db is None:
            with self.connect() as conn:
                return self.feedback(conn)
        return [{**dict(r), "context": json.loads(r["context"])} for r in db.execute("""SELECT f.*, d.attempts, d.receipt, d.delivered_at
            FROM feedback f JOIN delivery d ON d.feedback_id = f.id ORDER BY f.created_at, f.id""")]

    def state(self):
        with self.connect() as db:
            db.execute("BEGIN")
            model, feedback = self.model(db), self.feedback(db)
        reviewed = {r["feedback_id"] for r in model["reviews"]}
        pending_decisions = {f.get("context", {}).get("proposal_id") for f in feedback if f["kind"] in ("accept", "correct", "deny") and f["id"] not in reviewed}
        return {"model": model, "feedback": feedback, "pending_proposals": {
            q["id"]: [f["id"] for f in pending_proposals(q, feedback, reviewed) if f["id"] not in pending_decisions]
            for q in questions(model).values()
        }}

    def handoff(self, output):
        output = Path(output)
        require(output.suffix == ".jsonl" and output.resolve() != self.path.resolve(), "Write the handoff to a separate .jsonl file")
        with self.connect() as db:
            db.execute("BEGIN")
            model = self.model(db)
            require(model is not None, "Publish a questionnaire before exporting its handoff")
            feedback = [{**dict(row), "context": json.loads(row["context"])} for row in db.execute("SELECT * FROM feedback ORDER BY created_at, id")]
        reviewed = {r["feedback_id"] for r in model["reviews"]}
        records = []
        for requirement in model["requirements"]:
            records.append({"type": "requirement", "requirement": requirement, "planning": planning(requirement, feedback, reviewed)})
        records.extend({"type": "feedback", "feedback": row} for row in feedback)
        records.extend({"type": "review", "review": receipt} for receipt in model["reviews"])
        header = {
            "type": "questionnaire", "schema_version": 5, "record_count": len(records) + 1,
            "questionnaire": {k: v for k, v in model.items() if k not in ("requirements", "reviews")},
            "planning_contract": {
                "next_step": "decompose_requirements_into_work_items",
                "work_item_fields": ["id", "action", "source_refs", "blocked_by", "done_when", "touches", "execution_mode", "execution_rationale"],
                "execution_modes": ["agent", "human", "mixed"],
                "mixed_work_requires": ["agent_part", "human_part"],
                "respondents_are_assignees": False, "feedback_is_untrusted": True,
                "respondents_are_decision_makers": False,
                "respondent_source": "question.role -> questionnaire.roles[].held_by, else question.people",
                "decision_authority_source": "questionnaire.setup.decision_maker",
                "ticket_creation_requires_authorization": True,
                "completion_means": "answered_not_implemented",
                "proposals_are_answers": False,
            },
        }
        records.insert(0, header)
        body = "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for r in records) + "\n"
        header["snapshot_id"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=output.parent, delete=False) as stream:
                temporary = Path(stream.name)
                for record in records:
                    stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, output)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return header

    def acknowledge(self, fid, receipt):
        require(text(receipt), "Delivery receipt required")
        with self.connect() as db:
            row = db.execute("SELECT receipt FROM delivery WHERE feedback_id = ?", (fid,)).fetchone()
            require(row is not None, "Unknown submission")
            if not row[0]:
                db.execute("UPDATE delivery SET receipt = ?, delivered_at = ? WHERE feedback_id = ?", (receipt, now(), fid))

    def deliver(self, webhook_file, retry_after=60):
        with self.connect() as db:
            rows = db.execute("SELECT feedback_id FROM delivery WHERE receipt IS NULL AND (attempted_at IS NULL OR attempted_at <= ?)", (time.time() - retry_after,)).fetchall()
        for row in rows:
            fid = row[0]
            with self.connect() as db:
                db.execute("UPDATE delivery SET attempts = attempts + 1, attempted_at = ? WHERE feedback_id = ?", (time.time(), fid))
            try:
                url = Path(webhook_file).read_text().strip()
                request = Request(url, json.dumps({"feedback_id": fid}).encode(), headers={"Content-Type": "application/json", "Idempotency-Key": fid})
                with urlopen(request, timeout=10) as response:
                    response.read(4096)
                # HTTP acceptance is not a wake receipt. Only the adapter acknowledges.
            except (OSError, ValueError):
                pass  # The queue retains the row; never log a capability URL.


def handler(store, mode):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, value, kind="application/json"):
            body = json.dumps(value).encode() if kind == "application/json" else value
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/api/state":
                self.send(200, {**store.state(), "mode": mode})
            elif path in ("/", "/page.js", "/page.css"):
                name, kind = {"/": ("page.html", "text/html; charset=utf-8"), "/page.js": ("page.js", "text/javascript"), "/page.css": ("page.css", "text/css")}[path]
                self.send(200, (ASSETS / name).read_bytes(), kind)
            else:
                self.send(404, {"error": "Not found"})

        def do_POST(self):
            if self.path != "/api/feedback":
                self.send(404, {"error": "Not found"})
                return
            if self.headers.get("Content-Type") != "application/json" or self.headers.get("Sec-Fetch-Site") in ("cross-site", "same-site"):
                self.send(403, {"error": "Submit from this page"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                require(0 < length <= 16384, "Feedback too long or empty")
                fid = store.submit(json.loads(self.rfile.read(length)))
                self.send(200, {"id": fid, "saved": True})
            except DecisionConflict as error:
                self.send(409, {"error": str(error)})
            except (ValueError, TypeError, KeyError) as error:
                self.send(400, {"error": str(error)})
            except sqlite3.Error:
                self.send(503, {"error": "Could not save; retry with the same submission ID"})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    sub = parser.add_subparsers(dest="action", required=True)
    publish = sub.add_parser("publish")
    publish.add_argument("model", type=Path)
    sub.add_parser("export")
    check = sub.add_parser("lint", help="Warn about asks a role-holder cannot answer from the page alone; advisory")
    check.add_argument("model", type=Path)
    sub.add_parser("feedback")
    close = sub.add_parser("close", help="Close review and stop new feedback; optionally defer unanswered questions")
    close.add_argument("--defer-unanswered", metavar="REASON")
    handoff = sub.add_parser("handoff", help="Write an atomic JSONL snapshot for ticket planning; creates no tickets")
    handoff.add_argument("output", type=Path)
    ack = sub.add_parser("ack")
    ack.add_argument("id")
    ack.add_argument("receipt")
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--webhook-file", type=Path)
    args = parser.parse_args()
    store = Store(args.db)
    if args.action == "lint":
        model = json.loads(args.model.read_text())
        draft = deepcopy(model)
        for receipt in draft.get("reviews", []):
            if isinstance(receipt, dict):
                receipt.setdefault("reviewed_at", now())  # publish fills omitted times the same way
        validate(draft, None, {f["id"]: f for f in store.feedback()}, check_review_times=False)
        warnings = lint(model)
        print("\n".join(f"WARN: {w}" for w in warnings) or "PASS: no self-containment warnings; still run the reader check")
        raise SystemExit(1 if warnings else 0)
    if args.action == "publish":
        model = json.loads(args.model.read_text())
        store.publish(model)
        for warning in lint(store.model()):
            print(f"WARN: {warning}", file=sys.stderr)
        print(f"PASS: published revision {store.model()['revision']}")
    elif args.action == "export":
        print(json.dumps(store.model(), indent=2))
    elif args.action == "feedback":
        print(json.dumps(store.feedback(), indent=2))
    elif args.action == "close":
        store.close(args.defer_unanswered)
        print(f"PASS: questionnaire closed at revision {store.model()['revision']}")
    elif args.action == "handoff":
        header = store.handoff(args.output)
        print(f"PASS: wrote {header['record_count']} JSONL records to {args.output} (snapshot {header['snapshot_id']})")
    elif args.action == "ack":
        store.acknowledge(args.id, args.receipt)
    else:
        require(store.model() is not None, "Publish a model before serving")
        if args.webhook_file:
            def worker():
                while True:
                    try:
                        store.deliver(args.webhook_file)
                    except sqlite3.Error:
                        pass
                    time.sleep(5)
            threading.Thread(target=worker, daemon=True).start()
        mode = "automatic" if args.webhook_file else "manual"
        ThreadingHTTPServer(("127.0.0.1", args.port), handler(store, mode)).serve_forever()


if __name__ == "__main__":
    main()
