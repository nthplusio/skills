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

One running record per project tells the owner where the work stands, what waits on them, and what landed. It is also their decision interface: the owner can understand the question, judge the recommendation, and give feedback from this page. One editor keeps it current, workers report to that editor, and every question reaches the owner already researched.

The record and feedback workflow are host-independent. Before setting up feedback or processing an owner's response, read [the feedback workflow](references/feedback.md). When running in Amp, also read [the Amp integration](references/amp.md) for publishing and messaging; other hosts do not need it. These references describe integration requirements, not a bundled feedback server.

## Roles

- **Owner:** the person who rules on decisions. They read the record and may
  edit it through its host.
- **Editor:** the one agent or thread that edits the record, usually the
  orchestrator. No other agent edits it; preserve the owner's edits.
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
| Owner's name and verified identity | `Dana`, with the host account authorized to rule |
| Editor and how reports reach it | an agent session, task queue or named human reviewer, with its delivery route |
| Where the record lives | a Markdown file in a repository, a wiki page or a hosted document |
| Feedback route and review mode | record comments reviewed manually on request, or a verified automatic review route |
| Source ladder, in order | meetings, then the design reference, then the apps, then the database read only |
| Whether workers can read the record | if not, the mirror in step 2 |

A caller that needs the record as data runs
`python3 -B <this skill>/scripts/record.py parse <record.md>`. This prints
JSON with the lanes, Done rows, and every item with its section, checked
state and fields. Use it to decide what to work on next, or to feed another
renderer such as the `dashboard` skill.

## Step 1: Find or start the record

Look for an existing record first. Check the caller's input, the host's documents, or a `STATUS.md` branch. Extend it; never start a parallel one.

To start one, copy
[`assets/tracking-document.template.md`](assets/tracking-document.template.md),
fill in the header, and ask the owner for the source ladder if nobody has
stated it. [`references/document.md`](references/document.md) defines each
section, and [`assets/example-record.md`](assets/example-record.md) shows a
filled-in record.

Establish the host's feedback capabilities using the feedback workflow. Put the review mode, destination, named editor and action that starts review in the record's **Where things stand** section. Reuse that route on later updates.

**Done when** the record exists at its host and
`python3 -B <this skill>/scripts/record.py check <record.md>` prints
`PASS`. A new record still holding template placeholders fails until they are
filled.

## Step 2: Give workers a mirror they can read

Workers may lack access to the hosted record. Then keep a read-only copy on its own orphan branch, which
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
4. If a mirror is needed, make the same change there: pull with `--ff-only`, then edit,
   commit and push.
5. Run `record.py check` and fix what it names. It catches open owner items
   without all their fields, items checked off without the ruling's date,
   dropdown chips in tables, and Done rows without a date or a linked commit.

## Step 4: Update at every milestone

| Milestone | Change |
| --- | --- |
| Delivery (push or merge) | Done row with Kind `Delivery`, checks and their counts; Lane work and Lanes updated; Where things stand rewritten |
| CI result | Add it to the Done row: "CI green on the first run", or exactly what failed and whether a rerun passed |
| New question | Route it first ([`references/answering-questions.md`](references/answering-questions.md)); add it to the record only where routing puts it |
| Research reply | An entry under Answered by research (open to veto), or a decision item under Needs \<Owner> |
| Owner feedback | Follow the feedback workflow: preserve the original response, identify who acts next, and record a ruling only when the owner has actually ruled |
| Lane state change | Lanes row and Lane work item |

In each reply that follows an update, identify the saved record revision (or commit/content hash) and whether the mirror, when used, matches it.

## Step 5: Draw the overview

Render the overview after each update:

```bash
python3 -B <this skill>/scripts/record.py overview <record.md> <overview.html>
```

The page is self-contained HTML in light and dark. The Overview tab keeps the current summary, count tiles, blocking-first decision queue, lane board and latest deliveries. Each tile opens its matching tab: Needs the owner, Owner ruled, Open to veto, Lanes, Delivered or Stopped. A queue row opens that specific decision; a lane card opens that lane's details.

Delivered and its CI totals include only history rows with Kind `Delivery`. Ruling events appear under Owner ruled without inflating its decision-item count. History retains all events, including unclassified legacy rows; classify those from evidence when migrating an older record, not from keywords or commit links.

Decision details show the full recommendation, why and tradeoff, what is held up, context and alternatives, with expandable sources and further reading. The other tabs retain rulings, research answers, lane owners and branches, lane work, all delivery checks and CI links, and stopped-work reasons. Summaries may be shortened; details keep the full recorded content. The Markdown record remains the source of truth.

Publish it where the owner reads the record, and update the same page on later renders; never create a second one. Embed the HTML when the host supports it. Otherwise link the HTML or keep the Markdown record alone. Host-specific publishing belongs in the integration reference, not in the record format.

When a decision is easier to judge as a picture, such as two layouts, a data
flow, or before and after, draw that picture too and embed it in the item's
Context using the host's supported visual format.

**Done when** the overview reflects the record's current revision, every tile opens the matching details, and opening an owner decision provides enough context to rule without following an external link. Inspect the rendered page and exercise a tile, a specific decision, its sources and a lane card before publishing renderer changes. The bundled renderer is read-only and uses the record's feedback route. A connected host may offer feedback controls only after the feedback workflow's capability checks pass; receiving an approval is not the same as recording a ruling.

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

When the owner responds, use the feedback workflow to distinguish a question, an alternative ruling, approval and veto. Show the receipt or follow-up beside the decision, including who acts next. Keep feedback processing independent of the tool that delivered it.

## Write for a busy owner

- Start with the outcome. In each item the first line answers "what do you
  need from me?", and the recommendation comes before its reasons.
- Use plain words. Define project terms the first time or replace them; cut
  internal codes when a name will do.
- Make each decision self-contained: state what happens today, what would change, the recommended answer, and why its tradeoff is acceptable. Spell out the recommendation rather than giving only an option letter. Put supporting detail in nested bullets; links supply further evidence, not the explanation needed to decide.
- Cite exactly: `file:line`, the meeting and its timestamp, or the query and
  its counts. Never cite "the meeting" or "the code".
- Use plain-text state words in tables. **Never put dropdown chips in
  tables.**
