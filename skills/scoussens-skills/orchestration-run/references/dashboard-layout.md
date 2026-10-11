# Dashboard layout

The contract for `assets/dashboard-template.html` and `scripts/render_dashboard.py`.
Read it before creating or changing either one. Routine runs only write
`status.json`; the [dashboard data](dashboard-data.md) contract covers that.

The page has two audiences. The overview serves non-technical testers and
executives, so it uses plain labels and each row's `work.summary`. Selecting an
item or decision drills in to the technical detail for engineers and agents.

## Overview

- **Header:** title, `notice`, goal, and the real `updated_at` shown in the
  reader's local time. A reload never advances the snapshot time.
- **Progress summary:** how many items are wrapped up; a meter split into Done,
  Wrapped up without delivery, In progress and Needs attention; a link to pending
  decisions; and separate counts by business status and by agent status.
  Cancellation and deferral never count as Done.
- **Ledger:** every task, grouped into Needs attention, In progress and Wrapped up.
  Each row shows the three status views side by side: a stage stepper with the
  current stage and target stage, the business status, and the agent status.
  Keep the plain summary, revisit trigger and related decision IDs visible in the
  row without opening a dialog. Keep every stage indicator independent.
- **Decision queue:** one queue below the ledger. Each entry keeps its unblock
  preview, affected tasks, answer route and a copyable ID.
- **Technical reference:** expandable evidence and history, plus the run ID and
  raw snapshot time.

## Dialogs

Default to a closed dialog on initial load unless the user requests a selected
decision up front.

- **Item dialog:** plain summary and stage cards first; then agent status
  (state, activity, owner link and ID, last check, location, handoff); then
  technical details (work state and reason, blocker, next action, done-when,
  receipt, outcome proof, resources, dependencies, obligations); then each
  requested stage's note and proof; then the copy tools.
- **Decision dialog:** the question, recommendation, affected tasks, what an
  answer unblocks, and the answer route, beside the affected tasks' technical
  context. A human-only gate states that the user answers it directly in its
  owning conversation.

## Copy and routing

The page lets the user copy an ID, a prepared question, or the selected item or
decision context. Copied context carries the run ID, snapshot time, states,
blocker, next action, proof IDs and approval constraints.

- Task and proof questions go to the coordinator. Task context goes to the
  task's existing work owner.
- Decision context and questions use the decision's recorded discussion route.
  Keep the work owner distinct from that answer destination.
- Put Copy context before the existing conversation link: the user copies, opens
  and pastes. State beside each control that copying sends nothing and grants no
  approval.

## Verifying a change

Render [`evals/dashboard-preview.json`](../evals/dashboard-preview.json), which
covers every work state and stage outcome, and inspect the overview, an item
dialog and a decision dialog at desktop and phone widths. Then run the
orchestration evals (`npm run test:orchestration`). Routine data updates need
only the renderer check, not repeated screenshots of an unchanged layout.
