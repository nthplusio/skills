# The record, section by section

The record is one Markdown page. Start it from
[`../assets/tracking-document.template.md`](../assets/tracking-document.template.md);
[`../assets/example-record.md`](../assets/example-record.md) is a filled-in
example. `scripts/record.py` finds sections by these heading words, so keep
them: a heading may add words after them, such as
`### Needs Dana` or `### Decisions already approved (21)`.

## Header

- **Title:** `# <Project>: work done and remaining`.
- **Editing rule:** one sentence naming the editor, saying workers read the
  mirror and report changes by message instead of editing.
- **Mirror command:** the exact command a worker runs to read the mirror.
- **`Last updated: YYYY-MM-DD`:** change it on every edit. A host's date
  chip, such as Amp's `{{date:2026-11-05}}`, is fine.
- **Overview embed:** the overview visual, when the host can show one (see
  SKILL.md, step 5).

## Where things stand

Three to five bullets the owner can read in ten seconds: the outcome so far,
the delivery head with its CI result, how many decisions wait on the owner and
the one holding up the most work, and where the mirror lives. Rewrite these
bullets at each milestone; do not append to them.

## Lanes

A table: `Lane | Owner | Branch | State | Now`. One row per worker thread,
person or watcher. State is a plain word: Working, Held, Idle, Watching or
Ended. **Never put a dropdown chip or other interactive chip in a table**: chip
syntax contains `|` and breaks the row, and repeated saves stack escape
characters.

## How open questions get answered

The owner's rule for answering questions, with its date: the sources in their
fixed priority order, that a research thread checks each question first, that
only unsettled questions reach the owner, and what the editor decides itself.
[`answering-questions.md`](answering-questions.md) describes the procedure.

## Remaining work

### Needs \<Owner>

Every question only the owner can settle, in the decision-item format
([`../assets/decision-item.template.md`](../assets/decision-item.template.md)).
Put open items first, with the one holding up the most work at the top. When
the owner rules, **check the item off in place**. Add a first sub-bullet
`**Ruled YYYY-MM-DD by <Owner>:** <the ruling>`, and keep the
recommendation beneath it so the reasoning stays. When a ruling differs from
the recommendation, say what it replaces. Move ruled items to
**Decisions already approved** only when the owner asks you to tidy up.

The decision item has these fields:

| Field | Holds | Required |
| --- | --- | --- |
| Title | The question in plain words, ending with `?` | yes |
| Context | One sentence that stands alone, then detail as nested bullets | yes |
| Sources checked | Each source with a citation: `file:line`, meeting and timestamp or cue, or the query and its counts. Name the sources that had nothing. Link the research thread | yes |
| Options | The real alternatives, lettered. Leave it out when there is only one sensible answer | when there are alternatives |
| Recommendation | The answer, outcome first. "None yet" with the reason when research could not form one | yes |
| Why | The reason the sources give, then `**Tradeoff:**` and what it accepts | yes |
| Holding up | The ticket, lane or piece that waits on the ruling, or "nothing yet" | yes |

Context is expandable: the first sentence is all a busy owner needs. Detail
goes in nested bullets under it, which rich editors can fold. On a host that
renders HTML, `<details>` works too.

### Decisions already approved

Rulings the owner approved in a batch, one line each: the rule as it now
reads, the date, and `*Holds:*` what it unblocked.

### Answered by research (open to \<Owner>'s veto)

Answers the sources settled, and decisions the editor made itself. Label each
one with how it was settled: `(research, YYYY-MM-DD)` with the citations and
the research link, or `(decided by me, YYYY-MM-DD)` with why it is
reversible. The owner can veto any of them. When the owner vetoes one, record
the veto and its date in place and move the question to **Needs \<Owner>** if
it is still open.

### Stopped

Work or messages deliberately not done, each with why and what replaced it, so
nobody restarts them.

### Lane work

One checklist item per active piece: the lane, the piece, its state, and what
it waits on. Check an item off when it is delivered, and add a Done row for it.

## Done

A table, newest first: `Date | What | Where`.

- **Date:** `YYYY-MM-DD`, or `earlier` for rows carried over from before the
  record existed.
- **What:** what landed, in one sentence. Then the checks that were run, with
  their counts, and the CI result with a link to the run. Say "CI green on
  the first run", or say exactly what failed and whether a rerun passed.
- **Where:** the commit, linked to its page. A ruling that has no commit names
  the lane or thread that carries it.

Rulings get a Done row too, so the table is the project's history.
