---
name: harness-discovery
description: >-
  Discovers what the current agent harness can do — independent threads or
  sessions, subagents, monitoring and wake-ups, skill loading, instruction files,
  structured questions, model choice, and HTML publishing destinations — plus the
  repository's ticket conventions, and saves sourced observations keyed by
  harness name. Load this when pstack-sync, dashboard, or another skill needs
  discovery, or when the user names /harness-discovery to refresh facts. Do not
  run it as the first step of a task that only needs one saved fact.
---

# Harness discovery

Save observed facts for any skill that needs them: `pstack-sync`, `dashboard`,
and skills that publish HTML. A caller loaded this skill, or the user named
`/harness-discovery`. Discovery describes what works; each caller decides what
to use. Do not start the caller's work from here.

## 1. Identify the harness and read saved discovery

Saved state lives in `<repository root>/.nthplusio-skills/`. First run
`python3 <this skill's folder>/scripts/state.py migrate`, which moves state saved
by earlier versions of these skills there, so a new entry never lands beside an
old file. A caller working in another repository,
such as pstack-sync in its skills repository, names that repository, and every
command below then takes `--root <that repository>`.
Identify the current harness's canonical product name from system context,
tool inventory, CLI version/help, or authoritative documentation. Use that exact
name as the `harnesses` key, for example `Amp` or `Claude Code`. A model name,
owner label, or execution host is not the harness name. The key's slug is the
key lowercased with each run of other characters turned into one hyphen
(`Claude Code` becomes `claude-code`). Callers may name a harness by either, so
two keys must not share a slug.

Then seed from the **registry**, the shared facts this skill ships in
`registry/<slug>.json`, one file per harness:

```bash
python3 <this skill's folder>/scripts/state.py seed --harness '<discovered name>'
```

The first line it prints decides how much of step 2 you do.

- `fresh`: the running harness still matches the entry's fingerprint. The entry
  is now in `discovery.json` (or an existing entry was kept). Inspect only the
  fields the entry's `limitations` say were not exercised, and the repository
  conventions, which are never in the registry.
- `stale`: the harness changed since the entry was written. Inspect every field
  in step 2, and after saving, run `state.py export --harness '<name>'` so the
  registry gains the change. Open a pull request with the exported file.
- `unverifiable`, or no registry entry: inspect as step 2 says, and `export`
  the result when the harness is one other installs will meet.

Reuse the saved key when it names this product. Record execution context separately.
If identity remains ambiguous after inspection, report the missing identity fact
and hold the entry rather than guessing from the model. Inspect other harnesses
only in their actual environments. Preserve their saved entries.

**Done when** the repository path, discovered harness name, execution context,
the seed result, and existing observations are known.

## 2. Inspect capabilities and repository conventions

A **work owner** is an independently addressable conversation or process that
can receive an assignment and be revisited. A **helper** performs bounded work
within an assignment. Classify tools by behavior, even if the harness calls
both sessions or subagents.

Use read-only tool inventories, schemas, CLI help, and authoritative docs.
Read repository guidance, issue templates, tracker configuration, and representative
tickets when accessible. Record established sources and layouts, not preferences.
An absent convention is a discovery result, not permission to adopt a default.

Fill [`assets/discovery.template.json`](assets/discovery.template.json).
Each harness entry records the observation time, inspected sources, and:

- Owners. Describe launch, inspect, message, collect, close/archive, and resume.
  Record shared, isolated, or selectable workspaces. Distinguish passive state
  and conversation reads from operations that wake owners or request reports.
  Describe pending user-input visibility, human-only gates, whether messages
  answer or queue, and direct conversation links or navigation by handle.
- Helpers. Describe invocation, collection, caller blocking, and follow-up, and
  whether a helper can be held to read-only (`readonly`). Record whether the
  harness has named subagent definitions with their own instructions and how
  one is dispatched (`definitions`), or `null` with how a generic helper is
  pointed at a definition file instead. Record the verified
  concurrent-invocation mechanism and its limits. A blocking
  batch may overlap helper calls while still holding the coordinator. Blocking
  alone establishes neither concurrency nor independent ownership.
- Monitoring. Describe notification coverage and lifetime, bounded waits with
  timeout arguments and caller behavior, and wake after the coordinator yields.
  Distinguish native notifications from owner-authored status messages. Keep
  inspection separate from completion collection. Record any authorization
  requirement and whether monitoring requires an active turn or manual resume.
- Skills. Describe loading and instruction propagation, where project and
  personal skills live (`locations`), how a running session picks up a
  changed skill (`reload`), and which frontmatter keys the harness reads and
  what any extra key such as `mode` means to it (`frontmatter`). Shared skill choices belong to setup, including any
  baseline required by repository/user guidance.
- Instructions. Name the files the harness loads into every session, user-wide
  (`instructions.user`) and per project (`instructions.project`).
- Questions. Describe the structured question tool, its limits, and when it may
  be used (`ask_user`), or `null` when questions go in the reply.
- Models. Describe how to run a helper or owner on a named model
  (`models.select`) and how to list the names this session accepts
  (`models.list`).
- Evidence. Describe file transfer and retention before owner closure. A message
  or commit ID does not transfer files between isolated environments.
- Artifacts. List usable destinations, update operations, audiences, and optional
  native comment/message interaction. Local HTML can be an option. In a remote
  environment, describe its supported user preview or portal. Use `null` for
  unavailable interaction. Record `auto_refresh` as a sourced description of
  supported embedded full-page reloads that retrieve updates from the same URL,
  or `null` when unavailable. Note embedding and caching limits, and record
  frame limits a page must work around, such as blocked clipboard writes or
  external fonts. Copyable questions need no messaging bridge.

Store operation descriptions with important arguments, not executable commands
to run from JSON. An inspected unavailable operation is `null` with a limitation.
A missing field is undiscovered and requires inspection. Preserve relevant existing
observations and update facts that are missing or contradicted. Record uncertainty
in limitations rather than representing an unverified feature as supported.

Discovery may write its repository report. It grants no permission to launch
probe owners, publish artifacts, create schedules/subscriptions, or mutate trackers.
Keep credentials, private receipts, chosen storage paths, shared-action approvals,
run cadence, and current ticket assignments out of discovery.

**Done when** each capability has a sourced description or explicit limitation,
and repository ticket conventions or their absence are recorded.

## 3. Save and validate observations

Merge only the current harness entry and changed repository facts into the saved
report. Preserve unrelated entries and user edits. Keep the report in the repository
so later setup can reuse it. Sanitize private context and paths before saving.
For observations made now, capture `observed_at` from the environment clock with
`python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())'`.
For reused observations, preserve their recorded time. A date from conversation
context is not a measured observation time.
A registry entry holds only what is true of the harness itself: no repository
URL, no local path, no choice a team made. `export` scrubs the repository path;
you remove the rest before the pull request.

Run:

```bash
python3 <this skill's folder>/scripts/state.py check discovery
python3 <this skill's folder>/scripts/state.py resolve --harness '<discovered name>'
```

The checker validates the observation format, not live tool execution. The second
command prints the entry a caller reads, with its key and slug.
Report the discovered name, saved path, and material limitations. When called
by another skill, return those facts to it without starting its work yourself.

**Done when** saved discovery passes the checker and matches the inspected sources.
