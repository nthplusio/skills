# Dashboard data

`status.json` is the coordinator's local display record, not a receipt format
workers must implement. The renderer turns it into one self-contained HTML file
without fetching data or calling harness tools. See the synthetic
[`evals/dashboard-preview.json`](../evals/dashboard-preview.json) for the shape.

## Run fields

- `schema_version`: `1`.
- `run_id`: stable ID included in copied dashboard questions.
- `title`, `goal`: short plain-language strings.
- `updated_at`: actual ISO 8601 timestamp, with timezone.
- `config_path`: absolute path of repository setup this run reads.
- `harness_name`: current harness name, exactly as keyed in setup. Required for
  new runs. Recover older records' name from their original context, not the model.
- `run_choices`: selected ticket IDs, finish line, destination, interval, and
  `confirmed_from` identifying the actual user instruction or answer. Defaults
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
optional `href`, `state`, `location`, and `handoff`. Its state is `active`,
`waiting`, `complete`, or `closed`. An owner ID belongs to exactly one ticket;
the renderer rejects duplicate owner IDs across rows, including closed owners.
For monitored runs, `owner.last_checked_at` records that owner's actual latest
state inspection with timezone, or `null` while uninspected. An unchanged scan
can advance this timestamp without changing activity or reassessing its proof.
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

Every task has all four `milestones`:

| Key | Meaning |
| --- | --- |
| `pr_readiness` | Implementation and required proof/review material are prepared. Not an actual review. |
| `code_publication` | The specified branch/PR has actually been published. Not a merge or deployment. |
| `deployment` | The intended revision is running in the specified environment. |
| `business_acceptance` | The requested business behavior is accepted against its stated criteria. |

Each milestone has a `state`, `note`, and `evidence` list of proof IDs.
States are `verified`, `pending`, `blocked`, and `not_requested`. A `verified`
milestone must reference proof assessed as `accepted`. `note` scopes the claim,
including the exact code-publication artifact or deployment target where relevant.
For an unrequested milestone, use an empty evidence list and explain nothing
unless it prevents a likely misunderstanding.

A complete/closed owner needs a retained `handoff`, no unfinished obligations,
no blocker, and all requested milestones verified. These checks prevent display
contradictions; they cannot verify that a human actually discharged an obligation.

## Evidence fields

Each entry has a stable `id`, `label`, `scope`, `result`, `assessment`, `note`,
and either `href` or literal `output`. Results are `passed`, `failed`,
`interrupted`, or `observed`. Assessments are `accepted`, `limited`, or
`superseded`. This distinguishes a check's outcome from whether it supports the
claimed milestone. A green workflow may be `passed` but `limited` for review
completion. Only accepted proof supports a verified display milestone.

Retain raw evidence outside the owner's disposable context. A link must remain
usable after closure. Keep failed/interrupted entries after successful evidence
arrives. Use `superseded` and a correction note for an earlier misleading verdict.
Never put secrets or unapproved private content in output that will be hosted.

The hosted renderer rejects local and loopback links. Replace them with approved
accessible links, or keep the receipt private and include sanitized literal
output sufficient for the displayed verdict. Record any accessibility limitation.
