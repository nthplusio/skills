---
name: orchestration-run
description: >-
  Coordinates ticket-owned threads, sessions, or teammates through a named
  milestone, repeatedly checks owner status, reuses retained proof, and maintains
  one HTML dashboard using repository setup for the current harness. Use for
  /orchestration-run, orchestrating multiple tickets, or resuming a coordinated
  run. Confirms only run-specific choices. Calls orchestration-setup when setup
  is missing or unsuitable. Do not use for a single implementation assignment.
---

# Orchestration run

Keep owners moving and make the state of their work scannable. You own
coordination and the status record; ticket owners own implementation.

## 1. Read setup and recover the run

Identify the current harness name from runtime context. Read
`<repository-root>/.orchestration/config.json`, or the explicit path or
`ORCHESTRATION_CONFIG`. Resolve its saved profile with:

```bash
python3 <orchestration-setup folder>/scripts/check_config.py <config.json> --harness '<current harness name>'
```

Use the emitted capabilities, ticket policy, shared skills, defaults, and resolved
`run_root`. The name selects the profile. Neither the model nor the working
directory selects another harness's settings. Install all three orchestration
skills together so their referenced resources are available.

If setup or saved discovery is missing, malformed, lacks this harness, or has a
material context mismatch, load `orchestration-setup`. That skill owns discovery
and the durable interview. Hold affected assignments until its output validates.
Keep unrelated saved profiles intact. A new run with valid setup needs neither
tool rediscovery nor a project/harness interview. Configuration describes tools
and preferences, not permission for shared actions.

On resume, use the harness-restored conversation and accessible run files to
recover the finish line, owners, decisions, and prior evidence assessments
before assigning work. Reuse the existing run and its IDs. If local display
files are missing, rebuild them from that context and retrievable artifacts.
Keep unavailable proof explicit and retrieve existing receipts before deciding
whether a check is needed. Conversation recovery follows the harness's rules.
If independent owners cannot be assigned and revisited, expose that limitation
instead of substituting blocking helpers and claiming concurrent ownership.

**Done when** the current harness resolves to valid setup. On resume, ownership,
choices, and proof assessments are restored before assigning work.

## 2. Establish the finish line and ownership

For a new run, propose one compact confirmation using the user's request and
profile defaults. Include selected tickets, finish line, dashboard destination
and audience, and scan interval. Ask only for unresolved run choices. A complete
explicit request already confirms them. A request for only a consequential
decision can defer presentation as step 5 describes. Save confirmed values in
this run with the supplied answer receipt or actual message link, leaving setup
defaults unchanged. On resume, reuse saved choices and
ask only about a requested change or missing run choice.

The default review-ready finish line means implementation and needed proof/review
material are prepared. It does not mean published, reviewed, merged, deployed, or
business-accepted. Record what proves the confirmed finish line for each task.

Use setup's confirmed ticket policy. Inspect selected tickets against it, not
the repository's general configuration again. For an unclear ticket, resolve
its missing outcome or proof before assignment. For independent outcomes or too
many criteria, use [split proposals](../orchestration-setup/references/ticket-template.md)
and await approval. Hold only affected assignments.

Each persistent work owner is bound to one ticket for its lifetime. Each ticket
has one accountable persistent owner. Inspect existing owners' original tickets
before reuse, including closed owners. Keep the same owner through investigation,
fixes, review preparation and that ticket's later follow-up. Closure does not
free an owner for a different ticket. Prefix its conversation title with the
ticket ID. The coordinator and bounded helpers are not ticket-owned workers.

Use bounded helpers for assistance within a ticket. Separately owned review,
environment work or another independent outcome needs its own ticket and owner.
Locate that ticket's existing owner before launching another. When the harness
cannot resume the original owner, use an explicit handoff to its replacement
for the same ticket and retain the original binding. There is one current owner,
not two competing owners. A new phase alone needs neither a new ticket nor owner.

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
from setup and this run explicitly, excluding all three orchestration skills. Owners
may load additional role-specific skills and use bounded helpers. Pass relevant
instructions to those helpers too; do not assume inheritance or launch recursive
coordinators. Use the harness's supported briefing mechanism if direct skill
loading is unavailable. Include step 3's status collection and decision routing
in owner briefs so owners can discuss ticket-local choices with the user and
record the outcome in their own conversations.

**Done when** run choices are confirmed, every assigned row is one ticket with
one lifetime-bound owner, and each owner has a checkable finish
line and resource/dependency boundaries. Unconfirmed definitions or splits are
explicitly held; unrelated owners can begin without guessing where input code
or proof lives.

## 3. Keep owners moving within authorization

Own routine status collection. Owners implement their tickets and leave results
and proof in their conversations or artifacts. Assign no heartbeat, reporting
schedule, or promise to update the coordinator.

Use configured passive inspection to read native activity and pending-input
state first, then relevant conversation content when needed. An operation that
wakes an owner or requests a report is a follow-up under cycle step 2, not passive
inspection. Prefer passive result retrieval; when completion needs a reply or
wait/join, choose one mechanism per owner and collect each result once. Status
inspection continues independently of completion collection.

### Coordination cycle

Select monitoring from the confirmed configuration. Use native notifications for
prompt checks and a bounded wait for periodic scans. Without notifications,
use timed inspection. Use a configured wake mechanism after the turn ends only
within explicit authorization for scheduled or background monitoring. Otherwise
keep the coordinator active through bounded waits. When neither continued
execution nor an authorized wake is available, inspect once, record the manual
resume limitation, and hand back the current snapshot.
Owners raise genuine blockers and necessary questions through their normal
workflow; they need not separately notify the coordinator.

Use the confirmed run interval, falling back to setup's default when already
confirmed for this run. Save the selected mechanism, interval, actual last check,
next check deadline, and any monitoring hold in the run record, not the harness
configuration. Bound each wait by the next scan deadline. Resume with an
immediate scan; a missed deadline or a new notification needs no extra wait.
Event-driven checks leave the next full-scan deadline unchanged so busy owners
cannot postpone inspection of quiet ones.

Repeat this cycle while assigned work or known obligations remain:

1. Inspect every unfinished owner on startup/resume and at each scan deadline.
   On a notification, check the affected owner promptly. Include pending input,
   activity, blockers, and outstanding obligations. Reuse a fresh observation
   from the same cycle; retrieve only new results or changed evidence. When
   progress remains unclear, record it as unknown with the actual check time
   while retaining observed activity. Silence or unchanged state alone does not
   prove a stall.
2. Route actionable findings and scoped next actions to the existing owner. An
   idle owner with obligations is unfinished, not complete. Message an active
   owner only when a specific fact missing after inspection prevents coordination
   or concrete evidence of a problem requires intervention. Record that reason
   before one scoped request. Keep unanswered follow-ups visible rather than
   resending every scan. Use the routing rules below for decisions and human-only
   gates; continue unrelated work and escalate material problems with a recommendation.
3. Assess new proof under step 4, maintain the record and selected dashboard
   under step 5, and reconcile completion/closure under step 6. Record each
   owner's actual check time. Refresh the record and selected dashboard after
   each periodic scan and meaningful event, including an unchanged scan's real
   timestamp. Keep retained proof assessments; inspection is not a rerun of tests.
4. If obligations remain, wait for a notification or the next scan deadline,
   then repeat. Long helper calls and caller-blocking dialogs delay inspection;
   record a missed check honestly and scan when control returns. The dashboard
   stays a snapshot while the coordinator cannot write it.

Exit when all assignments and known obligations are settled, the user pauses
the run, only human answers can unblock remaining work, or the harness cannot
continue monitoring. Before yielding, save the actual hold and answer/resume
route. Keep `next_check_at` only when continued execution or an authorized wake
will perform that check; otherwise set it to `null`. A completion notification
does not end monitoring of other owners.

### Helpers, decisions, and authorization

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
An owner can apply a local answer within existing authorization and record the
answer, source and outcome in its conversation for inspection; the user need
not repeat it to the coordinator.
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

**Cycle complete when** each due owner has a fresh observation or an explicit
inspection limitation, findings have an action/answer route, the record and
selected dashboard are current, and the next check or actual hold is recorded.
Continue cycles until an exit condition above is met; shared actions must fit
recorded authorization throughout.

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
Record `harness_name`, `config_path`, and the actual run-choice confirmation in
the record. A resume in a different harness needs explicit ownership/evidence
transfer; selecting its setup profile alone does not transfer an existing run.

Use the data contract in [dashboard data](references/dashboard-data.md).

Use the run-specific presentation choice confirmed in step 2 or restored on resume:

- If no destination is chosen and the user requests only a consequential
  decision, defer the destination question and keep presentation **unselected**.
  An unanswered destination question has the same outcome. Save `destination`,
  `local_path`, `artifact_id`, and `artifact_url` as `null` with a nonempty
  `presentation.hold` explaining the missing confirmation. Continue coordination
  and update the local status record; leave dashboard generation, writes and
  hosting held. An old page stays unchanged and is not the current display.
- Otherwise, reuse the confirmed destination without asking again. If still
  missing, ask one focused question offering available destinations and audiences.
  Ask separately from shared-action approvals. A setup preference, template
  value, or existing path alone is not a run-specific user answer.
- After an actual destination choice, save its values and clear the presentation
  hold. Generate from the bundled template and update that same artifact in place.
  Only this branch runs the renderer below.

Publishing the dashboard does not authorize uploading underlying private proof,
publishing code, or publishing skills. Use accessible proof links for its audience,
or identify privately retained proof. Follow the selected host's instructions.
In a remote sandbox, local HTML needs a supported preview or portal for the user;
a sandbox-local URL is not a delivery link.

Set `presentation.auto_refresh` from the selected destination's discovered
`auto_refresh` capability. Inspect missing capability facts through discovery.
Enable verified embedded refresh automatically at the confirmed run interval.
For unavailable or unverified support, keep the page static and state the limitation
in `notice`. When first using a destination, check the served page's refresh
directive and verify that a timed reload retrieves an updated artifact from the
same URL, without a manual reload. If the host strips refresh or serves stale HTML,
correct discovery and keep the page static with the limitation.
Reloads continue through pauses and completion and can discard open dialogs and
drafted questions. They do not run status checks or establish fresh evidence.

```bash
python3 <this skill's folder>/scripts/render_dashboard.py <status.json> <dashboard.html>
# Before hosting, reject local proof/owner links that the audience cannot use:
python3 <this skill's folder>/scripts/render_dashboard.py <status.json> <dashboard.html> --hosted
```

The renderer checks the display contract, not the truth of supplied evidence.
Refresh at step 3's cycle boundaries, including dependency/approval changes,
corrected verdicts and owner closure. Record each task's `work` status and reason
under the [work status contract](references/dashboard-data.md#work-status-and-resolution).
Recover missing outcomes from retained results and decisions; closure alone
leaves the outcome unclassified. Show all tasks in a grouped ledger: Needs
attention, Moving or ready, and Resolved for this run. Keep reasons, next actions,
deferral triggers and pending decision links visible beside the work status.
Summarize remaining work and each resolution separately; keep owner lifecycle
secondary and all four milestone indicators independent. Keep one decision queue
below the ledger.
Selecting a task opens its blocker, next action, and proof in a bounded dialog.
Selecting a decision opens its focused dialog. Default to a closed dialog on
initial load unless the user requests a selected decision up front. Keep unblock
previews and copyable IDs in the queue, with the recommendation and authoritative
answer route in the dialog.
Keep history and raw proof expandable. Stamp the real update time; do not imply
that a page reload advances the coordinator's snapshot time.

Keep task, proof, decision, and run IDs stable. The template lets the user copy
an ID, a question, or the selected issue/decision context with its snapshot time,
states, blocker, next action, proof IDs and approval constraints. Task/proof
questions go to the coordinator; task context goes to its existing work owner.
Decision context and questions use their recorded discussion route, with a
direct-thread instruction for human-only gates. Keep the work owner distinct
from that answer destination. Show affected tasks and what each decision unblocks
beside its recommendation.
Record the coordinator link and any configured native comment/message mechanism
in `presentation`. Put Copy context before the existing conversation link;
the user copies, opens and pastes. Neither action sends a message or grants
approval. Use host-native interaction when supported; do not invent a chat backend
or claim delivery from a clipboard action. Interpret answers against the same
record and update it without asking the user to repeat a decision already made
in its authoritative conversation.

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

For authorized cancellation or deferral, retain the decision receipt and scope
before withdrawing affected work. Record the distinct resolution under the work
status contract, settle remaining obligations and retain the handoff before
marking the owner complete. A deferral keeps its revisit trigger. Investigation
that establishes no change is needed keeps its supporting proof. These outcomes
settle the current assignment without claiming implementation was delivered.
Inspect due deferral triggers on resume and at coordination scans. When a trigger
fires, expose the follow-up for the same ticket and owner within the authorized
run scope; otherwise queue the required decision instead of silently restarting it.

Hypothetical future work and unrequested milestones do not keep a completed
owner open. Never delete evidence to clean up.

Keep the owner reference after closure. Resume that owner for later follow-up
when supported; otherwise transfer ownership explicitly using the retained
handoff. Closure does not make a ticket ownerless.

**Done when** each assignment meets its finish line or has a recorded authorized
resolution, all remaining requested milestones are verified, known obligations are settled,
completed owners have been closed or have truthful closure limitations, and the
status matches that result. The final chat states actual delivery, limitations,
and the dashboard location or presentation hold without repeating its audit trail.
