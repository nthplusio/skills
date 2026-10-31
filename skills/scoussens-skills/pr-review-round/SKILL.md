---
name: pr-review-round
description: >-
  Work a queue of open pull requests end to end — every non-draft PR against a
  base branch, oldest first, each reviewed at a depth scaled to its risk, every
  finding verified at the PR's current head rather than relayed. Report readiness;
  approve, dismiss, or land only within the user's authorized scope. Load this
  only when the user explicitly asks to work the queue — "review round", "work
  through the open PRs", "review everything targeting main", "clear the review
  queue", "triage the PR backlog and merge what's ready". Do not load it to
  review a single pull request, to recap what merged recently, or to explain a
  change to someone; answer those directly or reach for a single-PR skill
  instead.
disable-model-invocation: true
---

# PR review round

Assess every PR in a review queue. When authorized, land what is ready without
merging anything on the strength of a claim nobody checked.

**Verify, never relay.** Reviewing a queue tempts you into restating an
automated reviewer's findings and moving on. They are often already fixed,
sometimes mis-severed, and blind to the bugs that matter most. Every claim you
pass on, you own.

## Authority

Invocation selects the workflow, not permission to write. Start with the
requested repository, base, and scope:

- **Assessment-only** is the default for "review round", "which PRs are ready?",
  and requests to explain blockers. Read, verify, and draft verdicts locally;
  make no forge mutations, including comments, reviews, dismissals, or merges.
- **Authorized writes** cover only the actions and PRs the user names. Permission
  to post reviews does not authorize dismissing others' reviews or merging.
  "Merge what's ready" authorizes eligible merges, not blanket approval or
  dismissal. Finish the assessment and hold any missing action for approval.
- **Publication** is separate: a selected destination or silence does not
  authorize uploading repository content to an external audience.

**Approving can be the merge action.** When the author enables auto-merge —
`queue.py`'s `AUTO` column — clearing the review gate can enqueue or merge it,
with no merge command from you. Approval and dismissal on such a PR also need
merge authority. Re-read auto-merge immediately before either action.

Three rules hold regardless:

- Bind every write to the full head SHA you verified. Re-read the head before
  each action; if it changes, hold writes and review the new head. Use
  `review_write.py` for review/comment/dismissal actions and `land.py --enqueue`
  for merges. These helpers do not grant authority. Merge only an open,
  non-draft PR that still has that head and is `APPROVED` + `CLEAN` before every
  enqueue, including retries. An unknown state holds the write.
- Never approve your own PR. GitHub forbids it; on your own work, resolve the
  conflicts and name a reviewer.
- When a permission gate denies a merge command, record the denial and the
  observed readiness separately, give the head-bound command a human can run
  after rechecking the head and approval, confirm state with
  `land.py --watch <n>` (poll-only), and carry on with the round.

**Base branch.** Use whatever was passed as an argument. With no argument,
detect the default, name the branch you picked in your first message, and carry
on — many teams review onto `develop`/`staging`/`trunk` rather than the
repo default, and saying which you chose lets the user redirect you in one word
instead of discovering it in the summary.

**Destination.** The round report's page is a setting, and `explain-to` owns
settings. In that same first message, load `explain-to` and run its step 1, the
settings sheet (`references/settings-sheet.md` there), passing the artifact (a
round report: what came in, what landed, what is blocked and on whose desk),
the settings this skill fixes (reader: a teammate who was not there; output:
one HTML page built as [`references/report.md`](references/report.md) says;
interaction, length, and anchor as that spec sets them), and the one open
setting, the page's destination if not already fixed. Reuse known settings and
in-scope publication approval; ask only unresolved consequential choices.
Continue local assessment while the destination
is unresolved. Hold external publication until the user authorizes that
destination and audience; if access is unknown, report it as unknown rather
than private. Return the summary and a local draft meanwhile.

## Scripts

Run these from the repo root. Each exists because the equivalent ad-hoc command
is either long enough to retype wrong or hides a trap worth encoding.

```bash
S=<this skill's directory>/scripts

$S/detect_setup.sh [base]           # once per repo: review bot, merge queue, conventions
python3 $S/queue.py <base>          # triage: every PR, risk tier, who is blocking, AUTO
python3 $S/stale_sweep.py <base>    # staleness across the WHOLE queue, one pass
python3 $S/prstate.py <n>           # review state + head sha + staleness, one PR
python3 $S/findings.py <n>          # blocking review bodies + their inline comments
python3 $S/test_reach.py <n>        # added symbols with no test referencing them
python3 $S/ledger.py open|heads     # findings and heads carried in from earlier rounds
python3 $S/review_write.py --help   # head-bound, explicitly authorized review writes
python3 $S/land.py --enqueue <n>:<reviewed-full-sha> # authorized merges only
python3 $S/land.py --watch <n>      # poll only; never enqueues. Use with AUTO, or when
                                    # a permission gate denies the merge command
python3 $S/round_report.py <base>   # report data: urls, review timestamps, bodies
python3 $S/md_to_html.py            # render a review body's markdown (import: `render`)
```

## The loop

### 1. Detect the setup, once

`detect_setup.sh` tells you which bot posts blocking reviews, whether a merge
queue is in play, and which conventions docs exist. All three change your
behaviour: the bot login is what you will be dismissing, a merge queue changes
how you merge, and the conventions docs are what let you ground a severity claim
in a rule the team already agreed to rather than your own taste.

Read the conventions/ADR docs it finds. A finding that cites the repo's own
stated rule is one the author acts on; the same finding as a preference is one
they argue with.

### 2. Triage the whole queue

`queue.py <base>` lists every open non-draft PR oldest first, with a risk tier
and — most usefully — **who is blocking**. Oldest first is deliberate: those PRs
have the most review history to reconcile and are the ones the queue is waiting
on.

The blocker column separates two situations people conflate. A conflicting or
stale branch is the *author's* to fix and approving does not clear it. A missing
approval is *yours*. Knowing which you are looking at prevents the most common
wasted move: requesting changes because a branch needs a rebase.

### 3. Review each PR, at a depth matched to its risk

| Tier | What it touches | Depth |
|---|---|---|
| `DATA` | migrations, seeds, schema files, stores, persisted fields | Full independent trace. Migration and revert checks are mandatory. |
| `AUTH` | auth, JWT, principals, secrets, billing and entitlements | Full independent trace. Confirm what actually enforces the boundary before describing a gap. |
| `API` | routers, services, query builders, scheduled jobs, shared packages | Verify open findings, then trace the changed logic yourself. |
| `INFRA` | Terraform, workflows, Dockerfiles | Verify findings; check what breaks on rollout, not just at steady state. |
| `WEB` | components, hooks, styles | Verify findings; check the key logic in both directions. |
| `DOCS` | markdown, docs-only | Confirm the claims match the diff. |

Scale effort, not rigour. A cosmetic PR still gets its claims checked; it just
does not get a data-flow trace.

For every PR, in this order:

1. **Staleness first, for the whole queue at once.** Run
   `stale_sweep.py <base>` before you read a single diff; it is the cheapest
   high-value step in the round. Use `prstate.py <n>` for detail on one PR.

   Read the `AUTHOR` and `BASE` columns as opposites. `STALE?` means the author
   pushed work that may have fixed the finding, so read those commits first.
   `LIVE` means only base history merged in — the author has addressed nothing,
   and the findings stand however long the raw range looks. The `AGE` column is
   what catches your own three-week-old block.
2. **`ledger.py open`** for findings carried forward from earlier rounds, and
   `ledger.py heads` for the head each PR carried when you last reviewed it. A
   head that has not moved means the author pushed nothing: skip the diff,
   draft one response, post only with comment authority, and escalate on age.
3. **`findings.py <n>`** for the open blocking reviews. The substance is in the
   inline comments, not the body.
4. **Verify each finding at the head SHA yourself** (`git show <sha>:<path>`).
   Confirm it, confirm it is fixed, or confirm it is mis-severed. Verify the
   ledger's carried-forward findings the same way — a finding is not live
   because it is recorded.
5. **Run the risk-tier checks** from
   [`references/verification-playbook.md`](references/verification-playbook.md).
   That file is where the real technique lives — silent reverts, constraint
   changes that CI cannot catch, allowlists checked in only one direction,
   renames of persisted state. Read it before any DATA/AUTH/API/INFRA review.
6. **Read the PR body as a claim to test.** The gap between what it says and
   what the diff does is reliably where the interesting finding is — including
   authors who have already written down the reason their own PR should not
   merge yet.
7. **Decide, then apply the authority gate.** Verdict table, guarded write
   commands, and API race limits are in
   [`references/writing-reviews.md`](references/writing-reviews.md). In
   assessment-only mode, retain the proposed verdict and evidence locally.

### 4. Reconcile the count before moving on

`queue.py` prints how many open non-draft PRs it found. Before you land anything,
check that your verdict list has an entry for **every one of them** and say the
number out loud in your summary: "14 found, 14 verdicts".

A dropped PR is worse than an unreviewed one, because the summary asserts the
round is complete. `round_report.py` names any PR you left no review or comment
on, and separates never-reviewed from reviewed-in-an-earlier-round. In an
assessment-only round, reconcile those warnings against your local verdicts;
absence of a posted review is expected, not a reason to post one.

### 5. Land what is ready

With merge authority, use `land.py --enqueue <n>:<reviewed-full-sha> [n:sha...]`.
It checks approval, head, and mergeability on every attempt and passes
`--match-head-commit` to GitHub. Changed heads, lost approval, conflicts, and
failed or uncertain writes stop that PR's writes. It re-enqueues only when an
actual queue read confirms absence; unknown membership holds writes.

Approval can change after the helper's read and before the merge request.
`--match-head-commit` guards the head, not approval. Server-side branch
protections are necessary to enforce approval at merge time; polling does not
eliminate that race. Hold the merge if a required atomic guarantee is unavailable.

Without merge authority, or with `AUTO` set, use `land.py --watch <n>`.
Bare PR numbers also default to read-only. Report **queued** only when
`mergeQueueEntry` exists, **merged** only when `state=MERGED`, and **pending,
queue unknown** when the queue read fails. `CLEAN`, auto-merge, and a successful
merge command are not evidence of queue membership. Conflicted, closed, held,
or timed-out PRs never count as landed; the helper exits nonzero for them.

Merges reshuffle the queue. A PR you approved five minutes ago can go
conflicting because another landed first. When that happens, run
[technique 12](references/verification-playbook.md) on the overlapping file
before commenting — the interesting bug often exists in neither branch, only in
the merged result. Then draft a comment naming the file and whose desk it is on;
post only with comment authority, and leave the approval in place.

### 6. Dismiss with evidence, never on faith

Dismissal needs explicit authority and overrides another reviewer's judgment,
so the message is the whole justification. Name the SHA you checked and what
you confirmed:

> Both findings fixed at `a1b2c3d`: `orders/store.py:88-120` now reads
> `OrderPresets` with a legacy fallback, matching the router.

If you cannot state what you verified, you have not verified it yet. Never
dismiss conditionally ("if CI comes back clean") — it reads as housekeeping, so
nobody re-checks it. Full guidance: [`writing-reviews.md`](references/writing-reviews.md).

### 7. Record, sweep again, then report

**Record the round's findings** with `ledger.record` — each with `status`,
`file:line`, the `head` you found it at, and its `unblock`. That is what makes
the next round open with the open findings instead of re-deriving them.

**Re-run `queue.py`.** Drafts get marked ready mid-round and PRs open while you
work; a round that ignores them is not finished. In one round this surfaced a PR
that had left draft an hour earlier carrying the batch's most consequential
finding.

**Then `round_report.py <base>`** and build both deliverables from its output,
never from memory: it returns each PR's `url`, the `reviewed_at` of the review
you submitted, and the full body of every review and comment you left, plus the
PRs that merged during the round and have already left `queue.py`'s list.

In assessment-only mode, combine that observed forge state with your local
verdicts. Label them **proposed, not posted**, with the reviewed head and local
assessment time; do not invent a submitted review timestamp.

Terminal summary and HTML artifact spec — including the per-PR link, timestamp,
expandable review body and optional teach-me prompt:
[`references/report.md`](references/report.md).

## What good looks like

The reviews worth writing share a shape: they open with what was verified and at
which commit, name one or two blocking items with a concrete failure scenario
and a `file:line`, separate those from things worth logging, and credit the
specific decision the author got right. They also correct the record when a
previous finding — automated or your own — turns out to be overstated, because
the author is reading both and silence leaves them guessing.

The round ends with an evidence-backed verdict for every PR and an accurate
account of who is blocked on whom. When landing is authorized, it also reports
which PRs actually merged and which still need action.
