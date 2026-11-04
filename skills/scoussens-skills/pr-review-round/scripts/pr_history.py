#!/usr/bin/env python3
"""Normalize collected PR evidence and render a neutral handoff history.

Canonical source in pr-detail. Bundled copies are checked by the round evals.
Usage: python3 pr_history.py evidence.json > history.json
"""
import argparse
from datetime import datetime
from html import escape
import json
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from md_to_html import render as markdown


def _link(url, label):
    parts = urlsplit(url or "")
    text = escape(str(label))
    if parts.scheme not in ("https", "http") or not parts.netloc:
        return text
    return f'<a href="{escape(url, quote=True)}">{text}</a>'


def normalize(evidence):
    pr = evidence["pr"]
    author = (pr.get("author") or {}).get("login")
    gaps = list(evidence.get("failedFetches", [])) + list(evidence.get("truncatedSources", []))
    dismissals = {}
    for item in evidence.get("timeline", []):
        dismissed = item.get("dismissedReview") or {}
        if dismissed.get("review_id") is not None:
            dismissals[dismissed["review_id"]] = (dismissed.get("state") or "").upper()
    threads = evidence.get("threads", [])
    events = []
    if pr.get("createdAt"):
        events.append(dict(id="pr-opened", kind="opened", at=pr["createdAt"], actor=author,
                           actorType=evidence.get("accountTypes", {}).get(author, "Unknown"),
                           label="PR opened", body="", url=pr.get("url"),
                           returned=False, head=None, findings=[]))
    for review in pr.get("reviews", []):
        if review.get("state") == "PENDING":
            continue
        state = review.get("state")
        original = dismissals.get(review.get("id")) if state == "DISMISSED" else state
        who = review.get("author") or {}
        findings = []
        for thread in threads:
            comments = (thread.get("comments") or {}).get("nodes") or []
            if comments and (comments[0].get("pullRequestReview") or {}).get("databaseId") == review.get("id") and review.get("id") is not None:
                findings.append(thread)
        returned = original == "CHANGES_REQUESTED" and who.get("login") != author
        label = "Returned to developer" if returned else {
            "APPROVED": "Approved", "COMMENTED": "Reviewed without a formal verdict",
        }.get(original, "Review dismissed; original verdict unknown")
        events.append(dict(id=f'review-{review.get("id")}', kind="review", at=review.get("submittedAt"),
                           actor=who.get("login"), actorType=who.get("type") or
                           evidence.get("accountTypes", {}).get(who.get("login"), "Unknown"),
                           label=label, body=review.get("body") or "", url=review.get("url"),
                           returned=returned, head=review.get("commitOid"), findings=findings,
                           state=state, originalState=original))
    attached = {thread["id"] for event in events for thread in event["findings"]}
    for thread in threads:
        comments = (thread.get("comments") or {}).get("nodes") or []
        if thread["id"] not in attached and comments:
            root = comments[0]
            events.append(dict(id=f'thread-{thread["id"]}', kind="feedback", at=root.get("createdAt"),
                               actor=(root.get("author") or {}).get("login"), actorType="Unknown",
                               label="Inline feedback; review association unknown", body="", url=root.get("url"),
                               returned=False, head=None, findings=[thread]))
    for comment in pr.get("comments", []):
        who = comment.get("author") or {}
        events.append(dict(id=f'comment-{comment["id"]}', kind="comment", at=comment.get("createdAt"),
                           actor=who.get("login"), actorType=who.get("type") or "Unknown", label="Comment",
                           body=comment.get("body") or "", url=comment.get("url"), returned=False,
                           head=None, findings=[]))
    labels = {"ready_for_review": "Ready for review", "review_requested": "Review requested",
              "convert_to_draft": "Returned to draft", "review_dismissed": "Review dismissed",
              "head_ref_force_pushed": "Branch force-pushed", "merged": "Merged", "closed": "Closed",
              "reopened": "Reopened"}
    for item in evidence.get("timeline", []):
        if item.get("event") not in labels:
            continue
        events.append(dict(id=f'event-{item.get("id")}', kind=item["event"], at=item.get("at"),
                           actor=item.get("actor"), actorType=item.get("actorType") or "Unknown",
                           label=labels[item["event"]], body="", url=item.get("url") or pr.get("url"),
                           returned=False, head=item.get("sha"), findings=[]))
    ticket = evidence.get("ticketEvidence") or {"status": "unavailable", "tickets": [], "events": []}
    for item in ticket.get("events", []):
        if not item.get("url") or not item.get("at"):
            raise ValueError("tracker events require a source URL and timestamp")
        events.append(dict(id=item["id"], kind="tracker", at=item["at"], actor=item.get("actor"),
                           actorType="Tracker", label=item["label"], body=item.get("body", ""),
                           url=item["url"], returned=False, head=None, findings=[]))
    for item in events:
        if item["at"] is None:
            gaps.append(f'undated:{item["id"]}')
    events.sort(key=lambda item: (datetime.fromisoformat(item["at"].replace("Z", "+00:00")).timestamp()
                                  if item["at"] else float("inf"), item["id"]))
    return dict(schemaVersion=1, repository=evidence.get("repository"), number=pr["number"],
                url=pr.get("url"), head=pr.get("headRefOid"), base=pr.get("baseRefOid"),
                collectedAt=evidence.get("collectedAt"), gaps=sorted(set(gaps)),
                omittedSources=evidence.get("omittedSources", []), ticketEvidence=ticket, events=events)


def format_time(value, timezone):
    if not value:
        return "Time unknown"
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        ZoneInfo(timezone)).strftime("%b %d, %H:%M %Z")


def render(history, timezone="UTC", review_detail=""):
    events = history["events"]
    returns = [event for event in events if event["returned"]]
    trail = []
    short = {"opened": "Opened", "ready_for_review": "Ready", "review_requested": "Review",
             "convert_to_draft": "Draft", "merged": "Merged", "closed": "Closed"}
    for event in events:
        if event["kind"] in ("head_ref_force_pushed", "review_dismissed", "comment", "feedback"):
            continue
        label = "↩ Developer" if event["returned"] else short.get(event["kind"],
                    "Review" if event.get("originalState") == "COMMENTED" else event["label"])
        if trail and trail[-1][0] == label:
            trail[-1] = (label, trail[-1][1] + 1, event["returned"])
        else:
            trail.append((label, 1, event["returned"]))
    if len(trail) > 8:
        trail = [(f'{sum(item[1] for item in trail[:-8])} earlier events', 1, False), *trail[-8:]]
    trail_html = ''.join(f'<li class="{"return" if returned else ""}">{escape(label)}'
                         f'{" ×" + str(count) if count > 1 else ""}</li>' for label, count, returned in trail)
    notes = []
    if history["gaps"]:
        notes.append("Some PR history could not be read: " + ", ".join(history["gaps"]) + ". The return count may be incomplete.")
    ticket = history["ticketEvidence"]
    if ticket.get("status") != "complete":
        notes.append("Ticket history is " + ticket.get("status", "unavailable") +
                     ". PR reviews do not tell us when the ticket changed status or who caused a delay.")
    if any(e.get("state") == "DISMISSED" and not e.get("originalState") for e in events):
        notes.append("A removed review has no recorded original decision. We cannot tell whether it asked for changes.")
    rows = []
    for event in events:
        findings = []
        for thread in event["findings"]:
            comments = (thread.get("comments") or {}).get("nodes") or []
            marked = "Discussion marked resolved" if thread.get("isResolved") else "Discussion still open"
            findings.append(f'<section class="finding"><p>{marked}. This does not confirm that the code is fixed.</p>' +
                            "".join(f'<p>{_link(c.get("url"), (c.get("author") or {}).get("login") or "Unknown actor")} '
                                    f'{escape(c.get("path") or "")}:{escape(str(c.get("line") or ""))}</p>'
                                    f'<div class="md">{markdown(c.get("body") or "")}</div>' for c in comments) + '</section>')
        reason = event["body"] or ("See the code comments below for the reason." if findings else
                                  "No reason recorded." if event["returned"] else "")
        body = f'<div class="md">{markdown(reason)}</div>'
        if event["kind"] == "comment" and reason:
            body = f'<details><summary>Read comment</summary>{body}</details>'
        body += "".join(findings)
        if event["kind"] in ("review", "feedback") and (reason or findings):
            label = "Why changes were requested" if event["returned"] else "Read review and code comments"
            body = f'<details><summary>{label}</summary>{body}</details>'
        head = f'<p class="muted">Code version reviewed <code>{escape(event["head"])}</code></p>' if event["head"] else ""
        dismissed = '<p class="muted">This review was later removed. It remains in the history.</p>' if event.get("state") == "DISMISSED" else ""
        rows.append(f'<li class="history-event {"return" if event["returned"] else ""}">'
                    f'<time>{escape(format_time(event["at"], timezone))}</time><div>'
                    f'<p>{_link(event["url"], event["label"])}</p>'
                    f'<p class="muted">{escape(event["actor"] or "Unknown actor")} · {escape(event["actorType"])}</p>'
                    f'{head}{dismissed}{body}</div></li>')
    attempts = [e for e in events if e["kind"] == "review"]
    rounds = ''.join(f'<li>{escape(format_time(e["at"], timezone))} · {escape(e["actor"] or "Unknown actor")} · '
                     f'{_link(e["url"], e["label"])}'
                     f'{" · now dismissed" if e.get("state") == "DISMISSED" else ""}</li>' for e in attempts)
    tickets = ' · '.join(f'Ticket {_link(t.get("url"), t["id"])} · {escape(t.get("state") or "Status unknown")}'
                      for t in ticket.get("tickets", []))
    coverage = (" · Some PR history is missing" if history["gaps"] else "") + (
        " · Ticket history " + ticket.get("status", "unavailable") if ticket.get("status") != "complete" else "")
    return (f'<div class="pr-history"><div class="handoff-line"><ol class="handoff-trail" aria-label="PR handoff trail">{trail_html}</ol>'
            f'<span class="muted">↩ {len(returns)} {"return" if len(returns) == 1 else "returns"}{escape(coverage)}</span></div>'
            f'<details class="history-detail"><summary>Details · why it went back and review notes</summary>'
            f'<div class="history-content"><p>{tickets}</p>{review_detail}' + ''.join(f'<p class="evidence-gap">{escape(note)}</p>' for note in notes) +
            f'<p class="muted">Collected {escape(history.get("collectedAt") or "at an unknown time")}. '
            'The trail shows event order, not time spent. Earlier review findings may already be fixed. '
            'A code update or removed review does not confirm a fix.</p>'
            f'<h3>Ticket and PR history</h3><ol class="history-events">{"".join(rows)}</ol>'
            f'<details><summary>All reviews · {len(attempts)} posted reviews, not a count of developer revisions</summary>'
            f'<ol>{rounds}</ol></details></div></details></div>')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    print(json.dumps(normalize(json.loads(args.evidence.read_text())), indent=2))
