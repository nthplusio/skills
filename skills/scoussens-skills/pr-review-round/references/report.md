# Reporting the round

Produce exactly one report artifact: the HTML page, or a short Markdown decision document when HTML adds no value, delivered at the authorized
destination. Refresh that same page when reconciling the round; do not create a
parallel document or second report artifact. Accompany it with a brief chat or
terminal summary that links to the page. Retained JSON is supporting evidence,
not another report. Build the page and summary from `round_report.py`'s JSON,
not from memory — by report time the merged PRs have left `queue.py`'s list and
the bodies you posted are hundreds of lines back.

For assessment-only rounds, add the locally verified verdicts as **proposed,
not posted**, with their head SHA and assessment time. Keep those separate from
the API's submitted review bodies and timestamps. A proposed approval is not
an approval on GitHub.

`round_report.py` bounds the round from the ledger's previous `ended_at`. A
fixed clock window is wrong in both directions: too wide and it reports PRs that
landed before the round opened, too narrow and it drops a long round's earliest
merges.

## Terminal summary

Group by outcome, because that is the question being asked. Lead with what
landed. One line per PR naming the *finding* — "silently reverts the
shared-config consolidation" is information; "12 files changed" is not.

```markdown
## Merged — N
| PR | Reviewed | What |
| [#NNNN](url) | 16:04 | one-line statement |

## Queued, not landed — N
- **[#NNNN](url)** (16:12) — approved; in the merge queue, not yet on <base>.

## Approved, on the author — N
- **[#NNNN](url)** (16:19) — approved; needs a base merge (conflicting).

## Changes requested — N
(most consequential finding first, not PR order)
- **[#NNNN](url)** (16:31) — one-line statement of the actual defect.
```

Link every PR number and give every row the time its review was submitted;
`round_report.py` returns both as `url` and `reviewed_at`. Terminal clients make
markdown links clickable, so a linked number costs nothing.

**Say plainly what is queued versus merged.** A PR in a merge queue has not
landed. Use the returned `queue_state`: `queued` means an observed
`mergeQueueEntry`, `not_queued` means observed absence, and `unknown` means the
query failed, was unavailable, or saw a different head. `CLEAN` and auto-merge
do not prove membership. Keep approved-but-not-queued and queue-unknown rows
separate from queued rows. Conflicted and closed PRs are not merged.

## HTML artifact

Build from the bundled template, using a run-specific directory:

```bash
RUN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/pr-round.XXXXXX")
python3 "$S/round_report.py" <base> --scope <initial-pr-numbers.json> --tickets <tickets.json> \
    --assessments <assessments.json> > "$RUN_DIR/round.json" &&
  python3 "$S/render_round.py" "$RUN_DIR/round.json" --base <base> \
    --timezone <IANA-zone> --assessments <assessments.json> > "$RUN_DIR/report.html"
```

Omit `--tickets` or `--assessments` when not supplied. The timezone defaults to
UTC. Use the reader's known timezone when available. Rendering is offline and
makes no forge changes. Retain the JSON beside the HTML for later inspection.

`round_report.py` includes saved ledger assessments by default; `--assessments` overlays the supplied local records. Pass that same file to collection and rendering so request reconciliation and the visible assessment use the same inputs. The collected JSON retains these assessments even for merged/closed PRs. Flag a merge at an unassessed source head and retain earlier unposted findings without claiming they apply to unseen code.

Request-event markers, user/team targets, unknown coverage and configured human approval gates follow `references/review-handoffs.md`. Reconcile request counts separately from PR counts and substantive completion. Refresh this same artifact after final action readback; a proposed local assessment never answers a request on the forge.

The optional assessment file is local evidence, never a claim that a review was
posted. Use this shape, with one entry per assessed PR:

```json
{
  "repository": "owner/repo",
  "assessments": [{
    "number": 482, "head": "<full-reviewed-head>", "base": "<full-reviewed-base>",
    "assessed_at": "2026-11-03T15:20:00Z", "risk": "DATA",
    "evidence_inputs": {"forge": "<PR updatedAt>", "issues": "<hash from refreshed round JSON>", "policy": "<resolved review configuration revision>"},
    "decisions": [{
      "id": "rollback-filters", "kind": "code", "axis": "Spec", "severity": "blocking",
      "criterion": "Rollback preserves saved filters", "summary": "Rollback drops saved filters",
      "owner": "Author", "unblock": "Restore the persisted filter field on rollback", "effort": "one migration change",
      "proposed_action": "request-changes",
      "evidence": {"source": "<reproduction log URL or retained file>", "at": "2026-11-03T15:20:00Z", "observation": "Saved filter disappears after rollback"}
    }]
  }]
}
```

Use `code`, `evidence`, `decision`, `reviewer-incomplete` or `ready` as defined in `writing-reviews.md`. A clean assessment has one `ready` record, not an empty decision list. Persist it with `ledger.record_assessment`; optional detailed findings remain in `ledger.record`. This extends the round's existing ledger, not a second issue tracker. Legacy SHA-only proposals must be reconciled into this schema before reuse.

`evidence_inputs` comes from a fresh `round_report.py` collection. Include issue descriptions, relevant comments/decisions, criteria and source update times in `ticketEvidence`; its content hash makes external changes invalidate a recommendation. `policy` hashes the resolved profile and all directly referenced policy/checklist contents, including bundled defaults; changed rules invalidate reuse and guarded writes. Files linked from those policies still require source refresh and explicit provenance; this is not a transitive documentation crawler. Supply `round_report.py --review-config <repository-relative-path>` for an alternate profile and carry the same path as top-level `review_config` in the assessment bundle; omit it for the standard profile. Run write helpers from the target repository root so they can recompute the policy revision. Preserve the original `assessed_at` when reusing code checks and describe their scope/limits in `provenance`. Add `posted_action: {action, url, at}` only after an actual write/readback, never for a proposed action. For an accepted evidence/owner gap add `waiver: {actor, source, at, scope, criterion}`; `criterion` must exactly match this record. Preserve waivers across new heads only after confirming their scope still applies; they cannot waive code verification or unfinished review.

For directly fetched requirements, include `requirements` in the PR's `ticketEvidence`. Each source supplies `source`, `retrieved_at`, `acceptance_text` (the original acceptance section), `criteria: [{id, quote}]` and `matrix: [{criterion_id, result, ...}]`. Populate each matrix row with the implemented path, evidence/source/time and limit as above. A genuine source with no criteria uses an empty acceptance section and empty lists; a failed lookup is unavailable, not empty. The collector flags nonempty acceptance text with zero extracted criteria, missing source metadata, missing matrix rows or quotes absent from the source. These checks catch extraction/mapping mismatches, not every possible natural-language omission; compare the original source yourself. Linked tickets supplied without requirement evidence leave Spec coverage incomplete. The same contract accepts local requirement files and agreed untracked contracts, without a hosted tracker dependency.

Every write additionally takes `--authority authority.json`:

```json
{"repository":"owner/repo","prs":[482],"actions":["request-changes"],"instruction":"<link or exact originating instruction>","possible_landing":false}
```

Use only authorized actions (`approve`, `request-changes`, `comment`, `dismiss`, `enqueue`, `enable-auto-merge`). Approval/dismissal that can release auto-merge and both landing actions require `possible_landing: true` with permission covering that consequence. Record exact PRs rather than extending an old batch's authority. Files record permission; they do not grant it. Helpers refresh forge state, but the reviewer must refresh tracker evidence before invoking them.

Changed head/base, discussion or issue inputs and inconsistent collection make a proposal stale. Reassess it
before treating it as current. Keep source reviews and proposed assessments in
separate disclosures. A local proposal never acquires a submission timestamp.
For reused assessments, include a `provenance` string that names the earlier
round and says which checks were not rerun. Retain the original head and time.
Label recommendations as "Report recommendation, not posted". Retain GitHub's
status in Details so the reader can distinguish a recommendation from a posted
review. An out-of-date recommendation displays "Review again" and never supplies
the row's next action as if it were verified against the collected code version.

Before rendering, add a `summary` to each saved PR record. Write one short
sentence that says what changes for the user or operator. Keep `title` unchanged.
Write each decision's `unblock` as a plain next action, with its responsible person or role in `owner`. Keep technical findings in the linked evidence.
Follow the language guidance in `references/pr-family.md`. The renderer uses the
original title if no summary is supplied; this fallback is not a language rewrite.

Publish only to a destination and audience the user authorized, using saved
facts or narrow capability inspection as `explain-to`'s `references/formats.md` ("Hand-offs by
harness") describes. Settings, availability, and silence are not publication
consent. If the only available destination is public or its audience is unknown,
hold the upload and return a local draft until disclosure is authorized.

If an `artifact-design` skill is available, load it first — it calibrates how
much design the page warrants.

The page answers, for a teammate who was not there: what came in, what landed,
what is blocked and on whose desk, what the notable findings were.

Keep one value sentence, status, named next action and posted/not-posted indicator visible per PR. Count queue coverage separately from substantive review completion; an evidence gap is not verification. Before publishing, enforce both the 100 KB UTF-8 view budget and the destination's actual limit (use the smaller). The renderer replaces oversized embedded history with explicit evidence links and a gap note, preserving every row. If decision rows alone exceed the budget, return a short Markdown document with links. Retain full raw JSON separately; no silent truncation or compressed runtime loader. Regenerate timestamps/counts/status from records rather than patching transient states manually.

- Header: base branch, date, counts (reviewed / merged / blocked).
- A dense row per PR: **PR number linked**, plain summary, status, and next
  person/action. Use readable text rather than smaller fonts to achieve density.
- A compact handoff trail and return count in each row. Keep the next action
  separate from the trail so an old request for changes does not look unresolved.
- **Each row expands into lifetime history and review-round detail**, collapsed
  by default. Details holds ticket status, original title, author, technical risk,
  **review timestamp**, code version, the latest return's time and original reason,
  and the source-linked history. Original posted reviews remain separately expandable.
- **An optional teach-me button per row** (below); its absence does not block
  review, reporting, or delivery, and does not require installing `pr-teacher`.
- A section for the substantive findings, each with `file:line` and the
  scenario — the reusable part, and the reason anyone opens the page.
- A short synthesis: patterns worth acting on, gates that failed to catch things.

### Per-PR affordances

**Link.** A verdict a reader cannot act on is one they defer.

**Review timestamp.** The page's own honesty check. A round takes an hour and
the queue moves underneath it, so "reviewed 16:04" is what lets a reader tell a
verdict formed *before* a merge reshuffled the branch from one formed after.
Render a real time, not "recently".

**Details.** The shared renderer shows explicit handoffs in
chronological order. Each return includes the reviewer, timestamp, reviewed head,
original objection, and associated inline findings. Its nested review-attempt
summary counts submissions, not developer rework. Missing tracker history and
incomplete forge evidence remain visible. Full history is not restricted to the
round's acting reviewer or start time. Follow `references/pr-family.md` for
handoff semantics and tracker enrichment.

**Original review body.** `render_round.py` renders original posted reviews and
comments using the bundled Markdown renderer at build time. A comment has a
comment timestamp, not a submitted-review timestamp. Keep historical findings
separate from a head-bound current assessment. A resolved thread flag alone is
not a verified code fix.

The template owns scoped review styles and overflow handling. Inline its shared
CSS rather than loading external resources. Native disclosures support pointer
and keyboard use without runtime scripts.

Before delivery, open the generated HTML in a browser. Check a collapsed row,
expanded history, nested review attempts, original reviews, a local proposal,
and an evidence-gap row. Check narrow width, keyboard expansion, and browser
errors. Inspect screenshots of the affected states. Verify every fetched PR
appears once and that queued, merged, unknown, and proposed states stay distinct.

**Optional teach-me prompt.** The other three point backwards, at what was decided. This
one points forward, at the code. A round report is read by people who own two or
three of its rows, and their next question after "why is this blocked" is "what
do I have to understand to unblock it".

Keep favicon and title stable across rounds so redeploys stay recognisable.

## The teach-me button

A round report already knows the verdict, the head SHA, and the open findings,
so the prompt can ask for a deep-dive *shaped by the review* rather than a
generic walkthrough. On a merged PR the reader wants the mechanism; on a blocked
one they are usually the author, and their real question is what to fix.

```
/pr-teacher — build an interactive teaching artifact for
<owner/repo> PR #<N> — "<title>".

  Author: <author> · Risk tier: <tier> · <stats>
  Reviewed at <sha> on <date>: <VERDICT>
  Open findings: <one line per blocking item, file:line where the review had one>

Cover the mechanism first, then use the findings above as the spine of the
"what would break" section — I want to understand why each one is a problem in
this code, not just that it was flagged.

If `/pr-teacher` isn't installed: read the PR with `gh pr view <N> --repo
<owner/repo>` and `gh pr diff <N>` (that API caps at 20,000 diff lines — above
it, fetch the branch and use `git diff $(git merge-base origin/<base> <head>)
<head>`), read the changed files and the code around them, then prepare one
self-contained HTML artifact covering the problem it solved, a map of where each
changed file sits and why, how the mechanism works (mermaid where a diagram
beats prose), before/after on the decisive hunks, the open findings above traced
to the code that causes them, and 6-10 self-check questions with revealable
answers grounded in the real code. Prefer real paths and line numbers over
illustrative ones. Publish only to an authorized destination and audience.
```

**Build it from data attributes, not duplicated markup.** Put the row's identity
on the `<article>` (`data-num`, `data-repo`, `data-title`, `data-author`,
`data-tier`, `data-stats`, `data-sha`, `data-date`, `data-verdict`, and
`data-findings` as a `|`-delimited list) and have one function assemble the
prompt. The visible row and the copied prompt then cannot drift. **Skip the
`Open findings:` line when the attribute is empty** — an empty label reads as a
bug.

### Copying reliably

Read [teacher-button.md](teacher-button.md) before writing the copy handler.
Artifact frames reject `writeText` even when capability checks pass.
