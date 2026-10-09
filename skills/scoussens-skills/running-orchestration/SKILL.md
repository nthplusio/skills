---
name: running-orchestration
description: >-
  Coordinates ticket-owned threads, sessions, or teammates through a named
  milestone, reuses retained proof, and maintains one visual HTML dashboard.
  Use when asked to orchestrate multiple tickets, keep work-owner conversations
  moving, or resume a coordinated run. Uses setting-up-orchestration for a local
  harness JSON configuration. Do not use for a single implementation assignment
  or bounded subagent task.
---

# Running orchestration

Keep owners moving and make the state of their work scannable. You own
coordination and the status record; ticket owners own implementation.

## 1. Read setup and recover the run

On resume, use the harness-restored conversation and accessible run files to
recover the finish line, owners, decisions, and prior evidence assessments
before assigning work. Reuse the existing run and its IDs. If local display
files are missing, rebuild them from that context and retrievable artifacts.
Keep unavailable proof explicit and retrieve existing receipts before deciding
whether a check is needed. Conversation recovery follows the harness's rules.

Locate the configuration using the explicit path or `ORCHESTRATION_CONFIG`,
then the per-harness default documented by `setting-up-orchestration`. Read
the stored JSON. If it is missing, malformed, has an unsupported version, or
describes capabilities unavailable in this execution context, load that skill
to create or repair it using confirmed settings. Read the resulting file, not
a remembered capability summary. Explicit project/team settings take precedence
over personal defaults; leave the personal configuration unchanged.

Use its owner/helper terminology, operations, skill propagation, evidence
transfer, and `run_root`. Resolve only a material capability mismatch; do not
redo discovery for every run. Configuration describes tools, not permissions.
If independent owners cannot be assigned and revisited, expose that limitation
instead of substituting blocking helpers and claiming concurrent ownership.

**Done when** the runner has read a suitable configuration and knows the confirmed
working-state location. On resume, existing ownership and decisions are restored
and evidence gaps are visible before assigning work. Coordination can proceed
while dashboard presentation awaits the user's choice in step 5.

## 2. Establish the finish line and ownership

Use the user's named milestone. Without one, default to **review-ready PRs**:
implementation and the needed proof and review material are prepared. This
does not mean a PR is published, reviewed, merged, deployed, or business-accepted.
State the finish line once and record what proves it for each task.

Locate existing owners before launching replacements. Keep a ticket's owner
through investigation, fixes, and PR preparation. Start another owner for an
independent review, a different required environment, or a separate assignment,
not simply a new phase. Prefix ticket-owned conversation titles with their
ticket IDs; use a short outcome label for work without a ticket. A ticket is
not a prerequisite for orchestration.

Record each task's owner handle/link, work location, files and runtime resources,
dependencies, completion criterion, and next action. Different workspaces do
not contain each other's unpushed code. Transfer exact files or accessible
commits and needed setup before assigning work that depends on them.

Separate conflicting work first through checkouts, file responsibilities, or
environments. When sharing is necessary, designate one writer or reserve a
runtime window. Confirm release of a shared resource before assigning it to
another owner. Conversation closure proves closure, not release of its runtime
or file reservations. Only conflicting work waits. Transfer ownership explicitly
before replacing an owner or taking over its implementation yourself.

Brief owners with the goal, relevant evidence, decisions already made,
boundaries, proof needed, and work location. Pass the applicable shared skills
from setup and this run explicitly, excluding both orchestration skills. Owners
may load additional role-specific skills and use bounded helpers. Pass relevant
instructions to those helpers too; do not assume inheritance or launch recursive
coordinators. Use the harness's supported briefing mechanism if direct skill
loading is unavailable. Include step 3's decision routing in owner briefs so
owners can discuss ticket-local choices with the user and report the outcome.

**Done when** every task has one accountable owner, a checkable finish line,
and clear resource/dependency boundaries. Each owner can begin without guessing
where its input code or proof lives.

## 3. Keep owners moving within authorization

Use the configured inspection, messaging, and result-collection operations.
Choose one completion mechanism per owner, such as a reply or a wait/join;
do not double-collect merely to obtain the same report. An idle owner may be
waiting for input, not finished. Route findings and follow-up fixes to its owner.

When several substantial coordination jobs are independent, automatically use
bounded helpers concurrently through the configured mechanism. For example,
helpers can assess different owners' incoming proof or send scoped follow-ups
to those existing owners. Handle simple status updates yourself. Helpers assist
the coordinator; they do not become ticket owners or additional coordinators.

Give each helper a separate owner/evidence scope, existing receipts, allowed
follow-ups, and the briefing/skill instructions from step 2. Keep authorization,
cross-ticket conflicts, resource allocation, and the status/dashboard writes with
the coordinator. Collect proof-backed findings, actual follow-up results, and
remaining decisions, then incorporate them once using step 4's proof rules.

Use verified helper capabilities: concurrent calls may overlap while their caller
still waits for the batch. Claim background responsiveness only when the harness
supports it. If helpers or concurrent invocation are unavailable, coordinate
directly; record a material limitation without holding unrelated owner work.

Let owners resolve ordinary technical choices within their assignment. Route a
ticket-local product or behavior question to its existing owner for discussion
with the user. Keep cross-ticket priorities, conflicts, shared resources and
shared-action approvals with the coordinator. Pause only affected work.

Keep one pending decision queue in the current record, ordered by blocked work
and urgency. Each decision has a stable ID, affected tasks, a concise question,
recommendation, what its answer unblocks, and one authoritative discussion owner
and link or harness handle. Surface several independent decisions together
instead of serial blocking coordinator dialogs. The user can discuss a local
choice in its owner thread or give quick answers by ID to the coordinator.
Relay exact user answers to the discussion owner when the harness permits it.
An owner can apply a local answer within existing authorization and report the
answer, source and outcome; the user need not repeat it to the coordinator.
Record the decision and scope once, and remove it from the pending queue.
Answering changes the decision queue, not the owner's activity status. Update
owner activity from inspected state or an actual progress report; a delivery
receipt proves communication, not that the owner resumed work.

Inspect native input gates using configured capabilities. A human-only gate
must be answered by the user in its owning conversation; show that direct route
and keep it pending until the harness confirms it is answered. A queued message,
clipboard action or recommendation is not an answer. When a coordinator dialog
blocks its caller, neither helpers nor pending reports establish background
responsiveness. Prefer the decision queue while unrelated owners continue;
retain the real dashboard update time when refresh is unavailable during a wait.

Record approval scope, destination, and side effects and carry that permission
to the relevant owners. A milestone goal is not approval for a shared database
write, access/secrets change, push, merge, or deployment. Include indirect
effects such as auto-merge or an automatic deployment before seeking approval.
Ask again only when the action exceeds the granted scope.

**Done when** runnable work continues, every pending decision has a clear answer
route, and requested shared actions fit recorded authorization.

## 4. Consume proof once

Require inspectable artifacts, literal check output, or retained receipts from
owners, not assurances that checks passed. Inspect the claim, relevant code and
environment, result, and limitations once, then retain and reuse that assessment.
Owners need not adopt the dashboard's JSON format to provide proof.

Before repeating any check, name the **relevant change, contradiction, or specific
evidence gap** that makes its retained proof insufficient. Retrieve existing
missing evidence or clarify scope first. Risk may require a different uncovered
check, not duplication of a sufficient check. Rerun only the affected check.
A changed hash alone does not establish a behavioral difference; identify the
failure it could cause before imposing a hold or demanding byte equality.

Preserve failed, interrupted, and successful evidence separately. Mark an
incorrect conclusion superseded, link its correction, and update the current
verdict. Do not erase earlier failure or portray artifact inspection as a new
execution. See [representative cases](references/orchestration-cases.md).

Keep PR readiness, code publication, deployment, and business acceptance separate.
Required CI/reviews must actually produce the required result. A green workflow
without a posted review is not a review; local tests do not prove live persistence.
Mark unrequested milestones **Not requested**, not blocked. Record extra required
steps, such as landing a merge, as obligations rather than implying a published
PR is merged.

**Done when** each consequential verdict cites sufficient proof within its scope,
and any repeated validation has a named reason recorded before execution.

## 5. Maintain one visual status record

Keep `<run_root>/<run-id>/status.json` as this run's current record. One
coordinator writes it. Reuse accessible run files when resuming; unrelated runs
use separate directories. These files are local working state, not a separate
recovery system. Keep status, generated HTML, and retained proof outside Git,
including when the user chooses a custom location.

Use the data contract in [dashboard data](references/dashboard-data.md).

Resolve presentation separately from coordination on each invocation:

- If no destination is chosen and the user requests only a consequential
  decision, defer the destination question and keep presentation **unselected**.
  An unanswered destination question has the same outcome. Save `destination`,
  `local_path`, `artifact_id`, and `artifact_url` as `null` with a nonempty
  `presentation.hold` explaining the missing confirmation. Continue coordination
  and update the local status record; leave dashboard generation, writes and
  hosting held. An old page stays unchanged and is not the current display.
- Otherwise, confirm a destination chosen in the invocation or restored user
  instruction, or ask one focused destination question offering usable configured
  destinations and their audiences. Ask separately from shared-action approvals.
  A template value, existing path, or configured option is not a user answer.
- After an actual destination choice, save its values and clear the presentation
  hold. Generate from the bundled template and update that same artifact in place.
  Only this branch runs the renderer below.

Publishing the dashboard does not authorize uploading underlying private proof,
publishing code, or publishing skills. Use accessible proof links for its audience,
or identify privately retained proof. Follow the selected host's instructions.
In a remote sandbox, local HTML needs a supported preview or portal for the user;
a sandbox-local URL is not a delivery link.

```bash
python3 <this skill's folder>/scripts/render_dashboard.py <status.json> <dashboard.html>
# Before hosting, reject local proof/owner links that the audience cannot use:
python3 <this skill's folder>/scripts/render_dashboard.py <status.json> <dashboard.html> --hosted
```

The renderer checks the display contract, not the truth of supplied evidence.
Update the record when an owner reports a meaningful change, a dependency or
approval changes, a verdict is corrected, or an owner closes. Show decisions
needed beside a compact task/owner matrix with four distinct milestone indicators.
Selecting a task opens its blocker, next action, and proof in the details pane.
Keep history and raw proof expandable. Stamp the real update time; do not imply
a static page updates itself.

Keep task, proof, decision, and run IDs stable. The template lets the user copy
an ID or a question containing its run/task/proof context. Task and proof
questions go to the coordinator; decision questions use their recorded
discussion route, with a direct-thread instruction for human-only gates. Show
affected tasks and what each decision unblocks beside its recommendation.
Record the coordinator link and any configured native comment/message mechanism
in `presentation`. Explain that copy does not send. Use host-native interaction
when supported; do not invent a chat backend or claim delivery from a clipboard
action. Interpret answers against the same record and update it without asking
the user to repeat a decision already made in its authoritative conversation.

Render representative states and inspect the result when creating or changing
the template. Routine data updates need the renderer check and a correct
destination update, not repeated screenshots of an unchanged layout.

Chat updates cover decisions needed, material blockers/plan changes, and reached
milestones. Say what changed, what needs attention, and the recommendation where
applicable. Link the dashboard; leave routine receipts and investigation detail
there. Honor harness progress requirements with brief updates.

**Done when** the selected dashboard presents the current record with accessible
or clearly private proof, or the record explicitly holds unselected presentation
without writing HTML. A presentation hold does not hold unrelated owner work.

## 6. Close completed owners and finish the run

Decide completion before checking whether the harness can close an owner:

- Reconcile **known obligations** from assignments, next actions, resource
  handoffs and owner messages into `obligations`. An empty saved list does not
  prove those obligations settled. Required CI/review, needed approval and
  assigned follow-up count even before the next message arrives.
- While any assigned work or obligation remains, keep the owner **active** or
  **waiting**. Verified PR readiness stays verified. For example, a prepared
  patch with runtime release still pending is review-ready, but its owner is
  waiting for that release, not complete. Skip the completion/closure branch.
- Once the assigned finish line is proven and known obligations are settled,
  retain the result, usable proof, exact work location, limitations and
  continuation instructions outside context that closure makes inaccessible.
  Mark the owner **complete**, update status and any selected dashboard, then
  close it when supported and record the actual result. Only this completed
  branch may record **complete, closure unavailable/pending** instead of **closed**.

Hypothetical future work and unrequested milestones do not keep a completed
owner open. Never delete evidence to clean up.

Keep the owner reference after closure. Resume that owner for later follow-up
when supported; otherwise transfer ownership explicitly using the retained
handoff. Closure does not make a ticket ownerless.

**Done when** all assigned milestones are verified, known obligations are settled,
completed owners have been closed or have truthful closure limitations, and the
status matches that result. The final chat states actual delivery, limitations,
and the dashboard location or presentation hold without repeating its audit trail.
