# Data and delivery contract

## Publication

One database serves one questionnaire. `assets/example.json` is the minimal
model. Its `id` stays fixed and `revision` increases by one per publication.
Requirement and question IDs are lowercase slug strings; never recycle or
remove them. Deep links use `#requirement-ID`, `#question-ID`, and
`#feedback-UUID`. Editing labels does not change links. Keep retired questions
with an explanation rather than deleting them.

Requirement fields: `id`, `priority`, `title`, `text`, optional `details`, and
`questions`. Question fields: `id`, `title`, `prompt`, `people` (respondent
names, possibly empty), `status` (`open` or `answered`), optional
`follow_up_to` (another question ID), and `answer` only when answered.

New questionnaires include a top-level `setup` object. Its text fields are
`outcome`, `out_of_scope`, `readers`, `response_budget`, `reviewer`,
`decision_maker`, and `escalation`. The saved setup survives reviews and can
be revised explicitly; once present it cannot be removed. Private identities,
channels, and send authorization live in the run folder, not the served model.

Questions can also carry these fields:

- `request` contains `recommendation`, `why`, and `response`, all text. These
  describe the provisional recommendation, consequence, and sufficient reply.
  The template displays them while the question is open.
- `attention` contains `state`, `next_action`, and optional `evidence` using
  the same labeled-link format as answers. Its state is `waiting`,
  `clarification`, or `conflict`. The next action names who can supply what.
  A conflict needs evidence links for both claims. Answered questions remove
  `attention`; new unreviewed feedback remains visible independently.

Older publications without setup or request fields remain readable. An open
question without attention defaults to waiting, or clarification if it is a
follow-up. These fallbacks do not infer a verified recipient or authority.
The attention overview follows all active filters. Pending response counts
derive from saved feedback without a review receipt, even on answered
questions. Attention counts cover open questions and can overlap with pending
review. Last review and latest interpretation cover the whole questionnaire.
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

## Submission, delivery, and review are different states

`POST /api/feedback` accepts exactly `id` (canonical UUID), `question`, `name`,
`kind` (`answer`, `change`, `question`, `agree`), and `message`. Names are
self-entered, not identity claims. Text is displayed as text, not HTML.
`GET /api/state` returns the current model, feedback, and review mode.

The browser creates a submission UUID before sending and retains it for an
unchanged retry. The server commits the exact original fields and a pending
outbox row together. Replaying the same UUID and content returns success;
different content with the same UUID is rejected. Database triggers reject
feedback updates and deletes. Only trusted local tooling can publish reviews
or acknowledge delivery; neither is a browser API.

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
