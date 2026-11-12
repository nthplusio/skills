#!/usr/bin/env python3
"""Check, parse and draw a project tracking record.

Usage:
  record.py check <record.md>               exit 1 and name each problem
  record.py parse <record.md>               print the record as JSON
  record.py overview <record.md> <out.html> write the overview page

The record is the Markdown described in references/document.md. Only the
Python standard library is used.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from pathlib import Path

DATE = r"\d{4}-\d{2}-\d{2}"

# Section kinds, matched by keyword against `##` and `###` headings.
SECTIONS = [
    ("standing", r"^where things stand"),
    ("lanes", r"^lanes\b"),
    ("questions", r"^how open questions get answered"),
    ("needs", r"^needs\b"),
    ("research", r"^answered by research"),
    ("approved", r"approved"),
    ("stopped", r"^stopped\b"),
    ("lane_work", r"^lane work"),
    ("done", r"^done\b"),
]
REQUIRED = [kind for kind, _ in SECTIONS]
TITLES = {
    "standing": "Where things stand",
    "lanes": "Lanes",
    "questions": "How open questions get answered",
    "needs": "Needs <Owner>",
    "research": "Answered by research",
    "approved": "Decisions already approved",
    "stopped": "Stopped",
    "lane_work": "Lane work",
    "done": "Done",
}

FIELDS = ["context", "sources", "options", "recommendation", "why", "holding_up"]
FIELD_LABELS = {
    "context": r"context",
    "sources": r"sources checked|sources",
    "options": r"options",
    "recommendation": r"recommendations?",
    "why": r"why",
    "holding_up": r"holding up|holds",
}
OPEN_ITEM_NEEDS = ["context", "sources", "recommendation", "why", "holding_up"]
HISTORY_KINDS = {"delivery": "Delivery", "ruling": "Ruling", "other": "Other", "unclassified": "Unclassified"}


def kind_of(heading: str) -> str | None:
    text = heading.strip().lower()
    for kind, pattern in SECTIONS:
        if re.search(pattern, text):
            return kind
    return None


def plain(text: str) -> str:
    """Markdown inline text as plain text."""
    text = re.sub(r"\{\{date(?:#[^:]*)?:([^}]*)\}\}", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_`]", "", text)
    return text.replace("\\", "").strip()


def parse_table(lines: list[str]) -> list[dict]:
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines]
    if len(rows) < 2:
        return []
    head = [plain(c).lower() for c in rows[0]]
    out = []
    for row in rows[2:]:
        out.append({head[i]: row[i] if i < len(row) else "" for i in range(len(head))})
    return out


def field_of(line: str) -> tuple[str, str] | None:
    m = re.match(r"\s*- \*\*([^*]+?):?\*\*:?\s*(.*)", line)
    if not m:
        return None
    label = m.group(1).strip().rstrip(":").lower()
    for name in FIELDS:
        if re.match(rf"({FIELD_LABELS[name]})\b", label):
            return name, m.group(2)
    return None


def parse(text: str) -> dict:
    lines = text.splitlines()
    record: dict = {
        "title": "",
        "last_updated": None,
        "sections": [],
        "standing": [],
        "lanes": [],
        "done": [],
        "items": [],
        "tables_with_chips": [],
    }
    section = None
    item = None
    table: list[str] = []
    table_section = None

    def flush_table():
        nonlocal table
        if table:
            if any("{{dropdown" in l for l in table):
                record["tables_with_chips"].append(TITLES.get(table_section, table_section or "top"))
            if table_section in ("lanes", "done"):
                record[table_section].extend(parse_table(table))
        table = []

    in_code = False
    for n, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if line.startswith("|"):
            if not table:
                table_section = section
            table.append(line)
            continue
        flush_table()
        m = re.match(r"^(#{1,3}) (.*)", line)
        if m:
            item = None
            if len(m.group(1)) == 1 and not record["title"]:
                record["title"] = plain(m.group(2))
                continue
            kind = kind_of(m.group(2))
            if kind or len(m.group(1)) == 2:
                section = kind
                if kind:
                    record["sections"].append({"kind": kind, "heading": plain(m.group(2)), "line": n})
            continue
        m = re.search(rf"Last updated:\s*(?:\{{\{{date[^:]*:)?({DATE})", line)
        if m and record["last_updated"] is None:
            record["last_updated"] = m.group(1)
            continue
        m = re.match(r"^- (?:\[( |x|X)\] )?(.*)", line)
        if m and section:
            if section == "standing":
                record["standing"].append(m.group(2))
                item = None
                continue
            title = m.group(2)
            bold = re.match(r"\*\*(.+?)\*\*", title)
            item = {
                "section": section,
                "checked": m.group(1) in ("x", "X") if m.group(1) is not None else None,
                "title": plain(bold.group(1) if bold else title),
                "line": n,
                "text": [title],
                "fields": {},
                "field_content": {},
            }
            record["items"].append(item)
            continue
        if item and line.startswith("  "):
            item["text"].append(line)
            if re.match(r"  - ", line):
                found = field_of(line)
                item["_open"] = None
                item["_field"] = found[0] if found else None
                if found and found[0] not in item["fields"]:
                    item["fields"][found[0]] = found[1]
                    item["field_content"][found[0]] = found[1]
                    if not found[1].strip():
                        item["_open"] = found[0]
            else:
                if item.get("_field"):
                    item["field_content"][item["_field"]] += "\n" + line
                if item.get("_open"):
                    # Keep the first-bullet summary for callers of parse.
                    item["fields"][item["_open"]] = re.sub(r"^\s*(?:- |\d+\. )", "", line)
                    item["_open"] = None
            continue
        if line.strip() and not line.startswith(" "):
            item = None
    flush_table()
    for it in record["items"]:
        it["text"] = "\n".join(it["text"])
        it.pop("_open", None)
        it.pop("_field", None)
    return record


def problems(record: dict) -> list[str]:
    out = []
    if not record["title"]:
        out.append("no `# <Project>: ...` title")
    if not record["last_updated"]:
        out.append("no `Last updated: YYYY-MM-DD` line")
    present = {s["kind"] for s in record["sections"]}
    for kind in REQUIRED:
        if kind not in present:
            out.append(f"missing section: {TITLES[kind]}")
    for where in record["tables_with_chips"]:
        out.append(f"dropdown chip inside a table under {where}; use a plain State column")
    for it in record["items"]:
        if it["section"] != "needs":
            continue
        label = f"line {it['line']} \"{it['title']}\""
        if it["checked"]:
            if not re.search(rf"(rul|approv|decid|answer|settl)\w*[^\n]*?{DATE}|{DATE}[^\n]*?(rul|approv|decid)", it["text"], re.I):
                out.append(f"{label}: checked off without the ruling and its date")
            continue
        missing = [f for f in OPEN_ITEM_NEEDS if not plain(it["fields"].get(f, ""))]
        if missing:
            names = ", ".join(n.replace("_", " ").capitalize() for n in missing)
            out.append(f"{label}: open owner item lacks {names}")
    for row in record["done"]:
        kind = plain(row.get("kind", "")).lower()
        if kind and kind not in HISTORY_KINDS:
            out.append(f'Done row "{plain(row.get("what", ""))[:50]}": Kind must be Delivery, Ruling, Other or Unclassified')
        date = plain(row.get("date", ""))
        if not re.fullmatch(DATE, date) and date.lower() != "earlier":
            out.append(f"Done row \"{plain(row.get('what', ''))[:50]}\": date \"{date}\" is not YYYY-MM-DD")
        if not plain(row.get("where", "")):
            out.append(f"Done row \"{plain(row.get('what', ''))[:50]}\": empty Where; link the commit")
    return out


def ci_state(text: str) -> str:
    t = text.lower()
    if re.search(r"not (ci-)?green|ci (failed|red)|failed on|ci: fail", t):
        return "fail"
    if "green" in t or "ci: pass" in t:
        return "pass"
    return "none"


def lane_tone(state: str) -> str:
    s = state.lower()
    if re.search(r"held|block|wait|stuck", s):
        return "held"
    if re.search(r"work|active|run|watch", s):
        return "work"
    return "idle"


def inline(text: str) -> str:
    """Markdown inline text as safe HTML: code, bold and http(s) links only."""
    text = re.sub(r"\{\{date(?:#[^:]*)?:([^}]*)\}\}", r"\1", text).replace("\\", "")
    out = html.escape(text, quote=True)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', out)
    return out


def first_sentence(text: str, limit: int = 220) -> str:
    text = text.strip()
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    s = m.group(1) if m else text
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def spell_option(rec: str, options: str) -> str:
    """Expand a bare option letter, such as "A.", into that option's text."""
    m = re.fullmatch(r"\s*\**([A-Z])\**\.?\s*", rec)
    if not m:
        return rec
    found = re.search(rf"(?:^|\s){m.group(1)}: (.+?)(?=\s[A-Z]: |$)", options)
    return f"{m.group(1)}: {found.group(1)}" if found else rec


def blocks(text: str) -> str:
    """Render record paragraphs and nested bullets without accepting raw HTML."""
    out = []
    indents = []
    for line in text.splitlines():
        if not line.strip():
            continue
        bullet = re.match(r"^(\s*)(?:- |\d+\. )(.*)", line)
        if bullet:
            indent = len(bullet.group(1))
            while indents and indent < indents[-1]:
                out.append("</li></ul>")
                indents.pop()
            if not indents or indent > indents[-1]:
                out.append("<ul>")
                indents.append(indent)
            else:
                out.append("</li>")
            out.append(f"<li>{inline(bullet.group(2))}")
        else:
            out.append(f"<p>{inline(line.strip())}</p>")
    out.extend("</li></ul>" for _ in indents)
    return "".join(out)


def anchor(kind: str, title: str) -> str:
    return kind + "-" + hashlib.sha256(title.encode()).hexdigest()[:12]


def history_kind(row: dict) -> str:
    kind = plain(row.get("kind", "")).lower()
    return kind if kind in HISTORY_KINDS else "unclassified"


def overview(record: dict) -> str:
    items = record["items"]
    open_needs = [i for i in items if i["section"] == "needs" and not i["checked"]]
    ruled = [i for i in items if i["section"] == "needs" and i["checked"]]
    count = lambda kind: sum(1 for i in items if i["section"] == kind)
    holding = [i for i in open_needs if not re.match(r"nothing", plain(i["fields"].get("holding_up", "")), re.I)]
    lanes = record["lanes"]
    done = record["done"]
    deliveries = [r for r in done if history_kind(r) == "delivery"]
    ruling_history = [r for r in done if history_kind(r) == "ruling"]
    unclassified = sum(history_kind(r) == "unclassified" for r in done)
    ci = {"pass": 0, "fail": 0, "none": 0}
    for row in deliveries:
        ci[ci_state(row.get("what", ""))] += 1

    tiles = [
        ("needs", "Needs the owner", len(open_needs), f"{len(holding)} holding up work", "warn" if holding else ""),
        ("ruled", "Owner ruled", len(ruled) + count("approved"), "decision items; history below", ""),
        ("research", "Open to veto", count("research"), "answered by research or decided by the editor", ""),
        ("lanes", "Lanes", len(lanes), f"{sum(1 for l in lanes if lane_tone(l.get('state', '')) == 'held')} held", ""),
        ("done", "Delivered", len(deliveries), f"{ci['pass']} CI green, {ci['fail']} failed", "bad" if deliveries and ci_state(deliveries[0].get("what", "")) == "fail" else ""),
        ("stopped", "Stopped", count("stopped"), "deliberately not done", ""),
    ]
    tile_html = "".join(
        f'<div class="tile card {tone}"><div class="n">{n}</div><div class="k"><button type="button" class="card-link" data-target="{key}">{html.escape(k)}</button></div>'
        f'<div class="s">{html.escape(s)}</div></div>'
        for key, k, n, s, tone in tiles
    )

    def question_summary(i, linked=False):
        hold = plain(i["fields"].get("holding_up", "")) or "not stated"
        rec = spell_option(i["fields"].get("recommendation", ""), i["fields"].get("options", ""))
        title = html.escape(i["title"])
        if linked:
            title = f'<button type="button" class="card-link" data-target="{anchor("decision", i["title"])}">{title}</button>'
        return (
            f'<span class="ask"><strong>{title}</strong>'
            f'<span class="rec">Recommended: {html.escape(first_sentence(plain(rec))) if rec else "No recommendation yet."}</span></span>'
            f'<span class="hold"><span class="lbl">Holding up</span>{html.escape(first_sentence(hold, 160))}</span>'
        )

    ordered = sorted(open_needs, key=lambda i: bool(re.match(r"nothing", plain(i["fields"].get("holding_up", "")), re.I)))
    queue = "".join(
        f'<li class="q card{" idle" if re.match("nothing", plain(i["fields"].get("holding_up", "")), re.I) else ""}"><div class="question">{question_summary(i, linked=True)}</div></li>'
        for i in ordered
    ) or '<li class="empty">Nothing waits on the owner.</li>'

    def decision(i):
        fields = i["field_content"]
        detail = ""
        for key, label in [("recommendation", "Recommendation"), ("why", "Why this recommendation"),
                           ("holding_up", "Holding up"), ("context", "Context"), ("options", "Options")]:
            value = fields.get(key, "")
            if key == "options" and not value:
                continue
            if key == "recommendation":
                value = spell_option(value, fields.get("options", ""))
            detail += f'<dt>{label}</dt><dd>{blocks(value) if value.strip() else "Not recorded — ask the editor to complete this item."}</dd>'
        return (
            f'<details class="decision" id="{anchor("decision", i["title"])}">'
            f'<summary><span class="question">{question_summary(i)}</span><span class="hint">Decision context</span></summary>'
            f'<div class="decision-body"><dl>{detail}</dl>'
            f'<details class="evidence"><summary>Sources checked and further reading</summary>{blocks(fields.get("sources", "Not recorded."))}</details>'
            '<p class="feedback">To rule or give feedback, quote this question in a comment on the record or a reply to its editor. This view does not submit rulings.</p>'
            '</div></details>'
        )

    decisions = "".join(decision(i) for i in ordered) or '<p class="empty">Nothing waits on the owner.</p>'

    def item_list(selected):
        return "".join(
            '<article class="entry">'
            + (f'<p class="meta">{"Completed" if i["checked"] else "Open"}</p>' if i["section"] == "lane_work" else "")
            + blocks(i["text"]) + '</article>' for i in selected
        ) or '<p class="empty">No items recorded.</p>'

    lane_html = "".join(
        f'<div class="lane card {lane_tone(l.get("state", ""))}"><div class="lh"><strong><button type="button" class="card-link" data-target="{anchor("lane", plain(l.get("lane", "")))}">{html.escape(plain(l.get("lane", "")))}</button></strong>'
        f'<span class="st">{html.escape(plain(l.get("state", "")))}</span></div>'
        f'<div class="now">{html.escape(plain(l.get("now", "")))}</div></div>'
        for l in lanes
    ) or '<p class="empty">No lanes recorded.</p>'

    lane_details = "".join(
        f'<article class="entry" id="{anchor("lane", plain(l.get("lane", "")))}" tabindex="-1">'
        f'<h3>{inline(l.get("lane", ""))}</h3><dl>'
        + "".join(f'<dt>{label}</dt><dd>{inline(l.get(key, ""))}</dd>'
                  for key, label in [("owner", "Owner"), ("branch", "Branch"), ("state", "State"), ("now", "Now")])
        + '</dl></article>' for l in lanes
    ) or '<p class="empty">No lanes recorded.</p>'

    def history_table(rows, label):
        rendered = []
        for row in rows:
            kind = history_kind(row)
            ci_status = ci_state(row.get("what", "")) if kind == "delivery" else "none"
            ci_label = {"pass": "CI green", "fail": "CI failed", "none": "no CI"}[ci_status] if kind == "delivery" else "—"
            rendered.append(
                f'<tr><td class="d">{html.escape(plain(row.get("date", "")))}</td><td>{HISTORY_KINDS[kind]}</td>'
                f'<td><span class="ci {ci_status}">{ci_label}</span></td>'
                f'<td>{inline(row.get("what", ""))}</td><td>{inline(row.get("where", ""))}</td></tr>'
            )
        return (f'<div class="table-scroll" role="region" aria-label="{label}" tabindex="0"><table>'
                '<thead><tr><th>Date</th><th>Kind</th><th>CI</th><th>What happened and checks</th><th>Where</th></tr></thead>'
                f'<tbody>{"".join(rendered)}</tbody></table></div>')

    standing = "".join(f"<li>{inline(s)}</li>" for s in record["standing"][:5])
    recent = "".join(f'<li>{inline(first_sentence(r.get("what", ""), 200))}</li>' for r in deliveries[:3])
    history_note = (f'<p class="meta">{unclassified} unclassified history entries are not counted as deliveries. '
                    '<button type="button" data-target="history">Review history</button></p>') if unclassified else ""
    sections = [
        ("overview", "Overview", f'<ul class="standing">{standing}</ul><div class="tiles">{tile_html}</div>{history_note}'
         f'<h2>Waiting on the owner, and what each decision holds up</h2><ol class="queue">{queue}</ol>'
         f'<h2>Lanes</h2><div class="lanes">{lane_html}</div>'
         f'<h2>Latest deliveries</h2><ul>{recent}</ul><button type="button" data-target="done">View all deliveries and checks →</button>'),
        ("needs", "Needs the owner", f'<h2>Needs the owner</h2><p>Open a question for the recommendation, tradeoff and evidence.</p>{decisions}'),
        ("ruled", "Owner ruled", '<h2>Owner ruled</h2>' + item_list(ruled + [i for i in items if i["section"] == "approved"])
         + ('<h2>Ruling history</h2><p>Events may refer to decisions above; they do not add to the decision-item count.</p>'
            + history_table(ruling_history, "Ruling history") if ruling_history else "")),
        ("research", "Open to veto", '<h2>Open to veto</h2>' + item_list([i for i in items if i["section"] == "research"])),
        ("lanes", "Lanes", f'<h2>Lanes</h2>{lane_details}<h2>Lane work</h2>' + item_list([i for i in items if i["section"] == "lane_work"])),
        ("done", "Delivered", '<h2>Delivered</h2>' + (history_table(deliveries, "Delivery history") if deliveries else '<p class="empty">No deliveries recorded.</p>')
         + '<button type="button" data-target="history">View all project history</button>'),
        ("history", "History", '<h2>Project history</h2><p>Delivery, ruling and other events. Unclassified entries are retained, not counted as deliveries.</p>'
         + (history_table(done, "Project history") if done else '<p class="empty">No history recorded.</p>')),
        ("stopped", "Stopped", '<h2>Stopped</h2>' + item_list([i for i in items if i["section"] == "stopped"])),
    ]
    tabs = "".join(f'<button type="button" id="tab-{key}" data-target="{key}">{label}</button>' for key, label, _ in sections)
    panels = "".join(f'<section id="{key}" class="panel" aria-labelledby="tab-{key}" tabindex="0">{body}</section>' for key, _, body in sections)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(record['title'])}: overview</title>
<style>
:root{{color-scheme:light dark;--bg:#fff;--fg:#1d2433;--mute:#5d6778;--line:#e3e7ee;--card:#f6f8fb;--warn:#a15c00;--warnbg:#fff4e0;--bad:#b42318;--badbg:#fdecea;--ok:#1a7f37;--okbg:#e6f4ea;--work:#1f5fbf;--workbg:#e8f0fc}}
@media (prefers-color-scheme:dark){{:root{{--bg:#14171c;--fg:#e6e9ef;--mute:#9aa3b2;--line:#2a2f38;--card:#1b1f26;--warn:#f0b35a;--warnbg:#3a2a12;--bad:#ff8a80;--badbg:#3b1d1b;--ok:#6fd38a;--okbg:#16301f;--work:#8db7ff;--workbg:#18263d}}}}
*{{box-sizing:border-box}}body{{margin:0;font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif;background:var(--bg);color:var(--fg)}}
main{{max-width:1080px;margin:0 auto;padding:20px}}h1{{font-size:20px;margin:0}}h2{{font-size:15px;margin:22px 0 8px}}
.meta{{color:var(--mute);margin:2px 0 12px}}a{{color:var(--work)}}code{{font-size:12px}}
.standing{{margin:0 0 16px;padding-left:18px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,150px),1fr));gap:8px}}
.tile{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}}
.tile .n{{font-size:24px;font-weight:650}}.tile .k{{font-weight:600}}.tile .s{{color:var(--mute);font-size:12px}}
.tile.warn{{background:var(--warnbg);border-color:var(--warn)}}.tile.bad{{background:var(--badbg);border-color:var(--bad)}}
ol.queue{{list-style:none;margin:0;padding:0;display:grid;gap:6px}}
.q{{border:1px solid var(--warn);background:var(--warnbg);border-radius:8px;padding:12px}}
.q.idle{{border-color:var(--line);background:var(--card)}}
.lanes{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:8px}}
.lane{{border:1px solid var(--line);border-left:4px solid var(--mute);border-radius:6px;padding:8px 10px;background:var(--card)}}
.lane.work{{border-left-color:var(--work)}}.lane.held{{border-left-color:var(--warn)}}
.lh{{display:flex;justify-content:space-between;gap:8px}}.st{{font-size:12px;color:var(--mute)}}.now{{font-size:13px;margin-top:2px}}
table{{width:100%;border-collapse:collapse}}td{{border-top:1px solid var(--line);padding:6px 6px;vertical-align:top}}td.d{{white-space:nowrap;color:var(--mute)}}
.ci{{font-size:12px;padding:1px 7px;border-radius:10px;white-space:nowrap;background:var(--card);color:var(--mute)}}
.ci.pass{{background:var(--okbg);color:var(--ok)}}.ci.fail{{background:var(--badbg);color:var(--bad)}}
.empty{{color:var(--mute)}}
.tabs{{display:flex;flex-wrap:wrap;gap:4px;border-block-end:1px solid var(--line);padding-block:8px;margin-block-end:16px;position:sticky;inset-block-start:0;background:var(--bg);z-index:2}}
button{{font:inherit;text-align:inherit;border:0;padding:0;background:transparent;color:var(--work);cursor:pointer}}
.tabs button{{padding:10px 12px;border-radius:6px;color:var(--mute)}}
.tabs [aria-selected="true"]{{background:var(--workbg);color:var(--work);font-weight:650}}
[hidden]{{display:none!important}}.panel{{scroll-margin-block-start:16px}}
.card{{position:relative}}.card-link{{color:inherit;text-decoration:none}}.card-link::after{{content:"";position:absolute;inset:0}}
:focus-visible{{outline:2px solid var(--work);outline-offset:3px}}
.card-link:focus-visible{{outline:2px solid transparent}}.card:has(.card-link:focus-visible){{outline:2px solid var(--work);outline-offset:3px}}
a:active,button:active,summary:active{{background:var(--workbg)}}
@media (hover:hover) and (pointer:fine){{.card:hover,.tabs button:hover,summary:hover{{background:color-mix(in oklch,var(--workbg) 65%,var(--bg))}}}}
.question{{display:flex;flex-wrap:wrap;gap:16px;align-items:start}}.ask{{flex:3 1 280px}}.hold{{flex:2 1 180px}}
.rec,.lbl{{display:block;color:var(--mute);font-size:13px}}.rec{{margin-block-start:4px}}.lbl{{font-size:11px;text-transform:uppercase;letter-spacing:.04em}}
.decision,.entry{{border:1px solid var(--line);border-radius:8px;margin-block:10px;background:var(--card);scroll-margin-block-start:16px}}
summary{{cursor:pointer;padding:14px}}.decision>summary{{list-style:none}}.decision>summary::-webkit-details-marker{{display:none}}
.hint{{display:block;color:var(--work);font-size:12px;margin-block-start:10px}}.hint::before{{content:"＋ "}}.decision[open] .hint::before{{content:"− "}}
.decision-body,.entry{{padding:16px}}.decision-body{{border-block-start:1px solid var(--line);background:var(--bg);border-radius:0 0 8px 8px}}
dl{{margin:0}}dt{{font-weight:650;margin-block-start:16px}}dt:first-child{{margin-block-start:0}}dd{{margin:4px 0 0;max-inline-size:85ch}}dd p,.entry p{{margin-block:4px}}dd ul{{padding-inline-start:20px}}
.evidence{{margin-block-start:18px;border-block-start:1px solid var(--line)}}.evidence summary{{padding-inline:0;color:var(--work)}}
.feedback{{font-size:12px;color:var(--mute);margin-block:20px 0}}h3{{font-size:16px;margin-block:0 12px}}
.table-scroll{{overflow:auto}}th{{text-align:start;padding:8px 6px;white-space:nowrap}}td:nth-child(2){{white-space:nowrap}}td:last-child{{min-inline-size:9ch}}body{{overflow-wrap:anywhere}}
</style></head><body><main>
<h1>{html.escape(record['title'])}</h1>
<p class="meta">Last updated {html.escape(record['last_updated'] or 'unknown')}. Drawn from the record; the record is the source of truth.</p>
<nav class="tabs" aria-label="Project sections">{tabs}</nav>
{panels}
</main>
<script>
{{
const tabs = [...document.querySelectorAll('.tabs button')];
const panels = [...document.querySelectorAll('.panel')];
document.querySelector('.tabs').setAttribute('role', 'tablist');
tabs.forEach(tab => {{
  tab.setAttribute('role', 'tab');
  tab.setAttribute('aria-controls', tab.dataset.target);
}});
panels.forEach(panel => panel.setAttribute('role', 'tabpanel'));
function navigate(targetId = 'overview', focus = false) {{
  const target = document.getElementById(targetId);
  const panel = target?.closest('.panel') || panels[0];
  panels.forEach(p => p.hidden = p !== panel);
  tabs.forEach(tab => {{
    const selected = tab.dataset.target === panel.id;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
  }});
  if (target && target !== panel) {{
    if (target.matches('details')) target.open = true;
    target.style.scrollMarginBlockStart = document.querySelector('.tabs').offsetHeight + 16 + 'px';
    if (focus) (target.querySelector('summary') || target).focus({{preventScroll: true}});
    target.scrollIntoView({{block: 'start'}});
  }} else if (focus) {{
    document.getElementById('tab-' + panel.id).focus();
    document.querySelector('.tabs').scrollIntoView({{block: 'start'}});
  }}
}}
document.querySelector('.tabs').addEventListener('keydown', event => {{
  const index = tabs.indexOf(event.target);
  if (index < 0) return;
  const next = {{ArrowRight: (index + 1) % tabs.length, ArrowLeft: (index + tabs.length - 1) % tabs.length, Home: 0, End: tabs.length - 1}}[event.key];
  if (next === undefined) return;
  event.preventDefault();
  tabs[next].click();
  tabs[next].focus();
}});
document.addEventListener('click', event => {{
  const button = event.target.closest('button[data-target]');
  if (button) navigate(button.dataset.target, true);
}});
navigate();
}}
</script></body></html>
"""


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("check", "parse", "overview") or (argv[0] == "overview" and len(argv) != 3):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    record = parse(Path(argv[1]).read_text(encoding="utf-8"))
    if argv[0] == "parse":
        print(json.dumps(record, indent=2))
        return 0
    if argv[0] == "check":
        found = problems(record)
        for p in found:
            print(f"FAIL {p}")
        if found:
            print(f"{len(found)} problem(s)")
            return 1
        print("PASS record follows the format")
        return 0
    out = Path(argv[2])
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(overview(record), encoding="utf-8")
    tmp.replace(out)
    print(f"PASS wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
