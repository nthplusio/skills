---
name: dashboard
description: >-
  Renders one status file into a self-contained HTML status page for a
  non-technical reader and keeps it current in place at a destination the user
  chooses. Any producer feeds it through the same contract — an orchestration
  run, a single task that spawned subagents, a thread that spawned child
  threads. Use when asked for a "dashboard for this run", a "status page for
  these threads", or to "show me where the subagents are", and when a
  coordinating skill needs to present progress as one page. Do not load it to
  decide what the status is; the producer owns the record, and this skill
  draws it.
metadata:
  needs: artifacts
---

# Dashboard

One page that a tester or an executive can scan to see where the work is,
what is stuck, and what they need to decide, with the technical detail one
click away for engineers and agents. The page is drawn from one status file.
Whoever writes that file is the **producer**; this skill renders, delivers and
refreshes the page and does not judge the record's truth.

## Step 1 — Take the status file

The input is one JSON file that follows
[`references/status-contract.md`](references/status-contract.md). Read the
contract before writing or checking a file. The required fields are
`schema_version`, `run_id`, `title`, `tasks` and `presentation`; everything
else is optional and the contract says what the page shows in its place.

- A producer that already writes the file names its path. `orchestration-run`
  keeps `<run_root>/<run-id>/status.json` and checks its own lifecycle rules
  with its `validate_run.py` before calling this skill.
- A producer without a file, such as a task that spawned subagents or a thread
  that spawned child threads, writes the minimal record from the
  [producers table](#producers) and keeps it updated from what it can inspect:
  the harness's thread or subagent status, not a guess.
- The renderer rejects an unknown top-level key or an invalid value by name.
  Fix the record; do not extend the contract from one producer's needs.

Write the overview fields in plain language, as the contract's *Writing for
the reader* section says.

**Done when** you hold the path of one status file and know which producer
keeps it current.

## Step 2 — Settle the destination with the user

The page's destination is a setting, and `explain-to` owns settings. Load
`explain-to` and run its step 1, the settings sheet
(`references/settings-sheet.md` there), passing these facts:

- **The artifact.** A status page drawn from this skill's template; its
  layout, labels and dialogs are fixed by the template, not by the sheet.
- **Fixed settings.** Reader: the *business stakeholder* profile, because the
  overview uses plain labels and each row's summary, and the technical detail
  sits behind a click. Interaction: interactive, as the template already
  defines it (item and decision dialogs, copy controls), with no further spec.
  Anchor: none. Length: the template's own.
- **The open setting.** Output, from the destinations this session can
  deliver to the user. A **local file** counts when the user can open it. In a
  remote environment where the harness entry says the user cannot open local
  files, it is not offered. **Hosted pages** come from the running harness's
  discovery entry (`artifacts`), each with who can see it and whether it
  reloads an updated page from the same URL (`auto_refresh`). A tool that
  stores text does not count, because it drops the page's styles and scripts.
- **The rule for the Why cell.** Publishing shows every row's title, owner
  handle, link and proof to everyone who can see the page, so the narrowest
  audience that includes the people who need to read it is the
  recommendation. The user decides.

Skip the sheet, and name the destination in the first assumption line of
the reply, when the producer passes a destination the user already confirmed
(an orchestration run's confirmed run choices), when the user already said
where ("just open it", "publish it"), or when only one destination is
deliverable. A setup preference, a template value or an existing path is not
a choice. When the user asks only for a decision and leaves the destination
unanswered, keep the page unrendered and let the producer record the hold;
an old page stays unchanged and is not the current display.

**Done when** you hold one destination, agreed through the sheet or left as
the only one available, and its `auto_refresh` capability.

## Step 3 — Render

```bash
python3 <this skill's folder>/scripts/render_dashboard.py <status.json> <dashboard.html>
# Before hosting, reject local proof and owner links the audience cannot open:
python3 <this skill's folder>/scripts/render_dashboard.py <status.json> <dashboard.html> --hosted
python3 <this skill's folder>/scripts/render_dashboard.py --contract-version
```

The renderer writes the page atomically and leaves the previous page in
place when the record fails its checks, so a bad update never blanks the
destination. `PASS: rendered <path>` is the only success line. Set
`presentation.auto_refresh` from the destination's discovered capability, not
from a preference: `true` embeds a reload at the producer's
`monitoring.interval_seconds`; `false` or absent renders a static snapshot
and the page says so. Record the chosen destination and its hosted ID or URL
in the record's `presentation` so the next render updates the same artifact.

**Done when** the renderer prints `PASS` for the record at the chosen
destination's hosting mode.

## Step 4 — Deliver and keep it current

Write the page to the destination and update the same artifact or URL on
every later render; never create a second page for the same `run_id`. The
producer names the refresh interval; render after each of its updates.

After each update, compare the served page with the rendered file instead of
opening a browser:

```bash
python3 <this skill's folder>/scripts/check_served.py <dashboard.html> <served URL>
```

`PASS` ends the check. `LIMITED` means the page cannot be fetched from here,
such as behind a sign-in; record that limitation once and reuse it. `FAIL`
means the destination serves stale bytes; update it again. When first using a
destination with `auto_refresh`, check the served page's refresh directive
and that a timed reload retrieves an updated page from the same URL without
a manual reload; if the host strips the directive or serves stale HTML,
correct discovery and keep the page static with the limitation in `notice`.
Take screenshots or inspect the DOM only when the template or renderer
changed, as [`references/dashboard-layout.md`](references/dashboard-layout.md)
describes.

In a remote sandbox, a sandbox-local path or URL is not a delivery link; the
user needs a supported preview or portal. Publishing the page does not
authorize publishing the proof it links to, the code, or anything else.

**Done when** the destination serves the rendered bytes, or a recorded
limitation explains why that cannot be checked, and the reply gives the user
the path or link with who can see it.

## Producers

Three producers, and the smallest record each writes. Every row needs `id`,
`title` and `owner` with `id`, `label` and `state`; the contract lists the
optional fields and their defaults.

| Producer | Rows | Minimal status file |
| --- | --- | --- |
| An orchestration run (`orchestration-run`) | one per ticket, with stages, work status, proof, decisions and the run's lifecycle fields | The run writes the full shape in `evals/dashboard-preview.json` and checks it with its own `validate_run.py` first. The minimal run adds `goal`, `updated_at`, `config_path`, `run_choices`, `monitoring`, `approvals`, `follow_ups`, `skill_version`, `evidence`, `decisions` and `history` to the record below, and every row carries `milestones`, `runtime` and `work`. |
| A single task that spawned subagents | one per subagent | `{"schema_version": 2, "run_id": "task-migrate-auth", "title": "Migrate the auth module", "presentation": {}, "tasks": [{"id": "research", "title": "Compare the two session stores", "owner": {"id": "subagent-1", "label": "Research subagent", "state": "complete"}, "work": {"state": "delivered", "summary": "Recommended the signed-cookie store.", "reason": "Report returned."}}, {"id": "tests", "title": "Port the session tests", "owner": {"id": "subagent-2", "label": "Test subagent", "state": "active", "activity": "Rewriting the expiry cases."}}]}` |
| A thread that spawned child threads | one per child thread | `{"schema_version": 2, "run_id": "thread-42", "title": "Child threads of T-42", "presentation": {}, "tasks": [{"id": "T-42-1", "title": "Index last week's meetings", "owner": {"id": "thread-42-1", "label": "Meeting index thread", "state": "active", "href": "https://example.org/threads/T-42-1"}}, {"id": "T-42-2", "title": "Draft the release brief", "owner": {"id": "thread-42-2", "label": "Release brief thread", "state": "waiting"}, "work": {"state": "waiting", "summary": "Waiting for the meeting index to finish.", "reason": "The brief cites the index."}}]}` |

A subagent or thread producer sets `owner.state` from the harness's own
status (running, idle, awaiting input, finished, archived) and adds `work`
when it can say how a row ended. It adds `updated_at` at each render so the
reader sees how old the snapshot is, and `decisions` when a child is waiting
on the user.

## Changing the page

The template is `assets/dashboard-template.html`; the renderer is
`scripts/render_dashboard.py`. Before changing either, read
[`references/dashboard-layout.md`](references/dashboard-layout.md), which
fixes the overview, the dialogs, the copy and routing rules, and how to
verify a change. A change to a field, a value set or a default is a change
to the contract: update `references/status-contract.md`, bump
`CONTRACT_VERSION` in the renderer, and tell the producers.
