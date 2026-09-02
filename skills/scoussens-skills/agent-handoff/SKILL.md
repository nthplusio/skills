---
name: agent-handoff
description: Write a handoff another agent or person can act on without coming back to ask a question — opening with a preflight that proves the state still holds, carrying only the context and decisions that are load-bearing for what remains, and putting the remaining work in a dependency-mapped action table with a completion criterion on every row. Load this only when the user explicitly asks for a handoff — "write a handoff", "hand this off", "brief the next session", "I'm running out of context, write this up", "package this for a subagent", "document where we got to so someone else can pick it up". Do not load it to summarise a conversation, to write a status update or a standup note, to plan work nobody has started, or to write a commit message or pull request description; answer those directly instead.
---

# Agent handoff

A handoff is not a summary. A summary tells the receiver what happened; a
handoff lets them act. The test is whether they can start work without coming
back to ask a question — and the questions they would ask are always the same
three: what is true right now, what has already been settled, and what is next.
That is the whole document.

Two failures account for most bad handoffs. The first is **exposition** — a
narrative of the session in the order it happened, from which the receiver has
to reconstruct the task themselves. The second is **decay** — a handoff
describes a world that keeps moving after you write it, so a receiver who
trusts it acts on a branch that has since moved, a check that has since gone
red, or work someone else has already done.

Structure fixes the first. A preflight fixes the second.

## Ask three questions first

Two of these you cannot derive; the third you can usually confirm rather than
ask.

1. **Who picks this up?** A fresh session of the same agent, a subagent being
   delegated to, or a person. The structure below does not change — same
   preflight, same three sections, same five columns. What changes is what each
   one has to spell out: a fresh session needs every referent resolved inside
   the document, a subagent needs its boundaries more than your history, a
   person needs the rationale first and will skim the rest. When you do not
   know, write for the fresh session — it is the strictest of the three. See
   [references/writing-for-the-receiver.md](references/writing-for-the-receiver.md).
2. **Where does it land?** A file in the repository, a paste-ready block in the
   reply, or a comment on the tracker issue. See [Deliver it](#deliver-it).
3. **What does finished look like for the whole job?** The table says what to do
   next; it does not say what the work is for, and a receiver who executes every
   row and stops still has to guess whether the job is done. The conversation
   usually establishes this already — state it back and let the user correct
   you rather than asking cold.

## Build it backwards

The document reads Preflight → Context → Decisions → Actions. You build it in
the opposite order, and that is the point: **the action table is the spine, and
every other line has to be load-bearing for a row in it.**

Write the actions first. Then admit a fact into Context only when some row
needs it in order to be executed, and a decision only when some row would
otherwise be reopened. A fact supporting no row is exposition. It reads as
diligence and spends attention the receiver needs elsewhere.

That rule applies sentence by sentence, which is why it beats a length limit.

## Establish what is true before writing any of it

Everything downstream inherits the accuracy of this step, and it pays twice:
the facts you gather become Context, and the commands you gathered them with
become the preflight.

```bash
git status --porcelain --branch && git rev-parse --short HEAD
git stash list && git worktree list
gh pr view --json number,state,mergeStateStatus,statusCheckRollup 2>/dev/null
```

Record the answer beside each command, never the command alone. A preflight
line reading `git rev-parse --short HEAD` with no expected hash asks the
receiver to run something and compare it against nothing.

[references/gathering-state.md](references/gathering-state.md) covers the full
sweep — the position, the work in flight, the environment, the tracker — plus
which facts decay fastest and how to turn a finding into a check whose failure
is actionable.

## The action table

Every remaining piece of work is one row. A row is the unit the receiver picks
up, so it has to be small enough to finish and specific enough to verify.

| ID | Action | Blocked by | Done when | Touches |
| --- | --- | --- | --- | --- |
| A1 | Add `retryCount` to the job model and migrate | — | `pnpm db:migrate` applies clean and the column exists | `packages/db/schema.prisma` |
| A2 | Increment `retryCount` on the worker's catch path | A1 | A failing job's row reads 3 after three attempts | `apps/worker/src/run-job.ts` |
| A3 | Confirm the retry cap with the client | EXT client | They state a number | — |
| A4 | Cap retries and route the overflow to the dead-letter queue | A2, A3 | A job over the cap lands in `dead_letter` | `apps/worker/src/run-job.ts` |

**`ID`** exists so other rows can point at it. Anything stable works; `A1`,
`A2` is enough.

**`Action`** is one imperative line. If it needs two, it is two rows.

**`Blocked by`** is what makes this a map rather than a list, and it carries one
distinction that matters more than anything else on the page: **an internal
blocker resolves by working; an external one does not.** A row waiting on `A1`
clears the moment the receiver does `A1`. A row waiting on a client, a review, a
deploy window, or a credential clears only when somebody else acts, and a
receiver who cannot tell them apart works down a queue that stalls silently.
Write internal blockers as IDs, external ones as `EXT <who owns it>`, and an
unblocked row as an em dash.

**`Done when`** is the row's completion criterion, and it decides whether the
handoff works at all. *Update the worker* ends whenever the receiver decides it
feels done. *A failing job's row reads 3 after three attempts* ends when it is
observably true. Prefer something the receiver can run or see.

**`Touches`** saves the receiver a search, then does a second job nobody expects
of it: it says which unblocked rows can run **at the same time**. Two ready rows
touching the same file are not parallel work. The dependency column gives the
order; this column gives the width.

## Context is the position, not the game

A chess position is completely described without the moves that produced it,
and so is yours. Write what stands now, in the present tense — the receiver is
inheriting a position, not a history.

Three things earn their place almost every time, because the receiver cannot
recover them by looking:

- **Where the work physically is.** Branch, worktree, uncommitted and staged
  changes, stashes, anything half-applied.
- **What is half-done.** Partly-finished work is the most dangerous thing in a
  handoff, because from the outside it looks finished. Say how far it got and
  what state it left behind — the migration written but not applied, the three
  of five call sites updated, the test that passes for the wrong reason.
- **The traps you already hit.** A failing check with a non-obvious cause, a
  command that only works from one directory, a generated file that goes stale.
  Each is legwork the receiver would otherwise repeat from scratch.

Everything else has to earn its row.

## Decisions keep the receiver from reopening them

A decision recorded without its rejected alternatives gets relitigated. The
receiver reaches the same fork, does not know you already stood there, and
either reruns the whole analysis or quietly takes the other branch. The second
is worse: it lands as an inconsistency nobody notices for a week.

Each decision needs four things and fits in two lines:

- **What was settled**, stated as a rule the receiver can apply.
- **Why**, in one clause — the constraint that forced it.
- **What was rejected**, named. This is the part doing the work.
- **What would reopen it** — the fact that, were it false, would change the
  answer.

Attribute the user's decisions to the user, and say so plainly. A receiver
reading *we chose Postgres* may argue with it. One reading *the user chose
Postgres over SQLite because the reporting workload needs window functions*
will not.

## Open with a preflight

The document decays from the moment you save it, so it opens with a short block
of checks the receiver runs before touching anything — each carrying the result
you observed.

```
Preflight — stop if any line disagrees.
- `git rev-parse --short HEAD` → a4f19c2
- `git status --porcelain` → 3 modified files, the ones listed under Context
- `gh pr checks 214` → green
- NTPL-88 in the tracker → In Progress, assigned to you
```

Four to six lines. A preflight long enough to skim past is a preflight nobody
runs, so check only the facts the actions actually depend on.

Say what a disagreement means, not merely that it happened. A moved `HEAD` may
be harmless or may void the entire table, and only you know which.

## Check the table before you hand it over

A dependency table is a directed graph written by hand, and by hand is where
graphs acquire cycles that deadlock, dependencies pointing at rows that do not
exist, and rows with no end condition. None of that is visible by reading.

```bash
python3 scripts/check-handoff.py <file>
```

It fails on duplicate IDs, dangling dependencies, cycles (printing the loop),
and blank actions or completion criteria. Those are properties of the table
rather than of the script, so read for them by hand if it is not there. Then it prints back what the table
actually says — which rows are ready now, which wait on someone outside the
room, the longest chain through the dependencies, and any two ready rows that
touch the same file and therefore cannot run at once. Read that output as a
description of the plan you just wrote. It is the cheapest review the document
will get, and it routinely disagrees with what you thought you had written.

## Deliver it

| | Best for | What it changes |
| --- | --- | --- |
| **File in the repository** | Agent to agent, and anything past a handful of rows | Survives the session and can be handed over as a path. Put it where the repo already keeps working notes, and say in your reply whether you think it should be committed |
| **Paste-ready in the reply** | Starting the next session immediately | Nothing on disk. Keep it inside a single fenced block so it survives one copy |
| **Tracker comment** | Work that belongs to an issue somebody else will claim | Lives with the ticket. Tables render, but check the tracker's flavour and keep `Touches` short |

Whatever the format, hand over **one document**. A handoff split across a file,
a message, and a memory of something you said earlier is three-quarters of a
handoff, and the receiver gets no signal about which quarter is missing.

If the `speak-clearly` skill is available, apply it to the prose sections.

Close your reply by naming what you verified, what you could not, and the row
you are least confident about.

## Do not use this skill for

- **Summarising a conversation.** A summary is read; a handoff is executed.
- **A status update or standup note.** Those report progress to somebody who is
  not going to do the work.
- **Planning work nobody has started.** A handoff transfers a position. With no
  position to transfer, you are writing a plan.
- **A commit message or pull request description.** Those explain a change that
  is already finished.

It is invoked deliberately, by name or by an explicit request to hand work over.

## Done when

- The receiver is identified, and the depth of the prose matches them.
- Every fact in Context is load-bearing for a row in the action table.
- Every row carries a completion criterion the receiver can run or observe.
- Internal blockers are IDs; external blockers name who owns them.
- The table holds no cycle, no dependency naming a row that does not exist,
  and no row missing a criterion. `scripts/check-handoff.py` proves all three
  in one pass where it is available.
- The ready set, the longest chain, and the file conflicts the table implies
  are the ones you meant it to say.
- Half-finished work is described by how far it got and what it left behind,
  rather than by what it was meant to do.
- Every decision names what was rejected and what would reopen it, and the
  user's decisions are attributed to the user.
- The preflight is four to six lines, each carrying the result you observed,
  and it says what a disagreement means.
- The whole handoff is one document.
- Your reply names what you could not verify and the row you trust least.
