---
name: pr-review-round
description: >-
  Reviews every non-draft PR against a base branch, oldest first, with
  risk-scaled depth and findings verified at the current head. Reports readiness;
  approves, dismisses, or merges only within explicit authority. Use only when
  asked for a review round, queue triage, or to clear the review queue. Not for
  a single-PR review, a merged-work recap, or explaining a change.
disable-model-invocation: true
---

# PR review round

Read [references/pr-family.md](references/pr-family.md) before collecting evidence.
Before drafting the artifact, read [report writing](references/report-writing.md) for repository preferences and the optional clarity-then-voice passes.
This skill coordinates the queue. Compose single-change review checks where
available, reuse matching evidence, and keep scoring and teaching in their owners.

Assess every PR in a review queue. When authorized, land what is ready without
merging anything on the strength of a claim nobody checked.

## Repository configuration

Read [references/review-profile.md](references/review-profile.md), then run `python3 <this skill>/scripts/review_config.py --root <repository>` (add `--config <repository-relative-path>` when the caller supplies one). Read the resolved setup outputs, ticket/execution policies and applicable review references. `configuring-reviews` can create or tailor this profile; it is not required to run a review. Without a profile, use bundled defaults and existing repository guidance. A broken explicit profile or reference is a configuration gap, not permission to silently skip checks.

The starting checklists cover [conventions](references/defaults/conventions.md), [data](references/defaults/data-layer.md), [integrations](references/defaults/integration.md), [security](references/defaults/security.md) and [verification](references/defaults/verification.md). Repository profiles can extend, replace, disable or add categories. Choose checks from changed behavior and reference applicability, not only path-based risk hints. Record the selected rules and coverage; these heuristics do not override repository requirements, acceptance criteria or action gates.

Use the configured execution policy and the active harness's capabilities rather than a fixed agent product, model or tool name. Both review axes are required, not parallel helpers: `auto` uses available authorized helpers, otherwise separate serial passes; `serial` launches none; unavailable `parallel` support is a disclosed limitation. Pass pinned revisions and applicable rules to any helper. The bundled forge helpers use GitHub/`gh`; this is a tool prerequisite, not a harness or ticket-provider choice. Do not substitute unguarded writes when these helpers cannot run.

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

**Enabling auto-merge is a landing action.** Use `land.py --enable-auto-merge` with the same gates as enqueueing, from the first attempt. Direct `gh pr merge`, `--auto`, and ad-hoc API mutations bypass local decisions and are not this workflow's write path. Every write requires a saved authority record: repository, exact PR numbers, allowed actions, originating instruction and whether possible landing is included; schema in `references/report.md`. Refresh tracker evidence and owner decisions before creating write inputs. Helpers enforce recorded decisions and live forge revisions, not live tracker access or the user's actual permission.

Three rules hold regardless:

- Bind every write to the full head SHA you verified. Re-read the head before
  each action; if it changes, hold writes and review the new head. Use
  `review_write.py` for review/comment/dismissal actions and `land.py --enqueue` or `--enable-auto-merge`
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
one decision report built as [`references/report.md`](references/report.md) says, with its short Markdown fallback;
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
python3 $S/review_config.py --root <repository> # resolved review/policy references
python3 $S/queue.py <base>          # triage: every PR, risk tier, who is blocking, AUTO
python3 $S/stale_sweep.py <base>    # staleness across the WHOLE queue, one pass
python3 $S/prstate.py <n>           # review state + head sha + staleness, one PR
python3 $S/findings.py <n>          # blocking review bodies + their inline comments
python3 $S/test_reach.py <n>        # added symbols with no test referencing them
python3 $S/ledger.py open|heads     # findings and heads carried in from earlier rounds
python3 $S/review_write.py --help   # head-bound, explicitly authorized review writes
python3 $S/land.py --help          # guarded enqueue/auto-merge; requires authority and assessments
python3 $S/land.py --watch <n>      # poll only; never enqueues. Use with AUTO, or when
                                    # a permission gate denies the merge command
python3 $S/round_report.py <base>   # report data: urls, review timestamps, bodies
python3 $S/render_round.py <round.json> --base <base> --timezone <IANA-zone> # offline HTML
python3 $S/md_to_html.py            # render a review body's markdown (import: `render`)
```

## The loop

### 1. Resolve configuration and detect the setup

Resolve the review profile first. `detect_setup.sh` supplements its pointers with observed forge state: which bot posts blocking reviews, whether a merge
queue is in play, and which conventions docs exist. All three change your
behaviour: the bot login is what you will be dismissing, a merge queue changes
how you merge, and the conventions docs are what let you ground a severity claim
in a rule the team already agreed to rather than your own taste.

Read configured references and applicable conventions/ADR docs it finds. Detection does not replace setup output or invent ticket policy. A finding that cites the repo's own
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
| `DATA` | migrations, seeds, schema files, stores, persisted fields | Full trace, including migration and recovery under the configured strategy. |
| `AUTH` | auth, JWT, principals, secrets, billing and entitlements | Full independent trace. Confirm what actually enforces the boundary before describing a gap. |
| `API` | routers, services, query builders, scheduled jobs, shared packages | Verify open findings, then trace the changed logic yourself. |
| `INFRA` | Terraform, workflows, Dockerfiles | Verify findings; check what breaks on rollout, not just at steady state. |
| `WEB` | components, hooks, styles | Verify findings; check the key logic in both directions. |
| `DOCS` | markdown, docs-only | Confirm the claims match the diff. |

This table is a default triage hint, not a fixed repository policy. Apply the resolved review references and configured verification requirements instead when they differ. Existing `.pr-review-tiers.json` path overrides still refine queue classification; link that file from profile guidance when used. DATA checks follow the repository's recovery strategy rather than demanding a destructive revert. A profile's checklist exclusions do not waive unmet acceptance criteria.

Scale effort, not rigour. A cosmetic PR still gets its claims checked; it just
does not get a data-flow trace.

For every PR, in this order:

1. **Staleness first, for the whole queue at once.** Run
   `stale_sweep.py <base>` before you read a single diff; it is the cheapest
   high-value step in the round. Use `prstate.py <n>` for detail on one PR.

   Read the `AUTHOR` and `BASE` columns as opposites. `STALE?` means the author
   pushed work that may have fixed the finding, so read those commits first.
   `LIVE` means no author commits were found; refresh evidence and owner decisions before retaining a finding. The `AGE` column is
   what catches your own three-week-old block.
2. **`ledger.py open`** for findings carried forward from earlier rounds, and
   `ledger.py heads` for the head each PR carried when you last reviewed it. A
   matching head **and base** permit reuse of code checks, not the verdict. Refresh relevant comments, reviews, issue updates and accepted owner decisions first. Keep original assessment time, scope and exclusions when reusing checks. New evidence can clear an unchanged-head evidence decision; new code invalidates affected code claims without deleting unrelated owner decisions. Never ask an owner to accept the same unchanged gap twice.
3. **`findings.py <n>`** for the open blocking reviews. The substance is in the
   inline comments, not the body.
4. **Verify each finding at the head SHA yourself** (`git show <sha>:<path>`).
   Confirm it, confirm it is fixed, or confirm it is mis-severed. Verify the
   ledger's carried-forward findings the same way — a finding is not live
   because it is recorded.
5. **Select relevant verification techniques** from
   [`references/verification-playbook.md`](references/verification-playbook.md).
   Treat it as an optional technique library selected by the configured references, not an extra mandatory checklist after a category was replaced or disabled. It covers silent reverts, constraint
   changes that CI cannot catch, allowlists checked in only one direction,
   renames of persisted state. Use the relevant techniques when an enabled reference or repository rule calls for them.
6. **Read the PR body as a claim to test.** The gap between what it says and
   what the diff does is reliably where the interesting finding is — including
   authors who have already written down the reason their own PR should not
   merge yet.
7. **Decide, then apply the authority gate.** Verdict table, guarded write
   commands, and API race limits are in
   [`references/writing-reviews.md`](references/writing-reviews.md). In
   assessment-only mode, retain the proposed verdict and evidence locally.
   Map every acceptance criterion to its quoted requirement, implemented path, observed evidence/source/time, result and evidence limit. Distinguish independent verification, author claims, missing evidence and explicitly accepted gaps. Keep Standards and Spec outcomes separate; a pass on one never masks a failure on the other. For a documented tracking exception, say "no linked ticket" and assess the stated PR contract rather than inventing ticket criteria.

### 4. Reconcile the count before moving on

`queue.py` prints how many open non-draft PRs it found. Before you land anything,
check that your verdict list has an entry for **every one of them** and say the
number out loud in your summary: "14 found, 14 recorded; 11 substantive reviews complete, 3 incomplete". Queue coverage is not acceptance certification. Save the original scope as a JSON list of PR numbers for the final `round_report.py --scope` reconciliation, including PRs that close during review.

A dropped PR is worse than an unreviewed one, because the summary asserts the
round is complete. `round_report.py` names any PR you left no review or comment
on, and separates never-reviewed from reviewed-in-an-earlier-round. In an
assessment-only round, reconcile those warnings against your local verdicts;
absence of a posted review is expected, not a reason to post one.

### 5. Land what is ready

With merge authority, use `land.py --enqueue <n>:<reviewed-full-sha> [n:sha...] --repo <owner/repo> --authority <authority.json> --assessments <assessments.json>`; use `--enable-auto-merge` instead of `--enqueue` to enable auto-merge. The same path guards the first attempt and later retries. It checks unresolved decisions, scoped authority, approval, source/discussion revisions and mergeability, and passes
`--match-head-commit` to GitHub. Changed heads, lost approval, conflicts, and
failed or uncertain writes stop that PR's writes. It submits at most once per PR per invocation and reads head, review state and queue membership after every write, even an uncertain response. Reconcile and refresh inputs before a new invocation; unknown membership holds writes. A local recommendation is not an enforced GitHub gate. Report any authorized acceptance of evidence/owner gaps explicitly.

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

**Record every PR assessment** with `ledger.record_assessment`, including clean reviews. Keep detailed findings with `ledger.record` — each with `status`,
`file:line`, the `head` you found it at, and its `unblock`. That is what makes
the next round open with the open findings instead of re-deriving them.

**Re-run `queue.py`.** Drafts get marked ready mid-round and PRs open while you
work; a round that ignores them is not finished. In one round this surfaced a PR
that had left draft an hour earlier carrying the batch's most consequential
finding.

**Then `round_report.py <base> --scope <initial-pr-numbers.json>`** and build the single report and chat
summary from its output,
never from memory: it returns each PR's `url`, the `reviewed_at` of the review
you submitted, and the full body of every review and comment you left, plus the
PRs that merged during the round and have already left `queue.py`'s list.

The same pass collects lifetime history from all reviewers through the bundled
collector's `--history` profile. It skips source files and per-commit CI. The
round boundary filters round outcomes, not earlier handoffs. Enrich linked
ticket transitions using the shared contract and pass `--tickets tickets.json`.
If history is unavailable, retain the PR events and display the gap.

For tracked work, use the profile's existing ticket policy and setup output for evidence writeback, lifecycle milestones, completion gates and automation ownership. Return criterion-level evidence, remaining decisions and PR links only with tracker-write authority. Read back supported state at the configured milestones; flag mismatches instead of duplicating automation-owned transitions. Preserve metadata and discover supported operations in the active tools or file workflow. Propose a follow-up's owner and concrete criteria before authorized creation. Neither a development merge nor a deployment universally means Done; that mapping belongs to repository policy. An explicit no-tracker policy or tracking exception stays explicit, not invented ticket acceptance.

In assessment-only mode, combine that observed forge state with your local
verdicts. Label them **proposed, not posted**, with the reviewed head and local
assessment time; do not invent a submitted review timestamp.

Run `render_round.py` with saved evidence and optional `--assessments` as
[`references/report.md`](references/report.md) specifies. Use its template rather
than rebuilding the report layout. Each row shows the compact handoff trail and
expands into original objections, inline findings, and review-round detail.
Write the summary and next action for product owners using the family language
guidance. Keep the summary, status, next person/action, and trail visible. Put
review timestamps, code versions, technical risk, and original evidence in Details.
A historical return does not establish a current blocker or developer quality score.

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
