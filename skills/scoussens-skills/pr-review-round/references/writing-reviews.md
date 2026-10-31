# Writing the review, and reporting the round

## The shape that works

A review is read by someone who wants to know two things fast: am I blocked,
and on what. Structure for that.

**Open with what you verified, not what you suspect.** "I checked X at
`<sha>` and it holds / it does not" is worth more than a paragraph of framing.
It also tells the author you actually looked, which is what makes the rest
credible.

**Separate blocking from everything else, explicitly.** Three tiers carry
almost all the useful signal:

- **Blocking** — must change before merge. Ideally one or two items.
- **Should fix before merge** — real, not fatal, and cheap now.
- **Non-blocking, logging it** — worth a ticket, out of this PR's scope.

Authors ration attention. A flat list of eight observations gets skimmed; a
review that says "one blocking item, one line" gets acted on today.

**Anchor every claim to `file.ext:line`.** A finding the author has to go
hunting for is a finding they will defer.

**Give the failure as a scenario, not a category.** Compare:

> Preset name not reset on scope change.

against:

> Restore "View1" on Orders→Region, switch the grouping to Customer, hit Save
> without touching the input: it POSTs `View1` to the shared `/orders` path
> with Customer's table state, and since the upsert is keyed on `(name, path)`
> it silently overwrites the Region preset.

The second is actionable and, importantly, falsifiable — the author can check
whether you are right.

**Offer the smallest correct fix.** If there is a genuine choice, give both and
say which you prefer and why. If the fix is one line, say it is one line.

**End every changes-requested review with an Unblock line.** This is a required
section, not a courtesy. Name the smallest change that makes each blocking
finding *false*, who has to make it, and how big it is:

> **Unblock:** three `ALTER … SET DATA TYPE` lines in the fix script you are
> already re-running · author · one command

The line shortens the path off the verdict; it never lowers the bar. "Three
ALTER lines" is an unblock. "I could live with it" is not a finding being
resolved, it is a review being withdrawn — if that is genuinely the right call,
change the verdict and say why, rather than smuggling it into this line.

Three things make an Unblock line honest:

- **It makes the finding false.** If the change you name would leave the defect
  in place, it is not an unblock.
- **It names the owner.** A conflict, a rebase, and a database migration run
  are the author's; a mis-severed finding is yours to correct.
- **Work outside the PR is offered, not performed.** When the unblock is an
  environment change — apply this DDL, reseed that database — say so and stop.
  Running it is outward-facing and needs its own authorisation, even mid-round.

Record it in the ledger too (`unblock` on the finding), so the PR's next round
opens with the path off the block instead of re-deriving it.

**Credit specifically or not at all.** "The `isReadOnly` guard keys on what the
import flow can actually handle rather than on the entity name" tells the author
which instinct to repeat. "Nice work!" does not.

**Correct the record when a prior finding was wrong.** If the automated review
overstated something, say so plainly in the review — the author is reading both.
Silently dropping it leaves them wondering whether it still applies.

## Choosing the verdict

The table names proposed actions. In assessment-only mode, keep them local.
Execute each action only with authority for that action and PR; approval or
dismissal that can release auto-merge also needs merge authority. Preserve the
independent risk-tier trace and evidence requirements before granting clearance.

| Situation | Action |
|---|---|
| Code ready, branch conflicting or behind | **Approve**, then comment about the conflict. Approving clears the review gate — the only gate you control. Requesting changes for a rebase is noise. |
| Blocking finding confirmed at head | Request changes, one clear list |
| Blocking findings all fixed since the review | Dismiss the stale review naming the SHA and what you confirmed, then approve |
| The author's own body says it is unverified | Hold the line they drew; that is a legitimate block |
| Findings real but pre-existing and out of scope | Approve, note as follow-up |
| Automated review is red because the tool errored | Say so in the review; do not treat it as a finding |
| You are the author | You cannot approve. Resolve conflicts, engage the findings honestly, ask for a named non-author reviewer |

On your own PRs, resist the urge to wave findings through. Answer them — either
fix it, or explain the trade-off and why the sequencing makes sense. "This
collides with #NNNN which is editing the same file right now" is a real reason;
"it's fine" is not.

## Dismissing a review

Dismissal is not a formality — it is a claim that you checked. Say what you
checked:

> Dismissing my earlier review — both blocking bugs are resolved at `a1b2c3d`.
> (1) Split-brain collection: fixed, `orders/store.py:88-120` now reads
> `OrderPresets` with a legacy fallback, matching the router. (2) Cross-region
> leakage: no longer a bug — the shared bucket plus opt-in sub-path is now the
> documented intent. The PR remains blocked on the bot's current review.

Note the last clause. When several reviews are in force, say which ones still
gate, so the author is not guessing.

## Commands

Use the guarded helper after verifying the full head SHA, not an unpinned
`gh pr review` call. `--write` asserts authority for this specific action; omit
it when preparing a proposed action. `--allow-landing` additionally asserts
merge authority and is required for approval or dismissal if auto-merge is
enabled. Neither flag substitutes for the user's permission or for evidence.

```bash
# Set S to this skill's scripts directory; HEAD is the full SHA already reviewed.
python3 "$S/review_write.py" approve <n> --repo "$REPO" --head "$HEAD" \
  --body-file /tmp/r<n>.md --write
python3 "$S/review_write.py" request-changes <n> --repo "$REPO" --head "$HEAD" \
  --body-file /tmp/r<n>.md --write
python3 "$S/review_write.py" comment <n> --repo "$REPO" --head "$HEAD" \
  --body-file /tmp/c<n>.md --write
python3 "$S/review_write.py" dismiss <n> --repo "$REPO" --head "$HEAD" \
  --review-id <review-id> --body-file /tmp/d<n>.md --write
```

The helper reads the head immediately before each write, rejects self-approval,
and pins review submissions through REST `commit_id`. It includes the verified
head in every body and checks it again after the write. If the head moved,
reconcile the posted action and review the new head before further writes.

**API limit:** comments and dismissals have no atomic expected-head parameter.
A preflight and postflight check can detect movement, not undo a write that
raced it. Review `commit_id` pins the review's subject, not all concurrent
approval or auto-merge changes. If the requested guarantee needs an atomic
gate the API cannot supply, hold the action for a human. Never describe these
checks as eliminating the race. On a permission denial or uncertain response,
inspect remote state before retrying; the helper does not retry mutations.

## Reporting the round

Terminal summary and artifact spec: [`report.md`](report.md).
