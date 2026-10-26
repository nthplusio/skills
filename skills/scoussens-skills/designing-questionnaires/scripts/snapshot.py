"""Render any JSONL handoff as one offline, read-only HTML snapshot."""
import argparse
import hashlib
import html
import json
import os
import tempfile
from pathlib import Path
from string import Template

from questionnaire import ASSETS, pending_proposals, planning, questions, require, validate


def read_snapshot(source):
    raw = source.read_bytes().decode("utf-8")
    require(raw.endswith("\n"), "JSONL must end with a newline")
    records = [json.loads(line) for line in raw[:-1].split("\n")]
    header = records[0]
    require(header["type"] == "questionnaire" and header["schema_version"] in (1, 2, 3), "Expected JSONL handoff schema version 1, 2 or 3")
    require(type(header["record_count"]) is int and header["record_count"] == len(records), "JSONL record count mismatch")
    require(all(r["type"] in ("requirement", "feedback", "review") for r in records[1:]), "Unexpected JSONL record type")
    canonical_header = {k: v for k, v in header.items() if k != "snapshot_id"}
    canonical = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n" for r in [canonical_header, *records[1:]])
    require(hashlib.sha256(canonical.encode("utf-8")).hexdigest() == header["snapshot_id"], "JSONL snapshot hash mismatch")
    requirements = [r["requirement"] for r in records if r["type"] == "requirement"]
    feedback = [r["feedback"] for r in records if r["type"] == "feedback"]
    reviews = [r["review"] for r in records if r["type"] == "review"]
    model = {**header["questionnaire"], "requirements": requirements, "reviews": reviews}
    require(len({f["id"] for f in feedback}) == len(feedback), "Duplicate feedback ID")
    for row in feedback:
        require(all(isinstance(row[k], str) for k in ("id", "question", "name", "kind", "message", "created_at")), "Feedback fields must be text")
    validate(model, None, {f["id"]: f for f in feedback}, check_review_times=False)
    qs = questions(model)
    require(all(f["question"] in qs for f in feedback), "Feedback names an unknown question")
    for record in records:
        if record["type"] == "requirement":
            expected = planning(record["requirement"], feedback, {r["feedback_id"] for r in reviews})
            if header["schema_version"] < 3:
                require(not expected.pop("pending_proposal_ids") and not any(f["kind"] in ("propose", "adopt", "accept", "correct") for f in feedback), "Proposals require schema version 3")
            if header["schema_version"] == 1:
                require(not expected.pop("deferred_question_ids") and model.get("state") != "closed", "Closure requires schema version 2")
            require(record["planning"] == expected, "Snapshot has inconsistent planning readiness")
    return raw, header, model, feedback


def write_snapshot(source, output):
    require(source.suffix == ".jsonl", "Read a .jsonl handoff")
    require(output.suffix == ".html" and output.resolve() != source.resolve(), "Write to a separate .html file")
    raw, header, model, feedback = read_snapshot(source)
    esc = html.escape
    reviews = {r["feedback_id"]: r for r in model["reviews"]}
    qs = questions(model)
    closed = model.get("state") == "closed"
    navigation = []
    sections = []
    for requirement in model["requirements"]:
        rid = requirement["id"]
        navigation.append(f'<li><a href="#requirement-{rid}">{esc(requirement["title"])}</a></li>')
        sections.append(f'<section class="requirement" id="requirement-{rid}"><header><span class="badge">{esc(requirement["priority"])} priority</span><h2>{esc(requirement["title"])}</h2><p>{esc(requirement["text"])}</p></header>')
        if requirement.get("details"):
            sections.append(f'<details><summary>Requirement details and research</summary><p class="verbatim">{esc(requirement["details"])}</p></details>')
        for question in requirement["questions"]:
            qid = question["id"]
            sections.append(f'<article class="question" id="question-{qid}"><span class="badge">{question["status"].capitalize()}</span><h3>{esc(question["title"])}</h3><p class="verbatim">{esc(question["prompt"])}</p>')
            if question.get("follow_up_to"):
                sections.append(f'<p>Follow-up to <a href="#question-{question["follow_up_to"]}">{esc(questions(model)[question["follow_up_to"]]["title"])}</a></p>')
            if question["status"] == "answered":
                sections.append(f'<div class="answer"><h4>Recorded answer</h4><p class="verbatim">{esc(question["answer"]["text"])}</p><ul>')
                evidence_links = question["answer"]["evidence"]
            else:
                label = "Deferred — not answered" if question["status"] == "deferred" else "Open — not answered"
                sections.append(f'<div class="answer"><h4>{label}</h4>')
                if question.get("deferral"):
                    sections.append(f'<p class="verbatim">{esc(question["deferral"])}</p>')
                attention = question.get("attention", {})
                if attention:
                    timing = "Before deferral" if question["status"] == "deferred" else "Next action"
                    sections.append(f'<p class="verbatim">{timing} ({esc(attention["state"])}): {esc(attention["next_action"])}</p>')
                sections.append('<ul>')
                evidence_links = attention.get("evidence", [])
            for evidence in evidence_links:
                sections.append(f'<li><a href="{esc(evidence["href"])}" rel="noreferrer">{esc(evidence["label"])}</a></li>')
            sections.append('</ul></div>')
            sections.append(f'<p class="muted">Suggested respondents: {esc(", ".join(question["people"]) or "Not specified")}</p>')
            proposals = pending_proposals(question, feedback)
            if proposals:
                sections.append(f'<div class="answer"><h4>Proposed answers — not settled ({len(proposals)})</h4><p>Awaiting SME acceptance or correction. A review receipt alone does not settle a proposal.</p><ul>')
                for proposal in proposals:
                    sections.append(f'<li><a href="#feedback-{esc(proposal["id"])}">{esc(proposal["name"])}</a>: <span class="verbatim">{esc(proposal["message"])}</span></li>')
                sections.append('</ul></div>')
            if question.get("answer", {}).get("acceptance_id"):
                answer = question["answer"]
                sections.append(f'<p>Accepted proposal: <a href="#feedback-{esc(answer["proposal_id"])}">Original proposal</a> · <a href="#feedback-{esc(answer["acceptance_id"])}">Acceptance or correction</a></p>')
            if question.get("request"):
                request = question["request"]
                sections.append(f'<details><summary>Original recommendation and ask</summary><p class="verbatim">{esc(request["recommendation"])}</p><p class="verbatim">{esc(request["why"])}</p><p class="verbatim">{esc(request["response"])}</p></details>')
            replies = [f for f in feedback if f["question"] == qid]
            sections.append(f'<h4>Feedback and review ({len(replies)})</h4>')
            if not replies:
                sections.append('<p class="muted">No submissions.</p>')
            for reply in replies:
                receipt = reviews.get(reply["id"])
                sections.append(f'<section class="reply" id="feedback-{esc(reply["id"])}"><h5>{esc(reply["name"])} · {esc(reply["kind"])}</h5><p class="muted">{esc(reply["created_at"])} · self-reported name</p><p class="verbatim">{esc(reply["message"])}</p>')
                context = reply.get("context", {})
                if context:
                    sections.append(f'<p class="muted">Source revision: {esc(str(context["revision"]))}</p>')
                if context.get("proposal_id"):
                    sections.append(f'<p><a href="#feedback-{esc(context["proposal_id"])}">Original proposal</a></p>')
                if receipt:
                    affected = ' · '.join(f'<a href="#question-{q}">{esc(qs[q]["title"])}</a>' for q in receipt["question_ids"])
                    sections.append(f'<div class="review"><strong>Reviewed</strong><p class="verbatim">{esc(receipt["summary"])}</p><p class="muted">{esc(receipt["reviewed_at"])}</p><p>Affects: {affected}</p></div>')
                else:
                    sections.append('<p class="pending">Unreviewed — no review receipt recorded.</p>')
                sections.append('</section>')
            sections.append('</article>')
        sections.append('</section>')
    labels = {"outcome": "Outcome", "out_of_scope": "Out of scope", "readers": "Readers", "response_budget": "Response budget", "reviewer": "Review policy", "decision_maker": "Decision authority", "escalation": "Escalation"}
    setup = ''.join(f'<div><dt>{label}</dt><dd class="verbatim">{esc(model["setup"][key])}</dd></div>' for key, label in labels.items()) if model.get("setup") else '<p>No review setup was recorded.</p>'
    template = Template((ASSETS / "snapshot.html").read_text(encoding="utf-8"))
    document = template.substitute(
        title=esc(model["title"]), intro=esc(model["intro"]), notice=esc(model["notice"]),
        revision=model["revision"], questionnaire_id=esc(model["id"]), snapshot_id=esc(header["snapshot_id"]),
        snapshot_label="Final snapshot — Closed" if closed else "Current-state snapshot — Open",
        closure=f'<p class="verbatim">Closed {esc(model["closure"]["closed_at"])}: {esc(model["closure"]["reason"])}</p>' if closed else '',
        counts=''.join(f'<p><strong>{sum(q["status"] == state for q in qs.values())}</strong> {state}</p>' for state in ("answered", "open", "deferred")),
        reviewed_count=len(reviews), pending_count=len(feedback) - len(reviews),
        navigation='\n'.join(navigation), sections='\n'.join(sections), setup=setup,
        jsonl=esc(raw).replace("\r", "&#13;"),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(document)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return header["snapshot_id"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="JSONL from questionnaire.py handoff")
    parser.add_argument("output", type=Path, help="Standalone .html file")
    args = parser.parse_args()
    try:
        snapshot_id = write_snapshot(args.source, args.output)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        parser.error(f"Cannot create snapshot: {error}")
    print(f"PASS: wrote HTML snapshot to {args.output} (snapshot {snapshot_id})")


if __name__ == "__main__":
    main()
