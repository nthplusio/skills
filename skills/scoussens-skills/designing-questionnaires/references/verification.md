# Acceptance procedure

Run the local tests, then exercise the **actual selected adapter**. A fake
receiver tests the delivery contract, not a harness's ability to wake an agent.
Use disposable generic data, not copied customer feedback.

1. Publish the example and open the served page in the installed browser. Expect
   three open, zero answered, and one selected detail on desktop. Filter High +
   Alex: only “Which export format?” remains. Add Jordan: both High questions
   appear. High + Anyone gives an explicit empty state. Global open/answered
   totals stay fixed while attention counts follow the filters. Search for
   `JORDAN permissions`: only the access question appears. Remove the search
   chip and sort by question name. Reset and follow a question link; it opens
   the targeted question. Open that link in a fresh tab. A deep link to a hidden
   question or source response clears obstructing filters and reveals it.
   Filter Role: Access policy owner; only the access question remains, and the
   list names the role and its holder. The retention question shows an
   unfilled role. Expand the saved setup and verify the outcome, roles and
   holders, response budget, and review policy. Check the glossary and the
   format question's Terms used here and Options. Open a question and check its recommendation, consequence,
   and response format without needing the agent conversation.
2. Submit “CSV is sufficient for the monthly comparison. Which encoding will
   preserve accented names?” to the format question. Observe exact text in
   storage and visible pending delivery/review. Inspect the actual reviewer
   message and its matching delivery receipt. A log from the server is not
   enough. Replay the same UUID and body; expect one stored response and one
   review effect. Replay different text under that UUID; expect rejection.
3. While notification is unavailable, submit another disposable response.
   Confirm it remains saved and pending. Restore the route and retry the same
   ID. Verify recovery after restarting the local host, and distinguish this
   from a cold/suspended harness resume test. Do not interrupt shared services.
4. Leave an unsent draft under a different question. The reviewing agent reads
   the format response, changes the requirement to CSV, publishes its answer
   with a source-feedback link, and adds a named encoding follow-up. The same
   publication includes the response's review receipt. The page offers an
   update without replacing the draft. Load it; the draft and deep links remain.
   Expect three open, one answered. Switch between questions, filter the draft's
   question out, then return. Its text and open form remain. Confirm original
   feedback unchanged.
   Remove attention from the answered question and give the follow-up a
   clarification state and a named next action. Verify saved setup unchanged,
   the last review time visible, and pending-review counts cleared by the
   receipt rather than delivery. Follow the latest interpretation to its source.
5. Filter Answered; inspect the answer and follow its source link. Filter the
   suggested respondent and priority together. Inspect the new follow-up.
   Submit to the new question without restarting the server. Repeating review
   must not create another follow-up or overwrite the original receipt.
   Submit a challenge to the answered question. It stays Answered while its
   response appears awaiting review. Filter Needs review and confirm it includes
   this answered question. In a disposable revision, publish an open
   conflict with both claims' evidence links and the saved decision maker. Check
   the question and attention overview display that saved authority, distinct
   from the suggested respondent. Confirm
   filters also scope the attention counts and next actions. Verify polling
   preserves focus on an unchanged navigation link and any open disclosure.
6. Inspect at desktop and 390 CSS pixels wide. Check no horizontal overflow,
   the review-mode notice is visible before scrolling or expanding navigation,
   readable labels, keyboard focus, toggles, open form, empty result, pending
   feedback and answered question. On narrow screens, filters start collapsed;
   selecting a result opens its detail, and Back to questions restores the list
   and filters. Verify browser Back and Forward, and focus after following a
   question or evidence link. Capture and inspect representative states;
   record pointer/keyboard interactions if supported. Name the tested engine.
7. If tab storage is blocked, verify the update control refuses a destructive
   reload and asks the reader to copy drafts. A denied save must leave text
   editable. Treat browser/offline limitations as such, not as saved feedback.

Record the actual commands/results and screenshots in the consuming project.
Report lifecycle tests not run (suspension, archival, gateway authentication,
multiple writers, other browsers/harnesses). Stop short of claiming an automatic
loop if no reviewer received and interpreted the saved feedback.

## Proposed-answer scenarios

Use the reference host with disposable data. Save a custom proposal and adopt
a recommendation on another question. Use as proposal must select the visible
Propose an answer for SME review option and prefill editable text. Verify
unchanged text saves as adoption and edited wording as a custom proposal.
Reload and inspect exact text, source
revision, attribution, pending status and the unchanged answered count.
Publish a review receipt alone: the proposal must still need SME review in
the page and JSONL. Reject an attempted answer citing only that proposal.

Open Review proposals. Check that unrelated filters clear, all candidates
remain visible and none is preselected. Enter Reviewing as once. Open Correct
proposal: the editor starts with the original wording. Change it and cancel;
expect no saved response and the original text when reopened. Edit again,
allow polling, then load a new revision: the correction draft survives. A
stale-tab save must fail without losing its draft or rewriting the proposal.

Accept a corrected answer, then accept the next proposal unchanged. Expect
one immutable decision per save, correct proposal links, automatic queue
advance and an explicit empty queue. Each save immediately increments the
publication revision, answers with the exact accepted wording, and publishes
receipts and terminal outcomes atomically. There is only one Review proposals
queue and no agent approval step. Check failure leaves the prior publication
and candidates intact. Replay a saved UUID after a publication and closure:
expect success without duplicates or another revision. Self-acceptance is
allowed; a self-entered name is attribution, not authentication.

Deny one of several candidates without feedback and another with a reason.
Cancel first to prove no denial is saved; reload an unsent reason to verify
draft retention. Check that each decision links only its intended proposal,
the next candidate remains available, and concurrent decisions cannot settle
one candidate twice. At save time, both originals and reasons remain visible,
receipts publish, and denied candidates leave the queue and JSONL pending list.
They cannot be accepted later. Denying every candidate leaves the question open.
Denying a challenge must preserve an existing accepted or direct answer.

Inspect host-published proposal/acceptance IDs and both evidence links. Check
accepted wording, green accepted state, provenance and cleared proposal
readiness in schema-4 JSONL and offline HTML. Other existing unresolved
candidates must be Not selected, not denied, linked to that acceptance. Add a
new proposal against that answer: it remains an unresolved challenge without
replacing the answer. Attempt accept/correct without replacement confirmation:
expect rejection with the answer intact. Confirm replacement explicitly and
verify `context.replace: true`, the new exact answer, and unchanged history.
Reopen the question: all terminal outcomes survive and stay out of the queue.
Verify schema-1–3 snapshots still render without inferring new decisions.

Inspect desktop and narrow correction/queue states and record pointer
interaction. Verify old database rows, outbox receipts, publications and pending
decisions survive upgrade unchanged; no old decision is silently applied.
Ambiguous old feedback requires explicit reviewer reconciliation. Run the
ordinary answer/change/question/agree reviewer path as a control: completeness
and conflicts still require interpretation. Follow a host decision with agent
research and a requirement edit; the decision must not be reapplied and its
receipt must remain unchanged. Route a real conflict to the saved decision
maker rather than silently rewriting the SME's decision.

## Evaluate research instructions separately

The scenarios in `evals/evals.json` are agent-behavior evaluations, not tests run
by Python unittest. For cases 7–10, prepare disposable source checkouts, saved
questionnaires and reports matching the stated starting conditions. Supply the
scenario prompt to the agent, but keep expected outputs and assertions with
the evaluator. Inspect actual tool calls, reports and exported JSONL; a written
plan does not prove delegation or source inspection occurred.

Record the model/harness, source revisions, fixture setup, observed actions and
each assertion's result. A missing fixture or unsupported helper capability is
an unexercised case, not a pass. Passing host contracts alone does not establish
that agents follow the research and category-routing instructions.
