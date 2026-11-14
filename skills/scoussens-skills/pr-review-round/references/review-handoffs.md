# Reconcile review requests

A renewed request is work waiting on the reviewer, even at an unchanged head with `CHANGES_REQUESTED`. Request state does not replace code findings, CI, conflicts, approval or auto-merge gates. The requester may be the author, a maintainer or automation; retain the observed account rather than attributing every request to the author.

## Collect and reconcile

`queue.py` overlays paginated reviews, timeline requests/removals and outstanding user/team requests. Its shared collector uses REST first for outstanding targets, then paginated GraphQL if needed. Retain failed attempts even when fallback succeeds. Failed reads, unknown targets, missing event identity, truncated pages and inconsistent snapshots mean unknown coverage, not an empty request list. User and team targets remain distinct; do not infer team membership or a team's response from one user's review.

The sweep folds decisive reviews by reviewer. A later approval or dismissal supersedes that reviewer's older changes request; a comment does not erase it. Original submissions remain in history. Code updates without a request make code evidence stale, not an invented handoff.

For every request event, record one disposition:

- `assessed-locally`: an assessment covers this event; no forge response is implied.
- `awaiting-owner-decision`: the refreshed assessment names the owner and exact decision.
- `reviewer-incomplete`: unfinished review names the missing work and reviewer.
- `superseded`: another request to the same target replaced this event.
- `removed`: the request was removed or is no longer outstanding without an observed response.
- `answered`: a later submitted review from the requested user is observed and the request is no longer outstanding. Preserve response URLs and the actual verdict; a comment response is not approval.

`unhandled` means no disposition has been established. Duplicate delivery of the same event ID creates no extra work. A new request has its own identity even at the same head. If ordering or coverage is uncertain, keep that limitation visible rather than claiming every handoff is reconciled.

## Save local dispositions

Use the existing assessment ledger, not a second tracker. Include optional `request_events` on an assessment:

```json
"request_events": [
  {"event_id": "12345", "target": "user:reviewer", "at": "2026-11-13T18:00:00Z", "disposition": "assessed-locally"},
  {"event_id": "12346", "target": "team:data-reviewers", "at": "2026-11-13T18:01:00Z", "disposition": "awaiting-owner-decision"}
]
```

The parent assessment supplies PR number, head, base, policy revision, refreshed requirement inputs, decisions and original evidence times. `at` is when the local disposition was recorded; the request's original time comes from forge evidence. `ledger.record_assessment` validates and persists these markers. `ledger.handled_requests` returns the last handled event per PR/target with its original head/base and evidence revisions, even if a later assessment omits markers. Retain all handled events needed for this round, including superseded or removed events in the collected history. Preserve earlier assessment records rather than rewriting their evidence times.

Only the three local dispositions can be supplied by the reviewer. The collector derives `answered`, `removed` and `superseded` from observed forge state. A saved assessment without a matching event marker does not handle a new request. Before reusing a local marker, refresh discussion, directly fetched requirements, original owner decisions and policy; match head/base and evidence revisions. Keep criterion-scoped exceptions without extending them or asking for the same unchanged decision again.

## End the round honestly

Before declaring the round reconciled, account for every scoped PR and every request event, and report remaining unhandled requests and unknown coverage separately. An explicit reviewer-incomplete disposition accounts for the handoff but does not complete its review. Re-read state after the last authorized action, pass the saved assessments to `round_report.py --assessments`, then regenerate the same report artifact from its JSON. Assessments from the ledger are included by default. Local findings stay visible even if the PR merges or closes before publication. Close the ledger with `ledger.round_end(round_id, scoped_pr_numbers, repository, reconciliation=collected_records)` only after reconciliation; it refuses dropped PRs, unhandled requests or unknown request coverage. You can still publish a partial report with those limits while the round remains unfinished.

Compare the final merged source head, not the merge commit, with saved assessments and linked earlier rounds. If no matching record is retained, say **Merged head has no saved local assessment**. Missing local records do not establish missing review. Show observed exact-head reviews with actor/type, verdict, source and whether they preceded or followed the merge; preserve failures as unknown coverage. Later exact-head assessments remain retrospective, with their original times and scoped owner decisions. Keep earlier unposted findings as historical/local evidence and assign a maintainer to reconcile their relevance. Do not silently post them, reopen work or claim a defect exists at the merged head without checking it.

## Approval eligibility is repository policy

Read setup/configuration outputs and their referenced bot workflow/policy before assuming automation can supply a required approval. Apply that repository's size/path/actor limits to the observed diff. If the PR exceeds a configured auto-approval limit, name the human approver needed; no approval is not a code defect. Missing policy evidence means eligibility unknown, not an invented universal threshold.

Save an optional `approval_gate` on the assessment (or enrich the collected record), with `owner`, `reason` and `source`. The renderer keeps it visible separately from readiness. For example, a repository's documented file/line limit may require a human approver for a large PR. These are evidence fields, not new review-profile keys; keep configurable thresholds in the existing setup/guidance references. Bot approval, queue admission, an admin bypass and owner acceptance are different facts. None grants this workflow write authority.
