---
name: pr-teacher
description: >-
  Teach one pull request as an interactive artifact — the problem it solved, how
  its mechanism actually works, a map of where every changed file sits and why,
  something the reader can operate rather than only read, and a grounded
  self-check. Load this only when the user wants to understand or be taught a
  specific PR — "teach me PR 412", "explain this pull request", "help me
  understand what #1234 does", "walk me through this change", "I have to review
  this and I don't know the codebase", "quiz me on this PR", or when they paste
  a PR URL and ask what it does. Do not load it to recap a period of merged
  work, to produce a review verdict, or to answer one narrow factual question
  about a diff; answer those directly instead.
disable-model-invocation: true
---

# PR teacher

Produce one self-contained HTML artifact that teaches a single pull request
well enough that the reader can afterwards answer detailed questions about it
under pressure — in a review, in an interview, or when the thing breaks at
2am and they are the one who has to reason about it.

That bar matters, because it rules out the obvious failure mode. A summary of
what a diff changed is easy and nearly useless: the reader finishes it able to
recite file names and unable to explain why the change works. Aim instead for
the understanding someone has after they've debugged the code themselves.

## Step 1 — Resolve which PR

You need `owner/repo` and a PR number. Get them from whatever the user gave
you, in this order of preference:

- An explicit URL (`github.com/owner/repo/pull/N`) — unambiguous, use it.
- A bare number plus the current directory — resolve the repo with
  `gh repo view --json nameWithOwner -q .nameWithOwner`.
- A description with no number ("that CA bundle fix") — search rather than
  guess: `gh pr list --search "<terms>" --state all --limit 10` and confirm
  the match with the user if more than one is plausible.

Stop and ask if you cannot pin it down. Teaching the wrong PR in convincing
detail is worse than a clarifying question.

## Step 2 — Gather ground truth before composing anything

Everything you write has to trace back to something you actually read. Run
these first:

```bash
gh pr view <N> --repo <owner/repo> --json title,body,author,state,mergedAt,\
additions,deletions,changedFiles,files,headRefName,baseRefName
gh pr diff <N> --repo <owner/repo>
gh pr view <N> --repo <owner/repo> --json reviews,comments
```

Then — and this is the step that separates a real teaching artifact from a
narrated diff — **read the changed files in the repository, plus the code on
either side of them**: what calls into the changed function, what it calls,
what the tests assert. The diff tells you what moved. The surrounding source
tells you why that was the right place to move it, what else depended on the
old behavior, and what the author chose *not* to do. The reader's hardest
questions will all come from that second category.

If the repo is checked out locally, read the files directly. If not, use
`gh api repos/<owner>/<repo>/contents/<path>?ref=<sha>` or clone shallowly.

**Absorb the house rules too.** Look for `CLAUDE.md`, `CONTRIBUTING.md`,
`docs/conventions.md`, an ADR or `docs/decisions/` directory, and any
architecture notes the PR references. A change that looks arbitrary usually
becomes obvious once you know the convention it is satisfying — and "which
rule made them put it there" is exactly the kind of question the reader wants
to be able to answer. Where a PR *departs* from a documented rule, that is
worth teaching, not smoothing over.

Read the review conversation as well. Disagreements are compressed lessons:
they show where a reasonable engineer expected something different, which is
where the reader's intuition will also mispredict.

## Step 3 — Find the spine before you build

Before writing any HTML, answer one question for yourself: **what is the
single load-bearing idea here — the one that, once understood, makes
everything else in the PR follow?**

It is usually a specific, surprising, checkable fact. To show the *shape*
without handing you an answer — these are illustrative, from no particular
codebase, and yours will look nothing like them:

- *the graceful-shutdown handler awaits a buffer that shutdown itself stopped
  draining* — so the clean exit path is the only one that loses data.
- *the retry wrapper treats every exception as transient* — so a `401` is
  retried until the account locks itself out.
- *the cache key omits locale* — so whoever makes the first request of the day
  picks everyone else's language.

Notice what they have in common: each is one sentence, names a specific
mechanism, and implies a consequence that sounds wrong until you trace it.
Find the equivalent sentence for the PR in front of you — derived from the
code you read in Step 2, never pattern-matched onto an example above.

Build the whole artifact around that spine. An artifact organized as seven
disconnected panels reads as a checklist; one organized around a spine reads
as an explanation, and it is far easier to remember. If you genuinely cannot
find a spine, the PR is probably mechanical (a dependency bump, a rename) —
say so plainly and keep the artifact short rather than inflating it.

## Step 4 — Build the artifact

Load the `artifact-design` skill first to calibrate the visual treatment. This
is a teaching instrument, not a landing page: information design, real
hierarchy, restraint with motion. Aim for something the reader will scroll
through twice, not something that performs at them once.

**Keep the page mostly teaching.** `artifact-design` says to inline a typeface
as a `@font-face` data URI rather than link one, because the artifact CSP
blocks font CDNs and a linked font fails silently. That advice is about *not
linking*; it is not a licence to embed a family. One run of this skill shipped
a 437KB page that was 87% base64 font — eight weights — which is mostly
payload the reader waits on before reaching a word of explanation. Budget
roughly **120KB for fonts and no more than two weights**, and prefer a
considered system stack unless the subject genuinely calls for a distinctive
face. A teaching page rarely does.

Include these, in an order that serves the spine — the sequence below is the
usual one, not a mandate:

**1. The problem.** Open with the concrete symptom somebody actually
observed: an error string, a failing request, a wrong number on a screen, a
build that burned 28 minutes and produced nothing. Specifics anchor memory in
a way that "improves reliability" never will. If there was an incident, lead
with it. If the PR is preventative, say what would have happened.

**2. The file-structure map.** A visual tree of every path the PR touched,
placed in the repository's real layout, each node annotated with what changed
there and — the part that teaches — why that directory is the right home for
it under this project's conventions. Make nodes expandable for per-file
detail. The reader should come away able to answer "where does this live and
why" without looking it up. For a PR spanning many files, group by subsystem
and show counts rather than listing all hundred.

**3. The mechanism.** How the change actually works, stepped through in
order. Where control flow, data flow, or a state transition carries more than
prose would, draw it — a ```mermaid fence renders natively in artifacts, so
reach for one rather than describing a graph in words.

**4. Before and after.** The two or three hunks that carry the real change,
side by side, with the decisive lines called out. Use the actual code and real
line numbers. Show only the lines where the behavior turns — a reader who
scrolls past forty lines of unchanged context learns nothing.

**5. Something the reader operates.** See `references/interactions.md` for
how to choose one that fits this particular change — this is the section most
often done badly, because a tabbed accordion is easy and teaches nothing. The
test is simple: does it make the reader *predict, then check*? If they can
absorb it by scrolling past, it is decoration.

**6. Why it matters.** Blast radius, what breaks without it, what it
unblocks, what it cost to find. Be concrete about scope — one tenant or all
of them, one endpoint or the whole API, CI only or production.

**7. Self-check.** Six to ten questions with revealable answers, escalating
from recall ("which module owns X?") through mechanism ("what happens on the
second call?") to judgment ("why this approach over the alternative, and what
does it give up?"). Ground every answer in the real code. The judgment
questions are the valuable ones — they are what the reader will actually be
asked, and they are the ones a diff summary cannot produce.

## Step 5 — Publish

Publish with the `Artifact` tool. Give it a stable favicon (`🔬` works well
for this series) and a title naming the PR, so a reader who generates several
can tell their tabs apart.

## Honesty rules

These matter more here than in most artifacts, because the reader is going to
repeat what you tell them to other engineers.

- **Every claim traces to something you read.** Where you are inferring
  intent rather than reading it, say so — "the author does not explain this,
  but the surrounding code suggests…" is genuinely more useful than false
  confidence, because it tells the reader where the solid ground ends.
- **Teach the open questions, and quote them.** If a reviewer raised something
  unresolved, or the PR merged with changes still requested, or a known
  limitation is documented in a comment, include it — a reader who believes a
  change is settled when it is contested will be caught out, and the shape of
  the disagreement is often the most instructive part. **Give the reviewer's
  actual words**, pulled from `gh pr view --json reviews`, rather than your
  summary of them. Paraphrase loses the thing that makes a review useful: the
  precise objection, in the vocabulary the team argues in. "The reviewer had
  concerns about error handling" teaches nothing next to the sentence they
  actually wrote. Attribute it, and say whether it was resolved, deferred, or
  overridden at merge.
- **Real identifiers over illustrative ones.** Actual paths, actual function
  names, actual line numbers. A reader who memorizes a plausible-sounding
  invented name is worse off than before.
- **Assume language fluency, not codebase familiarity.** Explain what *this*
  lock protects and who contends for it, and let the reader already know what
  a lock is.
