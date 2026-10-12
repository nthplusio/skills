# Reading an open-PR backlog

Reached from Step 2c, and only for the open-PR inventory scope. The digest
scopes ask "what shipped"; this one asks "what is open, and what of it is
still alive." Those need different evidence, and the flags below are it.

The measured lesson from the first run of this mode: on a large backlog,
**most PRs were drafts, and they were three different things wearing one
badge** — dead work, environment-provisioning placeholders, and genuine
work-in-progress. A flat oldest-first list cannot tell those apart, and a
reader who can't tell them apart reads the open count as the backlog,
which badly overstates the live work. Every flag below exists to separate
those three populations.

## The flag that matters most: is the ticket already closed?

**This is the highest-value check in the whole mode and the cheapest to
get wrong.** A draft whose ticket is already `Done` or `Canceled` is
finished business — the work merged by another route, or was deliberately
dropped, and nobody closed the branch. On the first run this was **a
meaningful share of the drafts**, every one closable on the spot.

Do not spend one per-ticket lookup per PR to find them. Sweep the tracker
for closed tickets in bulk instead. If the tracker is Linear,
`mcp__linear__list_issues` accepts a `fields` allowlist:

```
mcp__linear__list_issues  state:"completed"  team:"<team>"
                          fields:["id","status","completedAt"]  limit:250
```

Repeat with `state:"canceled"`, once per team the extracted IDs actually
mention (the prefixes tell you: `ABC-` → one team, `WEB-` → another). Other
trackers usually have an equivalent bulk search with a status filter; if
there is none, fall back to per-ticket lookups. A handful of per-team calls
replaces dozens of per-ticket ones, which return multi-KB descriptions you
don't need for a status check.

Three rules for using the result, each of which caused a real error or
near-error:

- **Intersect programmatically, never by eye.** PR numbers and ticket
  numbers occupy the same numeric range and collide constantly — `ABC-412`
  can be a cancelled ticket while `#412` is an unrelated open PR.
  Write both sets to files and `comm` them.
- **`hasNextPage: true` means absence proves nothing.** The completed-issue
  list truncates at the limit. A ticket missing from the sweep is
  *unconfirmed*, not *open*. Only ever claim "this ticket is closed," never
  "this ticket is still open," on the strength of this sweep.
- **Confirm each hit with one per-ticket lookup before publishing it.** The
  sweep finds candidates; a per-hit confirmation makes the claim safe to put
  in front of the person who owns the branch. N hits is N calls — worth it,
  because "close this, it's already done" is the one assertion in the
  artifact that a reader will act on immediately.

A closed ticket is also where the *interesting* detail lives. One closed
ticket turned out to be `Done` **and** to carry a revert PR, meaning the
open draft's large diff described a state the repo had deliberately walked
back — a much stronger reason to close it than staleness alone.

## PRs that are not really PRs

Two distinct populations, and conflating them produces bad advice:

- **Zero changed files.** `changedFiles == 0` — a branch and a seed commit
  and nothing else. These are often the unbuilt rungs of a PR stack planned
  in one sitting, where only the lower rungs got code. Always closable.
- **Near-empty, but deliberately.** One or two files, a handful of lines,
  often titled something like "placeholder to provision env" or "env-only
  DB". In a repo whose CI mints a per-PR database or environment keyed to
  the PR number, **the draft PR is the mechanism for getting that
  environment**, and the diff is beside the point. These are the ones you
  must not tell someone to close: another open PR may name that database as
  its staging ground, so closing it destroys infrastructure in use.

Distinguishing them takes one look at the ticket body, not a guess from the
diffstat. Check `CLAUDE.md` for a PR-provisioner / ephemeral-environment
pattern before labelling any small draft abandoned.

The number worth stating plainly once you've separated these: **the draft
count is not a work-in-progress count.** Say so in the synthesis, with the
figure, or the reader will keep reading it as one.

## Duplicate PRs on one ticket

If the tracker links PRs to tickets (Linear's `get_issue` returns them as an
`attachments` array), count them. One ticket can carry many, sometimes two
still open simultaneously — a 2-line stub and a several-thousand-line
implementation, by different authors. That pair is a real finding: one of
them is wasted review surface, and only the ticket's linked-PR list makes it
visible, since neither PR references the other.

Also watch for the same ticket ID extracted from two open PRs in your own
Step 3 output. That's the same signal, free, and it can catch such pairs
before any tracker call.

## Size and CI flags

- **`changedFiles` in the thousands with near-zero deletions** is a
  committed dependency or build directory, not authored code. A single such
  PR can hold most of the files in the whole inventory. Say so and quote
  both totals — the raw sum and its contribution — or every repo-wide
  number you print is quietly meaningless.
- **`statusCheckRollup == []` is not "CI passing."** It's "no checks ran,"
  which on a diff of a hundred-plus files is a gap worth flagging, not a
  clean bill. Give it a visually distinct pill from passing.
- **A failing check is sometimes not about the PR.** A red X can be an AI
  review bot exhausting its turn budget on a large diff *after* posting its
  review, and some reviewers say so in the review body. Read the review
  before reporting red as a defect.

## Staleness

Derive it from `updatedAt`, not `createdAt` — those answer different
questions, and only the second one is interesting. A two-month-old PR pushed
this morning is active; a three-week-old PR untouched since the hour it
opened is abandoned. Report both ("open 40d · idle 40d") when they diverge,
and let the idle figure drive the flag.

## Ordering and grouping

Order within a group by age, and say why in one line — age is the signal
this mode exists to surface, so an unexplained ordering wastes it.

Group by **workstream**, not by health. Health is a badge on the row; the
grouping should answer "what is this team actually building," which is the
question an inventory is for. If, say, forty drafts fall into nine
workstreams and five of them hold most of the work, that shape reads as
"five real programmes plus residue," and that is the finding. Sorting the
same drafts into "dead / stale / active" buckets would have hidden it.

Then lift the actionable subset into **one callout above the groups** —
the PRs closable today, with the one-phrase reason each (`ticket already
Done`, `0 files changed`). The reader who wants only the to-do list gets
it without reading every section; the rows stay in their workstreams too,
so nothing is only in one place.
