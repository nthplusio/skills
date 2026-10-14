# Amp agent runtime adapter

Runs the `orchestrate` set's spawn, wait, and handoff loop on Amp orb threads through the `amp` CLI. One worker is one thread; one run is one user turn in that thread. The adapter implements the `AgentRuntime` and `ModelCatalog` interfaces in [`../interface.ts`](../interface.ts) and carries the Amp versions of the set's two ports.

## Files

| Path | Role |
| --- | --- |
| `agent-runtime.ts` | `AgentRuntime` over the `amp` CLI. |
| `models.ts` | `ModelCatalog` of Amp agent modes. |
| `agent-runtime/scripts/core/runtime.ts` | Facade with the Cursor SDK's static `Agent` shape, built over the runtime, so the ported files keep upstream's call sites; also the operator gates (`measurementGate`, `checkRepoUrlAgainstOrigin`) and the id checks (`requireThreadId`, `resolveSelfAgentId`). Listed in the `agent-runtime` port, so the sync installs it beside the port files. |
| `agent-runtime/scripts/core/andon-file.ts` | `FileAndonSource`: the stop signal read from `<workspace>/andon.json` when the root planner has no Slack kickoff. Also a port-added file. |
| `agent-runtime/scripts/{core/agent-manager,cli/task,cli/inspect,cli/forensics,tools/nudge-root,tools/probe-models}.ts` | The `agent-runtime` port: upstream files with their SDK calls routed through the facade. |
| `agent-runtime/scripts/tools/dashboard.ts` | Port-added: writes a `dashboard` skill status record from a run workspace and renders it. See Dashboard. |
| `models/scripts/models.ts` | The `models` port: upstream's catalog shape over Amp modes. |
| `__tests__/` | `bun test` against a fake `amp` on `PATH`: the runtime (`agent-runtime.test.ts`), the facade's `Agent.create`, `send`, `wait` round trip and its id checks (`runtime.test.ts`), the operator gates and the `selfAgentId` guard (`gates.test.ts`), and `models --check` through the port's `tools/probe-models.ts` (`probe-models.test.ts`; upstream's test of that tool calls the SDK signature and is ignored by the set), the dashboard producer against a fixture workspace and the real renderer (`dashboard.test.ts`), the doctor's checks with a recording command runner (`doctor.test.ts`), and the idle-planner follow-up after `run` (`planner-nudge.test.ts`). |

The sync installs each port file at its path under `<skills>/orchestrate/scripts/`; `runtime.ts` finds `agent-runtime.ts` and `models.ts` at `<skills>/pstack-sync/adapters/amp/` beside it, or under the newest `pstack-sync@<hash>/adapters/amp/` sibling in Amp's skill cache, where each skill is installed as `<name>@<hash>` (or in the pack layout, or where `ORCHESTRATE_AMP_RUNTIME_DIR` points).

## Operation to command

| Interface | Command | Notes |
| --- | --- | --- |
| `spawn({name, repoUrl, startingRef, model, prompt})` | `amp -ox --project <repoUrl> --visibility private --no-archive-after-execute --title <name> -l orchestrate [-m <model>]`, prompt on stdin | Returns in about 3 s with the thread URL; the thread id is the agent id, the run id is `m0`. The prompt is prefixed with an instruction to `git fetch origin <startingRef> && git checkout <startingRef>`, because an orb opens the project's default branch. `model: inherit` passes no `-m`. |
| `getRun(agentId, runId)` | `amp threads export <id>` | Terminal when `meta.lastKnownAgentState.state` is `idle` and the last message is an assistant message with text after the run's start. `working`, `streaming`, `running_tools`, and any unknown state count as running. |
| `wait(run)` | `amp threads export <id>`, polled | `finalText` is the last assistant text of the run, verbatim; `branches` is the `## Branch` line of that text, or empty; `durationMs` spans the run's user message to its last assistant message. Every 60 s it also runs `amp threads search "id:<id> archived:true" --json` so a thread archived by another process reads as cancelled. After `ORCHESTRATE_WAIT_TIMEOUT_SEC` (default 7200) without a terminal state it returns `status: "error"` with an `error` message naming the thread, which may still be running. |
| `stream(run)` | `amp threads export <id>`, polled | Yields assistant text deltas, `tool_use` blocks as `tool_call`, and a final `status`; shares `wait`'s poller, so it has the same archived check and deadline (the final status is then `error` with the message). |
| `cancel(agentId, runId)` | `amp threads archive <id>` | The CLI has no command that stops a running turn, so `cancel` archives the thread and marks the run cancelled while any turn in progress finishes on its own. |
| `sendFollowUp(agentId, text)` | `amp threads continue <id> -ox`, text on stdin | The new run id is the message index the text lands at, read from an export just before. A message sent while the thread is working queues behind the current turn. |
| `list({limit})` | `amp threads list --json --limit <n>` | `title` becomes the agent name, `updated` the timestamp; `kickoff` adopts a running root planner by exact title `<rootSlug>-root`. |
| `latestRun(agentId)` | `amp threads export <id>` | The last user text message and its status. User-role messages Amp injects itself (text starting `<integration_hint>`) do not count as run starts. |
| `agentUrl(agentId)` | none | `https://ampcode.com/threads/<id>`; `ORCHESTRATE_AMP_URL` overrides the origin. |
| `models()` | `amp plugins show-agent-options --json` | `inherit`, `low`, `medium`, `high`, `ultra`, plus any `agentModes`, `modes`, or `pluginModes` the payload names. The CLI does not list plugin modes today, so the five built-ins are what you get. |
| `probe(model)` | none | A name check against `models()`, not a live call: nothing is spawned and no turn runs, so `models --check` confirms the name is one the CLI lists, not that the mode works for this account. |

Run ids are `m<index>`, the index of the user message that started the run in the thread's message list. `state.json` stores them beside the thread id, so `recoverRunning`, `cancel`, `tail`, and `inspect` reattach after a restart.

## Where the thread id comes from

A thread id exists only after `amp -ox` runs, but upstream builds the prompt between `Agent.create` and `agent.send` and puts the agent id in it. Until `send`, the facade reports `agent.agentId` as `$AMP_THREAD_ID`, the environment variable every orb sets to its own thread id, and `send` appends a note telling the agent to expand it (`echo $AMP_THREAD_ID`). After `send`, `agentId` is the real id and that is what `state.json` records.

The root prompt tells the root planner to set `plan.selfAgentId` to the value of its `AMP_THREAD_ID` variable. If the literal `$AMP_THREAD_ID`, an empty string, or anything else that is not a thread id lands in plan.json, the loop treats `selfAgentId` as unset (`resolveSelfAgentId`): one attention line says so, children record `parentAgentId: null`, Slack footers omit the link, and `nudge-root.ts` and `kill-tree --agent-id` refuse the placeholder with the same advice.

## Auth

The `amp` CLI's login (`amp login` once on the machine that runs the loop) or an access token in `AMP_API_KEY`, which orbs set and the CLI honours. A missing login surfaces as an `AgentRuntimeError` (upstream's `CursorAgentError` name) from `kickoff` or `spawn`, exit code 2.

## Andon

Upstream raises Andon through Slack: the root polls the kickoff message for `:rotating_light:`, and `andon raise` / `andon clear` post to Slack, the only `AndonSource` upstream ships. On Amp a root planner whose plan has a Slack kickoff keeps that behaviour. A root planner without one polls `<workspace>/andon.json` instead (`FileAndonSource`): writing `{"reason": "<why>", "raisedBy": "<who>"}` there raises Andon, deleting the file clears it, and the poller writes the cached state children read through git as before. `andon raise` and `andon clear` live in `cli/andon.ts`, which is not a port file, so they still need Slack; see Follow-ups.

## Dashboard

`tools/dashboard.ts` turns a run workspace into the one-page status view the `dashboard` skill renders, for the people following the run who do not read `state.json`:

```bash
bun scripts/tools/dashboard.ts <workspace> [--out <html>] [--hosted] [--status-only]
```

It reads `<workspace>/plan.json`, `state.json`, `handoffs/` and `attention.log`, writes `<workspace>/status.json` as a schema 2 record of the skill's `references/status-contract.md`, and runs the skill's `scripts/render_dashboard.py` on it, to `--out` (default `<workspace>/dashboard.html`). The renderer's `PASS: rendered <path>` line is the success output; when it rejects the record, the tool prints the renderer's stderr and exits 1, leaving `status.json` in place and any earlier page untouched. `--status-only` writes the record and skips the render; `--hosted` passes the renderer's hosted link check and leaves local handoff links out of the record, keeping the handoff lines as literal output.

The record, per the contract and the producers table in the skill's `SKILL.md`:

| Record field | Source |
| --- | --- |
| `run_id`, `title`, `goal` | `rootSlug` plus `plan.selfAgentId` when it is a thread id; `plan.summary`, else the `rootSlug`; `plan.goal`. |
| `tasks[]` | One row per task in `state.json`, in order. `id` is the task name, `title` the first sentence of its `scopedGoal`. |
| `owner` | The task's thread: `id` is `agentId` (`unassigned-<task>` before a spawn), `label` the task name, `href` from `agentUrl`, `state` from the task status: `pending` → `waiting`, `running` → `active`, `handed-off` → `complete`, `error` → `blocked`, `cancelled` and `pruned` → `closed`. `location` is the branch; `handoff` and `last_checked_at` come from the handoff file and `lastUpdate`. |
| `work` | From the handoff: `Status success` and a verifier's verified verdicts → `delivered`; `partial` and `verifier-failed` → `needs_decision`; `blocked` and `verifier-blocked` → `blocked`; no Status line → `unknown`. A running task is `working`, an unspawned one `ready` or `waiting` on its `dependsOn`, an `error` row `blocked`, `cancelled` and `pruned` rows `cancelled`. |
| `milestones` | `defined` from the plan entry; `pr_readiness` and `code_publication` from the handoff and its `## Branch` line (neither is requested for a verifier, whose verdict is its `verification` stage; an `openPR` task without a `prNumber` stays pending); `verification` from `state.json`'s `verification` or a planned verifier; `deployment` and `business_acceptance` not requested, because the loop stops at the branch. |
| `evidence[]` | One entry per handoff file: its Status, Verification and Branch lines as the note and literal output, the file as the link, `passed` for success and verified verdicts, `failed` for blocked, error and `verifier-failed`, `interrupted` for `verifier-blocked`, `observed` otherwise. |
| `decisions[]` | An uncleared `state.andon` is the one decision, routed to the root planner thread. `plan.json` carries no other decision field. |
| `history[]` | The last 50 `attention.log` lines, or `state.attention` when the log is missing. |
| `updated_at`, `contract_version`, `presentation` | Now; the renderer's `--contract-version`; `local` with the page path and the root planner thread as `coordinator_href`. `closed_at` is never set: no plan field says the run is done. |

The dashboard skill is found the way `runtime.ts` finds the adapter: `ORCHESTRATE_DASHBOARD_DIR` when set, else `<skills>/dashboard` beside this skill, else the newest `dashboard@<hash>` sibling in Amp's skill cache, else the pack layout relative to the file. The renderer runs as `python3 -I <dir>/scripts/render_dashboard.py` with an argument array, never a shell line.

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
| `ORCHESTRATE_DASHBOARD_DIR` | unset | Directory holding the `dashboard` skill (`scripts/render_dashboard.py`) when `tools/dashboard.ts` finds it in neither layout. |
| `ORCHESTRATE_AMP_RUNTIME_DIR` | unset | Directory holding `agent-runtime.ts` and `models.ts` when neither layout applies. The facade imports code from it, so it is a code-loading setting: only the operator sets it. |
| `ORCHESTRATE_REPO_URL` | unset | The repository the operator runs the loop for. `plan.repoUrl` must match it; unset means unchecked. See Security. |
| `ORCHESTRATE_MEASUREMENTS` | unset | `1` lets the loop run planner-authored measurement commands when plan.json also opts in; anything else keeps them off. See Security. |

## Security

The OS-3 review (`.amp/in/artifacts/orchestrate-sync/os-3-security-review.md`) named four concerns. The port settles them as follows.

1. **Measurement commands.** `tasks[].measurements[].command` runs through `bash -c`. plan.json is written by the root planner, an LLM, and with `syncStateToGit` by anyone who can push the state branch, so plan.json alone cannot turn the commands on. They run only when the operator sets `ORCHESTRATE_MEASUREMENTS=1` in the environment of the process that runs the loop **and** plan.json sets `"measurementsEnabled": true` at the top level (`measurementGate` in `agent-runtime/scripts/core/runtime.ts`). Without the variable each handoff logs `skipped N declared measurement(s): ORCHESTRATE_MEASUREMENTS is unset` to `attention.log` and proceeds; with the variable but no opt-in the line names the missing key. `PlanSchema` is strict and lives outside the port, so `agent-manager.ts` lifts `measurementsEnabled` before parsing and writes it back on every save. The schema change itself belongs in `schemas.ts` and the planner docs; see Follow-ups.
2. **Clone origin.** `plan.repoUrl` must name the repository in `ORCHESTRATE_REPO_URL`, which only the operator sets (`checkRepoUrlAgainstOrigin` in `runtime.ts`). The workspace's `remote.origin.url` is not a fallback, because whoever edits plan.json can also run `git remote set-url`. A mismatch fails `AgentManager.load` with a `PlanValidationError`. When the variable is unset the loop logs one attention line, spawns proceed (an orb project is something the signed-in user already has access to), and the measurement clone stays refused, so measurements need both variables.
3. **Operator mode and file uploads.** `cli/comments.ts` and `cli/util.ts` are not port files, so the port cannot change them; the workspace confinement stays as upstream wrote it and the operator-mode lift stays reachable. See Follow-ups.
4. **`@cursor/sdk` dependency.** Every SDK call is routed through the facade. The port carries `scripts/package.json` and its lockfile without `@cursor/sdk`, and the set's seed transforms redirect the two remaining `import type` lines in `schemas.ts` and `core/handoff.ts` to the facade, so the installed tree typechecks clean with no SDK on disk.

Two more boundaries the audit of this adapter raised: agent ids from `state.json` or `--agent-id` flags are refused unless they are a whole thread id before they become an `amp` argument (`threadIdArg`, `requireThreadId`), so `--last` or `--help` cannot redirect a command; and `wait` and `stream` stop after `ORCHESTRATE_WAIT_TIMEOUT_SEC` instead of polling a dead orb until the loop's checkpoint.

## Limits

- Polling, not streaming: text appears in `tail` and `inspect` up to one poll interval (10 s) late, and a finished run is noticed within one interval.
- No mode listing: the CLI accepts plugin modes by key, but no command lists them, so `models` shows the five built-ins and `models --check` can only confirm those.
- `cancel` archives and marks the run cancelled; the CLI has no stop, so a turn in progress finishes on its own.
- `models --check` is a name check; it does not run a turn in each mode.
- Raising Andon from the CLI (`andon raise`, `andon clear`) needs Slack; without it, write or delete `<workspace>/andon.json`.
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

When `run` returns with every task terminal and `plan.selfAgentId` names a thread, it reads that thread's state through the facade (`listRuns`, which is `finished` only when the export's `meta.lastKnownAgentState` is `idle` after an assistant reply) and, if the thread is idle, sends one follow-up naming the terminal tasks so the planner reads the handoffs and continues; that is the case when the loop was started as an orb service or in the background and the planner's turn ended. A thread that is working is running the loop in the foreground and gets nothing, an unknown state is left alone, and `attention.log` records the decision either way as `planner nudge sent` or `planner nudge skipped` (`nudgeIdlePlanner` in `agent-runtime/scripts/cli/task.ts`, tested in `__tests__/planner-nudge.test.ts`).

Tests: `bun test` in this directory (`adapters/amp`), against `__tests__/fake-amp/amp`.

## Doctor

`tools/doctor.ts` is the preflight the dispatcher runs before kickoff. The first real runs lost their loop starts to things it now checks: `node_modules` missing in the skill's `scripts/`, the runtime not found in the orb's hashed skill cache, a repository that was not yet an Amp project, and pushes the Amp GitHub App was not allowed to make.

```bash
bun tools/doctor.ts --repo https://github.com/<owner>/<repo> [--workspace <dir>] [--json]
```

One line per check, `pass|warn|fail <name>: <what was found> — <fix>`; `--json` prints `{ ok, checks: [{ name, level, found, fix }] }` with the same content. Exit 1 when any check fails, else 0. Every external command runs from an argv array through one runner, so the URL and paths never pass through a shell.

| Check | Looks at | Fix on fail |
| --- | --- | --- |
| `dependencies` | `node_modules` beside the scripts' `package.json` | `bun install --frozen-lockfile` in that directory |
| `runtime` | `resolveRuntimeDir()`: the adapter beside the skill, under the newest `pstack-sync@<hash>` sibling, or in `ORCHESTRATE_AMP_RUNTIME_DIR` | sync pstack-sync beside the skill or set the variable |
| `amp-cli` | `ORCHESTRATE_AMP_BIN`, else `amp` on `PATH` | install the CLI or set the variable |
| `amp-auth` | `amp threads list --json --limit 1`, the cheapest call that fails without a login (`Invalid or missing API key. Run 'amp login'`) | `amp login`, or `AMP_API_KEY` |
| `amp-project` | `amp projects get <repo> --json` (needs `--repo`; warn without it) | `amp projects create <repo> --personal`; kickoff's `No accessible Amp project matches` is this |
| `push-access` | inside a checkout whose `origin` is the repository (`--workspace`, then the cwd): `git push --dry-run origin HEAD:refs/heads/orchestrate-doctor-probe`; otherwise `gh api repos/<owner>/<repo> --jq .permissions.push`; otherwise warn | grant the pushing identity (in an orb, the Amp GitHub App) write access |
| `repo-url-env` | `ORCHESTRATE_REPO_URL` equal to `--repo`, ignoring case and a trailing `.git` | set it in the shell that runs `cli.ts`; warn when unset, fail when different |
| `slack` | `SLACK_BOT_TOKEN` present or absent | information only, always a pass |
| `plan` | with `--workspace`, `<dir>/plan.json` through `parsePlanJson` from the installed `schemas.ts`, with the adapter's `measurementsEnabled` lifted out first as `AgentManager.load` does; also `plan.repoUrl` against `--repo` | fix the fields the schema names |

Run it from the installed skill (`<skills>/orchestrate/scripts`); from the pack layout `schemas.ts` is absent and the plan check says so.

**Where `ORCHESTRATE_REPO_URL is unset` came from.** The first run logged `repoUrl ... not checked against an origin: ORCHESTRATE_REPO_URL is unset` although the planner had started the loop with `amp orb service start <name> --command 'ORCHESTRATE_REPO_URL=<url> bun .../cli.ts run ...'`. The service runner does deliver a leading assignment: in this orb `amp orb service start rf-env-probe --command 'PROBE_VAR=yes env'` logged `PROBE_VAR=yes` as the first line of the child's environment, and `amp orb service status` shows the unit as `ExecStart=/bin/bash -lc PROBE_VAR=yes env`, so the command is a bash command line and `VAR=value cmd` works as in any shell. Nothing in the loop reads the variable too early either: `checkRepoUrlAgainstOrigin` in `core/runtime.ts` reads `process.env` when it is called, from `AgentManager.load`, not at module load. The line comes from the other direction: `AgentManager.load` runs for every `cli.ts` command that opens the workspace (`tree`, `status`, `inspect`, `kill-tree`, as well as `run`), and each of them writes the attention line when the variable is unset in *its* process. A `tree` run from the planner's own shell without the variable logs the line; later loads that have the variable neither clear it nor log again, because `load` deduplicates attention messages by text. So the doctor's `repo-url-env` line warns about the shell, not the service runner, and there is no `env VAR=value` or `bash -lc` workaround to recommend. Export the variable in the planner's shell once, before any `cli.ts` command.

## Follow-ups outside the port

- Add `measurementsEnabled` (boolean, default false) to `PlanObjectSchema` in `schemas.ts`, regenerate `schemas/plan.schema.json`, and mention it in `references/planner.md`.
- Decide operator mode in `cli/util.ts` and `cli/comments.ts`: keep the workspace confinement on regardless of `~/.orchestrate/operator-mode`, or make the flag something the orb user cannot create.
- Teach `andon raise` and `andon clear` in `cli/andon.ts` the file mode (`--workspace` without Slack writes or deletes `<workspace>/andon.json`), so operators do not write the file by hand.
