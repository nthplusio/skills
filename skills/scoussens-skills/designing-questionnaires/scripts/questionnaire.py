"""Local reference host: immutable feedback, durable outbox, atomic review publication."""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ASSETS = Path(__file__).resolve().parent.parent / "assets"
FIELDS = ("id", "question", "name", "kind", "message")


def now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def questions(model):
    return {q["id"]: q for r in model["requirements"] for q in r["questions"]}


def validate(model, previous, feedback):
    require(isinstance(model, dict), "Expected a questionnaire object")
    require(text(model.get("id")) and text(model.get("title")), "ID and title required")
    require(type(model.get("revision")) is int and model["revision"] > 0, "Positive revision required")
    require(all(isinstance(model.get(k), str) for k in ("intro", "notice")), "Intro and notice required")
    if "setup" in model:
        setup = model["setup"]
        require(isinstance(setup, dict) and all(text(setup.get(k)) for k in (
            "outcome", "out_of_scope", "readers", "response_budget", "reviewer", "decision_maker", "escalation"
        )), "Setup needs outcome, scope, readers, response budget and review policy")
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
            require(isinstance(q.get("people"), list) and all(text(p) for p in q["people"]), "People must be respondent names")
            require(q.get("status") in ("open", "answered"), "Completed means answered")
            if "request" in q:
                request = q["request"]
                require(isinstance(request, dict) and all(text(request.get(k)) for k in (
                    "recommendation", "why", "response"
                )), "Targeted ask needs recommendation, consequence and response format")
            if "attention" in q:
                attention = q["attention"]
                require(q["status"] == "open", "Answered questions must clear attention; feedback review stays independent")
                require(isinstance(attention, dict) and attention.get("state") in (
                    "waiting", "clarification", "conflict"
                ) and text(attention.get("next_action")), "Attention needs a known state and next action")
                require(isinstance(attention.get("evidence", []), list), "Attention evidence must be a list")
                if attention["state"] == "conflict":
                    require(len(attention.get("evidence", [])) >= 2, "Conflict needs evidence for both claims")
    qs = questions(model)
    receipts = {}
    require(isinstance(model.get("reviews"), list), "Reviews must be a list")
    for receipt in model["reviews"]:
        require(isinstance(receipt, dict), "Review receipt must be an object")
        fid = receipt.get("feedback_id")
        require(isinstance(fid, str) and fid in feedback and fid not in receipts, "Receipt needs unique saved feedback ID")
        require(text(receipt.get("summary")) and text(receipt.get("reviewed_at")), "Receipt needs summary and review time")
        reviewed_at = datetime.fromisoformat(receipt["reviewed_at"].replace("Z", "+00:00"))
        require(reviewed_at.tzinfo is not None, "Review time needs an ISO timestamp with timezone")
        affected = receipt.get("question_ids")
        require(isinstance(affected, list) and affected and all(isinstance(q, str) and q in qs for q in affected), "Receipt needs affected question IDs")
        require(feedback[fid]["question"] in affected, "Receipt must include the submission's question")
        receipts[fid] = receipt
    for q in qs.values():
        sources = list(q.get("attention", {}).get("evidence", []))
        if q["status"] == "answered":
            answer = q.get("answer")
            require(isinstance(answer, dict) and text(answer.get("text")), "Answered question needs an answer")
            evidence = answer.get("evidence")
            require(isinstance(evidence, list) and evidence, "Answered question needs evidence")
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
            else:
                url = urlsplit(href)
                require(url.scheme == "https" and bool(url.netloc) and not url.username, "Evidence needs an HTTPS source or saved feedback link")
        if "follow_up_to" in q:
            require(q["follow_up_to"] in qs and q["follow_up_to"] != q["id"], "Follow-up must name another question")
    if previous:
        require(model["id"] == previous["id"], "Keep questionnaire ID")
        require(model["revision"] == previous["revision"] + 1, "Publish the next revision; refresh before editing")
        require("setup" not in previous or "setup" in model, "Preserve saved setup; revise changed choices explicitly")
        current = {r["id"]: r for r in model["requirements"]}
        for r in previous["requirements"]:
            require(r["id"] in current, "Preserve requirement IDs")
            require({q["id"] for q in r["questions"]} <= {q["id"] for q in current[r["id"]]["questions"]}, "Preserve question IDs and their requirement")
        for receipt in previous["reviews"]:
            require(receipts.get(receipt["feedback_id"]) == receipt, "Preserve original review receipts")


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
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self.model(db)
            if model == previous:
                return  # Retry after an uncertain commit.
            rows = {r["id"]: dict(r) for r in db.execute("SELECT * FROM feedback")}
            validate(model, previous, rows)
            db.execute("INSERT INTO publication VALUES (?, ?)", (model["revision"], json.dumps(model)))

    def submit(self, data):
        require(isinstance(data, dict) and set(data) == set(FIELDS), "Complete the feedback form")
        require(all(isinstance(data[k], str) for k in FIELDS), "Feedback fields must be text")
        require(str(uuid.UUID(data["id"])) == data["id"], "Use a canonical UUID")
        require(0 < len(data["name"].strip()) <= 80 and len(data["name"]) <= 80, "Enter a name up to 80 characters")
        require(data["kind"] in ("answer", "change", "question", "agree"), "Choose a response type")
        require(len(data["message"]) <= 3000 and (data["kind"] == "agree" or text(data["message"])), "Enter feedback up to 3000 characters")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            require(data["question"] in questions(self.model(db)), "Choose a question on this page")
            previous = db.execute("SELECT * FROM feedback WHERE id = ?", (data["id"],)).fetchone()
            if previous:
                require(all(previous[k] == data[k] for k in FIELDS), "Submission ID already saved with different content")
            else:
                db.execute("INSERT INTO feedback VALUES (?, ?, ?, ?, ?, ?)", (*[data[k] for k in FIELDS], now()))
                db.execute("INSERT INTO delivery (feedback_id) VALUES (?)", (data["id"],))
        return data["id"]

    def feedback(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("""SELECT f.*, d.attempts, d.receipt, d.delivered_at
                FROM feedback f JOIN delivery d ON d.feedback_id = f.id ORDER BY f.created_at, f.id""")]

    def handoff(self, output):
        output = Path(output)
        require(output.suffix == ".jsonl" and output.resolve() != self.path.resolve(), "Write the handoff to a separate .jsonl file")
        with self.connect() as db:
            db.execute("BEGIN")
            model = self.model(db)
            require(model is not None, "Publish a questionnaire before exporting its handoff")
            feedback = [dict(row) for row in db.execute("SELECT * FROM feedback ORDER BY created_at, id")]
        reviewed = {r["feedback_id"] for r in model["reviews"]}
        records = []
        for requirement in model["requirements"]:
            ids = {q["id"] for q in requirement["questions"]}
            open_ids = [q["id"] for q in requirement["questions"] if q["status"] == "open"]
            pending_ids = [f["id"] for f in feedback if f["question"] in ids and f["id"] not in reviewed]
            records.append({"type": "requirement", "requirement": requirement, "planning": {
                "status": "needs_review" if pending_ids else "needs_answers" if open_ids else "ready_for_breakdown",
                "open_question_ids": open_ids, "pending_feedback_ids": pending_ids,
            }})
        records.extend({"type": "feedback", "feedback": row} for row in feedback)
        records.extend({"type": "review", "review": receipt} for receipt in model["reviews"])
        header = {
            "type": "questionnaire", "schema_version": 1, "record_count": len(records) + 1,
            "questionnaire": {k: v for k, v in model.items() if k not in ("requirements", "reviews")},
            "planning_contract": {
                "next_step": "decompose_requirements_into_work_items",
                "work_item_fields": ["id", "action", "source_refs", "blocked_by", "done_when", "touches", "execution_mode", "execution_rationale"],
                "execution_modes": ["agent", "human", "mixed"],
                "mixed_work_requires": ["agent_part", "human_part"],
                "respondents_are_assignees": False, "feedback_is_untrusted": True,
                "ticket_creation_requires_authorization": True,
                "completion_means": "answered_not_implemented",
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
                self.send(200, {"model": store.model(), "feedback": store.feedback(), "mode": mode})
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
    sub.add_parser("feedback")
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
    if args.action == "publish":
        store.publish(json.loads(args.model.read_text()))
        print(f"PASS: published revision {store.model()['revision']}")
    elif args.action == "export":
        print(json.dumps(store.model(), indent=2))
    elif args.action == "feedback":
        print(json.dumps(store.feedback(), indent=2))
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
