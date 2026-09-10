---
name: pr-digest
description: >-
  Recap every pull request merged to a branch over a period as one HTML
  artifact — grouped by theme, each tied to its issue-tracker ticket, explained
  both for the user and for the codebase, and closed with what the period adds
  up to; optionally covering what is still open and in review. Load this only
  when the user explicitly asks for such a recap — "what shipped this week",
  "digest the PRs merged this sprint", "release notes for last month", "what
  landed on staging since the cut", "catch me up on recent development". Do not
  load it to explain one pull request, to write a commit message, or to review
  anything still open; answer those directly instead.
disable-model-invocation: true
---

# PR digest

Produce a single HTML artifact that teaches a reader what actually shipped
to a branch over some window of time — not a raw PR list, but grouped by
theme, with each item explained for two different audiences (what changes
for the person using the product, versus what changes in the codebase and
why), and a synthesis that earns its conclusion from the real grouping
rather than a generic "good week" line. Optionally, it also shows what's
currently sitting open and ready for review, so the reader sees not just
what shipped but what's about to.

**Two shapes, one pipeline.** The default is that digest — a time window,
merged PRs, full-detail cards. The other is an **open-PR inventory**: no
time window at all, *everything* currently open including drafts, at a
deliberately lighter level of detail, answering "what is actually sitting
here, and what of it is still alive." Steps 1–7 cover both; where they
diverge it's marked. Pick the shape in Step 0 and don't mix them — a
reader who asked what the backlog looks like is not served by a
this-week narrative, and vice versa.

## Step 0 — Ask before running

Confirm branch, scope, and period with one
`AskUserQuestion` call (up to 4 questions fit in one prompt, so this is a
single round-trip, not three). Skip asking anything the user already
stated explicitly in their own words; if they said "digest the last two
weeks on `release/foo` including in-review PRs," you already have all
three answers and should just confirm briefly rather than re-ask.

- **Branch** — offer the repo's resolved default (see Step 1) as the
  recommended option, plus any other branch the user has mentioned this
  session, and let "Other" cover the rest.
- **Scope** — three options, and this is the question that picks the shape:
  1. *Merged only* (recommended) — the digest.
  2. *Merged + currently ready-for-review* — the digest plus a second,
     live-snapshot section.
  3. *Everything currently open, drafts included* — the **inventory**
     (Step 2c). No merged PRs at all.
- **Time period** — offer "This week so far" (recommended default),
  "Last week," "This sprint/cycle," and let "Other" cover an explicit
  range. Ask for the period every run *when the scope involves merged
  PRs*: one extra turn buys back a whole rerun whenever a hardcoded
  default would have guessed wrong.
- **Depth** — *full detail* (recommended) vs. *light pass* (title + Linear
  ID + one line each, no per-PR "for the user / under the hood" split).
  Ask this only when you already have reason to expect a big result — a
  month-plus window, or an inventory on a long-lived branch. Otherwise let
  Step 2's count-based check ask it later, once you know the real number.

**The period question is moot in inventory scope, so don't ask it there.**
An inventory is a live snapshot with no window. Offering a period anyway
invites the user to answer a question you're about to ignore — on the first
run of this mode the user typed their actual scope into the period slot,
because the period options didn't fit what they wanted. If you can't tell
from their words which scope they mean, ask scope first and alone; a second
turn is cheaper than a digest of the wrong shape.

**Also default to inventory when their words point there** rather than
offering it as one option among three: "what's open," "what's in flight,"
"the backlog," "what's sitting there," "all open PRs," "how many PRs do we
have open," "what can we close." None of those describe a time window.

## Step 1 — Resolve the branch and the time window

**Branch**: default to whatever this repo treats as the PR-merge target —
check `CLAUDE.md`'s SDLC/branching notes or the git-status header shown at
session start ("Main branch (you will usually use this for PRs)") first;
fall back to `gh repo view --json defaultBranchRef -q .defaultBranchRef.name`
if neither is available. This is the *recommended* option in Step 0's
question, not a silent decision — only skip asking if the user already
named a branch.

**Period**: *inventory scope has no period — skip straight to Step 2c.*
Otherwise, once Step 0 settles on a period, convert it to explicit UTC
ISO-8601 instants (`date -u -d "..." +%Y-%m-%dT%H:%M:%SZ`) before doing
anything else, and use the current calendar week (Monday through now) as
the concrete shape of "this week so far" rather than a trailing "last 7
days" — a trailing window drifts across weekday boundaries and produces a
different-shaped digest depending on what day someone happens to run it,
which makes two runs a week apart hard to compare. For "this sprint" or
"this cycle," call `mcp__linear__list_cycles` and use the active cycle's real
start and end dates — a guessed week boundary lands on the wrong sprint.

This isn't pedantry: GitHub's `mergedAt` timestamps are always UTC, and
the detection script in Step 2 matches directly against them — passing a
bare `YYYY-MM-DD` and hoping the timezones work out is exactly the kind of
assumption that produces a digest silently missing PRs at the edges of the
window. Decide once, upfront, whose clock defines "this week" (the user's
local time is usually right), then do the UTC conversion so the rest of
the pipeline never has to think about timezones again.

## Step 2 — Find every PR that actually merged (digest scopes only)

Run `scripts/find_merged_prs.sh <branch> <start-utc> <end-utc>` from this
skill's directory. It shells out to `gh pr list --search "merged:X..Y"`
rather than walking git history — read the comment block at the top of
that script if you want the full story, but the short version: three
different git-log strategies were tried while building this skill (grep
the default merge-commit title, `--first-parent` traversal, `--merges`
with `--since`/`--until`) and each one silently **under-counted** real
merged PRs, for structural reasons a better regex or a wider date window
can't fix — squash-merged PRs collapse to a single-parent commit invisible
to `--merges`, and stacked PRs (one person's PR opened against a
teammate's still-open feature branch) only ever show a base ref of that
feature branch, not this one, which git ancestry alone can't distinguish
after the head ref is deleted on merge. GitHub's own PR search knows the
real base ref and real merge time directly, so it doesn't have either
problem. If `gh auth status` fails, the script exits with an explanation
rather than quietly falling back to a git-log approach that's already been
shown to undercount — tell the user to run `gh auth login` and stop there;
a degraded answer that *looks* complete is worse than a clear error.

Handle the two edge cases up front:

- **Zero PRs.** Say so plainly and move on to Step 2b if in-review PRs
  were requested — an empty merged list doesn't mean an empty digest.
- **A very large result** (rule of thumb: 50+ PRs — a month-long or
  whole-sprint window on an active repo can get there fast). Full-detail
  treatment means one `gh pr view` and often one Linear lookup per PR;
  before burning that, tell the user the count and ask whether they want
  the full treatment or a lighter pass (title + Linear ID + one line,
  no per-PR "for the user / under the hood" split).

## Step 2b — Find PRs ready for review (only if requested)

Run `scripts/find_open_prs.sh <branch>`. Unlike the merged list, this is a
**live snapshot, not bound to the time window** — a PR opened three weeks
ago that's still sitting ready for review today belongs in the digest
precisely because it's stale, so filtering it out by open-date would hide
the thing worth noticing. The script excludes drafts by default, which is
what this step wants; `--include-drafts` is Step 2c's business.

Read `references/review-status.md` and derive the two pills for each result:
one CI pill from `statusCheckRollup`, and one review pill that must survive the
`reviewDecision` trap — a comment-only review, however thorough, leaves
`reviewDecision` at `REVIEW_REQUIRED`, and reading that as "nobody has looked"
once told a PR author their own just-finished review was "awaiting review" in
the same paragraph that quoted it.

Same large-result guidance as Step 2 applies here independently — a
long-lived branch can easily have 20+ PRs sitting open.

## Step 2c — Take inventory of everything open (inventory scope only)

Run `scripts/find_open_prs.sh --include-drafts <branch>`. Without that flag
the script filters drafts out, which for this scope would discard most of
the answer: on the first run of this mode **46 of 58 open PRs were drafts**,
and they were the entire point.

This replaces Steps 2 and 2b — there is no merged set and no time window.
Everything open counts, however old, because age is the finding rather than
a reason to filter.

**Then read `references/backlog-health.md` before writing anything.** A
backlog is not a long digest, and the reason is specific: drafts are not one
population. They are dead work, deliberate environment-provisioning
placeholders, and genuine work-in-progress, mixed together and
indistinguishable from a flat list. That reference carries the checks that
separate them — the cheap bulk Linear status sweep that finds PRs whose
ticket is already closed, how to spot a zero-file PR versus a
one-file-but-load-bearing one, the duplicate-PRs-per-ticket count, and why
an empty `statusCheckRollup` is not "CI passing."

Two guardrails specific to this scope:

- **Report the count before you spend on it.** 50+ open PRs is normal on a
  long-lived branch, and full-detail treatment is one `gh pr view` plus a
  Linear lookup each. State the count and confirm depth (Step 0's fourth
  question, if you didn't already ask it) before enriching. Light pass is
  usually right here: the value of an inventory is the shape of the whole,
  not the detail of any one row.
- **Reconcile the rendered set against the fetched set before publishing.**
  Write both PR-number lists to files and `comm` them — every open PR
  appears exactly once, nothing invented, nothing dropped. An inventory's
  whole claim is completeness, so a silently missing row is the one defect
  that discredits the entire artifact, and it costs one command to rule out.

## Step 3 — Enrich each PR

For each PR — merged, ready-for-review, or draft — pull the detail that
actually explains it:

- `gh pr view <n> --json title,body,author,mergedAt,additions,deletions,changedFiles,files` —
  the PR's own account of what changed and how it was tested. **Skip this
  call entirely on a light pass**: Step 2/2c already returned title, author,
  branch, dates and diffstat in bulk, and that is everything a one-line
  entry needs. One `gh pr view` per PR across 58 PRs buys nothing a light
  pass will print.
- **Extract the Linear ticket ID(s) from the title and `headRefName`
  first, case-insensitively** (`[A-Za-z]{2,10}-[0-9]{1,6}`, normalized to
  uppercase — e.g. `INT-1234`, `UI-267`, `API-171`, `DEVOPS-168`; keep the
  prefix open, this workspace uses several). Case-
  insensitivity matters: branch names here are lowercase by convention
  (`sethcoussens/int-1765-fix-...`), so a pattern that only matches
  uppercase silently misses every ticket that only shows up in the branch
  name and not the title. Title/branch matches are reliable signals of
  *this PR's own* ticket — treat a match found only in the PR body as a
  cross-reference to some other, related PR/ticket, not necessarily this
  one's (bodies routinely say things like "builds on INT-1766" or "fixes
  a CI failure from #1762").
- **Don't trust the regex blindly — two known ways it lies:** (1) this
  repo's own PR template has an unfilled placeholder
  (`<!-- ... write "Fixes INT-123" here -->`) that survives verbatim in
  PRs where nobody replaced it, and will match the pattern as a fake
  ticket; (2) a loose prefix match also catches incidental code-shaped
  tokens in prose (`cache-5`, `tier-1`, `actions-3`). The cheap, reliable
  fix for both: the Linear lookup in the next bullet **is** the real
  filter — a candidate ID that 404s or errors just isn't a ticket, drop it
  silently rather than trying to out-guess it with a better regex.
- **Not every PR has a ticket** — dependency bumps and some infra chores
  won't, and that's fine; it means the PR is routine housekeeping, not
  that something went wrong. Give it a compact one-line entry instead of
  forcing a full card with invented context.
- For every PR with a surviving ticket ID, call `mcp__linear__get_issue` —
  batch all of these lookups in parallel in one turn rather than one at a
  time. This is where the *why* actually lives: a PR body says what files
  changed, but the Linear issue says what problem it was solving and what
  was deliberately left out of scope. Explain from the issue; a paraphrased
  diff stat is not an explanation.
- **On a light pass, spend `get_issue` selectively rather than uniformly.**
  Two things make a lookup earn its cost: the title is opaque, or the ticket
  *state* is the finding. Opaque titles are common and obvious once you look
  — a branch-name dump like "Vigneshkotagiri/api sd endpoints validation"
  tells the reader nothing, whereas "fix(api): compress responses" is
  already a one-line entry. Skip the lookup where the title already explains
  the change, and say in the artifact which subset you verified rather than
  implying you checked all of them.
- **When you need ticket *state* across many PRs, sweep, don't poll.**
  `mcp__linear__list_issues` takes a `fields` allowlist
  (`["id","status","completedAt"]`) and a `state` filter, so a handful of
  per-team calls returns every closed ticket compactly — versus one
  multi-KB `get_issue` per candidate. On the first inventory run this was 6
  calls instead of ~50. `references/backlog-health.md` has the exact query
  and, importantly, the three ways the intersection goes wrong.

## Step 4 — Group into themes, not merge order

Read across everything you just gathered before writing a word. Several
PRs merged the same week are often chapters of one larger thing — an epic
closing across 2-3 PRs, a multi-PR migration — and belong in one themed
section together, in the order they logically build on each other, not in
raw chronological/PR-number order. A one-off bug fix or a routine
dependency bump doesn't need a theme invented for it; group truly small,
mechanical items (dependabot bumps, one-line fixes with no ticket) into a
short "housekeeping" section as compact single-line entries rather than
padding them into full cards.

The ready-for-review set (if requested) doesn't need this same thematic
treatment — there are usually far fewer of them, and the reader's question
is "what's in flight and is it stuck," not "how does this fit the week's
narrative." A flat list ordered oldest-open-first is normally enough; only
group them if two or more are visibly part of the same stack.

**In inventory scope, group by workstream and flag health separately.** The
grouping answers "what is this team actually building"; a badge on each row
answers "is this one alive." Don't collapse the two by sorting into
dead/stale/active buckets — on the first run, 46 drafts fell into nine
workstreams with the largest holding six, which reads as *five real
programmes plus residue*, and that shape **is** the finding. Bucketing by
health would have destroyed it.

Order within each group by age, and say in one line that you did. Age is
the signal this scope exists to surface, so leaving the ordering
unexplained wastes it.

## Step 5 — Write it for two audiences (or one line, on a light pass)

For each PR that gets a full card, write two short, separate call-outs
instead of one blended paragraph — the split forces honesty about what
actually changed:

- **For the user** — the visible or eventual effect on someone using the
  product. If there genuinely isn't one yet (foundational/plumbing work,
  a change behind a feature flag), say that plainly instead of inflating
  it with vague "improves reliability" language. For a ready-for-review
  PR, this is necessarily anticipated ("once this merges...") rather than
  observed — say so.
- **Under the hood** — the technical why, grounded in the Linear issue's
  stated goal/background and the PR's own testing notes, not a rephrasing
  of which files changed.

For each ready-for-review card, add the CI-status pill and the review-status
pill from Step 2b (`approved` / `changes requested` / `no blocking issues` /
`awaiting review` — four visually distinct states, not the same pill
recolored) plus, whenever Step 2b surfaced one, the excerpt from the latest
review body as a third, short element — a status pill or line is enough, it
doesn't need its own paragraph. Only "awaiting review" should ever appear
without an excerpt; the other three all have a real review to quote.

**On a light pass, one line per PR replaces both call-outs** — what the
change is and, where it matters, why it's stuck. Don't write a thinner
version of the two-audience split; write the one sentence a reader needs to
decide whether to open it. Reserve two or three sentences for the handful
of rows that genuinely carry a finding (the mergeable one, the accidental
11,000-file diff, the duplicate), and keep every other row to one.

Write one synthesis paragraph covering the merged set: what the whole
window adds up to. Earn this from the actual grouping you did in Step 4 (a
consolidation week? a feature push? routine maintenance plus one big
migration?). The test: a synthesis that would fit any other week has not
earned its conclusion.

**In inventory scope the synthesis answers a different question** — not
"what did this window add up to" but "what is this backlog, really." The
first run's answer was that a 58-PR backlog was *not* a review-throughput
problem: 10 of the 12 ready PRs already had written findings, so nothing
was unlooked-at, and a third of the drafts were dead or were provisioning
placeholders rather than work-in-progress. Reach for that kind of
conclusion — a count reframed into what it means — and state plainly which
numbers are misleading and why (**the draft count is not a
work-in-progress count**). The equivalent failure to "a synthesis that
would fit any other week" is a synthesis that just recites the tile
numbers back.

## Step 6 — Build and publish

Before writing any HTML, invoke the `artifact-design` skill to calibrate
treatment. This is a utilitarian report, not a landing page — real
typographic hierarchy, a considered palette, grouped sections, PR cards
linking out to GitHub and Linear — not an oversized hero or heavy
animation.

**Layout, top to bottom:**

1. Masthead with the stat tiles (PR count, unique Linear issues touched,
   contributor count, lines changed — computed from the data you actually
   gathered, not an estimate).
2. The synthesis paragraph(s), placed here at the top — but **collapsed by
   default** (a native `<details>`/`<summary>` is enough; no need for
   custom JS). The reader who wants the takeaway first can open it in one
   click; the reader who wants to browse PR-by-PR isn't forced past a wall
   of prose to get to the list.
3. If in-review PRs were requested, **two tabs** — "Merged" and "Ready for
   review" — plain buttons toggling which panel is visible (a few lines of
   vanilla JS; track the active tab with a class, no framework needed).
   Skip the tabs entirely when the digest is merged-only; a single
   always-visible section doesn't need tab chrome.
4. The themed merged-PR sections (Step 4) inside the "Merged" tab/panel;
   the flat ready-for-review list inside the other.

**Layout in inventory scope** — same skeleton, four substitutions:

1. Tiles count what an inventory reader needs: open total, drafts vs.
   ready, authors, tickets touched, how many are stale past 30 days, and
   **how many are closable now**. That last tile is the one that turns a
   survey into something actionable.
2. Synthesis stays here, still collapsed, still first.
3. Tabs become "Ready for review" and "Drafts" — put ready first, it's the
   actionable half even though it's the smaller one.
4. Inside the drafts panel, lead with **one callout listing the PRs that
   can close today**, each with its one-phrase reason (`ticket Done 08-19`,
   `0 files changed`), then the workstream groups. Rows stay in their
   groups as well, so nothing lives in only one place — the callout is a
   shortcut for the reader who wants only the to-do list, not a separate
   grouping.

Two things to state rather than quietly print, both from the first run:
the diff totals when one PR dominates them (11,659 of 13,655 files came
from a single accidental commit, which makes every unqualified repo-wide
number misleading), and which subset of tickets you actually verified when
a light pass verified some but not all.

If this skill gets run repeatedly, keeping a consistent favicon across
runs (a single emoji, e.g. 📰) helps the reader recognize the series in
their browser tabs — but defer to whatever `artifact-design` recommends
for the rest of the visual treatment. Publish with the `Artifact` tool.

## Step 7 — Give every PR a "teach me this one" button

A digest answers *what shipped*. The predictable next question, on the two or
three entries the reader actually cares about, is *how does that one work* —
so end each card with a button that copies a ready-to-paste prompt for the
`/pr-teacher` skill, which builds an interactive deep-dive on a single PR.

**Build the prompt from data attributes, not duplicated markup.** Put the
card's identity on the `<article>` (`data-num`, `data-repo`, `data-title`,
`data-author`, `data-branch`, `data-stats`, `data-files` as a `|`-delimited
list) and have one JS function assemble the prompt from them. Writing the
prompt text once and reading it from the DOM means the visible card and the
copied prompt cannot drift apart, and adding a PR later is one `<article>`
rather than an article plus a hand-maintained prompt string.

**What the prompt should say.** Name the skill, carry enough identity that
it resolves without guessing, and add a compact fallback so it still produces
something useful for a reader who doesn't have the skill installed — a
shared digest often outlives the machine it was generated on:

```
/pr-teacher — build an interactive teaching artifact for
<owner/repo> PR #<N> — "<title>".

  Author: <author> · Branch: <branch> · <stats>
  Files: <path>, <path>, …

If `/pr-teacher` isn't installed: read the PR with `gh pr view <N> --repo
<owner/repo>` and `gh pr diff <N>`, read the changed files and the code
around them in the repo, then publish one self-contained HTML artifact
covering the problem it solved (leading with the concrete symptom), a
clickable map of where each changed file sits and why, how the mechanism
works (mermaid where a diagram beats prose), before/after on the two or
three decisive hunks, one thing I can operate that makes me predict-then-
check, why it matters, and 6-10 self-check questions with revealable
answers grounded in the real code. Prefer real paths and line numbers over
illustrative ones, and tell me about anything a reviewer left unresolved.
```

Keep the fallback to roughly that length. It exists so the button degrades
gracefully, not to reproduce the whole skill — and a prompt long enough to
compete with the skill is one that will silently go stale in every artifact
you have already published.

**On a light pass, omit `data-files` rather than fetching it.** The file
list is the one prompt field that costs a `gh pr view` per PR, and
`/pr-teacher` discovers the files itself from `gh pr diff`. Have
`buildPrompt()` skip the `Files:` line when the attribute is absent, keep
the button on every row, and say in your summary that you made this
trade — a button that works on all 58 rows beats a fuller prompt on none.

**Copying reliably — read `references/teacher-button.md` before writing the
handler.** The artifact iframe withholds `clipboard-write` while still
*passing* every capability check, so `navigator.clipboard.writeText()` rejects
at call time and a feature-detection guard routes around the working fallback.
Chain the fallback on rejection, and render the prompt into a selectable
element as the third resort.

A one-line hint next to the button ("Paste into Claude Code for an
interactive deep-dive") is worth the space the first time someone sees a
digest; the button label alone doesn't explain where the prompt is meant to
go.
