---
name: orchestration-discovery
description: >-
  Discovers the current agent harness's orchestration capabilities and repository
  ticket conventions, and saves observations by harness name. Use for
  /orchestration-discovery, missing discovery during orchestration setup, or
  refreshing capability facts after the harness or execution context changes.
---

# Orchestration discovery

Save observed facts for `orchestration-setup`. Discovery describes what works.
Setup interviews the user about what to use. `orchestration-run` coordinates work.

## 1. Identify the harness and read saved discovery

Use `<repository-root>/.orchestration/discovery.json` unless the user supplies
another repository discovery path. Read the existing file before updating it.
Identify the current harness's canonical product name from system context,
tool inventory, CLI version/help, or authoritative documentation. Use that exact
name as the `harnesses` key, for example `Amp` or `Claude Code`. A model name,
owner label, or execution host is not the harness name.

Reuse the saved key when it names this product. Record execution context separately.
If identity remains ambiguous after inspection, report the missing identity fact
and hold the entry rather than guessing from the model. Inspect other harnesses
only in their actual environments. Preserve their saved entries.

**Done when** the repository path, discovered harness name, execution context,
and existing observations are known.

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
  Record shared, isolated, or selectable workspaces. Describe pending user-input
  visibility, human-only gates, whether messages answer or queue, and direct
  conversation links or navigation by handle.
- Helpers. Describe invocation, collection, caller blocking, and follow-up.
  Record the verified concurrent-invocation mechanism and its limits. A blocking
  batch may overlap helper calls while still holding the coordinator. Blocking
  alone establishes neither concurrency nor independent ownership.
- Monitoring. Describe notification coverage and lifetime, bounded waits with
  timeout arguments and caller behavior, and wake after the coordinator yields.
  Keep inspection separate from completion collection. Record any authorization
  requirement and whether monitoring requires an active turn or manual resume.
- Skills. Describe loading and instruction propagation. Shared skill choices
  belong to setup, including any baseline required by repository/user guidance.
- Evidence. Describe file transfer and retention before owner closure. A message
  or commit ID does not transfer files between isolated environments.
- Artifacts. List usable destinations, update operations, audiences, and optional
  native comment/message interaction. Local HTML can be an option. In a remote
  environment, describe its supported user preview or portal. Use `null` for
  unavailable interaction. Copyable questions need no messaging bridge.

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

Run:

```bash
python3 <this skill's folder>/scripts/check_discovery.py <discovery.json>
```

The checker validates the observation format, not live tool execution.
Report the discovered name, saved path, and material limitations. When called
by setup, return those facts to setup without starting its interview yourself.

**Done when** saved discovery passes the checker and matches the inspected sources.
