# Writing for the receiver

The structure of a handoff never varies. Every one opens with a preflight,
then Context, Decisions, and an action table carrying all five columns. What
varies is how much each part has to spell out, because the three receivers
fail in different ways.

Decide this once, before writing, and hold it for the whole document. A
handoff that addresses a subagent in its Context section and a colleague in its
Decisions section reads as though two people wrote it, and the receiver cannot
tell which parts were meant for them.

## A fresh session of the same agent

It shares your tools, your conventions, and your repository access. It shares
none of your memory.

**Every referent has to resolve inside the document.** *The bug we discussed*,
*the approach we settled on*, *that file* — each is a dead pointer, and the
receiver cannot ask what it meant. Names, paths, identifiers, line numbers.

**Do not re-explain the codebase.** It will read `AGENTS.md`, the config, and
the surrounding code as readily as you did, and a paragraph restating what a
file already says is a cache of a cheap lookup. Spend the space on what it
cannot find by looking — the convention nobody wrote down, the reason behind a
choice, the trap that cost you an hour.

**It will trust you completely**, which makes a wrong line worse here than
anywhere else: a confident error becomes an executed error. Mark the lines you
are unsure of, in the document, as unsure.

**Its characteristic failure is redoing work.** It reads the goal, does not
realise three of the five call sites are already updated, and starts from the
top. Guard against that in Context, by stating exactly how far each half-done
piece got.

## A subagent being delegated to

It gets a slice, not the whole, and its view is partial by design.

**Boundaries beat history.** It needs the goal of its slice, the surfaces it
owns, and — stated positively — what stays as it is. A subagent with a partial
view will helpfully repair something outside its slice, and the repair lands as
a conflict or a surprise in a diff nobody expected it in.

**Context shrinks to what the slice needs**, and the load-bearing rule does the
cutting for you: rows the subagent does not own contribute no facts.

**Decisions become constraints.** Frame each as a rule it must not violate
rather than as history it should appreciate, and keep the rejected alternative,
because that is what stops it re-deriving the choice from first principles
inside its own slice.

**Say what to report back**, and in what shape. A subagent that finishes its
rows and returns prose leaves you re-reading the work to find out what happened.

## A person

They bring judgement and can ask you a question. They also skim, and they have
no patience for machine formatting.

**The first screen carries the point.** Lead with where the work stands and
what to do next. A person who has to read three paragraphs to find the task
will read none of them.

**Rationale over enumeration.** Decisions is the section they most need, and it
should read as reasoning rather than as a record.

**Keep the table.** It is the most human-useful part of the document — the one
place the shape of the remaining work is visible at a glance — and dropping it
for a colleague is a common and costly instinct. `Done when` may loosen from a
command to an observable outcome; the columns stay.

**Say what is reversible.** A person weighs risk before acting, and the fact
that a step can be undone in a minute changes whether they take it today.

The preflight becomes *here is how to check nothing has moved since I wrote
this*, and it may be a sentence rather than a command list.

## When the receiver is unknown

Write for the fresh session. It is the strictest of the three: no shared
referents, no ability to ask, complete self-containment. A handoff that works
for it works for the other two, and the reverse does not hold.
