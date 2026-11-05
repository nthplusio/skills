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
            }
            record["items"].append(item)
            continue
        if item and line.startswith("  "):
            item["text"].append(line.strip())
            if re.match(r"  - ", line):
                found = field_of(line)
                item["_open"] = None
                if found and found[0] not in item["fields"]:
                    item["fields"][found[0]] = found[1]
                    if not found[1].strip():
                        item["_open"] = found[0]
            elif item.get("_open"):
                # A field written as a label with nested bullets takes its first bullet.
                item["fields"][item["_open"]] = re.sub(r"^\s*(?:- |\d+\. )", "", line)
                item["_open"] = None
            continue
        if line.strip() and not line.startswith(" "):
            item = None
    flush_table()
    for it in record["items"]:
        it["text"] = "\n".join(it["text"])
        it.pop("_open", None)
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
        missing = [f for f in OPEN_ITEM_NEEDS if f not in it["fields"]]
        if missing:
            names = ", ".join(n.replace("_", " ").capitalize() for n in missing)
            out.append(f"{label}: open owner item lacks {names}")
    for row in record["done"]:
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


def overview(record: dict) -> str:
    items = record["items"]
    open_needs = [i for i in items if i["section"] == "needs" and not i["checked"]]
    ruled = [i for i in items if i["section"] == "needs" and i["checked"]]
    count = lambda kind: sum(1 for i in items if i["section"] == kind)
    holding = [i for i in open_needs if not re.match(r"nothing", plain(i["fields"].get("holding_up", "")), re.I)]
    lanes = record["lanes"]
    done = record["done"]
    ci = {"pass": 0, "fail": 0, "none": 0}
    for row in done:
        ci[ci_state(row.get("what", ""))] += 1

    tiles = [
        ("Needs the owner", len(open_needs), f"{len(holding)} holding up work", "warn" if holding else ""),
        ("Ruled", len(ruled) + count("approved"), "approved or ruled", ""),
        ("Open to veto", count("research"), "answered by research or decided by the editor", ""),
        ("Lanes", len(lanes), f"{sum(1 for l in lanes if lane_tone(l.get('state', '')) == 'held')} held", ""),
        ("Delivered", len(done), f"{ci['pass']} CI green, {ci['fail']} failed", "bad" if done and ci_state(done[0].get("what", "")) == "fail" else ""),
        ("Stopped", count("stopped"), "deliberately not done", ""),
    ]
    tile_html = "".join(
        f'<div class="tile {tone}"><div class="n">{n}</div><div class="k">{html.escape(k)}</div>'
        f'<div class="s">{html.escape(s)}</div></div>'
        for k, n, s, tone in tiles
    )

    def queue_row(i):
        hold = plain(i["fields"].get("holding_up", "")) or "not stated"
        idle = re.match(r"nothing", hold, re.I)
        rec = spell_option(i["fields"].get("recommendation", ""), i["fields"].get("options", ""))
        return (
            f'<li class="q{" idle" if idle else ""}"><div class="ask"><strong>{inline(i["title"])}</strong>'
            f'<span class="rec">{inline(first_sentence(rec)) if rec else "No recommendation yet."}</span></div>'
            f'<div class="arrow" aria-hidden="true">→</div>'
            f'<div class="hold"><span class="lbl">Holding up</span>{html.escape(first_sentence(hold, 160))}</div></li>'
        )

    ordered = sorted(open_needs, key=lambda i: bool(re.match(r"nothing", plain(i["fields"].get("holding_up", "")), re.I)))
    queue = "".join(queue_row(i) for i in ordered) or '<li class="empty">Nothing waits on the owner.</li>'

    lane_html = "".join(
        f'<div class="lane {lane_tone(l.get("state", ""))}"><div class="lh"><strong>{inline(plain(l.get("lane", "")))}</strong>'
        f'<span class="st">{html.escape(plain(l.get("state", "")))}</span></div>'
        f'<div class="now">{inline(l.get("now", ""))}</div></div>'
        for l in lanes
    ) or '<p class="empty">No lanes recorded.</p>'

    done_html = "".join(
        f'<tr><td class="d">{html.escape(plain(r.get("date", "")))}</td>'
        f'<td><span class="ci {ci_state(r.get("what", ""))}">{ {"pass": "CI green", "fail": "CI failed", "none": "no CI"}[ci_state(r.get("what", ""))] }</span></td>'
        f'<td>{inline(first_sentence(r.get("what", ""), 200))}</td><td>{inline(r.get("where", ""))}</td></tr>'
        for r in done[:12]
    )
    more = f'<p class="more">{len(done) - 12} earlier rows are in the record.</p>' if len(done) > 12 else ""
    standing = "".join(f"<li>{inline(s)}</li>" for s in record["standing"][:5])

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
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px}}
.tile{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}}
.tile .n{{font-size:24px;font-weight:650}}.tile .k{{font-weight:600}}.tile .s{{color:var(--mute);font-size:12px}}
.tile.warn{{background:var(--warnbg);border-color:var(--warn)}}.tile.bad{{background:var(--badbg);border-color:var(--bad)}}
ol.queue{{list-style:none;margin:0;padding:0;display:grid;gap:6px}}
.q{{display:grid;grid-template-columns:minmax(0,3fr) auto minmax(0,2fr);gap:10px;align-items:center;border:1px solid var(--warn);background:var(--warnbg);border-radius:8px;padding:8px 12px}}
.q.idle{{border-color:var(--line);background:var(--card)}}.q .rec{{display:block;color:var(--mute);font-size:13px}}
.arrow{{color:var(--mute);font-size:18px}}.hold .lbl{{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--mute)}}
.lanes{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}}
.lane{{border:1px solid var(--line);border-left:4px solid var(--mute);border-radius:6px;padding:8px 10px;background:var(--card)}}
.lane.work{{border-left-color:var(--work)}}.lane.held{{border-left-color:var(--warn)}}
.lh{{display:flex;justify-content:space-between;gap:8px}}.st{{font-size:12px;color:var(--mute)}}.now{{font-size:13px;margin-top:2px}}
table{{width:100%;border-collapse:collapse}}td{{border-top:1px solid var(--line);padding:6px 6px;vertical-align:top}}td.d{{white-space:nowrap;color:var(--mute)}}
.ci{{font-size:12px;padding:1px 7px;border-radius:10px;white-space:nowrap;background:var(--card);color:var(--mute)}}
.ci.pass{{background:var(--okbg);color:var(--ok)}}.ci.fail{{background:var(--badbg);color:var(--bad)}}
.empty,.more{{color:var(--mute)}}
@media (max-width:640px){{.q{{grid-template-columns:1fr}}.arrow{{display:none}}}}
</style></head><body><main>
<h1>{html.escape(record['title'])}</h1>
<p class="meta">Last updated {html.escape(record['last_updated'] or 'unknown')}. Drawn from the record; the record is the source of truth.</p>
<ul class="standing">{standing}</ul>
<div class="tiles">{tile_html}</div>
<h2>Waiting on the owner, and what each decision holds up</h2>
<ol class="queue">{queue}</ol>
<h2>Lanes</h2>
<div class="lanes">{lane_html}</div>
<h2>Delivered</h2>
<table><tbody>{done_html}</tbody></table>{more}
</main></body></html>
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
