#!/usr/bin/env python3
"""Render saved round_report.py JSON without network access or forge writes."""
import argparse
from html import escape
import json
from pathlib import Path
import re
from string import Template

from md_to_html import render as markdown
from pr_history import format_time, render as history_html


def render(records, base, timezone="UTC", assessments=None):
    rows = []
    identities = [(record["repository"], record["number"]) for record in records]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate PRs in round report")
    if assessments and any(record["repository"] != assessments["repository"] for record in records):
        raise ValueError("assessments belong to a different repository")
    proposals = {item["number"]: item for item in (assessments or {}).get("assessments", [])}
    if len(proposals) != len((assessments or {}).get("assessments", [])):
        raise ValueError("duplicate assessments for one PR")
    if set(proposals) - {record["number"] for record in records}:
        raise ValueError("assessment refers to a PR outside the report")
    for record in records:
        number = record["number"]
        proposal = proposals.get(number)
        current = ""
        matches = False
        if proposal:
            matches = bool(re.fullmatch(r"[0-9a-f]{40}", proposal["head"])) and proposal["head"] == record["head"] and not any(
                gap in record["history"]["gaps"] for gap in
                ("snapshot-consistency", "queue-head-changed", "history-collection"))
            label = "Report recommendation · not posted to GitHub" if matches else "Earlier recommendation · code changed or could not be confirmed; review again"
            current = (f'<section class="proposal"><h3>{label} · {escape(proposal["verdict"])}</h3>'
                       f'<p class="muted">Assessed {escape(proposal["assessed_at"])} at '
                       f'<code>{escape(proposal["head"])}</code></p>'
                       f'<p class="muted">{escape(proposal.get("provenance") or "Local assessment")}</p>'
                       f'<p>Recommended next person · {escape(proposal["owner"])}</p>'
                       f'<p>{escape(proposal["blocker"])}</p>'
                       f'<details><summary>What the reviewer checked</summary>'
                       f'<div class="md">{markdown(proposal["body"])}</div></details></section>')
        verdict = record["verdict"]
        status = {
            "MERGED": "Merged", "CLOSED": "Closed", "CHANGES_REQUESTED": "Changes requested",
            "APPROVED_QUEUED": "Waiting to merge", "APPROVED_QUEUE_UNKNOWN": "Approved · merge queue unknown",
            "APPROVED": "Approved", "APPROVED_CONFLICTING": "Branch conflict",
            "CHANGES_REQUESTED_CONFLICTING": "Changes requested · branch conflict", "CONFLICTING": "Branch conflict",
            "NEEDS_REVIEW": "Needs review", "DRAFT": "Draft",
        }.get(verdict, verdict.replace("_", " ").capitalize())
        if verdict in ("MERGED", "CLOSED"):
            owner = "No review action needed."
        elif "CONFLICTING" in verdict:
            owner = "Developer to resolve the branch conflict and address any requested changes."
        elif verdict == "CHANGES_REQUESTED":
            owner = "Developer to address the changes requested on GitHub."
        elif verdict == "APPROVED_QUEUED":
            owner = "Wait for the merge queue. This change has not merged."
        elif verdict.startswith("APPROVED"):
            owner = "Maintainer to confirm it is safe to merge."
        else:
            owner = "Reviewer to check this change."
        if proposal and verdict not in ("MERGED", "CLOSED"):
            if matches:
                owner = f'{proposal["owner"]} · {proposal["blocker"]}'
                status = {"CHANGES_REQUESTED": "Needs fixes", "ACCEPTANCE_HOLD": "Needs confirmation",
                          "APPROVE": "Recommended approval"}.get(proposal["verdict"], "Review recommendation")
            else:
                owner = "Reviewer to check the code again. The earlier recommendation is out of date."
                status = "Review again"
        bodies = []
        for review in record["reviews"]:
            bodies.append(f'<section><p>Posted review · {escape(review["submitted_at"])} · '
                          f'{escape(review["state"])}</p><p class="muted">Reviewed head '
                          f'<code>{escape(review.get("commit_id") or "Unknown")}</code></p>'
                          f'<div class="md">{markdown(review["body"])}</div></section>')
        for comment in record["comments"]:
            bodies.append(f'<section><p>Commented · {escape(comment["created_at"])}</p>'
                          f'<div class="md">{markdown(comment["body"])}</div></section>')
        url = record["url"]
        if not url.startswith(("https://", "http://")):
            raise ValueError("PR URL must use HTTP or HTTPS")
        if type(number) is not int or number < 1:
            raise ValueError("PR number must be a positive integer")
        stamp = "No review posted this round"
        if record["reviewed_at"]:
            stamp = "Reviewed " + format_time(record["reviewed_at"], timezone)
        elif record["comments"]:
            stamp = "Commented " + format_time(max(c["created_at"] for c in record["comments"]), timezone)
        risk = (proposal or {}).get("risk") or "not assessed"
        evidence = (f'<p>Original PR title · {escape(record["title"])}</p>'
                    f'<p class="muted">{escape(record["repository"])} · Developer {escape(record["author"] or "Unknown")} · '
                    f'Code version <code>{escape(record["head"] or "Unknown")}</code></p>'
                    f'<p class="muted">{escape(stamp)} · Technical risk {escape(risk)} · '
                    f'GitHub status {escape(verdict)}</p>{current}'
                    '<details><summary>Reviews and comments posted in this round</summary>'
                    f'{"".join(bodies) or "<p>No review or comment posted by this reviewer in this round.</p>"}</details>')
        summary = record.get("summary") or record["title"]
        basis = " · Report recommendation, not posted" if proposal and matches and verdict not in ("MERGED", "CLOSED") else ""
        rows.append(f'<article class="pr-row" data-pr="{number}"><div class="row-heading">'
                    f'<h2><a href="{escape(url, quote=True)}">#{number}</a> {escape(summary)}</h2>'
                    f'<span class="verdict">{escape(status)}</span></div>'
                    f'<p class="current-action"><strong>Next</strong> {escape(owner)}<span class="muted">{basis}</span></p>'
                    f'{history_html(record["history"], timezone, evidence)}</article>')
    assets = Path(__file__).resolve().parents[1] / "assets"
    return Template((assets / "report-template.html").read_text()).substitute(
        base=escape(base), timezone=escape(timezone), count=len(records),
        merged=sum(record["state"] == "MERGED" for record in records), rows="".join(rows),
        collected=escape(max((r["history"].get("collectedAt") or "Unknown" for r in records), default="No PR evidence")),
        synthesis=f'<p>{escape(assessments["synthesis"])}</p>' if assessments and assessments.get("synthesis") else "",
        history_css=(assets / "pr-history.css").read_text())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--base", required=True)
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--assessments", type=Path)
    args = parser.parse_args()
    print(render(json.loads(args.report.read_text()), args.base, args.timezone,
                 json.loads(args.assessments.read_text()) if args.assessments else None))
