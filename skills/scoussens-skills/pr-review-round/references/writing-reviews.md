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

Record an owned decision, not a "hold". Decision kind, severity, axis and GitHub state are separate:

- `code`: author owns a reproduced failure or documented rule violation; clear it by verifying the smallest fix.
- `evidence`: name the person able to run the missing workflow and the criterion; clear it with evidence or an authorized owner's criterion-scoped acceptance of the gap.
- `decision`: the product, architecture or operator owner owes a specific scope, rollout or risk choice.
- `reviewer-incomplete`: the reviewer owes unfinished review work. This is not an author defect and cannot be waived into completed review.
- `ready`: independent review is complete; mutable forge gates still apply. A rebase belongs to the author as a forge next action, not a code defect.

Save every assessment, including clean ones, with `ledger.py record <round-id> <assessments.json>`. Use the schema in `report.md`: head/base, original assessment time and scope, input revisions, and decisions with criterion/rule, source/time/observation, severity, axis, owner, smallest unblock, effort and proposed action. Record an actual posted action/URL/time only after readback. An accepted gap keeps its actor, source, time, exact criterion and scope; it does not clear unrelated requirements.

The table names proposed actions. In assessment-only mode, keep them local.
Execute each action only with authority for that action and PR. An authority
"with approvals" covers an approval that releases auto-merge; a dismissal follows
the `dismiss-review` policy or a one-PR grant. Preserve the
independent risk-tier trace and evidence requirements before granting clearance.

| Situation | Action |
|---|---|
| Code ready, branch conflicting or behind | **Approve**, then comment about the conflict. Approving clears the review gate — the only gate you control. Requesting changes for a rebase is noise. |
| Blocking finding confirmed at head | Request changes, one clear list |
| Blocking findings all fixed since the review | Dismiss the stale review naming the SHA and what you confirmed, then approve |
| The author's body says a required workflow is unverified | Needs evidence: name its criterion, workflow runner and requested evidence; do not call the PR body proof |
| A scope/risk choice prevents a recommendation | Needs owner decision: name the owner, specific choice and proposed comment channel |
| Independent review is not finished | Review incomplete: reviewer owns finishing it; do not request author fixes |
| Findings real but pre-existing and out of scope | Approve, note as follow-up |
| Automated review is red because the tool errored | Say so in the review; do not treat it as a finding |
| Another PR, open or merged, carries this change | Needs owner decision for the author: close in favor of #N, or say what this PR still adds. Name what the replacement drops |
| Two PRs do the same work and neither contains the other | Needs owner decision: say which to keep and why, on both PRs |
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
`gh pr review` call. Supply `--authority <authority.json>` and `--assessments <assessments.json>` on every write (schema in `report.md`). The helper generates the required **Unblock** section with owner, smallest fix and effort from code decisions; it rejects changes-requested without a code decision. Evidence and owner requests use the proposed comment channel; reviewer-incomplete work stays local with the reviewer. `--write` selects execution; omit
it when preparing a proposed action. The authority file, not a flag, decides each write: a held write names the
policy question to ask, and `authority.py grant` records the yes. No flag substitutes for the user's permission or for evidence.

```bash
# Set S to this skill's scripts directory; HEAD is the full SHA already reviewed.
python3 "$S/review_write.py" approve <n> --repo "$REPO" --head "$HEAD" \
  --body-file /tmp/r<n>.md --authority <authority.json> --assessments <assessments.json> --write
python3 "$S/review_write.py" request-changes <n> --repo "$REPO" --head "$HEAD" \
  --body-file /tmp/r<n>.md --authority <authority.json> --assessments <assessments.json> --write
python3 "$S/review_write.py" comment <n> --repo "$REPO" --head "$HEAD" \
  --body-file /tmp/c<n>.md --authority <authority.json> --assessments <assessments.json> --write
python3 "$S/review_write.py" dismiss <n> --repo "$REPO" --head "$HEAD" \
  --review-id <review-id> --body-file /tmp/d<n>.md --authority <authority.json> --assessments <assessments.json> --write
```

The helper reads the head immediately before each write, rejects self-approval,
and pins review submissions through REST `commit_id`. It includes the verified
head in every body and checks it again after the write. If the head moved,
reconcile the posted action and review the new head before further writes.

A `comment` is a pull request review with event `COMMENT`, bound to the
reviewed head like an approval. It shows in GitHub's review list and the PR's
reviewers, so the author sees that the PR was reviewed; it does not change
GitHub's review decision. After every check passes, the helper reads your
reviews on the PR. When your latest approval or changes request at the reviewed
head already has the requested state, or a comment review there has the same
body, it prints that review's URL and posts nothing. A review at an older head
does not count, so re-running a write is safe.

**API limit:** dismissals have no atomic expected-head parameter.
A preflight and postflight check can detect movement, not undo a write that
raced it. Review `commit_id` pins the review's subject, not all concurrent
approval or auto-merge changes. If the requested guarantee needs an atomic
gate the API cannot supply, hold the action for a human. The helpers independently re-read the actual target branch before and after writes, and `scripts/freshness.py` judges any move against saved `evidence_inputs`. A base move that changes none of the PR's files while GitHub reports it mergeable, and new discussion that is only bot comments, automated events or this round's own writes, are benign: the write proceeds and records why. A new head, overlap, conflict, a person's comment or review, a bot's changes request, or any unreadable read holds it. Postflight reads detect movement but cannot undo a raced write or pin the merged result atomically. Never describe these
checks as eliminating the race. On a permission denial or uncertain response,
inspect remote state before retrying; the helper does not retry mutations.
After a review write returns an error, `review_write.py` reads your reviews
back once and reports a review it finds at the reviewed head as posted.

## Reporting the round

Terminal summary and artifact spec: [`report.md`](report.md).
