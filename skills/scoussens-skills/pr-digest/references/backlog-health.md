# Reading an open-PR backlog

Reached from Step 2c, and only for the open-PR inventory scope. The digest
scopes ask "what shipped"; this one asks "what is here, and what of it is
still alive." Those need different evidence, and the flags below are it.

The measured lesson from the first run of this mode: on a 58-PR backlog,
**46 were drafts, and they were three different things wearing one badge** —
dead work, environment-provisioning placeholders, and genuine
work-in-progress. A flat oldest-first list cannot tell those apart, and a
reader who can't tell them apart concludes "we have 58 PRs of backlog,"
which was wrong by roughly a third. Every flag here exists to separate
those three populations.

## The flag that matters most: is the ticket already closed?

**This is the highest-value check in the whole mode and the cheapest to
get wrong.** A draft whose Linear ticket is already `Done` or `Canceled` is
finished business — the work merged by another route, or was deliberately
dropped, and nobody closed the branch. On the first run this was **7 of 46
drafts**, every one closable on the spot.

Do not spend one `mcp__linear__get_issue` per PR to find them. Sweep with
`mcp__linear__list_issues` instead, which accepts a `fields` allowlist:

```
mcp__linear__list_issues  state:"completed"  team:"<team>"
                          fields:["id","status","completedAt"]  limit:250
```

Repeat with `state:"canceled"`, once per team the extracted IDs actually
mention (the prefixes tell you: `INT-` → one team, `UI-` → another). Six
calls covered four teams on the first run, versus ~50 `get_issue` calls, and
`get_issue` returns multi-KB descriptions you don't need for a status check.

Three rules for using the result, each of which caused a real error or
near-error:

- **Intersect programmatically, never by eye.** PR numbers and ticket
  numbers occupy the same numeric range and collide constantly — `INT-1215`
  is a cancelled ticket, `#1215` is an open PR about `UI-306`, and
  `INT-1876` is a cancelled ticket while `#1876` is something else entirely.
  Write both sets to files and `comm` them.
- **`hasNextPage: true` means absence proves nothing.** The completed-issue
  list truncates at 250. A ticket missing from the sweep is *unconfirmed*,
  not *open*. Only ever claim "this ticket is closed," never "this ticket is
  still open," on the strength of this sweep.
- **Confirm each hit with one `get_issue` before publishing it.** The sweep
  finds candidates; a per-hit confirmation makes the claim safe to put in
  front of the person who owns the branch. Seven hits is seven calls — worth
  it, because "close this, it's already done" is the one assertion in the
  artifact that a reader will act on immediately.

A closed ticket is also where the *interesting* detail lives. `INT-1269`
turned out to be `Done` **and** to carry a revert PR, meaning the open
draft's 716-file diff described a state the repo had deliberately walked
back — a much stronger reason to close it than staleness alone.

## PRs that are not really PRs

Two distinct populations, and conflating them produces bad advice:

- **Zero changed files.** `changedFiles == 0` — a branch and a seed commit
  and nothing else. On the first run, three such PRs were consecutive rungs
  of a five-PR stack planned in one sitting where only two rungs got code.
  Always closable.
- **Near-empty, but deliberately.** One or two files, a handful of lines,
  often titled something like "dummy commit to startDPR" or "Sentinels Only
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

`mcp__linear__get_issue` returns an `attachments` array listing every PR
ever opened against that ticket. Count it. On the first run one ticket had
**eight**, another **six** with two still open simultaneously — a 2-line
stub and a 4,914-line implementation, by different authors. That pair is a
real finding: one of them is wasted review surface, and only the ticket's
attachment list makes it visible, since neither PR references the other.

Also watch for the same ticket ID extracted from two open PRs in your own
Step 3 output. That's the same signal, free, and it caught both cases above
before any Linear call.

## Size and CI flags

- **`changedFiles` in the thousands with near-zero deletions** is a
  committed dependency or build directory, not authored code. One such PR
  held 11,659 of the 13,655 files in the whole inventory. Say so and quote
  both totals — the raw sum and its contribution — or every repo-wide
  number you print is quietly meaningless.
- **`statusCheckRollup == []` is not "CI passing."** It's "no checks ran,"
  which on a 149-file diff is a gap worth flagging, not a clean bill. Give
  it a visually distinct pill from passing.
- **A failing check is sometimes not about the PR.** On the first run a red
  X was the repo's own review bot exhausting its turn budget on a large
  diff *after* posting its review. The reviewer said so explicitly in the
  review body. Read the review before reporting red as a defect.

## Staleness

Derive it from `updatedAt`, not `createdAt` — those answer different
questions, and only the second one is interesting. A 59-day-old PR pushed
this morning is active; a 22-day-old PR untouched since the hour it opened
is abandoned. Report both ("open 67d · idle 67d") when they diverge, and let
the idle figure drive the flag.

## Ordering and grouping

Order within a group by age, and say why in one line — age is the signal
this mode exists to surface, so an unexplained ordering wastes it.

Group by **workstream**, not by health. Health is a badge on the row; the
grouping should answer "what is this team actually building," which is the
question an inventory is for. On the first run 46 drafts fell into nine
workstreams with the largest holding six — a shape that reads as
"five real programmes plus residue," and that is the finding. Sorting the
same 46 into "dead / stale / active" buckets would have hidden it.

Then lift the actionable subset into **one callout above the groups** —
the PRs closable today, with the one-phrase reason each (`ticket Done
08-19`, `0 files changed`). The reader who wants only the to-do list gets
it without reading nine sections; the rows stay in their workstreams too,
so nothing is only in one place.
