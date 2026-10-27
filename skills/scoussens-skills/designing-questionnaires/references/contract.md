# Data and delivery contract

## Publication

One database serves one questionnaire. `assets/example.json` is the minimal
model. Its `id` stays fixed and `revision` increases by one per publication.
Requirement and question IDs are lowercase slug strings; never recycle or
remove them. Deep links use `#requirement-ID`, `#question-ID`, and
`#feedback-UUID`. Editing labels does not change links. Keep retired questions
with an explanation rather than deleting them.

Requirement fields: `id`, `priority`, `title`, `text`, optional `details`, and
`questions`. Question fields: `id`, `title`, `prompt`, either `role` (a role
ID) or legacy `people` (respondent names, possibly empty), `status` (`open`,
`answered`, or `deferred`), optional `follow_up_to` (another question ID), and
`answer` only when answered.

Top-level `roles` lists who the questions are for. Each role has a slug `id`,
a `name` shown on the page, `knows` (what the role knows and cares about, which
sets the question's vocabulary), and `held_by` (names, possibly empty while the
role is unfilled). A question with `role` takes its respondents from that
role's `held_by` and must not also carry `people`. Change who holds a role in
one place; role IDs, like question IDs, are never removed once published.
Optional top-level `glossary` lists `{"term", "definition"}` entries with
unique terms. The page shows the full glossary and, on each question, the
terms that appear in its text or requirement context.

Publications without `roles` stay valid and keep `people`. Upgrading an older
publication, including one that put role labels in `people`, is an ordinary
next revision: add `roles`, replace each question's `people` with `role`, and
keep every ID. Feedback, receipts and earlier publications are untouched; no
database migration runs.
Deferred questions carry a text `deferral` reason and keep their original ask
and attention context. They are not counted as answered or awaiting a reply.

New questionnaires include a top-level `setup` object. Its text fields are
`outcome`, `out_of_scope`, `readers`, `response_budget`, `reviewer`,
`decision_maker`, and `escalation`. The saved setup survives reviews and can
be revised explicitly; once present it cannot be removed. Private identities,
channels, and send authorization live in the run folder, not the served model.

Questions can also carry these fields:

- `request` contains `recommendation`, `why`, and `response`, all text. These
  describe the provisional recommendation, consequence, and sufficient reply.
  Optional `options` lists two or more distinct, mutually exclusive choices;
  the recommendation names exactly one of them. The template displays them
  while the question is open.
- `attention` contains `state`, `next_action`, and optional `evidence` using
  the same labeled-link format as answers. Its state is `waiting`,
  `clarification`, or `conflict`. The next action names who can supply what.
  A conflict needs evidence links for both claims. Answered questions remove
  `attention`; new unreviewed feedback remains visible independently.
- `proposal_outcomes` is an optional mapping from proposal UUID to
  `{"state": "accepted", "decision_id": "feedback UUID"}`. State is one of
  `accepted`, `denied`, or `not_selected`; the decision ID links the SME decision
  that settled the candidate. Terminal outcomes survive reopening. Preserve
  stored entries alongside immutable originals, receipts, and history.

Older publications without setup or request fields remain readable. An open
question without attention defaults to waiting, or clarification if it is a
follow-up. These fallbacks do not infer a verified recipient or authority.
The attention overview follows all active filters. Pending response counts
derive from saved feedback without a review receipt, even on answered
questions. Attention counts cover open questions and can overlap with pending
review. Global open/answered totals and filter-option counts cover the whole
questionnaire. Checkboxes match any selected value within a group and all
selected groups together. Search matches every word across the question,
prompt, requirement context, role name and respondent names. The Role filter
appears only when the model declares roles. Selecting a question keeps
other forms and drafts mounted. Last review and latest interpretation cover
the whole questionnaire.
While an update awaits loading, the page names the displayed question revision;
feedback receipts continue to refresh without rebuilding forms.

```json
{
  "text": "CSV is sufficient for the first version.",
  "evidence": [{"label": "Report format guidance", "href": "https://example.org/report-guide"}]
}
```

An answer needs at least one labeled HTTPS evidence link or
`#feedback-<saved UUID>`. A feedback link must have a corresponding review
receipt that names the answered question. Evidence links support a claim;
the validator cannot judge whether the source actually proves it.

Each stored entry of top-level `reviews` has `feedback_id`, `reviewed_at` (ISO
time with timezone), `summary`, and `question_ids`. Omit `reviewed_at` for a new
receipt: the host fills it from its clock at publication. If explicitly supplied,
it must fall between the original submission time and the host's current time.
Retries with an omitted time reuse the stored timestamp. Include the original
question plus any affected follow-ups. Earlier receipts remain unchanged,
including legacy timestamps; publication history preserves earlier answers
when a later revision explicitly reopens a question.
The host validates and commits a complete model in one SQLite transaction.
An invalid update leaves the previous publication available. Concurrent edits
of the same revision are rejected unless the entire model is identical.

## Close-out

Snapshots never close a review. When the owner asks to end it, run:

```bash
# All questions answered:
python3 "$SKILL/scripts/questionnaire.py" --db "$RUN/review.sqlite" close
# End an unfinished review, with an owner-approved reason:
python3 "$SKILL/scripts/questionnaire.py" --db "$RUN/review.sqlite" close --defer-unanswered "Carry remaining decisions into the next review."
```

Close-out publishes `state: closed` and `closure` with `reason` and the host's
`closed_at` timestamp. An omitted state means open for existing publications.
The deferral option changes only open questions to `status: deferred`, with
that reason in `deferral`; answers, sources, setup, feedback and receipts stay
unchanged. Closing without the option rejects open questions. A repeated close
leaves the existing closure intact. A concurrent publication requires refreshing
and retrying; it is never overwritten.

New feedback is rejected after closure; identical retries of already-saved
submissions still succeed. The live page shows Closed and a Deferred filter.
An already-open tab keeps drafts while it offers the new revision; after loading,
unsent text remains available to copy. Unreviewed submissions remain unreviewed,
including challenges to answered questions. Closing does not fabricate receipts
or cancel pending delivery. The reviewer may still publish receipts for saved
feedback while keeping the questionnaire closed.

Regenerate JSONL and HTML after closing. Reopening requires an explicit owner
request and a new publication: set `state: open`, remove `closure`, and return
deferred questions to open while removing their `deferral` fields. Publication
history and earlier snapshots keep the previous closure and reasons.

## Submission, delivery, and review are different states

`POST /api/feedback` accepts `id` (canonical UUID), `question`, `name`,
`kind` (`answer`, `change`, `question`, `agree`, `propose`, `adopt`, `accept`,
`correct`, `deny`), `message`, and the proposal `context` described below. Names are
self-entered, not identity claims. Text is displayed as text, not HTML.
`GET /api/state` returns the current model, feedback, and review mode.

### Proposed-answer review

`propose` saves a candidate. `adopt` saves the exact current recommendation
as a candidate. Both require `context: {"revision": N}` with the displayed
publication revision. `accept` saves the exact proposal wording; `correct`
saves the SME's corrected wording. `deny` saves a denial with optional feedback
in `message`, which can be empty. All three decisions require
`context: {"revision": N, "proposal_id": "UUID"}`. Accept/correct on an
answered question also requires explicit replacement confirmation, recorded as
`replace: true` in that context; it is otherwise optional. Other kinds omit
context or use `{}`. New proposal actions reject stale revisions; identical saved
retries still succeed after later publications or closure. Editing the
recommendation before proposing uses `propose`, not `adopt`.

Use as proposal selects the visible Propose an answer for SME review option
and prefills an editable answer. Saving the unchanged recommendation records
`adopt`; saving edited wording records `propose`.

The inline card shows attribution and proposal outcome. Review proposals
opens an SME queue, clearing unrelated filters. Enter a self-reported name
once under Reviewing as. Accept and next saves acceptance and moves to the
next queued question. Correct proposal opens the proposal text in an editor;
Accept corrected answer saves it, while Cancel discards only the unsaved edit.
Polling keeps editors mounted; session drafts and retry IDs survive the
explicit Load updated review action. Competing proposals remain visible,
with no preselected winner. There is one Review proposals queue, counting only
unresolved candidates, not a second publication queue. Closed reviews disable
new decisions. Manual versus automatic agent review does not delay SME decisions.

For each new accept/correct/deny, the host commits the immutable feedback,
review receipts, outcome updates, and incremented publication in one SQLite
transaction. Failure leaves the prior publication and candidates unchanged.
No second agent approval or publication step is required. Accept/correct
immediately sets the question to answered, clears attention, and supplies
`answer.proposal_id` and `answer.acceptance_id`, linking the original proposal
and decision. `answer.text` is the exact accepted or corrected message. Both
originals have receipts and labeled `#feedback-ID` evidence links. Any existing
receipt is retained unchanged rather than regenerated. Propose/adopt alone,
including a reviewer receipt for them, never settle an answer.

Deny proposal opens an empty optional-feedback editor. Deny and next confirms
the denial; Cancel discards the unsaved reason without denying anything.
Saving immediately marks that proposal denied and excludes it from pending
proposals. Its original, attribution, denial and
optional reason remain visible. A denial affects only its linked proposal;
other candidates and any current answer stay unchanged. If all candidates
are denied, an unanswered question stays open. Submit a new proposal to try
again rather than accepting or rewriting terminal history. Concurrent decisions
cannot settle a candidate twice; an identical retry succeeds.

Acceptance marks the chosen proposal `accepted` and other existing unresolved
proposals `not_selected`, linked to the same decision. Display Not selected,
not Denied: those candidates were not individually rejected. Keep prior
terminal outcomes unchanged. Later proposals are unresolved challenges and
leave the answer intact. Accepting or correcting a challenge replaces that
answer only with explicit replacement confirmation. Reopening a question does
not return terminal proposals to the queue; submit a new candidate instead.

Self-acceptance is allowed. Names are attribution, not authentication or proof
of authority. Direct answer/change/question/agree feedback retains the existing
reviewer interpretation path for completeness and conflicts. The agent still
researches, edits requirements, and routes real conflicts to the saved decision
maker. It preserves host decisions and receipts instead of reapplying or
overwriting them; do not relabel a proposal to bypass an SME decision.

Opening an older database adds a `context` column with an empty-object default;
original feedback fields, outbox rows, receipts and publications are unchanged.
Back up before upgrading. Old pending decisions are not silently applied.
The reviewer explicitly reconciles ambiguous old feedback and any fork that
treated proposals as final answers before publishing new changes. Historical
data stays untouched; never fabricate acceptance or rewrite old receipts.

The browser creates a submission UUID before sending and retains it for an
unchanged retry. The server commits the exact original fields and a pending
outbox row together. Replaying the same UUID and content returns success;
different content with the same UUID is rejected. Database triggers reject
feedback updates and deletes. General model publication and delivery
acknowledgment remain trusted local operations, not browser APIs. SME decision
submission is the bounded browser path that lets the host publish its outcome.

The following delivery states describe ordinary feedback. SME decision receipts
and outcomes publish during saving, independently of notification delivery.

| State | Evidence | Page wording |
| --- | --- | --- |
| Saved | Feedback + outbox committed | Pending delivery to reviewer |
| Delivered | Adapter observed an actual wake/message effect and persisted its receipt | Reviewer notified. Pending review. |
| Reviewed | Reviewer published a review receipt and resulting model atomically | Reviewed, with interpretation |

The optional worker sends `{"feedback_id":"UUID"}` to the configured webhook
with `Idempotency-Key: UUID`. It retries unacknowledged rows after 60 seconds,
including after restart. A successful HTTP response means transport acceptance
only: it **never clears the outbox**. An adapter must read the original row,
invoke a supported wake mechanism, then call the trusted local
`questionnaire.py --db DB ack UUID RECEIPT` or perform the equivalent receipt
update. Keep capability URLs in owner-only files, outside the served directory.

Delivery is at least once, not exactly once. The adapter deduplicates by
questionnaire + submission ID, serializes deliveries to its reviewer, and
recovers an uncertain successful wake before retrying. The reviewer separately
deduplicates by review receipt. If the receiver cannot prove whether it woke
the reviewer, leave delivery pending and reconcile against the receiver's
history; do not manufacture a receipt. A manual queue is an honest fallback,
not an automatic-review integration.

## Draft and persistence boundaries

The client stores drafts and retry IDs in `sessionStorage` under the
questionnaire ID, on input and before sending. Review polling never rebuilds
forms or forces a reload. The “Load updated review” button saves drafts before
reloading and refuses to reload when storage fails. Stable question IDs restore
drafts even if a question became answered. Closing the tab, private-browser
storage loss, or changing origins is outside this guarantee. The full database
holds submissions, delivery receipts and publication history; back up all of
it using SQLite's backup operation, not a live partial file copy.

The example host is a single local service, not a multi-tenant production
application. It provides no login, identity verification, rate limiter, external
backup, or always-on availability. An authenticated gateway must protect **all**
routes, including feedback reads and writes. Review content is visible to the
entire allowed page audience. Get authorization before widening that audience.
