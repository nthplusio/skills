# Amp agent runtime adapter

Runs the `orchestrate` set's spawn, wait, and handoff loop on Amp orb threads through the `amp` CLI. One worker is one thread; one run is one user turn in that thread. The adapter implements the `AgentRuntime` and `ModelCatalog` interfaces in [`../interface.ts`](../interface.ts) and carries the Amp versions of the set's two ports.

## Files

| Path | Role |
| --- | --- |
| `agent-runtime.ts` | `AgentRuntime` over the `amp` CLI. |
| `models.ts` | `ModelCatalog` of Amp agent modes. |
| `agent-runtime/scripts/core/runtime.ts` | Facade with the Cursor SDK's static `Agent` shape, built over the runtime, so the ported files keep upstream's call sites. Listed in the `agent-runtime` port, so the sync installs it beside the port files. |
| `agent-runtime/scripts/{core/agent-manager,cli/task,cli/inspect,cli/forensics,tools/nudge-root,tools/probe-models}.ts` | The `agent-runtime` port: upstream files with their SDK calls routed through the facade. |
| `models/scripts/models.ts` | The `models` port: upstream's catalog shape over Amp modes. |
| `__tests__/` | `bun test` against a fake `amp` on `PATH`: the runtime (`agent-runtime.test.ts`), the facade's `Agent.create`, `send`, `wait` round trip and its id checks (`runtime.test.ts`), the operator gates and the `selfAgentId` guard (`gates.test.ts`), and `models --check` through the port's `tools/probe-models.ts` (`probe-models.test.ts`; upstream's test of that tool calls the SDK signature and is ignored by the set). |

The sync installs each port file at its path under `<skills>/orchestrate/scripts/`; `runtime.ts` finds `agent-runtime.ts` and `models.ts` at `<skills>/pstack-sync/adapters/amp/` beside it (or in the pack layout, or where `ORCHESTRATE_AMP_RUNTIME_DIR` points).

## Operation to command

| Interface | Command | Notes |
| --- | --- | --- |
| `spawn({name, repoUrl, startingRef, model, prompt})` | `amp -ox --project <repoUrl> --visibility private --no-archive-after-execute --title <name> -l orchestrate [-m <model>]`, prompt on stdin | Returns in about 3 s with the thread URL; the thread id is the agent id, the run id is `m0`. The prompt is prefixed with an instruction to `git fetch origin <startingRef> && git checkout <startingRef>`, because an orb opens the project's default branch. `model: inherit` passes no `-m`. |
| `getRun(agentId, runId)` | `amp threads export <id>` | Terminal when `meta.lastKnownAgentState.state` is `idle` and the last message is an assistant message with text after the run's start. `working`, `streaming`, `running_tools`, and any unknown state count as running. |
| `wait(run)` | `amp threads export <id>`, polled | `finalText` is the last assistant text of the run, verbatim; `branches` is the `## Branch` line of that text, or empty; `durationMs` spans the run's user message to its last assistant message. Every 60 s it also runs `amp threads search "id:<id> archived:true" --json` so a thread archived by another process reads as cancelled. After `ORCHESTRATE_WAIT_TIMEOUT_SEC` (default 7200) without a terminal state it returns `status: "error"` with an `error` message naming the thread, which may still be running. |
| `stream(run)` | `amp threads export <id>`, polled | Yields assistant text deltas, `tool_use` blocks as `tool_call`, and a final `status`; shares `wait`'s poller, so it has the same archived check and deadline (the final status is then `error` with the message). |
| `cancel(agentId, runId)` | `amp threads archive <id>` | Archiving is the only stop the CLI offers; the orb may finish its current turn. |
| `sendFollowUp(agentId, text)` | `amp threads continue <id> -ox`, text on stdin | The new run id is the message index the text lands at, read from an export just before. A message sent while the thread is working queues behind the current turn. |
| `list({limit})` | `amp threads list --json --limit <n>` | `title` becomes the agent name, `updated` the timestamp; `kickoff` adopts a running root planner by exact title `<rootSlug>-root`. |
| `latestRun(agentId)` | `amp threads export <id>` | The last user text message and its status. User-role messages Amp injects itself (text starting `<integration_hint>`) do not count as run starts. |
| `agentUrl(agentId)` | none | `https://ampcode.com/threads/<id>`; `ORCHESTRATE_AMP_URL` overrides the origin. |
| `models()` | `amp plugins show-agent-options --json` | `inherit`, `low`, `medium`, `high`, `ultra`, plus any `agentModes`, `modes`, or `pluginModes` the payload names. The CLI does not list plugin modes today, so the five built-ins are what you get. |
| `probe(model)` | none | True when `model` is in `models()`. Nothing is spawned. |

Run ids are `m<index>`, the index of the user message that started the run in the thread's message list. `state.json` stores them beside the thread id, so `recoverRunning`, `cancel`, `tail`, and `inspect` reattach after a restart.

## Where the thread id comes from

A thread id exists only after `amp -ox` runs, but upstream builds the prompt between `Agent.create` and `agent.send` and puts the agent id in it. Until `send`, the facade reports `agent.agentId` as `$AMP_THREAD_ID`, the environment variable every orb sets to its own thread id, and `send` appends a note telling the agent to expand it (`echo $AMP_THREAD_ID`), including into `plan.selfAgentId`. After `send`, `agentId` is the real id and that is what `state.json` records.

## Auth

The `amp` CLI's login. Run `amp login` once on the machine that runs the loop; there is no API key variable. A missing login surfaces as an `AgentRuntimeError` (upstream's `CursorAgentError` name) from `kickoff` or `spawn`, exit code 2.

## Settings

All through environment variables, read when the runtime is created.

| Variable | Default | Meaning |
| --- | --- | --- |
| `ORCHESTRATE_AMP_BIN` | `amp` | The CLI binary. Tests point it at a fake. |
| `ORCHESTRATE_AMP_POLL_MS` | `10000` | Poll interval for `wait` and `stream`. |
| `ORCHESTRATE_AMP_MAX_EXPORT_FAILURES` | `30` | Consecutive failed exports tolerated before `wait` or `stream` throws; the thread keeps running on the server while the local view is dark. |
| `ORCHESTRATE_AMP_ARCHIVED_CHECK_MS` | `60000` | How often `wait` and `stream` check whether another process archived the thread. |
| `ORCHESTRATE_AMP_VISIBILITY` | `private` | Thread visibility. |
| `ORCHESTRATE_AMP_LABEL` | `orchestrate` | Label on every spawned thread; empty disables. |
| `ORCHESTRATE_AMP_URL` | `https://ampcode.com` | Web origin for `agentUrl`. |
| `ORCHESTRATE_AMP_COMMAND_TIMEOUT_MS` | `180000` | Wall-time cap for one CLI invocation. |
| `ORCHESTRATE_WAIT_TIMEOUT_SEC` | `7200` | Longest `wait` or `stream` polls a run that has not ended before returning `error`; the thread is not stopped. |
| `ORCHESTRATE_AMP_RUNTIME_DIR` | unset | Directory holding `agent-runtime.ts` and `models.ts` when neither layout applies. |
| `ORCHESTRATE_REPO_URL` | unset | The repository the operator runs the loop for. `plan.repoUrl` must match it; unset means unchecked. See Security. |
| `ORCHESTRATE_MEASUREMENTS` | unset | `1` lets the loop run planner-authored measurement commands when plan.json also opts in; anything else keeps them off. See Security. |

## Security

The OS-3 review (`.amp/in/artifacts/orchestrate-sync/os-3-security-review.md`) named four concerns. The port settles them as follows.

1. **Measurement commands.** `tasks[].measurements[].command` runs through `bash -c`. plan.json is written by the root planner, an LLM, and with `syncStateToGit` by anyone who can push the state branch, so plan.json alone cannot turn the commands on. They run only when the operator sets `ORCHESTRATE_MEASUREMENTS=1` in the environment of the process that runs the loop **and** plan.json sets `"measurementsEnabled": true` at the top level (`measurementGate` in `agent-runtime/scripts/core/runtime.ts`). Without the variable each handoff logs `skipped N declared measurement(s): ORCHESTRATE_MEASUREMENTS is unset` to `attention.log` and proceeds; with the variable but no opt-in the line names the missing key. `PlanSchema` is strict and lives outside the port, so `agent-manager.ts` lifts `measurementsEnabled` before parsing and writes it back on every save. The schema change itself belongs in `schemas.ts` and the planner docs; see Follow-ups.
2. **Clone origin.** `plan.repoUrl` must name the repository in `ORCHESTRATE_REPO_URL`, which only the operator sets (`checkRepoUrlAgainstOrigin` in `runtime.ts`). The workspace's `remote.origin.url` is not a fallback, because whoever edits plan.json can also run `git remote set-url`. A mismatch fails `AgentManager.load` with a `PlanValidationError`. When the variable is unset the loop logs one attention line, spawns proceed (an orb project is something the signed-in user already has access to), and the measurement clone stays refused, so measurements need both variables.
3. **Operator mode and file uploads.** `cli/comments.ts` and `cli/util.ts` are not port files, so the port cannot change them; the workspace confinement stays as upstream wrote it and the operator-mode lift stays reachable. See Follow-ups.
4. **`@cursor/sdk` dependency.** Every SDK call is routed through the facade. The port carries `scripts/package.json` and its lockfile without `@cursor/sdk`, and the set's seed transforms redirect the two remaining `import type` lines in `schemas.ts` and `core/handoff.ts` to the facade, so the installed tree typechecks clean with no SDK on disk.

## Limits

- Polling, not streaming: text appears in `tail` and `inspect` up to one poll interval (10 s) late, and a finished run is noticed within one interval.
- No mode listing: the CLI accepts plugin modes by key, but no command lists them, so `models` shows the five built-ins and `models --check` can only confirm those.
- `cancel` archives; it does not interrupt a turn in progress.
- A follow-up to a working thread is queued, not delivered mid-turn; `nudge-root.ts --wait-idle` is the safer form.
- `list` reports the thread's last-updated time where upstream expected a creation time; kickoff's 30-minute adoption window is measured from that.
- `run.conversation()` is unsupported; `supports("conversation")` is false.

## Running the loop on Amp

In the installed skill directory (`<skills>/orchestrate`):

```bash
cd scripts && bun install && cd ..
amp login                      # once per machine
bun scripts/cli.ts models      # the modes a plan may name
bun scripts/cli.ts kickoff "<goal>" --repo https://github.com/<owner>/<repo> [--model high]
```

`kickoff` spawns the root planner thread and prints `{ agentId, runId, status, url }`. The root planner writes `plan.json` and drives `bun scripts/cli.ts run --root <workspace>` from its orb; a local run of the same loop against a workspace with a `plan.json` is

```bash
ORCHESTRATE_REPO_URL=https://github.com/<owner>/<repo> bun scripts/cli.ts run <workspace>
```

which spawns one thread per ready task, waits, and writes `<workspace>/handoffs/<task>.md`. Add `ORCHESTRATE_MEASUREMENTS=1` only when you have read the `measurements[].command` lines in that plan.json and want the loop to run them.

Tests: `bun test` in this directory (`adapters/amp`), against `__tests__/fake-amp/amp`.

## Follow-ups outside the port

- Add `measurementsEnabled` (boolean, default false) to `PlanObjectSchema` in `schemas.ts`, regenerate `schemas/plan.schema.json`, and mention it in `references/planner.md`.
- Decide operator mode in `cli/util.ts` and `cli/comments.ts`: keep the workspace confinement on regardless of `~/.orchestrate/operator-mode`, or make the flag something the orb user cannot create.
- `prompts/root.md` says "Your thread id is `{{agentId}}`"; on Amp the value is `$AMP_THREAD_ID` plus the facade's note. A dialect row could phrase that directly.
