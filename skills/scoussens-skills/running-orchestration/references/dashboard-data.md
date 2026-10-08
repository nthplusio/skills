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
- `config_path`: absolute path of the stored harness JSON this run reads.
- `presentation`: chosen destination ID, local HTML path, and hosted artifact
  ID/URL if any. `coordinator_href` links back to the coordinator where supported;
  `interaction` describes a configured native comment/message mechanism or says
  to paste copied questions. Copying is not delivery. Setup lists destinations;
  this record stores the user's choice.
  Before that choice, set `destination`, `local_path`, `artifact_id` and
  `artifact_url` to `null` and record a nonempty `hold` explaining the missing
  confirmation. This is a status-only record; keep HTML generation/writes held.
  Clear `hold` after confirmation. A template destination is not confirmation.
- `notice`: optional visible qualification, such as a historical-preview label.
- `decisions`: objects with stable `id`, `text`, and `recommendation` strings.
- `tasks`: the current task rows.
- `evidence`: retained proof entries.
- `history`: concise strings recording material changes and corrected verdicts.

Task/proof/decision IDs use letters, numbers, underscores, or hyphens and start
with a letter or number. Keep IDs unchanged when updating the artifact. The
template uses them for selection, links, host comments, and copyable questions.

## Task fields

`id` is a stable ticket or task ID, `title` is the outcome, and `done_when` names
the assigned completion criterion. `owner` contains its actual harness `id`,
`label`, optional `href`, `state`, `location`, and `handoff`. Its state is
`active`, `waiting`, `complete`, or `closed`. Multiple tickets may share an
owner ID; its lifecycle must agree across rows and counts include it once.
Use `complete` when work is done but closure is unavailable/pending. Only
`closed` asserts that the harness close/archive operation succeeded. Settle all
of an owner's assigned tasks before marking that owner complete or closed.

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
