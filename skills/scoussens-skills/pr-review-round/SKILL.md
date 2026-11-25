---
name: pr-review-round
description: >-
  Reviews every non-draft PR against a base branch, oldest first, with
  risk-scaled depth and findings verified at the current head. Judges each PR
  against the others too: supersession, duplicates, conflicts and work the base
  already landed. Asks for a work level: assess, review with or without
  approvals, minor fixes and base merges, or workers that bring failing PRs to
  approval. Writes, merges and dismissals stay within explicit authority. Use only when
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

Invocation selects the workflow, not permission to write. The **work level**
sets which writes the round may make, and **decision policies** settle the
writes that would otherwise each need a chat message. Settle both once, in the
first message:

1. Write the request's explicit answers to `answers.json` (`level`, `approvals`,
   `policies`, and `instruction`, the user's exact words), then run
   `authority.py questions --root <repository> --answers answers.json`. It prints
   only what the request and the profile's `round` block leave open, each with its
   recommended answer, and which settings the profile set.
2. Ask those questions in one batch with the base branch and destination below,
   each with its recommended answer. Name the profile's settings so the user can
   change one in a word.
3. After the answers, update `answers.json`, run `authority.py init --repo
   <owner/repo> --scope $RUN/scope.json --answers answers.json --root <repository>
   --out $RUN/authority.json`, and show the user `authority.py show`. An
   unanswered setting takes the profile's value, then the default.
4. When the user grants a held write mid-round ("dismiss the bot's review on
   #3614"), record it with `authority.py grant $RUN/authority.json --pr 3614
   --action dismiss --instruction "<their words>"`. Never write or edit the
   authority file by hand.

The user can save their answers as the repository default through
`configuring-reviews` (`round` in the profile); do not write the profile yourself.

| Kind | The round, in mode `auto` | Default |
|---|---|---|
| `auto-merge-on-approval` | Turns on auto-merge right after its own approval | `auto` |
| `auto-merge-sweep` | Turns on auto-merge for an in-scope PR someone already approved at the assessed head, with nothing unresolved in its assessment | `auto` |
| `dismiss-review` | Dismisses another reviewer's review after verifying its findings are fixed | `ask` |
| `reapprove-base-only` | Approves again, as action `reapprove`, a PR whose round approval was dismissed when the new head adds only clean base merges | `auto` |

`ask` holds the write and the helper prints the question to ask; `never`
refuses it even with a grant. Both auto-merge kinds and `reapprove-base-only` need approvals. The levels:

| Level | The round does | Writes it allows |
|---|---|---|
| `assess` | Reviews for mergeability; this is assessment-only mode | None: verdicts, blockers and who acts stay local |
| `review` | Reviews for approval and posts the reviews | Comments and change requests; "with approvals" adds approvals, each followed by auto-merge |
| `moderate` | `review`, plus minor fixes and base merges on PR branches | Adds `update-branch` and `push-fix` (up to 50 changed lines) |
| `major` | `moderate`, plus a worker for each PR that fails approval, until it is approvable and mergeable | Adds `delegate`; worker fixes have no size cap |

Assess while the answer is pending, because every level starts with the same
review. Until the user answers, the level is `assess`. `check_authority`
refuses any write above the level, outside the scope file's PRs, or held by a
policy. A direct merge (`enqueue`) needs its own grant at every level: "merge
what's ready" authorizes eligible merges, not approval or dismissal. Finish the
assessment and hold any missing action for approval.
- **Publication** is separate: a selected destination or silence does not
  authorize uploading repository content to an external audience.

**Auto-merge is how approved PRs land.** Approving to merge includes
auto-merge. When the user picks approvals, an approval may release an
author's auto-merge (`queue.py`'s `AUTO` column), and the round turns
auto-merge on for each PR it approves with `land.py --enable-auto-merge`. No
separate merge permission is needed for either. Turn it on right after the
approval, while checks still run; GitHub's required checks do the waiting.
Prefer it to a direct merge, which waits for `CLEAN` and needs its own
instruction. Re-read the head and auto-merge immediately before approving.
A dismissal follows the `dismiss-review` policy, whose question names the
merge it can release. GitHub refuses auto-merge for stacked PRs; land
those with `land.py --enqueue --stack-method <method>` as step 5 describes,
which needs its own merge instruction. Direct `gh pr merge`, `--auto`, and ad-hoc API mutations bypass local decisions and are not this workflow's write path. Every write requires the authority file `authority.py init` wrote; schema in `references/report.md`. Refresh tracker evidence and owner decisions before creating write inputs. Helpers enforce recorded decisions and live forge revisions, not live tracker access or the user's actual permission.

Three rules hold regardless:

- Bind every write to the full head SHA you verified. Re-read the head before
  each action; if it changes, hold writes and review the new head. Use
  `review_write.py` for review/comment/dismissal actions and `land.py --enqueue` or `--enable-auto-merge`
  for merges. `review_write.py` posts a comment as a head-bound `COMMENT`
  review, so it shows in GitHub's review list, and skips a review you already
  posted at that head. These helpers do not grant authority. Merge only an open,
  non-draft PR that still has that head and is `APPROVED` + `CLEAN` before every
  enqueue, including retries. An unknown state holds the write.
- Never approve your own PR; GitHub forbids it. Do not approve a PR whose last
  push was yours when the base requires the last push to be approved by someone
  else; GitHub accepts that approval and does not count it. `review_write.py`
  holds both. On such work, resolve the conflicts and name a reviewer.
- When a permission gate denies a merge command, record the denial and the
  observed readiness separately, give the head-bound command a human can run
  after rechecking the head and approval, confirm state with
  `land.py --watch <n>` (poll-only), and carry on with the round.

**Branch writes.** At `moderate` and above, merge the base into a behind
branch with `branch_write.py update-branch`, and push a small fix from a
worktree at the reviewed head with `branch_write.py push-fix`. A fix is for a
confirmed finding with an obvious smallest change: a failing check, a typo, a
missed rename, a merge conflict. A design question or a fix over the cap is a
finding for the author, or worker work at `major`. Either write makes a new
head that this round must review again. After your push you are the last
pusher, so a base that requires last-push approval needs another approver.

**Workers at `major`.** For each PR whose verdict is not ready for a reason
code can fix, start one worker with the harness's thread or subagent tool.
Brief it with the repository, PR, reviewed head, the recorded decisions and
their unblock lines, and an authority file scoped to that one PR, written by
`authority.py init` with a one-number scope file and answers level `major`,
`approvals: false` and every policy `never`.
A worker never approves, dismisses, merges or starts workers, and stops at an
owner or evidence decision it cannot settle. Ask it to report the new head and
what it changed. A worker's report is a claim: review the new head yourself
before any verdict. Fork branches and owner decisions stay with their owners.

**Base branch.** Use whatever was passed as an argument. With no argument,
detect the default, name the branch you picked in your first message, and carry
on — many teams review onto `develop`/`staging`/`trunk` rather than the
repo default, and saying which you chose lets the user redirect you in one word
instead of discovering it in the summary.

**Destination.** The round report's page is a setting, and `explain-to` owns
settings. In that same first message, which also asks the authority questions, load `explain-to` and run its step 1, the
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
python3 $S/queue.py <base> [--save-scope <f> | --scope <f>] # triage: every PR, risk tier, who is
                                    # blocking, AUTO, your review against the head, changes since your last look,
                                    # related pairs and files the base changed under each PR
python3 $S/stale_sweep.py <base>    # staleness across the WHOLE queue, one pass
python3 $S/prstate.py <n>           # review state + head sha + staleness, one PR
python3 $S/findings.py <n>          # blocking review bodies + their inline comments
python3 $S/test_reach.py <n>        # added symbols with no test referencing them
python3 $S/ledger.py start|record|end # open the round, save assessments, close it (round checklist)
python3 $S/ledger.py open|heads|rounds # findings, heads and rounds carried in from earlier rounds
python3 $S/branch_rules.py <owner/repo> <base> # review rules an approval has to satisfy
python3 $S/review_write.py --help   # head-bound, explicitly authorized review writes
python3 $S/branch_write.py --help   # moderate/major: base merge or minor fix, leased on the reviewed head
python3 $S/authority.py questions|init|show|grant # the round's write permissions, settled at its start
python3 $S/land.py --help          # guarded enqueue/auto-merge; requires authority and assessments
python3 $S/land.py --watch <n>      # poll only; never enqueues. Use with AUTO, or when
                                    # a permission gate denies the merge command
python3 $S/stacks.py <n> --repo <owner/repo> # stack membership and order, read-only
python3 $S/reapprove.py <n> --repo <owner/repo> [--carry <assessments.json>] # base-only since the round's approval, read-only
python3 $S/round_report.py <base> --scope <scope.json> # report data: urls, review timestamps, bodies
python3 $S/render_round.py <round.json> --base <base> --timezone <IANA-zone> # offline HTML
python3 $S/md_to_html.py            # render a review body's markdown (import: `render`)
```

## The loop

### Round checklist

Run these six commands in this order, once per round. The numbered steps below say what to do between them. `$RUN` is a directory you create for this round's files. A command that refuses prints what is missing: fix that and run the command again.

```bash
RID=$(python3 $S/ledger.py start <base>)                  # 1. before triage; use the id it prints, never an invented one
python3 $S/queue.py <base> --save-scope $RUN/scope.json   # 2. triage (step 2); writes the round's scope once, related pairs beside it
python3 $S/ledger.py record $RID $RUN/assessments.json    # 3. after reviewing (steps 3-4); every scoped PR, clean ones too
python3 $S/queue.py <base> --scope $RUN/scope.json        # 4. before reporting (step 7); names PRs that JOINED or LEFT, adds their pairs
python3 $S/round_report.py <base> --scope $RUN/scope.json > $RUN/round.json    # 5. after the last write is read back
python3 $S/ledger.py end $RID --scope $RUN/scope.json --report $RUN/round.json # 6. closes the round, or prints each blocker
```

`assessments.json` is `{"repository": "<owner/repo>", "assessments": [...]}`, with the assessment schema in [`references/report.md`](references/report.md). Run command 3 again after reviewing a JOINED PR or changing an assessment. When command 6 prints a blocker you cannot clear in this round, report the round as unfinished and name that blocker.

### 1. Resolve configuration and detect the setup

Resolve the review profile first. `detect_setup.sh` supplements its pointers with observed forge state: which bot posts blocking reviews, whether a merge
queue is in play, which review rules an approval has to satisfy on the base, and which conventions docs exist. Each changes your
behaviour: the bot login is what you will be dismissing, a merge queue changes
how you merge, a code-owner or last-push rule decides whether your approval can clear the review gate, and the conventions docs are what let you ground a severity claim
in a rule the team already agreed to rather than your own taste.

Read configured references and applicable conventions/ADR docs it finds. Detection does not replace setup output or invent ticket policy. A finding that cites the repo's own
stated rule is one the author acts on; the same finding as a preference is one
they argue with.

### 2. Triage the whole queue

Read [review handoffs](references/review-handoffs.md). Overlay outstanding user/team requests and their event identities independently of review status, CI, conflicts and auto-merge. A same-head re-request is fresh reviewer work, not proof a prior objection is fixed. Reconcile collection gaps as unknown, and fold decisive reviews per reviewer rather than treating every historical return as a live block.

`queue.py <base>` lists every open non-draft PR oldest first, including upper stack layers that target a lower layer's branch instead of `<base>` (see Stacked PRs in `references/pr-family.md`), with a risk tier
and — most usefully — **who is blocking**. Oldest first is deliberate: those PRs
have the most review history to reconcile and are the ones the queue is waiting
on.

The blocker column separates two situations people conflate. A conflicting or
stale branch is the *author's* to fix and approving does not clear it. A missing
approval is *yours*. Knowing which you are looking at prevents the most common
wasted move: requesting changes because a branch needs a rebase.

Read the "Related PRs" lines before the first diff. Review each related pair back to back, even when other PRs sit between them in age order, so the second review starts with the first one's facts. The base-overlap lines name PRs whose files the base changed since they branched. Those are leads for a PR the base already landed and for silent reverts.

Review the current head of every PR `queue.py` prints under "Look again". For `REVIEW: another approver`, name the other approver instead of approving again; the lines under it give the base's review rules and any PR whose last push was yours. List the PRs it prints under "Review requested from you outside this table" in your summary. They target another base or are drafts, so keep them out of this round's scope and its assessments file. To review one on another base, run a second round on that base with the command `queue.py` prints.

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
2. **`ledger.py open`** for findings carried forward from earlier rounds. Only
   `unchanged` or `discussion changed` in `queue.py`'s `SINCE LAST LOOK` column,
   which mean the same head **and base**, permit reuse of code checks, not the verdict. Refresh relevant comments, reviews, issue updates and accepted owner decisions first. Keep original assessment time, scope and exclusions when reusing checks. New evidence can clear an unchanged-head evidence decision; new code invalidates affected code claims without deleting unrelated owner decisions. Never ask an owner to accept the same unchanged gap twice.
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
7. **Judge it against its neighbours.** A correct PR can still be the wrong
   one to merge. For each pair `queue.py` printed with this PR, and each
   base-overlap lead, decide whether one supersedes or duplicates the other,
   they conflict, one depends on the other, or they are independent. Test a
   supersession claim the way
   [technique 13](references/verification-playbook.md) says: every behaviour
   of the older PR is in the newer one or named as dropped. Record the
   relation on the assessment. A superseded or duplicate PR gets a blocking
   owner decision, never `ready`, and `ledger.py end` holds the round until
   every saved pair has a relation.
8. **Decide, then apply the authority gate.** Verdict table, guarded write
   commands, and API race limits are in
   [`references/writing-reviews.md`](references/writing-reviews.md). In
   assessment-only mode, retain the proposed verdict and evidence locally.
   Before extracting criteria, retain complete requirement responses and comment pages with source/time/revision/coverage using `requirements.py` as `references/report.md` specifies. Compare the complete sources with the extracted criteria; zero matrix gaps proves consistency, not completeness. Map every acceptance criterion to its quoted requirement, implemented path, observed evidence/source/time, result and evidence limit. Distinguish independent verification, author claims, missing evidence and explicitly accepted gaps. Keep Standards and Spec outcomes separate; a pass on one never masks a failure on the other. For a documented tracking exception, say "no linked ticket" and assess the stated PR contract rather than inventing ticket criteria.

### 4. Reconcile the count before moving on

`queue.py` prints how many open non-draft PRs it found, and `--save-scope` wrote their numbers. Before you land anything,
check that `assessments.json` has an entry for **every one of them** and a `request_events` disposition for every request `queue.py` printed as unhandled, then run checklist command 3. Report unhandled requests and unknown request coverage separately from PR coverage and review completion. Say the
number out loud in your summary: "14 found, 14 recorded; 11 substantive reviews complete, 3 incomplete". Queue coverage is not acceptance certification.

A dropped PR is worse than an unreviewed one, because the summary asserts the
round is complete. `round_report.py` names any PR you left no review or comment
on, separates never-reviewed from reviewed-in-an-earlier-round, and names a
review of yours that was dismissed or made at an earlier commit. In an
assessment-only round, reconcile those warnings against your local verdicts;
absence of a posted review is expected, not a reason to post one.

### 5. Land what is ready

Land related PRs in the order their relations give: a `depends-on` PR after the one it needs, and one side of a `conflicts` pair, then a fresh check of the other at its rebased head. Never land both sides of a duplicate pair.

After each approval, run `land.py --enable-auto-merge <n>:<reviewed-full-sha> [n:sha...] --repo <owner/repo> --authority <authority.json> --assessments <assessments.json>`. It turns auto-merge on while checks run and reports **AUTO-MERGE ENABLED, not merged** once GitHub shows it. With `auto-merge-sweep` on `auto`, run the same command for each PR `queue.py` lists as "Approved with auto-merge off" whose assessment at that head has nothing unresolved; the helper still requires GitHub's `APPROVED` decision. Confirm the merge later with `land.py --watch`. Use `--enqueue` only for a direct merge the user asked for. The same path guards the first attempt and later retries. It checks unresolved decisions, scoped authority, approval, the assessment's freshness (a harmless base or discussion move is accepted and recorded; see `references/report.md`) and mergeability, and passes
`--match-head-commit` to GitHub. Changed heads, lost approval, conflicts, and
failed or uncertain writes stop that PR's writes. It submits at most once per PR per invocation and reads head, review state and queue membership after every write, even an uncertain response. Reconcile before a new invocation, and review again only when a helper reports the assessment no longer holds; unknown membership holds writes. A local recommendation is not an enforced GitHub gate. Report any authorized acceptance of evidence/owner gaps explicitly.

Approval can change after the helper's read and before the merge request.
`--match-head-commit` guards the head, not approval. Server-side branch
protections are necessary to enforce approval at merge time; polling does not
eliminate that race. Hold the merge if a required atomic guarantee is unavailable.

For a stacked PR, `land.py --enqueue --stack-method <merge|squash|rebase>` runs one `gh stack merge <top> --yes`, which also lands every unmerged PR below it. Name each of those lower PRs with its reviewed head and authority; otherwise, or when membership is unknown, the helper holds without writing. `gh stack merge` has no expected-head guard, so the helper re-reads every covered head immediately before the write. It needs the official `github/gh-stack` extension; ask before installing it. Pass the method the repository uses for ordinary PRs, because the tool otherwise reuses the last method. A merge queue on the base chooses its own method and may land layers in separate groups.

Without approvals or a landing grant, or when `AUTO` is already on, use `land.py --watch <n>`.
Bare PR numbers also default to read-only. Report **queued** only when
`mergeQueueEntry` exists, **merged** only when `state=MERGED`, and **pending,
queue unknown** when the queue read fails. `CLEAN`, auto-merge, and a successful
merge command are not evidence of queue membership. Conflicted, closed, held,
or timed-out PRs never count as landed; the helper exits nonzero for them.

**Re-approve base-only heads.** When the base dismisses stale approvals on push, an author's base merge dismisses the round's approval. For each PR `queue.py` marks `REAPPROVE: base only`, with `reapprove-base-only` on `auto`, run `reapprove.py <n> --repo <owner/repo> --carry $RUN/assessments.json > $RUN/reapprove-<n>.json`. It checks that every commit since the approved head A is a clean merge from the base tip, compares each merge's tree with `git merge-tree --write-tree`, and carries the assessment at A to the live head H. Then run `review_write.py reapprove <n> --head <H> --assessments $RUN/reapprove-<n>.json` with a body naming A, H and the tree check; auto-merge follows per `auto-merge-on-approval`. Any other change, a conflict or a refused carry gets a normal re-review.

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

**Record every PR assessment** with checklist command 3, including clean reviews and the request-event markers it handles. A local assessment is not a posted response or approval. Keep detailed findings with `ledger.record` — each with `status`,
`file:line`, the `head` you found it at, and its `unblock`. That is what makes
the next round open with the open findings instead of re-deriving them.

**Run checklist command 4.** Drafts get marked ready mid-round and PRs open while you
work; a round that ignores them is not finished. Review and record each PR it
prints as JOINED, or report that PR as not reviewed in this round.

**After the final action readback, run checklist command 5** (add `--assessments <assessments.json>` to overlay records not yet saved to the ledger) and refresh the same report artifact and chat
summary from its output,
never from memory: it returns each PR's `url`, the `reviewed_at` of the review
you submitted, and the full body of every review and comment you left, plus the
PRs that merged during the round and have already left `queue.py`'s list. Then run checklist command 6. Report a merge with no approval from a person at the merged head, and a review `posted_by` "outside the round", as the observed facts `round_report.py` prints; an outside review is not this round's review. Reconcile merged source heads against retained assessments and linked earlier rounds; a missing record is **Merged head has no saved local assessment**, not proof nobody reviewed it. Show later exact-head reviews/assessments with their original time relative to merge and preserve scoped owner decisions and unposted findings. Use the distinct local-review and observed-GitHub labels in `references/report.md`. Keep required human approval from configured bot limits separate from source readiness.

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

The round ends with an evidence-backed verdict for every PR, a relation for
every pair of PRs that touch the same code, and an accurate account of who is
blocked on whom. When landing is authorized, it also reports
which PRs actually merged and which still need action.
