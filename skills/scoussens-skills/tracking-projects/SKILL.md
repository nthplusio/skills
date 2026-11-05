---
name: tracking-projects
description: >-
  Keeps a project's running record of work done and remaining, with lanes,
  owner decisions, research answers, a Done table with checks and CI, and an
  overview visual. Each decision gives the owner the question, context,
  sources, recommendation, why, and what it holds up. Use when asked to start
  or update a project tracking document, a status record that worker threads
  report to, or an owner decision queue, or when an orchestrating skill or
  agent needs one. Not for one-off status replies, standups, or ticket edits.
compatibility: Python 3.9+ for scripts/record.py (standard library only). Git for the worker mirror.
---

# Tracking projects

One running record per project tells the owner where the work stands, what
waits on them, and what landed. One editor keeps it current, workers report
to that editor, and every question reaches the owner already researched.

## Roles

- **Owner:** the person who rules on decisions. They read the record and may
  edit it in the browser.
- **Editor:** the one agent or thread that edits the record, usually the
  orchestrator. Nobody else edits it.
- **Workers:** lane threads, subagents, or people doing the work. They read
  the mirror and report changes to the editor by message.
- **Researchers:** threads or subagents that answer one question each from the
  sources, read only.

## Use from another skill or agent

A calling skill, such as an orchestration loop, passes these values and keeps
its own work. This skill owns the record's format and how it is edited.

| Input | Example |
| --- | --- |
| Project slug and title | `layout-rebuild` |
| Owner's name, used in headings | `Dana` |
| Editor: the thread or agent that edits | the orchestrator thread's ID |
| Where the record lives | an Amp document artifact, a Markdown file in a repository, or a wiki page |
| Source ladder, in order | meetings, then the design reference, then the apps, then the database read only |
| Whether workers can read the record | if not, the mirror in step 2 |

A caller that needs the record as data runs
`python3 -B <this skill>/scripts/record.py parse <record.md>`. This prints
JSON with the lanes, Done rows, and every item with its section, checked
state and fields. Use it to decide what to work on next, or to feed another
renderer such as the `dashboard` skill.

## Step 1: Find or start the record

Look for an existing record first. Check the caller's input, the thread's
artifacts, or a `STATUS.md` branch. Extend it; never start a parallel one.

To start one, copy
[`assets/tracking-document.template.md`](assets/tracking-document.template.md),
fill in the header, and ask the owner for the source ladder if nobody has
stated it. [`references/document.md`](references/document.md) defines each
section, and [`assets/example-record.md`](assets/example-record.md) shows a
filled-in record.

**Done when** the record exists at its host and
`python3 -B <this skill>/scripts/record.py check <record.md>` prints
`PASS`. A new record still holding template placeholders fails until they are
filled.

## Step 2: Give workers a mirror they can read

Workers often cannot open the editor's record, for example an artifact owned
by another thread. Then keep a read-only copy on its own orphan branch, which
only the editor commits to. The branch has no pull request and is never merged.

```bash
git worktree add --orphan -b <project>-status <worktree path>   # Git 2.42+
cp <record.md> <worktree path>/STATUS.md
git -C <worktree path> add STATUS.md && git -C <worktree path> commit -qm "Status: start"
git -C <worktree path> push -u origin <project>-status
```

The separate worktree leaves the main checkout untouched. Workers read the
mirror with the command in the record's header:

```bash
git fetch --quiet origin <project>-status && git show origin/<project>-status:STATUS.md
```

Tell each worker, in its first brief, to read the mirror before starting each
piece, never to edit the record or the branch, and to report changes by message
in the shape shown in [`references/examples.md`](references/examples.md#a-workers-report-to-the-editor).

## Step 3: Edit without losing the owner's changes

The owner edits the record too. On every edit:

1. **Re-read the current revision** immediately before the edit, even when you
   wrote the last one. Edit against that revision; on a host with revisions,
   pass it as the base revision.
2. If the host refuses because someone saved a newer revision, read that
   revision and apply your change to it. **Never overwrite the owner's edits
   or rulings**, and never force a write unless the owner explicitly asks.
3. Change only the parts the milestone touches. Set `Last updated`.
4. Make the same change in the mirror: pull with `--ff-only`, then edit,
   commit and push.
5. Run `record.py check` and fix what it names. It catches open owner items
   without all their fields, items checked off without the ruling's date,
   dropdown chips in tables, and Done rows without a date or a linked commit.

## Step 4: Update at every milestone

| Milestone | Change |
| --- | --- |
| Delivery (push or merge) | Done row with the checks and their counts; Lane work and Lanes updated; Where things stand rewritten |
| CI result | Add it to the Done row: "CI green on the first run", or exactly what failed and whether a rerun passed |
| New question | Route it first ([`references/answering-questions.md`](references/answering-questions.md)); add it to the record only where routing puts it |
| Research reply | An entry under Answered by research (open to veto), or a decision item under Needs \<Owner> |
| Owner's ruling | Check the item off in place with `**Ruled YYYY-MM-DD by <Owner>:**`; add a Done row; message the lanes it affects |
| Lane state change | Lanes row and Lane work item |

In each reply that follows an update, say which revision the record is now
at, and that the mirror matches it.

## Step 5: Draw the overview

Render the overview after each update:

```bash
python3 -B <this skill>/scripts/record.py overview <record.md> <overview.html>
```

The page is self-contained HTML in light and dark. It shows:

- tiles with counts: decisions waiting on the owner, rulings, answers open to
  veto, lanes, deliveries and stopped work
- the owner's decision queue, each question with its recommendation and what
  it holds up, the blocking ones first
- the lanes as a board, coloured by state
- the latest deliveries, with their CI results

Publish it where the owner reads the record, and update the same page on later
renders; never create a second one. In Amp, publish it as a `visual` artifact
in the `visuals` folder and embed it under `Last updated` with
`![Overview](<artifact URL>)`. The embed always shows the latest revision. On
a host that cannot show HTML, link the file instead, or leave it out.

When a decision is easier to judge as a picture, such as two layouts, a data
flow, or before and after, draw that picture too and embed it in the item's
Context. In Amp, use the `creating-views` skill.

**Done when** the overview reflects the record's current revision.

## Step 6: Bring decisions to the owner

Every question goes through the source ladder before the owner sees it. Follow
[`references/answering-questions.md`](references/answering-questions.md):

- The editor decides reversible, in-scope questions itself, and records each
  one as "decided by me".
- A research thread checks every other question and returns a recommendation
  with citations.
- When the sources settle a question, record the answer as open to the owner's
  veto.
- Only a question the sources cannot settle goes to the owner.

Each item that needs the owner uses
[`assets/decision-item.template.md`](assets/decision-item.template.md). It
shows the question, the context with detail that expands, the sources checked
with citations, the options when there are real alternatives, the
recommendation, why (the reason and the tradeoff it accepts), and what it is
holding up, or "nothing yet".

## Write for a busy owner

- Start with the outcome. In each item the first line answers "what do you
  need from me?", and the recommendation comes before its reasons.
- Use plain words. Define project terms the first time or replace them; cut
  internal codes when a name will do.
- Keep the detail one level down, in nested bullets. Each top-level line
  should be enough to act on.
- Cite exactly: `file:line`, the meeting and its timestamp, or the query and
  its counts. Never cite "the meeting" or "the code".
- Use plain-text state words in tables. **Never put dropdown chips in
  tables.**
