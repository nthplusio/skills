---
name: setting-up-orchestration
description: >-
  Discovers an agent harness's work-owner, helper, monitoring, evidence-transfer,
  skill, and artifact capabilities, confirms storage choices, and saves a local
  JSON configuration. Use when asked to set up orchestration, configure sessions
  or teammates for coordinated work, or repair a missing or unsuitable configuration.
  Use running-orchestration to coordinate an actual run, not this skill alone.
---

# Setting up orchestration

Write the harness configuration that `running-orchestration` reads. Discover
tool facts yourself; confirm the user's choices before saving new settings.

## 1. Read existing settings

Use personal settings by default. An explicitly selected project/team
configuration takes precedence for that context without changing personal
defaults. Locate the selected file through a supplied path or
`ORCHESTRATION_CONFIG` first. Otherwise look at:

- Linux/macOS: `${XDG_CONFIG_HOME:-$HOME/.config}/nthplusio/orchestration/<harness-id>/config.json`.
- Windows: `%APPDATA%\nthplusio\orchestration\<harness-id>\config.json`.

These paths are proposals when no settings exist, not permission to save them.
Resolve paths for this machine and read the selected file if available. Preserve
unrelated settings and user changes.

Reuse saved choices unless the user changes them or says they were never
confirmed. Update only capability facts that are missing or contradicted by
the available tools or environment. A different project or new run alone does
not require setup again; an explicit override selects that context's settings.

**Done when** the harness and selected configuration source are known, existing
settings have been read, and any unconfirmed storage choices are identified.

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
  Record whether their workspaces are shared, isolated, or selectable. Describe
  how `inspect` exposes pending user questions and human-only input gates, and
  whether `message` can answer a question or merely queues behind its gate.
  Record supported direct conversation links or navigation by owner handle,
  and any caller-blocking or unavailable question-routing behavior in
  `limitations`. These are tool facts, not permission to answer for the user.
- Helpers: invocation and collection, whether they block their caller, and
  whether they can receive follow-up messages. In `invoke`/`collect`, describe
  the verified concurrent-invocation mechanism and any known limits, including
  whether the caller waits for a batch. Record unavailable or unverified
  concurrency in `limitations`. Blocking the caller does not establish whether
  helper calls can overlap, and a blocking helper is not an independent owner.
- Monitoring: in `monitoring.notifications`, describe owner-state/input events
  or messages that reach the coordinator, their coverage, and whether they
  interrupt a wait or require an active conversation. In `monitoring.wait`,
  describe a bounded event wait or timed pause, its timeout arguments, whether
  it blocks the caller, and how the coordinator continues afterward. Keep status
  inspection separate from completion collection. In `monitoring.wake`, describe
  any supported mechanism that resumes the coordinator after its turn ends,
  including lifetime and authorization requirements. Notifications alone do not
  guarantee periodic inspection. Record unavailable operations as `null` and
  explain whether monitoring requires an active coordinator or manual resume.
  Discovering a wake mechanism grants no permission to create a schedule or
  subscription. Cadence and the selected monitoring mode belong to each run.
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
Repository ticket definitions and tracker choices belong to the runner's ticket
discovery, not this harness-wide configuration.

For example, an Amp configuration may map independently addressable owners to
`create_thread` and helpers to `Task`. Verify the tools available in the
session, including how results and closure work; this example grants no access
or permission. A different harness needs its own mapping.

Version 1 configurations without `monitoring` remain structurally valid. When
a run needs repeated inspection, discover and save this missing capability
section once using the existing confirmed storage choices. Missing facts are
undiscovered; an explicit `null` means the operation is unavailable.

**Done when** each needed capability has a supported operation or an explicit
limitation. Unsupported ownership must remain visible, not be disguised as
helper-based orchestration.

## 3. Confirm storage choices

Separate discovered capabilities from preferences. Ask one focused question
proposing the configuration path and `run_root` together when either is still
unconfirmed. Wait for confirmation before writing configuration or run files.
Explain that `run_root` holds local status, dashboard files, retained proof,
and handoffs. Prefer an absolute user-owned state directory, with a separate
run subdirectory for each coordinator. A path the user already supplied or
confirmed needs no repeat question.

Keep this machine's configuration and run files outside Git and the installed
skill directory. If a chosen path is inside a worktree, exclude it locally and
verify it is neither tracked nor staged. The runner asks separately where to
present each run's dashboard; a working directory does not select a host or
authorize publication.

Conversation recovery follows the harness's own rules. These local files are
working state, not a backup promised to other machines or harnesses.

**Done when** both paths are confirmed and any local exclusion is established.

## 4. Save and check the JSON

Fill the template with discovered capabilities and the confirmed `run_root`.

Save the JSON at the path from step 1, then run:

```bash
python3 <this skill's folder>/scripts/check_config.py <config.json>
```

The checker validates the file contract, not whether tools can perform the
operations. Confirm the operation descriptions against the inventory or docs
you inspected. If setup exposes a missing capability needed for the user's
goal, name that limitation and the smallest decision needed to proceed.

**Done when** the stored JSON passes the checker and its operation descriptions
match the harness. Reply with both paths and material limitations. Distinguish
the structural check from operational proof. The runner reads the resulting JSON.
