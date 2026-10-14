# Dashboard data

`status.json` is the coordinator's local record of a run, not a receipt format
workers must implement. Its shape, the fields the page draws and what each
value means on the page, is the `dashboard` skill's status contract, in that
skill's `references/status-contract.md`; the renderer there checks the shape.
This file holds the rules `orchestration-run` adds for a coordinated run, and
`scripts/validate_run.py` checks them before every render. The full shape with
every section populated is the dashboard skill's synthetic
`evals/dashboard-preview.json`.

A run record uses the whole contract: the run fields below, every row with
`milestones`, `work` and `runtime`, retained `evidence`, pending `decisions`,
and `history`. Stages advance only on accepted proof, whatever the agent's
state.

## Contents

- [Run fields](#run-fields)
- [Row rules](#row-rules), with [work status](#work-status-and-resolution) and [business stages](#business-stages)
- [Run lifecycle](#run-lifecycle)
- [Evidence](#evidence)

## Run fields

- `schema_version`: `2` for new runs. Schema 1 records still pass
  `validate_run.py` without the [run lifecycle](#run-lifecycle) checks; bring a
  resumed record up to schema 2 as that section describes.
- `run_id`: stable ID included in copied dashboard questions.
- `updated_at`: actual ISO 8601 timestamp, with timezone; approval expiry and
  runtime retention are judged against it.
- `config_path`: absolute path of the repository's `.nthplusio-skills/orchestration.json`
  this run reads. Required.
- `harness_name`: current harness name, exactly as keyed in setup. Required for
  new runs. Recover older records' name from their original context, not the model.
- `run_choices`: selected ticket IDs, target stage, publication scope, idle-scan
  limit, destination, interval, and `confirmed_from` identifying the actual user
  instruction or answer. Schema 1 records may carry a text finish line instead. Defaults
  propose choices for a new run. Resume reuses these choices without another
  interview. Run overrides leave project policy and harness defaults unchanged.
- `monitoring`: required for new coordinated runs; older records can omit it
  until resumed. `mode` describes the selected configured mechanism.
  `interval_seconds` is the positive scan interval, which the page also uses
  for its reload; `last_checked_at` is the actual latest scan timestamp, or
  `null` before inspection. `next_check_at` is the next scan deadline, or
  `null` when no continued execution or authorized wake will perform it.
  `hold` is `null` during normal monitoring, or names the actual
  pause/limitation and answer/resume route. This records step 3's cycle; the
  renderer neither schedules checks nor establishes their execution.
- `presentation`: the run-specific destination choice from step 2. Before that
  choice, set `destination`, `local_path`, `artifact_id` and `artifact_url` to
  `null` and record a nonempty `hold` explaining the missing confirmation; keep
  HTML generation and writes held. Clear `hold` after confirmation. A template
  destination is not confirmation. `auto_refresh` is derived from the selected
  destination's discovered capability, not a preference; `true` only for
  verified support for embedded full-page reloads from the same URL. When it is
  `false` or absent, state the hosting limitation in `notice`.
- `notice`: optional visible qualification, such as a historical-preview label,
  a hosting limitation, or a migration note while the record is behind this
  skill's version.
- `decisions`: pending questions in priority order. Include `task_ids` naming
  affected assigned rows that already exist in `tasks`. For unassigned tickets
  or proposed children, name their IDs in the decision text and leave
  `task_ids` empty until assigned; keep approval pending without inventing an
  owner or a matrix row. Set `requires_human: true` when only the user can
  answer a native gate in that conversation; otherwise exact answers by ID may
  be relayed when configured messaging permits it. Ticket-local choices use
  their owner; cross-ticket and shared-action decisions use the coordinator. A
  human-only gate always needs a named discussion owner.
- `history`: concise strings recording material changes and corrected verdicts.
  When a decision is answered, retain its ID, actual answer/source and scope
  once here or through an accessible conversation receipt, then remove it from
  `decisions`. An answered question is not proof its resulting action completed.

## Row rules

Each row represents one ticket in the repository's confirmed ticket source.
`id` is its stable ticket ID, `title` is the outcome, and `done_when` names the
assigned completion criterion. `owner` contains the actual harness `id`,
`label`, optional `href`, `state`, optional `activity`, `location`, and
`handoff`. Record `activity` from inspected state or an actual progress report.

An owner ID belongs to exactly one ticket, including closed owners. For
monitored runs, `owner.last_checked_at` records that owner's actual latest
state inspection with timezone, or `null` while uninspected. An unchanged scan
can advance this timestamp without changing activity or reassessing its proof.
When inspection leaves progress unknown, state that in `next_action` or `history`
and retain the observed `owner.state`; unknown progress is not a blocker by itself.
Retain unanswered scoped follow-ups in the blocker/next action and history.
Retain the original ticket binding in the row and any replacement handoff/history.
Inspect the owner's original assignment before reuse; no script can prove
historical bindings outside this record. Setup owns project ticket policy.
Record this run's selected policy source in `history`, not a second policy interview.

Use `complete` when work is done but closure is unavailable/pending. Only
`closed` asserts that the harness close/archive operation succeeded. Settle all
of its ticket's assigned work and known obligations before marking it complete
or closed. Code readiness and owner completion are independent: a required
runtime release keeps the owner active/waiting and belongs in `obligations`.
A `blocked` owner needs an actionable `blocker`. A complete or closed owner
needs a retained `handoff`, no unfinished obligations, no blocker, and no
pending or blocked stage. These checks prevent display contradictions; they
cannot verify that a human actually discharged an obligation.

`resources` lists file/runtime responsibilities. `blocked_by` lists known task
IDs or named external dependencies. `blocker` states the actionable hold, or is
empty. `next_action` stays visible. `obligations` lists assigned unfinished work
such as required CI, a requested review, or merge landing.

### Work status and resolution

Record `work` separately from `owner.state` in every new or resumed row, with
the state, a technical `reason`, and a plain-language `summary`:

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

`reason` describes the observed condition or result, not a repeat of the
status label. Add a summary to every new or resumed row, and update it
whenever the state or reason changes.

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
missing check times display as unrecorded rather than fresh. Unfinished work
with a recorded state other than `unknown` keeps its owner from completing.

Records without `work` still render with the contract's fallback: complete and
closed owners show **Confirming status**, not Done. On resume, recover actual
outcomes from retained results and decisions before replacing this fallback.
`validate_run.py` checks internal consistency, not whether a receipt really
authorized the resolution.

### Business stages

`milestones` holds the business stages in delivery order. Every task has all
eight; when resuming an older record, add any missing `defined`, `researched`,
`review` and `verification` stages from retained proof.

Mark every stage beyond this run's finish line `not_requested`: the last
requested stage is the target stage, and the first unverified requested stage is
the current stage. Stages stay independent: each needs its own proof, and a
verified later stage leaves earlier stages unverified.

A `verified` stage must reference proof assessed as `accepted` whose result is
not failed or interrupted. `note` scopes the claim, including the exact
code-publication artifact or deployment target where relevant. For an
unrequested stage, use an empty evidence list and explain nothing unless it
prevents a likely misunderstanding. A pending or blocked `business_acceptance`
stage carries `accountable`, the person who signs off, and `revisit`, a date
or event.

## Run lifecycle

Schema 2 adds these fields, and `validate_run.py` enforces them:

- Top-level fields are limited to the contract. Put extra notes in `history`
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
  `active` approval past `expires_at` is a finding, so mark it expired and ask again.
- Each task has `runtime`: an entry for each running or retained instance the
  owner created or holds. Each entry has an `id`, `kind`, `ref`, and `state`:
  `held` (in use), `released`, or `retained`. A retained entry needs a `reason`
  and an `until` timestamp. A finished owner or resolved row cannot hold runtime.
  The page shows a retained entry past its `until` date as overdue cleanup.
  `resources` keeps describing file and responsibility areas, not instances.
- `skill_version` records the skill version this run follows, from
  `validate_run.py --skill-version`; it covers this skill's files and the
  dashboard contract, stage list, template and renderer the run renders
  through. `contract_version` records the dashboard contract the record was
  written against, from the dashboard skill's
  `render_dashboard.py --contract-version`. `validate_run.py` reports a
  different current value for either as a note: migrate the record, then save
  the new versions.
- `history` entries are at most 800 characters. Unchanged scans add none.
- `follow_ups` lists work found beyond a task's target stage. Each entry has an
  `id`, `from_task` (an assigned row), `text`, `owner` (the ticket or person
  who owns it, or `null`) and an optional `trigger`. The page asks for owners
  for entries with `null`.
- `closed_at` marks a closed run. Every owner must then be complete or closed,
  with no held runtime, an owner for every follow-up, no pending decision and
  no scheduled check.
- A delivered row whose implementation was verified but never published shows
  as **Done, not submitted** on the page, and the headline counts those rows
  separately.
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

## Evidence

Each entry follows the contract's evidence shape: a stable `id`, `label`,
`scope`, `result`, `assessment`, `note`, and either `href` or literal `output`.
The result records a check's outcome; the assessment records whether it
supports the claimed stage. A green workflow may be `passed` but `limited` for
review completion. Only accepted proof supports a verified stage or a delivered
outcome.

Retain raw evidence outside the owner's disposable context. A link must remain
usable after closure. Keep failed/interrupted entries after successful evidence
arrives. Use `superseded` and a correction note for an earlier misleading verdict.
Never put secrets or unapproved private content in output that will be hosted.

The renderer's `--hosted` mode rejects local and loopback links. Replace them
with approved accessible links, or keep the receipt private and include
sanitized literal output sufficient for the displayed verdict. Record any
accessibility limitation.
