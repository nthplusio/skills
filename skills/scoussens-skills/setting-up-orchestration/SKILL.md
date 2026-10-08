---
name: setting-up-orchestration
description: >-
  Discovers an agent harness's work-owner, subagent, evidence-transfer, skill,
  and artifact capabilities and saves a local JSON configuration. Use when
  asked to set up orchestration, configure sessions or teammates for coordinated
  work, or repair a missing or unsuitable orchestration configuration. Use
  running-orchestration to coordinate an actual run, not this skill alone.
---

# Setting up orchestration

Write the harness configuration that `running-orchestration` reads. Record
usable capabilities, not assumptions based on another harness's vocabulary.

## 1. Locate the configuration

Use an explicitly supplied configuration path or `ORCHESTRATION_CONFIG` first.
Otherwise use:

- Linux/macOS: `${XDG_CONFIG_HOME:-$HOME/.config}/nthplusio/orchestration/<harness-id>/config.json`.
- Windows: `%APPDATA%\nthplusio\orchestration\<harness-id>\config.json`.

Resolve the path for this machine. Keep the configuration outside Git and the
installed skill directory. If the user chooses a path inside a worktree,
exclude it locally and confirm it is neither tracked nor staged. Preserve
unrelated configuration and user changes.

Read a saved configuration before changing it. Update only capabilities whose
record is missing or contradicted by the available tools or environment. A
different project or a new run is not itself a reason to redo setup.

**Done when** the configuration path and harness identity are known, and a
saved configuration has been read if one exists.

## 2. Discover capabilities

A **work owner** is an independently addressable conversation or process that
can receive an assignment and be revisited during the run. A **helper** performs
bounded work within an owner's assignment. A harness may call either one a
thread, session, teammate, subagent, or subprocess. Classify it by what it does.

Inspect tool inventories, tool schemas, CLI help, and authoritative harness
documentation. Use read-only inspection to resolve facts yourself. Do not
create disposable owners or publish artifacts merely to discover capabilities.

Record the actual supported operations in
[`assets/harness-config.template.json`](assets/harness-config.template.json):

- Owners: launch, inspect, message, collect results, close/archive, and resume.
  Record whether their workspaces are shared, isolated, or selectable.
- Helpers: invocation and collection, whether they block their caller, and
  whether they can receive follow-up messages. A blocking helper is not an
  independently addressable owner.
- Skills: loading and the supported way to pass relevant instructions to an
  owner or helper. Record baseline shared skills when the user's guidance
  establishes them. Neither orchestration skill belongs in that list.
- Evidence: transfer and retention before closure. A message or commit ID
  alone does not transfer files between isolated environments.
- Artifacts: available local presentation and supported hosting destinations,
  how each updates the same artifact, and who can view it. Include only usable
  destinations, not every service the harness might support elsewhere. In each
  destination's optional `interaction` field, describe supported comments,
  agent-message links, or other native interaction. Use `null` when unavailable.
  The template's copyable questions remain available without a messaging bridge.

An operation is a description of the verified tool or command and its important
arguments, not executable configuration. Use `null` for an unsupported operation
and explain the consequence in `limitations`. Never put credentials, current
tickets, shared-action approvals, or a chosen run destination in this file.

For example, an Amp configuration may map independently addressable owners to
`create_thread` and helpers to `Task`. Verify the tools available in the
session, including how results and closure work; this example grants no access
or permission. A different harness needs its own mapping.

**Done when** each needed capability has a supported operation or an explicit
limitation. Unsupported ownership must remain visible, not be disguised as
helper-based orchestration.

## 3. Save and check the JSON

Fill the template with discovered values. Use an absolute local `run_root`
outside repositories for per-run status, dashboards, retained proof, and
handoffs. Choose a user-owned state directory, not a shared runtime directory.
Use a separate run subdirectory for each coordinator.

Save the JSON at the path from step 1, then run:

```bash
python3 <this skill's folder>/scripts/check_config.py <config.json>
```

The checker validates the file contract, not whether tools can perform the
operations. Confirm the operation descriptions against the inventory or docs
you inspected. If setup exposes a missing capability needed for the user's
goal, name that limitation and the smallest decision needed to proceed.

**Done when** the stored JSON passes the checker and its operation descriptions
match the harness. Reply with its path and material limitations. The runner
reads this file; it does not reconstruct configuration from chat history.
