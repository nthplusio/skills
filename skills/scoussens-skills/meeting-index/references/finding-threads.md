# Finding the threads

The threads are the deliverable. Everything else in the index — the ledger, the
decisions table, the owner list — is apparatus that lets a reader verify them.
Get this step wrong and you have produced thirty accurate summaries that nobody
needed, because each one already existed wherever the meetings were recorded.

Do it deliberately, before writing anything, reading across all the summaries at
once rather than letting themes fall out of summarising each meeting in turn.
Per-meeting reading produces topics. Reading across produces threads.

## A topic is not a thread

This is the distinction that decides quality.

A **topic** is something that got discussed. "Authentication" is a topic. It can
appear in six meetings and still tell the reader nothing they could not get by
searching for the word.

A **thread** is something that *moved*, or conspicuously failed to. It has a
shape across time: it started somewhere, something happened to it, and it is now
in some state. "The session-expiry bug was misdiagnosed as token expiry for two
weeks, then traced to unparsed error codes on Wednesday, and the fix is in but
unverifiable without a production deploy" is a thread. It has a beginning, a
turn and an unresolved edge.

Test each candidate: **can you say what changed?** If the honest answer is "it
kept being discussed", it is a topic. Either find the movement inside it or drop
it.

## Five patterns worth hunting

**A decision that took several meetings to converge.** Trace where it started,
what the alternatives were, who moved, and where it landed. The path is usually
more useful than the conclusion, because it explains why the obvious-looking
answer was not taken sooner — which is exactly what someone re-opening the
decision needs to know.

**The same problem recurring.** Two instances of one root cause days apart is a
far stronger finding than either instance alone, and it usually argues for a
systemic fix that no single meeting proposed. This is the highest-value pattern
and the hardest to see from inside any one meeting, because each instance looked
local to the people in the room.

**Independent convergence.** Two unrelated conversations arriving at the same
answer without knowing about each other is strong evidence, and worth flagging
*as* independent — that is what makes it evidence rather than repetition.

**Something everyone is waiting on.** Cross-reference blockers against owners.
An item three workstreams depend on and nobody owns is the single most valuable
thing an index can surface, and it is invisible per-meeting because each meeting
only sees its own side of the dependency.

**A live tension.** Not everything resolves. A disagreement still in play, named
honestly as unresolved, is more useful than a synthesis that papers over it. If
two people are still arguing, say so and say what each is optimising for.

## How many

Six to twelve for a week is about right.

Fewer than six usually means you are summarising days rather than finding
storylines. Many more than twelve means you are listing topics and calling them
threads — go back and apply the "what changed?" test.

## Give each one a state

A reader scanning the band should know where things stand without reading the
prose. Assign each thread one state and show it:

| State | Means |
| --- | --- |
| **Locked** | Decided and closed. Safe to build on. |
| **Directional** | A lean, not a commitment. Expect it to move. |
| **In flight** | Actively being worked. |
| **Open** | Named, not resolved, no owner moving it. |
| **At risk** | Something depends on this and it is not tracking. |

Be honest with these. Marking a directional lean as locked makes the period look
more settled than it was, which is the most common way an index like this misleads.

## Name where to replay

Each thread should carry the meetings it runs through — dates, or ids — so a
reader who disbelieves you can go and check. A thread the reader cannot verify
is an assertion, and assertions are what they were trying to avoid by asking for
an index.

## What to lead with when you hand it over

The findings that were invisible from inside any single meeting. Not "here are
the sections" — they can see the sections. The recurrence, the unowned
dependency, the four-day decision, the convergence. Those are what the exercise
bought, and they are worth saying in conversation even though they are also in
the output.
