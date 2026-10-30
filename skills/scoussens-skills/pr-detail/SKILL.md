---
name: pr-detail
description: >-
  Retrospective on one pull request — a timeline of how it actually went, a
  ledger of what every reviewer said and whether it was acted on, and a scored
  evaluation of the execution, published as an HTML artifact. Load this only
  when the user explicitly asks how a PR went — "how did this PR go", "review
  the process on #101", "retrospective on this pull request", "how did this
  developer handle that change", "why did this PR take three weeks". Do not
  load it to teach the code a PR changed, to produce a review verdict on
  something still open, or to recap a period of merged work; answer those
  directly instead.
disable-model-invocation: true
---

# PR detail

Produce one HTML artifact that answers a question a lead actually has about a
specific pull request: **how did this go, and what does it say about how this
developer works?**

Written for the lead, not the author — third-person, assessment tone, the kind
of thing that could be quoted in a 1:1 or a performance note without
embarrassment. Which sets the bar: **every judgment in it has to be traceable
to a specific comment, commit, check run, or timestamp.** An evaluation of a
named person's work that rests on impressions is worse than no evaluation,
because it is persuasive and unfalsifiable at the same time. If you cannot
point at the evidence, cut the claim.

## Step 1 — Resolve which PR

You need `owner/repo` and a number:

- An explicit URL (`github.com/owner/repo/pull/N`) — unambiguous, use it.
- A bare number plus the current directory — `gh repo view --json nameWithOwner -q .nameWithOwner`.
- A description with no number — `gh pr list --search "<terms>" --state all --limit 10`,
  and confirm with the user if more than one is plausible.

Stop and ask if you cannot pin it down. Assessing the wrong person's PR in
convincing detail is the worst outcome this skill has available to it.

## Step 2 — Ask how deep to go, and where it goes

Ask one question of your own — whether to judge the PR standalone or against a
baseline — with the harness's structured question tool when it has one
(`ask_user` in its entry of the repository's `.nthplusio-skills/discovery.json`),
otherwise in your reply. The destination is a setting, and `explain-to` owns
settings: load `explain-to` and run its step 1, the settings sheet
(`references/settings-sheet.md` there), in the same message, passing the
artifact (a retrospective on one PR that scores a named developer's execution),
the settings this skill fixes (reader: the lead, in third person; output: one
HTML page laid out as Step 8 says; interaction, length, and anchor as that
layout sets them), and the one open setting, the page's destination. The rule
for the Why cell: the page evaluates a named person, so who can see each
destination decides it. The skill has already decided the rest.

- **Standalone (recommended default)** — this PR on its own evidence. One PR's
  worth of API calls, and the rubric is fixed, so scores are still comparable
  between runs.
- **Against the author's recent PRs** — pull their last ~10 merged PRs and
  compute the same mechanical counts, so "3 blocking findings" can be stated as
  "3, against their running average of 0.8." Far more meaningful and
  substantially slower.
- **Against repo norms on this branch** — the same counts across recent PRs
  from everyone. Answers "is this a lot?" but risks comparing a hard PR to easy
  ones; say so if the user picks it.

Skip the question outright if the user already said which they wanted.

## Step 3 — Gather the evidence

Resolve `SKILL_DIR` to this installed skill's absolute directory. Use a new
directory for each assessment and keep both files until the artifact is built:

```bash
RUN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/pr-detail.XXXXXX")
bash "$SKILL_DIR/scripts/gather_pr.sh" <owner/repo> <N> > "$RUN_DIR/pr.json" &&
  python3 "$SKILL_DIR/scripts/metrics.py" "$RUN_DIR/pr.json" > "$RUN_DIR/metrics.json"
```

If either command fails, stop rather than assessing an empty or stale file.
Read `evidence.failedFetches` and `evidence.truncatedSources` in the metrics
before interpreting any count. If `evidence.complete` is false, counts describe
only observed records: disclose each missing source, retry it or withhold the
dependent score, absence claim, and person-level conclusion. CI covers at most
the first 40 returned commits and reports that limit when exceeded; a failed
check-runs fetch is not a commit with passing checks. Remove only this run's
directory after finishing with its evidence.

`metrics.py` emits counts only, never judgment, and it already absorbs the
five data-source traps that would otherwise skew them — both scripts' comment
blocks explain each, worth opening only when a figure looks wrong. One
consequence reaches you regardless: attribute person-level facts from the
author-scoped fields (`commitsByAuthor`, not `commitsTotal`), because a branch
that absorbed upstream work carries other people's commits.

Then gather what the scripts deliberately do not:

- `gh pr diff <N> --repo <owner/repo>` — you need the actual change to judge
  scope and testing, not just its size.
- The linked tracker issue. Extract the ticket ID from the title and
  `headRefName` case-insensitively (`[A-Za-z]{2,10}-[0-9]{1,6}`, uppercased);
  branch names are often lowercase, so an uppercase-only pattern misses tickets
  that appear only in the branch. Look up each surviving ID in the tracker
  (for Linear, its MCP server's `get_issue` tool; otherwise its equivalent) — a 404 just
  means the regex matched something that wasn't a ticket, so drop it silently. **The issue's acceptance criteria are the scope
  yardstick**: "did this do what was asked, and only what was asked" is not
  answerable from the diff alone.
- The repo's own standards, so the evaluation grades against the team's rules
  rather than your preferences: `AGENTS.md` or `CLAUDE.md`, any conventions doc, and any ADR
  the PR or its review cites. If the repo documents a layering rule or a
  review SLA (for example in an ADR), cite it by name when a finding turns on
  one, and set `PR_DETAIL_SLA_HOURS` to a published SLA so `metrics.py`
  reports breaches against it.

## Step 4 — Separate the three actors before reading a single comment

A PR's comment stream mixes three kinds of participant, and conflating them
produces claims that are simply false about a person:

1. **The AI reviewer** — whichever bot login the repo uses; find it with
   `gh pr view <n> --repo <owner/repo> --json reviews -q '.reviews[].author.login'` rather than
   assuming a name. It is `[bot]`-suffixed in timeline events and un-suffixed in
   `reviews`, so match both forms. Its findings are real
   and worth counting, but "a bot flagged this" and "a teammate blocked this"
   are different facts and must read differently in the artifact.
2. **Human reviewers.** A human choosing to `REQUEST_CHANGES` is the strongest
   quality signal on the PR, because a person spent their own time deciding it
   wasn't ready.
3. **Pure automation** — tracker link-backs, per-PR environment postings, label
   bots. These are not feedback. Counting them as review activity inflates
   "engagement" with noise.

## Step 5 — Reconstruct the timeline

Build a chronological narrative from `timeline`, merged with the review
submissions from `reviews` — **`timeline`'s own `reviewed` events under-count
real reviews** (an empty-bodied review can be missing from it), so use it for
ordering and for the events reviews cannot express (`ready_for_review`,
`head_ref_force_pushed`, `review_dismissed`, `convert_to_draft`, `merged`) and
`reviews` for the review set itself.

What makes a timeline worth reading is not the event list — it is the gaps and
the loops. Call out, in prose next to the timeline:

- **Where the PR waited, and on whom.** Six days between a review and the next
  commit is the author sitting on feedback; six days between a push and the
  next review is the *reviewer* holding the PR. These look identical in an
  event list and mean opposite things about the developer. Get the direction
  right — grading an author for latency they didn't control is the single
  easiest way to make this document unfair.
- **Rework loops.** Each `review_dismissed` marks "the author pushed after
  feedback." Two rounds is normal; six suggests either a hard change or
  feedback that wasn't landing.
- **The shape of the ending.** Merged with threads open? Merged by someone
  other than the author? Auto-merge enabled early? Each says something specific
  about how much confidence the change had at the end.

## Step 6 — Build the good/bad ledger from what reviewers actually said

Do not invent praise or criticism. Both sides are already written down.

**The good side has a real source.** If the AI reviewer's body has a
strengths or verified section (concrete positives, or what was checked and
found sound), quote it. That is genuine, specific, attributable praise — use
it rather than writing your own generous summary. Human
approvals and any positive review comments belong here too. If a PR was
approved, say by whom.

**The bad side is the finding threads.** For each, the artifact needs four
things, and the fourth is the one that takes work:

1. What was raised — the finding's own title, if it has one (`metrics.py`
   reads a leading `**[Title]**`), and a trimmed excerpt in the reviewer's
   words. Paraphrase loses the precise objection, which is the useful part.
2. Who raised it and in which category — if its comments carry a category tag
   (`_(source: ...)_`), `metrics.py` splits by it. A tag can be
   **multi-valued**, so trust its `byCategory` over your own count.
3. Where — real path and line.
4. **What actually happened to it.** This is the part that separates an honest
   ledger from a scary one. A thread's `isResolved` flag is *weak evidence*: an
   unresolved thread can mean "still broken" or it can mean "fixed in the next
   commit and nobody clicked the button." On one PR all seven threads read as
   unresolved at merge, and the author had replied in none of them — but the
   fix may well be sitting in the diff. **Go look**: read the later commits and
   the merged code at that path. Then classify it honestly as *fixed in code* /
   *rebutted by the author* / *acknowledged and deferred* / *merged still open*
   / *cannot tell from the evidence*, and say which. "Cannot tell" is a legitimate
   answer and a better one than a confident guess.

A finding the author **correctly pushed back on is a positive, not an error.**
It shows they understood the code better than the reviewer did. Put it on the
good side of the ledger and say so.

## Step 7 — Score the six dimensions

Score each 1–10. A score without its evidence line is not a score, it is an
opinion with a number attached — so every one carries a single concrete
sentence naming the counts, quotes, or timestamps behind it, and the artifact
shows that sentence next to the bar, never behind a click.

| Dimension | What it measures | Evidence to cite |
|---|---|---|
| **Correctness** | Did it work, and did defects escape? | Blocking findings and their fate; human `CHANGES_REQUESTED`; post-merge fixes or reverts |
| **Scope discipline** | Did it do what was asked, and only that? | Diff size vs. the ticket; files unrelated to the ticket; any acceptance-criteria verdicts in the AI review (a criterion it couldn't confirm) |
| **Testing** | Was it verified before others had to? | Test files in the diff; any testing notes in the AI review; the PR body's own testing section; whether findings were the kind a test would have caught |
| **Convention adherence** | Does it match how the repo builds things? | Convention or framework findings; documented layering rules; named rules from the repo's conventions docs |
| **Review responsiveness** | How did they handle feedback? | Hours from review to their next commit; threads replied to; findings addressed vs. left; whether pushback was reasoned |
| **Submission readiness** | Was it ready when they asked for review? | CI state on the first pushed commit; `commitsWithFailingChecks`; fixup-style commits; draft hygiene; force-pushes after review |

**Normalize before you judge.** Three findings on a 1,500-line PR touching 22
files is a different fact from three findings on a 20-line fix; `metrics.py`
gives you `perKLoc` for exactly this. A hard PR attracting more review is
evidence about the problem, not about the person — and a lead reading this
needs to be able to tell those apart.

Close with an **overall read**: two or three sentences on what this PR
suggests about how the developer works, earned from the dimension scores rather
than averaged from them. Then a short **what to do differently** list — at most
three items, each tied to a specific thing that happened. The value of this
artifact to a lead is the coaching conversation it makes possible, and three
specific things beat ten general ones.

## Honesty rules

These carry more weight here than in the sibling skills, because this document
is about a person and may outlive the conversation that produced it.

- **Report behavior, never traits.** "Merged with seven review threads still
  open" is a fact a reader can check and the developer can respond to.
  "Careless" is neither. The behavior is also the more useful of the two,
  because it names something that can change.
- **Say what you couldn't see.** If the PR predates the AI reviewer, or the
  diff was too large to read in full, or the ticket had no acceptance
  criteria, put that in the artifact as a stated limit on the assessment. A
  confident evaluation built on partial evidence is the failure mode with the
  worst consequences here.
- **Attribute every delay to whoever held it.** A PR open eight days
  because review took six of them is a *flow* problem — worth surfacing against
  the repo's review SLA if it publishes one, and as the reviewer's, not the author's.
- **One PR is one data point.** Say so, in the artifact, when the run is
  standalone. Anyone reading a scored evaluation will be tempted to generalize
  from it, and the artifact should push back on that itself rather than relying
  on the reader's restraint.
- **Quote, attribute, and link.** Every finding links to its comment, every
  commit to its SHA, every check to its run. The reader should be able to
  disagree with you by clicking through — which is the property that makes the
  document safe to share.

## Step 8 — Build and publish

If an artifact-design skill is available, load it first. This is a decision-support document —
someone reads it before a conversation with a colleague. Dense, legible,
scannable in two minutes and re-readable in ten. Restraint matters more than
usual: visual drama around a person's evaluation reads as editorializing.

Layout, top to bottom:

1. **Masthead** — PR title, number linking to GitHub, author, base branch,
   merge state, linked ticket, and the hard numbers (+adds/−dels, files,
   days open, review rounds, findings). Facts only.
2. **Summary** — what the PR set out to do and whether it did it, grounded in
   the ticket rather than the diff stat.
3. **Timeline** — a vertical time-ordered track, each entry with actor and
   timestamp, visually distinguishing the three actor classes from Step 4.
   Annotate the gaps and loops (Step 5) inline; an unannotated event list is
   the version of this section that teaches nothing.
4. **Good / bad ledger** — two columns, quoted and attributed. Every finding
   row carries its category tag, its location, and its **fate** as a distinct
   visual state (fixed / rebutted / deferred / open at merge / unknown) — five
   distinguishable states, not one pill recolored.
5. **Developer evaluation** — the six dimensions as labeled bars, each with its
   score, its evidence sentence *visible* beside it, and the baseline
   comparison if Step 2 asked for one. Then the overall read and the at-most-
   three "what to do differently" items.
6. **Limits of this assessment** — the Step 7 honesty items, stated plainly and
   not collapsed. This section exists to be read.

Publish to the destination agreed in Step 2, read from the harness entry as
`explain-to`'s `references/formats.md` ("Hand-offs by harness") describes. Use
favicon `🔍` and a title with the PR number and a short name, so several runs
stay distinguishable in a tab strip.

## Staying in your lane

When someone asks how the code *works* mid-run, point them at `/pr-teacher`
for a separate run instead of growing a mechanism section here. This artifact is about execution;
a good evaluation stays out of the business of explaining the diff.
