# Status contract

One JSON file is the renderer's whole input. Any producer that writes this
shape gets the same page: an orchestrate loop, a single task that spawned
subagents, a thread that spawned child threads. The renderer turns the file
into one self-contained HTML page without fetching data or calling harness
tools.

The renderer checks the record's **shape**: known top-level keys, value sets,
well-formed IDs, and references that resolve. It does not judge whether the
record is true, whether proof supports a claim, or whether the producer
followed its own rules. A producer with such rules checks them before
rendering.

`contract_version` names this document and the renderer that implements it.
`python3 scripts/render_dashboard.py --contract-version` prints it, and every
page carries it in a comment on its second line. A producer records the
version it wrote against in the record's own `contract_version` and compares
it with the current one before rendering; a difference means a field, a value
set or a default changed since the record was written. The machine-readable
stage list is [`assets/stages.json`](../assets/stages.json).

## Contents

- [The record](#the-record)
- [Rows](#rows), with [agent status](#agent-status), [work status](#work-status) and [business stages](#business-stages)
- [Evidence](#evidence)
- [Decisions](#decisions)
- [Presentation](#presentation)
- [Monitoring and refresh](#monitoring-and-refresh)
- [Approvals, follow-ups and runtime](#approvals-follow-ups-and-runtime)
- [IDs](#ids)
- [Writing for the reader](#writing-for-the-reader)
- [A minimal record](#a-minimal-record)

## The record

Required:

- `schema_version`: `2`. Schema 1 is the shape records written before this
  contract used; it still renders, with unknown top-level keys ignored and
  `approvals` and `follow_ups` not read.
- `run_id`: stable ID, included in copied questions and copied context.
- `title`: short plain-language string.
- `tasks`: the [rows](#rows).
- `presentation`: where the page lives, per [presentation](#presentation).
  An empty object is allowed.

Optional, shown on the page when present:

- `goal`: one plain-language sentence under the title.
- `updated_at`: ISO 8601 timestamp with timezone. The header shows it in
  the reader's local time; without it the header says the snapshot time is
  not recorded. A reload never advances it.
- `notice`: a visible qualification, such as a historical-preview label.
- `decisions`, `evidence`, `history`: per their sections; empty when absent.
- `monitoring`: per [monitoring and refresh](#monitoring-and-refresh).
- `approvals`, `follow_ups`: per [approvals, follow-ups and runtime](#approvals-follow-ups-and-runtime).
- `closed_at`: timestamp. The header notice then says the page no longer
  changes.

Allowed and carried for the producer, not shown: `config_path`,
`harness_name`, `run_choices`, `contract_version`. The renderer rejects any
other top-level key by name, including `skill_version`, which contract 1
carried for a producer that no longer exists; keep extra notes in `history`.

## Rows

Each entry in `tasks` is one row: a ticket, a subagent, a child thread, or
whatever unit the producer tracks.

Required: `id`, `title`, and `owner` with `id`, `label` and `state`. The
`owner.id` is the actual harness handle of the agent that owns the row.
One owner may own multiple tasks, including closed tasks. Keep one row per
task with a unique work `id`; do not invent owner handles to distinguish rows.
Each task has one accountable writer; a shared owner does not combine its
tasks or authorize other writers to update that task's record.

Optional, with what the page shows when the field is absent:

| Field | Shown when absent |
| --- | --- |
| `owner.href` | the label without a link |
| `owner.activity` | nothing; when present it is a nonempty sentence about what the agent is doing now |
| `owner.location` | Not recorded |
| `owner.handoff` | Not complete |
| `owner.last_checked_at` | Check time not recorded |
| `owner.retained_code` | nothing; when present, `kind` is `pushed_branch`, `bundle` or `patch`, `ref` locates it, and `checksum` is shown when given |
| `work` | a status inferred from `owner.state`, per [work status](#work-status) |
| `milestones` | every stage as Not in scope and the stage column reading No stages requested |
| `blocker` | Nothing, or None in the technical detail |
| `next_action`, `done_when` | Not recorded |
| `resources`, `blocked_by`, `obligations` | None shared, None, None outstanding |
| `runtime` | nothing |

Each row records three independent views of status:

| View | Field | Answers |
| --- | --- | --- |
| [Business stage](#business-stages) | `milestones` | Where is the work, against the target stage? |
| [Business status](#work-status) | `work` | Is it moving, waiting on someone, or how did it end? |
| [Agent status](#agent-status) | `owner.state`, `owner.activity` | What is the agent that owns the row doing? |

### Agent status

| `owner.state` | Overview label | Meaning |
| --- | --- | --- |
| `active` | Working | The agent is working, possibly through its own subagents. |
| `waiting` | Waiting | The agent is idle until an answer, a review, a deployment or another event arrives. |
| `blocked` | Blocked | The agent cannot proceed. |
| `unreachable` | Not responding | The producer could not inspect the agent. |
| `complete` | Finished | Work and obligations are settled; closure is unavailable or pending. |
| `closed` | Closed | The harness close or archive operation succeeded. |

The item dialog shows `complete` as "Complete, closure pending / unavailable".

### Work status

`work` has a `state`, a nonempty `reason` in technical words, and optionally
a nonempty `summary` for the non-technical reader, a list of proof IDs in
`evidence`, a `receipt` naming the decision behind a cancellation or
deferral, and a `revisit` date or trigger. The overview shows `summary` and
falls back to `reason`; the item dialog shows both, the receipt, and the
outcome proof. `state` selects one group in the ledger:

| Group | States (overview label) | Meaning |
| --- | --- | --- |
| Needs attention | `needs_decision` (Needs a decision), `blocked` (Blocked), `waiting` (On hold), `unknown` (Confirming status) | A pending decision, a blocker, another wait, or insufficient information to classify. |
| In progress | `working` (In progress), `ready` (Ready to start), `awaiting_acceptance` (Ready for sign-off) | Work underway, ready to start, or awaiting the requested review or acceptance. |
| Wrapped up | `delivered` (Done), `no_change_needed` (No change needed), `cancelled` (Cancelled), `deferred` (Postponed) | The finish line is reached, investigation found no change needed, or a decision removed the work. |

A `delivered` row whose `pr_readiness` stage is verified and whose
`code_publication` stage is not shows as **Done, not submitted**, and the
headline counts those rows separately. Cancellation and deferral never count
as Done.

A row without `work` still renders: `active`, `waiting` and `blocked`
owners show `working`, `waiting` and `blocked` with a reason that says the
status was inferred; every other owner state shows **Confirming status**,
never Done.

### Business stages

`milestones` maps stage keys to `{"state", "note", "evidence"}` objects.
When it is present it holds at least `pr_readiness`, `code_publication`,
`deployment` and `business_acceptance`; the other four may be left out and
show as not recorded. An unknown key is rejected by name. The eight stages,
in delivery order, from [`assets/stages.json`](../assets/stages.json):

| Order | Key | Overview label | Meaning |
| --- | --- | --- | --- |
| 1 | `defined` | Defined | The outcome and acceptance criteria are written down and agreed. |
| 2 | `researched` | Researched | Open questions are investigated and an approach is chosen. |
| 3 | `pr_readiness` | Implemented | Implementation and required proof or review material are prepared. Not an actual review. |
| 4 | `code_publication` | Submitted | The branch or pull request has been published. Not a merge or deployment. |
| 5 | `review` | Reviewed | The requested code review produced its required result. |
| 6 | `verification` | Verified | An agent checked the change against the plan and spec before deployment. |
| 7 | `deployment` | Deployed | The intended revision is running in the specified environment. |
| 8 | `business_acceptance` | Accepted | Users accepted the deployed behavior against its stated criteria. |

States are `verified` (Done), `pending` (In progress), `blocked` (Blocked)
and `not_requested` (Not in scope). `evidence` lists proof IDs that exist in
the record's [evidence](#evidence). `note` scopes the claim and appears in
the item dialog; a not-requested stage with an empty note is left out of the
technical list. When a stage carries `accountable` and `revisit`, the dialog
shows who signs off and when.

The page derives each row's position: the **target** is the last stage that
is not `not_requested`, and the **current** stage is the first requested
stage that is not `verified`. A row whose requested stages are all verified
reads "<target> ✓, Reached this run's target". A cancelled or deferred row
reads "Stopped after <last verified stage>" or "Stopped before starting".

### Amp orchestration publication receipt

The Amp producer reads this optional handoff section. Its first nonempty
line must be a JSON object (no Markdown code fence):

```text
## Publication receipt
{"repo":"https://github.com/example/project","remote_ref":"refs/heads/orch/task","observed_commit_sha":"0123456789abcdef0123456789abcdef01234567"}
```

`repo` is an HTTPS repository URL with a nonempty path and no credentials,
query or fragment. `remote_ref` is a fully qualified `refs/heads/` or
`refs/tags/` ref; its suffix starts with a letter, number or underscore and
uses only letters, numbers, underscores, dots, slashes and hyphens. Empty
components, `..`, dot-prefixed components, and components ending in `.` or
`.lock` are invalid. `observed_commit_sha` is the exact nonzero 40- or
64-hex commit ID observed at that remote ref, not a short SHA or branch name.
The producer must observe the remote ref after publication and ensure it
matches the intended code before writing the receipt. The dashboard parses
the receipt; it does not query Git or independently authenticate the claim.

Without a valid receipt, code publication stays pending, even with a Branch
line, PR number or successful handoff. A requested PR without a recorded PR
number also remains pending. Verifiers do not request code publication.
Publication proves neither merge nor deployment nor business acceptance.
Unit tests and type checks are limited evidence for their stated scope,
not user acceptance; the Amp producer leaves business acceptance not requested.

## Evidence

Each entry has a stable `id`, `label`, `scope`, `result`, `assessment`,
`note`, and either `href` or literal `output`. Results are `passed`,
`failed`, `interrupted` or `observed`. Assessments are `accepted`, `limited`
or `superseded`. The page lists every entry under Technical reference, keeps
failed and superseded entries visible, and links stage and outcome proof by
ID.

With `--hosted`, the renderer rejects links the audience cannot open: local
paths, `file:` URLs, `localhost`, `.local` hosts, and loopback or private
addresses. Replace them with accessible links, or keep the receipt private
and include sanitized literal `output` sufficient for the displayed verdict.
Never put secrets or unapproved private content in output that will be
hosted.

## Decisions

Pending questions in priority order. Each has a stable `id`, `text` and
`recommendation`. Optional: `task_ids` naming rows that exist in `tasks`
(name unassigned work in the text instead), `unblocks` describing what an
answer enables, `discussion` with the authoritative conversation's
`owner_id`, readable `label` and `href` (empty when no link exists), and
`requires_human: true` when only the user can answer a native gate in that
conversation. `requires_human` belongs on the decision, beside `discussion`,
and needs a discussion owner. A decision without `discussion` routes to the
coordinator link in [presentation](#presentation).

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

## Presentation

Where the page lives and how a reader talks back. All fields are optional:

- `destination`: the chosen destination ID from saved `artifacts` facts or
  a sourced session-local observation, or `local`. This records a capability,
  not publication permission.
- `local_path`, `artifact_id`, `artifact_url`: the rendered file and the
  hosted copy, if any.
- `coordinator_href`: a link back to the producer's conversation. Copied
  questions and decisions without their own discussion route point here.
- `interaction`: one sentence on the configured comment or message mechanism,
  or that the reader pastes copied questions. Copying is not delivery.
- `auto_refresh`: boolean. `true` only when the destination verifiably
  reloads the updated page from the same URL; it embeds an HTML refresh at
  `monitoring.interval_seconds`. `false` or absent renders a static snapshot
  and the page says so.
- `hold`: the producer's note while the destination or disclosure is unresolved. The
  page does not show it; the producer keeps rendering held while it is set.

## Monitoring and refresh

`monitoring.interval_seconds` is a positive integer, required when
`presentation.auto_refresh` is `true`. The page then reloads at that
interval, through holds and after completion, and the header says so. A
reload discards open dialogs and drafted questions, runs nothing, and does
not change `updated_at`. The other monitoring fields (`mode`,
`last_checked_at`, `next_check_at`, `hold`, `unchanged_scans`) are the
producer's and are not shown.

## Approvals, follow-ups and runtime

Schema 2 sections the page lists under Technical reference:

- `approvals`: each with `id`, `scope`, `side_effects`, `receipt`,
  `granted_at`, `expires_at` (or `null`) and `state`: `active` (Active),
  `consumed` (Used), `expired` (Expired) or `revoked` (Revoked).
- `follow_ups`: work found beyond a row's target. Each has `id`, `text`,
  `from_task` naming a row in `tasks`, `owner` (a ticket or person, or `null`)
  and an optional `trigger`. A `null` owner shows "Needs an owner" and the
  overview counts those entries in a callout.
- `tasks[].runtime`: instances the row's owner created or holds. Each has
  `id`, `kind`, `ref` and `state`: `held` (In use), `released` or `retained`
  (Kept on purpose). A retained entry carries a `reason` and an `until`
  timestamp; when `until` is on or before `updated_at` the page marks it
  overdue and the overview counts it in a callout.

## IDs

Task, proof, decision, approval, follow-up and runtime IDs use letters,
numbers, underscores or hyphens and start with a letter or number. Keep them
stable between renders: the page uses them for selection, links, host
comments, and copied questions.

## Writing for the reader

The page's main readers are non-technical: a tester or an executive tracking
progress. Write `title`, `goal`, `work.summary`, and each decision's `text`,
`recommendation` and `unblocks` in plain language, without ticket jargon,
agent terms or proof IDs. Technical words belong in `reason`, `blocker`,
`next_action`, stage notes, owner handles and proof, which appear only when
a reader opens an item or decision.

## A minimal record

A thread tracking its child threads writes this, and the page shows three
rows with no stages, a snapshot header, and a static page notice:

```json
{
  "schema_version": 2,
  "run_id": "thread-42",
  "title": "Child threads of T-42",
  "presentation": {},
  "tasks": [
    {"id": "T-42-1", "title": "Index last week's meetings",
     "owner": {"id": "thread-42-1", "label": "Meeting index thread", "state": "active",
               "activity": "Reading the fourth of nine recordings."}},
    {"id": "T-42-2", "title": "Draft the release brief",
     "owner": {"id": "thread-42-2", "label": "Release brief thread", "state": "waiting"},
     "work": {"state": "waiting", "summary": "Waiting for the meeting index to finish.",
              "reason": "The brief cites the index."}}
  ]
}
```

The full shape, with every section populated, is
[`evals/dashboard-preview.json`](../evals/dashboard-preview.json).
