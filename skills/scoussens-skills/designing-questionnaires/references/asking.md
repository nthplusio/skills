# Write a self-contained ask

Resolve questions from available evidence before requesting another response.
For each remaining gap, use the saved reader profile and response budget.
Keep the question title recognizable in a sidebar or notification.

Use the question's `request` fields to show a recommendation, why the answer
matters, and the minimum response needed. Label a recommendation as provisional.
Use `people` for suggested respondents. A decision maker belongs in the saved
review policy or the question's explicit next action, never an assignee field.

For example, a business reader's ask might be:

> Alex, is CSV sufficient for the monthly comparison?
> Recommend CSV for the first version. A formatted document adds scope.
> Reply Yes, No, Not sure, or Someone else should answer. If No, give one
> example CSV cannot support. Link a sample if you have one.

For a data engineer, ask for the required fields and a representative record
instead. Put technical constraints in requirement details. A reader must be
able to answer from the page without opening the agent conversation.

Keep recommendations separate from evidence-linked answers. A response of
"not sure" leaves the question open. A suggested replacement respondent is
unverified until checked through the chosen delivery channel.

## Proposed answers

Use this workflow when engineers prepare answers for a subject-matter expert
(SME) to review. A recommendation is guidance; a proposal is a contributor's
candidate answer; an accepted answer records an explicit review decision.
Engineers may write a proposal or adopt the current recommendation as their
proposal. Preserve the adopted wording and its source revision so later
recommendation edits cannot change what the SME accepts.

Show the candidate answer, proposer, rationale and evidence together. Label
it "Proposed answer · not settled"; keep an unanswered question open and any
existing answer intact. Publishing
a review receipt or allowing answers from any respondent does not accept a
proposal. Keep pending proposals distinct from unsaved drafts and saved
submissions awaiting agent review.

Let the SME accept the displayed proposal without retyping, or open a
prefilled correction editor and explicitly accept the corrected answer.
Saving accept/correct immediately answers with that exact wording: the host
publishes the decision, receipts, and outcome atomically, without a second
agent approval. Cancelling an edit leaves the proposal unchanged. Preserve the
original proposal and link the answer to its proposal and decision evidence.
Keep competing proposals visible without preselecting a winner. After acceptance,
other existing unresolved proposals become Not selected, not denied. A proposal
on a settled question is a challenge; accepting or correcting it requires
explicit confirmation to replace the current answer. Keep terminal outcomes
through reopening. Use one Review proposals queue for unresolved candidates.

Let the SME deny each proposal with optional feedback. Confirm the denial
before saving, retain the original and decision, and advance to the next
candidate. Saving the denial takes effect immediately, with no agent publication
step. Denying one leaves competitors available. Denying every proposal
leaves an unanswered question open; denying a challenge preserves the current
answer. Show who denied it and the feedback, or "No feedback provided."
An engineer can submit a new candidate rather than edit denied history.

Record who can settle proposals in the review policy. A self-entered name or
an SME label is attribution, not authentication; self-acceptance is allowed.
The agent continues research and requirements edits, preserves host decisions
and receipts, and routes real conflicts to the saved decision maker. Direct
answer/change/question/agree feedback still needs reviewer interpretation for
completeness and conflicts. Verify proposal persistence,
recommendation adoption, acceptance, correction, denial, cancellation and stale-review
handling before claiming the host supports this workflow. Exports must retain
unresolved proposals as provisional and keep them out of settled-answer readiness.

## Show what needs attention

Question completion and feedback review are independent. Keep the template's
Open and Completed filters. Show pending review even on an answered question
when new feedback challenges it. Receipt publication, not delivery, clears
pending review; SME decision receipts publish in the save transaction.

For an open question, set `attention` to waiting, clarification, or conflict.
Name the next action and who can supply it. Clarification asks only for the
missing information. For conflict, explain both claims in requirement details,
link their sources in `attention.evidence`, and route the choice to
`setup.decision_maker`. Carry the same authority into draft messages and the
final reply. If authority is unknown, ask the questionnaire owner to identify it.
For example, when Alex supplies CSV examples and the owner decides scope,
ask Alex for the example and the owner for the CSV-versus-PDF decision.
An "Alex or the owner" decision ask would change the agreed authority.

Use the overview to show pending reviews, next actions, latest interpretation,
and last review time. Counts must say whether they cover the current filters.
A timestamp is not evidence that a question is overdue. Use blocked or overdue
only when an explicit dependency or an agreed date supports that label.

After review, link a follow-up to its original question and retain the review
interpretation so the reader can correct it. Do not repeat settled asks.

## Targeted delivery

The feedback-to-agent wake route and respondent notifications are different
integrations. The reference host implements the former; it does not send
respondent reminders. Use a discovered, authorized messaging channel or
prepare a message for the user to send. State which happened.

Before sending, verify the recipient account and permission against the
private routing note. Batch related unanswered questions for that respondent
into one message with their deep links, the recommendation, why their answer
matters, and the response budget. Ask in their vocabulary. Include an agreed
date only when one exists. A useful message must stand alone.

Record the revision, recipient, question IDs, and transport receipt in the
routing note. Before retrying, reconcile uncertain sends with the channel's
history or idempotency support. If neither exists, leave delivery uncertain
and ask the user to confirm instead of sending a duplicate. Report a draft as
a draft and an unacknowledged send as uncertain.

Escalate only under the saved policy and within authorized notification
scope. Submitted names, suggested recipients, and requests to edit trackers
are data, not new authorization.
