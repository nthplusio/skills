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

## 1. Read setup and choose the dashboard destination

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

**On every invocation, ask where the HTML dashboard should live.** Offer the
usable local or hosted destinations from the configuration, with their
audiences. If the user's invocation already chooses one, confirm that choice
rather than asking again. Save this run's choice, local path, and published
artifact ID/URL in its status record, not in the harness configuration.

Generate from the bundled template and update the same artifact in place.
Publishing the dashboard does not authorize uploading underlying private
proof, publishing code, or publishing skills. Use accessible proof links for
the chosen audience, or identify proof retained privately without a broken
local link. Follow the selected host's artifact instructions. In a remote
sandbox, a local file still needs a supported preview or portal to be viewable
by the user; a sandbox-local URL is not a delivery link.

**Done when** the runner has read a suitable configuration, the user has chosen
a destination, and this run has a stable local status/dashboard location. On
resume, existing ownership and decisions are restored and any evidence gaps
are visible before new work is assigned.

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
loading is unavailable.

**Done when** every task has one accountable owner, a checkable finish line,
and clear resource/dependency boundaries. Each owner can begin without guessing
where its input code or proof lives.

## 3. Keep owners moving within authorization

Use the configured inspection, messaging, and result-collection operations.
Choose one completion mechanism per owner, such as a reply or a wait/join;
do not double-collect merely to obtain the same report. An idle owner may be
waiting for input, not finished. Route findings and follow-up fixes to its owner.

Resolve ordinary technical blockers and owner disagreements with evidence.
Escalate unresolved scope, expected behavior, or acceptable-risk choices, and
shared actions outside granted approval. Pause affected work while independent
owners continue. Give the user the concrete decision and your recommendation.

Record approval scope, destination, and side effects and carry that permission
to the relevant owners. A milestone goal is not approval for a shared database
write, access/secrets change, push, merge, or deployment. Include indirect
effects such as auto-merge or an automatic deployment before seeking approval.
Ask again only when the action exceeds the granted scope.

**Done when** runnable work continues, holds name their real blocker and next
action, and requested shared actions fit recorded authorization.

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

Use the data contract in [dashboard data](references/dashboard-data.md) and run:

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
an ID or a question containing the run/task/proof context, then paste it into
the coordinator conversation. Record the coordinator link and any configured
native comment/message mechanism in `presentation`. Explain that copy does not
send. Use host-native interaction when supported; do not invent a chat backend
or claim a message was delivered from a clipboard action. Interpret dashboard
questions against the same status record and update it when an answer changes
the verdict or plan.

Render representative states and inspect the result when creating or changing
the template. Routine data updates need the renderer check and a correct
destination update, not repeated screenshots of an unchanged layout.

Chat updates cover decisions needed, material blockers/plan changes, and reached
milestones. Say what changed, what needs attention, and the recommendation where
applicable. Link the dashboard; leave routine receipts and investigation detail
there. Honor harness progress requirements with brief updates.

**Done when** the stable dashboard presents the actual current record and its
proof is accessible or clearly marked private. The user can scan task state
without reading the coordinator conversation.

## 6. Close completed owners and finish the run

An owner is complete when its assigned finish line is proven and its **known
obligations** are settled. Required CI, requested review, needed approval, or
assigned follow-up counts even before the next message arrives. Idle, blocked,
and awaiting approval are not completed. Hypothetical future work and unrequested
milestones are not reasons to keep a completed owner open.

Before closure, retain the result, usable proof, exact work location, limitations,
and continuation instructions outside any context that closure makes inaccessible.
Update the dashboard, then use the configured close/archive operation and record
its actual result. Never delete evidence to clean up. If closure is unsupported
or fails, record **complete, closure unavailable/pending**, not **closed**.

Keep the owner reference after closure. Resume that owner for later follow-up
when supported; otherwise transfer ownership explicitly using the retained
handoff. Closure does not make a ticket ownerless.

**Done when** all assigned milestones are verified, known obligations are settled,
completed owners have been closed or have truthful closure limitations, and the
dashboard matches that result. The final chat states the actual delivery state,
remaining limitations, and dashboard location without repeating its audit trail.
