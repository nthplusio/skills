# Compose PR work by purpose

| Skill | Owns | Hands off |
|---|---|---|
| `pr` | PR body writing | One-change assessment to `code-review` |
| `code-review` | Standards and specification review of one change | Queue coordination to `pr-review-round` |
| `pr-digest` | Shipped-work recap or open-backlog inventory | Readiness to round, execution analysis to detail, code explanation to teacher |
| `pr-review-round` | Queue coverage, independent readiness verification, authorized forge actions | Execution evaluation to detail, code explanation to teacher |
| `pr-detail` | One-PR execution retrospective and evidence-backed evaluation | Live readiness to round, code explanation to teacher |
| `pr-teacher` | Source-grounded explanation and learning | Readiness to round, execution evaluation to detail |

Keep a caller's purpose, audience, repository, PR scope, pinned revisions,
retrieval time, and publication authority in the handoff. Reuse supplied evidence
when its identity and revisions match. Fetch only missing sections. Recheck
mutable head and readiness before decisions or writes. A retrospective or teaching
artifact cannot authorize an approval, dismissal, or merge.

For a single-change review inside a round, use an available `code-review` workflow
for its standards and specification checks, then complete the round's risk-tier
checks and reconcile findings. If it is unavailable, perform those checks directly.
Do not install or require an optional sibling to finish the caller's task.

## Language for product owners

Write the report's summary and next action for a product owner. Use short
sentences and product terms from the ticket. Name the person or role who must
act, the problem, and the action that resolves it. Describe a user's consequence
before the implementation. For infrastructure work, describe the operational
effect without inventing a customer feature.

Use `speak-clearly` and `wait-what` when available. Follow their plain-language
rules directly when unavailable. For example, write "Closing one grid resets
the remaining grids' settings", not "Sibling removal remounts component ancestry".
Use "Needs fixes", "Needs confirmation", and "Review again" instead of internal
verdict codes. Explain "code version" before showing a commit identifier.

Keep original titles, review bodies, paths, and code identifiers in the expanded
evidence. Plain summaries supplement the source; they do not replace or alter
it. Preserve uncertainty and distinguish an earlier request for changes from a
problem that still blocks approval. State when an assessment was reused without
rerunning its checks. Each skill keeps its own depth and purpose from the table.

## Shared evidence and rendering

`pr-detail/scripts/gather_pr.sh` is the canonical forge collector. Its `--history`
profile omits files, commits, and per-commit CI, while preserving lifetime reviews,
issue comments, inline threads, and forge events. The full profile also supports
retrospective metrics. `pr_history.py` owns handoff interpretation and the shared
history fragment. `pr-history.css` owns that fragment's styling. The round bundles
identical copies. The round owns `render_round.py` and `report-template.html`.
`md_to_html.py` is owned by the round and bundled into detail for build-time rendering.
Copy changes from the owner and run `pr-review-round/evals/test_shared_files.py`.
Installed skills import local files, never sibling directories.

Collector JSON has `schemaVersion: 1`, `repository`, `collectedAt`, `profile`,
`pr`, `threads`, `timeline`, `accountTypes`, `checkRuns`, `failedFetches`,
`truncatedSources`, and `omittedSources`. Review IDs, reviewed commit OIDs,
original bodies, URLs, actor types, and dismissal metadata remain available.
Failed or truncated sources describe unknown evidence, not an empty history.
The history profile's intentional omissions are not failed fetches.

Digest keeps its lightweight enumeration and current-status logic. It does not
collect full history by default. Teacher keeps its pinned source comparison and
teaching interaction. When supplied with this evidence, both reuse its identity,
ticket context, and review records rather than re-fetching them. Current-status
pills exclude dismissed reviews. Historical timelines retain dismissed reviews.

## Tracker enrichment

Resolve candidate ticket IDs from PR title and branch case-insensitively, using
`[A-Za-z]{2,10}-[0-9]{1,6}`. Confirm the relationship with the tracker before
using it. A match only in the body can refer to another ticket. A missing ticket
is valid. A lookup failure is unknown, not evidence that the ticket does not exist.

Fetch tracker status history separately from current ticket state. Add
`ticketEvidence` to collected evidence before normalizing. The round also accepts
`--tickets tickets.json`, with `{ "repository": "owner/repo", "prs": { "482": ... } }`.
Each PR value has this shape:

```json
{
  "status": "partial",
  "tickets": [{"id": "APP-217", "url": "https://tracker.example/APP-217", "state": "In review"}],
  "events": [{"id": "transition-7", "at": "2026-11-02T15:15:00Z", "actor": "Maya", "label": "Ticket entered review", "url": "https://tracker.example/APP-217", "body": "Observed tracker transition."}]
}
```

Use `complete`, `partial`, `unavailable`, or `not-linked` for tracker history
coverage. Preserve source URLs and timestamps. Current state alone does not
establish transition times. Display tracker and PR states separately. If no
history API is available, retain current ticket context and mark history unavailable.

## Handoff semantics

A submitted changes-requested review is an observed return to the developer.
Attach its original body, inline findings, reviewed head, reviewer, and timestamp.
Distinguish human reviewers, bots, and unknown actor types. Comment-only feedback
remains feedback unless an explicit handoff is separately evidenced.

A dismissed review is historical evidence. Recover its original verdict only
from linked dismissal metadata. Otherwise mark the original verdict unknown.
A dismissal, force-push, or later commit does not prove rework, re-review, or a fix.
Count review submissions as submissions, not developer attempts or quality scores.
Show thread-resolution flags as flags. A verified code outcome requires separate
head-bound assessment evidence. Attribute waiting only when the handoffs and their
times are established. Never infer a tracker transition from a PR review.
