# Dashboard data

`status.json` is the coordinator's local display record, not a receipt format
workers must implement. The dashboard's main readers are non-technical
stakeholders, such as testers or executives, tracking progress. Write the
overview fields (`title`, `goal`, `work.summary`, and each decision's `text`,
`recommendation` and `unblocks`) in plain language, without ticket jargon, agent
terms or proof IDs. Technical fields (`reason`, `blocker`, `next_action`, stage
notes, owner and proof) appear only when a reader opens an item or decision. The
renderer turns the record into one self-contained HTML file without fetching
data or calling harness tools. See the synthetic
[`evals/dashboard-preview.json`](../evals/dashboard-preview.json) for the shape.

Each task row records three independent views of status:

| View | Field | Answers |
| --- | --- | --- |
| [Business stage](#business-stages) | `milestones` | Where is the work, against this run's target stage? |
| [Business status](#work-status-and-resolution) | `work` | Is it moving, waiting on someone, or how did it end? |
| [Agent status](#task-fields) | `owner.state`, `owner.activity` | What is the agent that owns the ticket doing? |

Stages advance only on accepted proof, whatever the agent's state.

## Contents

- [Run fields](#run-fields)
- [Task fields](#task-fields), with [work status and resolution](#work-status-and-resolution) and [business stages](#business-stages)
- [Run lifecycle](#run-lifecycle)
- [Evidence fields](#evidence-fields)

## Run fields

- `schema_version`: `2` for new runs. Schema 1 records still render without the
  [run lifecycle](#run-lifecycle) checks; bring a resumed record up to schema 2
  as that section describes.
- `run_id`: stable ID included in copied dashboard questions.
- `title`, `goal`: short plain-language strings.
- `updated_at`: actual ISO 8601 timestamp, with timezone.
- `config_path`: absolute path of the repository's `.nthplusio-skills/orchestration.json`
  this run reads.
- `harness_name`: current harness name, exactly as keyed in setup. Required for
  new runs. Recover older records' name from their original context, not the model.
- `run_choices`: selected ticket IDs, target stage, publication scope, idle-scan
  limit, destination, interval, and `confirmed_from` identifying the actual user
  instruction or answer. Schema 1 records may carry a text finish line instead. Defaults
  propose choices for a new run. Resume reuses these choices without another
  interview. Run overrides leave project policy and harness defaults unchanged.
- `monitoring`: required for new coordinated runs; older records can omit it
  until resumed. `mode` describes the selected configured mechanism.
  `interval_seconds` is the positive scan interval; `last_checked_at` is the
  actual latest scan timestamp, or `null` before inspection. `next_check_at` is
  the next scan deadline, or `null` when no continued execution or authorized
  wake will perform it. `hold` is `null` during normal monitoring, or names the
  actual pause/limitation and answer/resume route. This records step 3's cycle;
  the renderer neither schedules checks nor establishes their execution.
- `presentation`: chosen destination ID, local HTML path, and hosted artifact
  ID/URL if any. `coordinator_href` links back to the coordinator where supported;
  `interaction` describes a configured native comment/message mechanism or says
  to paste copied questions. Copying is not delivery. Setup lists destinations;
  this record stores the user's choice.
  Before that choice, set `destination`, `local_path`, `artifact_id` and
  `artifact_url` to `null` and record a nonempty `hold` explaining the missing
  confirmation. This is a status-only record; keep HTML generation/writes held.
  Clear `hold` after confirmation. A template destination is not confirmation.
  `auto_refresh` is a boolean derived from the selected destination's discovered
  capability, not a preference. Set it to `true` only for verified support for
  embedded full-page reloads that retrieve the updated artifact from the same URL.
  `false` or an absent field renders a static snapshot; state the hosting
  limitation in `notice`. When enabled, the template embeds HTML refresh using
  `monitoring.interval_seconds`, which must be a positive integer. Reloads continue
  during monitoring holds and after completion, with no dialog, draft, or expanded
  proof preservation. Browser throttling can delay reloads. A reload neither
  invokes the coordinator nor changes `updated_at` or proof timestamps.
- `notice`: optional visible qualification, such as a historical-preview label.
- `decisions`: pending questions in priority order, with stable `id`, `text`,
  and `recommendation` strings. Include `task_ids` naming affected assigned rows
  that already exist in `tasks`. For unassigned tickets or proposed children,
  name their IDs in the decision text and leave `task_ids` empty until assigned;
  keep approval pending without inventing an owner or a matrix row. Include
  `unblocks` describing the work an answer enables, and `discussion` containing
  the authoritative conversation's actual `owner_id`, readable `label`, and
  `href`. An unavailable link is empty; show the owner handle instead. Set
  `requires_human: true` when only the user can answer a native gate in that
  conversation. Otherwise, exact answers by ID may be relayed when configured
  messaging permits it. Ticket-local choices use their owner; cross-ticket and
  shared-action decisions use the coordinator. Older records without routing
  fields still render with the coordinator fallback. A human-only gate always
  needs a named discussion owner.
- `tasks`: the current task rows.
- `evidence`: retained proof entries.
- `history`: concise strings recording material changes and corrected verdicts.
  When a decision is answered, retain its ID, actual answer/source and scope
  once here or through an accessible conversation receipt, then remove it from
  `decisions`. An answered question is not proof its resulting action completed.

A human-only decision uses this shape. `requires_human` belongs on the decision,
alongside `discussion`:

```json
{
  "id": "Q3",
  "text": "Complete the existing sign-in dialog.",
  "recommendation": "Answer in the runtime owner conversation.",
  "task_ids": ["ENV-106"],
  "unblocks": "Runtime sign-in",
  "requires_human": true,
  "discussion": {
    "owner_id": "runtime-owner",
    "label": "Runtime owner",
    "href": "https://example.org/conversations/runtime-owner"
  }
}
```

Task/proof/decision IDs use letters, numbers, underscores, or hyphens and start
with a letter or number. Keep IDs unchanged when updating the artifact. The
template uses them for selection, links, host comments, and copyable questions.

## Task fields

Each row represents one ticket in the repository's confirmed ticket source.
`id` is its stable ticket ID, `title` is the outcome, and `done_when` names the
assigned completion criterion. `owner` contains its actual harness `id`, `label`,
optional `href`, `state`, optional `activity`, `location`, and `handoff`.

| `owner.state` | Overview label | Meaning |
| --- | --- | --- |
| `active` | Working | The agent is working, possibly through its own subagents. |
| `waiting` | Waiting | The agent is idle until an answer, a review, a deployment or another event arrives. |
| `blocked` | Blocked | The agent cannot proceed. Requires an actionable `blocker`. |
| `unreachable` | Not responding | The coordinator could not inspect the agent. Record the attempt in `next_action` or `history`. |
| `complete` | Finished | Work and obligations are settled; closure is unavailable or pending. |
| `closed` | Closed | The harness close/archive operation succeeded. |

`activity` is an optional, nonempty sentence describing what the agent is doing
now, such as "A research subagent is comparing two caching approaches." Record it
from inspected state or an actual progress report.

An owner ID belongs to exactly one ticket;
the renderer rejects duplicate owner IDs across rows, including closed owners.
For monitored runs, `owner.last_checked_at` records that owner's actual latest
state inspection with timezone, or `null` while uninspected. An unchanged scan
can advance this timestamp without changing activity or reassessing its proof.
When inspection leaves progress unknown, state that in `next_action` or `history`
and retain the observed `owner.state`; unknown progress is not a blocker by itself.
Retain unanswered scoped follow-ups in the blocker/next action and history.
Retain the original ticket binding in the row and any replacement handoff/history.
Inspect the owner's original assignment before reuse; the renderer cannot prove
historical bindings outside this record. Setup owns project ticket policy.
Record this run's selected policy source in `history`, not a second policy interview.
Use `complete` when work is done but closure is unavailable/pending. Only
`closed` asserts that the harness close/archive operation succeeded. Settle all
of its ticket's assigned work and known obligations before marking it complete
or closed. Code readiness and owner completion are independent: a required
runtime release keeps the owner active/waiting and belongs in `obligations`.

`resources` lists file/runtime responsibilities. `blocked_by` lists known task
IDs or named external dependencies. `blocker` states the actionable hold, or is
empty. `next_action` stays visible. `obligations` lists assigned unfinished work
such as required CI, a requested review, or merge landing.

### Work status and resolution

Record `work` separately from `owner.state` in every new or resumed row:

```json
{
  "work": {
    "state": "deferred",
    "summary": "Postponed until the sign-in fix is accepted.",
    "reason": "The user moved this change out of the current run.",
    "receipt": "Q4: user deferred this ticket in the owner conversation; retain the actual message link or receipt ID.",
    "revisit": "Reassess after the authentication fix is accepted.",
    "evidence": []
  }
}
```

`state` selects one group in the ledger. `reason` is nonempty text describing
the observed condition or result, not a repeat of the status label. `summary`
is an optional, nonempty sentence that tells a non-technical reader what is
happening and, when relevant, what they need to do. The overview shows `summary`
and falls back to `reason`; the item dialog shows both. Add a summary to every
new or resumed row, and update it whenever the state or reason changes.

The overview uses plain labels. The item dialog also shows the raw state key.

| Group | States (overview label) | Meaning |
| --- | --- | --- |
| Needs attention | `needs_decision` (Needs a decision), `blocked` (Blocked), `waiting` (On hold), `unknown` (Confirming status) | A pending decision, actionable blocker, another wait, or insufficient information to classify. |
| In progress | `working` (In progress), `ready` (Ready to start), `awaiting_acceptance` (Ready for sign-off) | Work underway, ready to assign/start, or awaiting the requested review or business acceptance. |
| Wrapped up | `delivered` (Done), `no_change_needed` (No change needed), `cancelled` (Cancelled), `deferred` (Postponed) | The assigned finish line is proven, investigation establishes no change is needed, or an authorized decision removes the work from this run. |

Use `delivered` only for the assigned `done_when` scope. A review-ready finish
line can be delivered without publication or deployment; the stages
still describe those independently. `delivered` and `no_change_needed` require
`work.evidence` naming accepted, nonfailed retained proof. For `cancelled` and
`deferred`, `receipt` identifies the actual authorizing decision and its scope.
`deferred` also requires a nonempty `revisit` date or observable trigger. A
suggestion to defer is still unfinished work until the authorized decision exists.

Every resolved row has no blocker, no unfinished obligations, and no pending or
blocked requested stage. Before cancellation or deferral, retain the decision
and prior stage verdicts in history. Withdraw only the obligations and
stage requests covered by that decision, preserving already verified claims
and their proof. Record withdrawn stage scope in its note with
`not_requested`; never turn cancellation into a verified stage. Settle any
remaining runtime release or handoff before resolving the row.

`needs_decision` requires a pending decision whose `task_ids` includes this row.
`blocked` requires an actionable `blocker`. `unknown` needs a reason and a next
inspection action. An old check time or unchanged activity alone establishes
neither a blocker nor a stall. Keep real `owner.last_checked_at` timestamps;
missing check times display as unrecorded rather than fresh.

Records without `work` still render: active/waiting owners receive an explicitly
qualified activity-based status. Complete/closed owners show **Confirming
status**, not Done. On resume, recover actual outcomes from retained
results and decisions before replacing this fallback. The renderer validates
internal consistency, not whether a receipt really authorized the resolution.

### Business stages

`milestones` holds the business stages in delivery order. Every task has all
eight; when resuming an older record, add any missing `defined`, `researched`,
`review` and `verification` stages from retained proof.

| Order | Key | Overview label | Meaning |
| --- | --- | --- | --- |
| 1 | `defined` | Defined | The outcome and acceptance criteria are written down and agreed. A ticket that arrives defined can cite the ticket as proof. |
| 2 | `researched` | Researched | Open questions are investigated and an approach is chosen. Not requested when no research is needed. |
| 3 | `pr_readiness` | Implemented | Implementation and required proof/review material are prepared. Not an actual review. |
| 4 | `code_publication` | Submitted | The specified branch/PR has actually been published. Not a merge or deployment. |
| 5 | `review` | Reviewed | The requested code review actually produced its required result. |
| 6 | `verification` | Verified | An agent checked the change against the plan and spec before deployment. |
| 7 | `deployment` | Deployed | The intended revision is running in the specified environment. |
| 8 | `business_acceptance` | Accepted | Users accepted the deployed behavior against its stated criteria. |

Mark every stage beyond this run's finish line `not_requested`: the last
requested stage is the target stage, and the first unverified requested stage is
the current stage. Stages stay independent: each needs its own proof, and a
verified later stage leaves earlier stages unverified.

Each stage has a `state`, `note`, and `evidence` list of proof IDs.
States are `verified` (Done), `pending` (In progress), `blocked` (Blocked), and
`not_requested` (Not in scope). A `verified`
stage must reference proof assessed as `accepted`. `note` scopes the claim,
including the exact code-publication artifact or deployment target where relevant.
For an unrequested stage, use an empty evidence list and explain nothing
unless it prevents a likely misunderstanding.

A complete/closed owner needs a retained `handoff`, no unfinished obligations,
no blocker, and all requested stages verified. These checks prevent display
contradictions; they cannot verify that a human actually discharged an obligation.

## Run lifecycle

Schema 2 adds these fields, and the renderer enforces them:

- Top-level fields are limited to this contract. Put extra notes in `history`
  rather than a new top-level key.
- `run_choices.target_stage` names the last requested [business stage](#business-stages),
  such as `pr_readiness` or `code_publication`.
- `run_choices.publication_scope` is the run's authorization for code
  publication. It is one of `none`, `draft` (push branches and open draft pull
  requests), `ready` (also mark them ready for review) or `merge` (also merge
  pull requests whose required checks pass). Any task whose `code_publication`
  stage is pending or blocked needs a scope other than `none`.
- `run_choices.idle_scan_limit` is a positive integer, three unless the user
  chose otherwise.
- `run_choices.confirmed_from` identifies the user's actual confirmation.
- `monitoring.unchanged_scans` counts consecutive scans that changed no task,
  decision or proof verdict. When it reaches `idle_scan_limit` and every
  unresolved task is `needs_decision`, `waiting` or `awaiting_acceptance`,
  `next_check_at` must be `null`, with a `hold` naming the resume route.
- `approvals` lists every granted permission for a shared action. Each entry has
  a stable `id`, `scope`, `task_ids` (assigned rows, or empty for the whole run),
  `side_effects`, `receipt` naming the actual answer, `granted_at`, `expires_at`
  (or `null`), and `state`: `active`, `consumed`, `expired` or `revoked`. An
  `active` approval past `expires_at` is rejected, so mark it expired and ask again.
- Each task has `runtime`: an entry for each running or retained instance the
  owner created or holds. Each entry has an `id`, `kind`, `ref`, and `state`:
  `held` (in use), `released`, or `retained`. A retained entry needs a `reason`
  and an `until` timestamp. A finished owner or resolved row cannot hold runtime.
  A retained entry past its `until` date appears as overdue cleanup on the page.
  `resources` keeps describing file and responsibility areas, not instances.
- `skill_version` records the skill version this run follows, from
  `render_dashboard.py --skill-version`. A different current version shows a
  migration notice on the page.
- `history` entries are at most 800 characters. Unchanged scans add none.
- `follow_ups` lists work found beyond a task's target stage. Each entry has an
  `id`, `from_task` (an assigned row), `text`, `owner` (the ticket or person
  who owns it, or `null`) and an optional `trigger`. The page asks for owners
  for entries with `null`.
- A pending or blocked `business_acceptance` stage carries `accountable`, the
  person who signs off, and `revisit`, a date or event.
- `closed_at` marks a closed run. The renderer then requires every owner to be
  complete or closed, no held runtime, an owner for every follow-up, no pending
  decision and no scheduled check.
- A delivered row whose implementation was verified but never published shows
  as **Done, not submitted**, and the headline counts those rows separately.
- When an owner is `complete` or `closed` with verified `pr_readiness` and
  unverified `code_publication`, `owner.retained_code` keeps that code outside
  its workspace: `kind` is `pushed_branch`, `bundle` or `patch`, `ref` locates
  it, and bundles and patches carry a `checksum`.

To bring a schema 1 record up to schema 2 on resume, move unknown top-level
fields into `history` or the fields above, record approvals already granted in
the run, add each task's `runtime` and confirm the missing run choices with the
user. Shorten history entries over 800 characters, keeping their detail in a
retained proof entry. Then set `schema_version` to `2` and record the migration
in `history`.

## Evidence fields

Each entry has a stable `id`, `label`, `scope`, `result`, `assessment`, `note`,
and either `href` or literal `output`. Results are `passed`, `failed`,
`interrupted`, or `observed`. Assessments are `accepted`, `limited`, or
`superseded`. This distinguishes a check's outcome from whether it supports the
claimed stage. A green workflow may be `passed` but `limited` for review
completion. Only accepted proof supports a verified display stage.

Retain raw evidence outside the owner's disposable context. A link must remain
usable after closure. Keep failed/interrupted entries after successful evidence
arrives. Use `superseded` and a correction note for an earlier misleading verdict.
Never put secrets or unapproved private content in output that will be hosted.

The hosted renderer rejects local and loopback links. Replace them with approved
accessible links, or keep the receipt private and include sanitized literal
output sufficient for the displayed verdict. Record any accessibility limitation.
