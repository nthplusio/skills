# Orchestrate thread hygiene program

What a finished orchestrate run leaves behind on Amp, and how the adapter stops that. Evidence from probes run on 2026-10-14 is in `.amp/in/artifacts/orchestrate-sync/thread-hygiene/findings.md` (not committed) and is restated here where a lane depends on it. Integration branch `thread-hygiene`, three lanes in worktrees, one PR to `main`.

## What the probes established

- Exports of archived threads still read, including the handoff, so a worker can be archived the moment its handoff is written. An archived thread cannot be continued, but `amp threads archive --unarchive` exists and a respawn spawns a fresh thread anyway.
- `amp -ox` never archives an orb thread itself; the loop must. The `-l` label flag on `amp -ox` does not apply; `amp threads label` afterwards does, and labels must match `[A-Za-z0-9][A-Za-z0-9-]*`.
- `amp threads rename` works once the thread has a message and fails on an empty thread.
- No CLI flag sets a parent thread. The plugin API does: `amp.getBuiltinAgent(mode).createThread({ parentThreadID, executor: 'orb', project, visibility: 'private' })`, then `addLabels` and `append`. A child made that way answers `amp threads search "parent:<id>"`. A plugin can serve a loopback HTTP endpoint from inside the thread's Amp process (`node:http`), started on `session.start`, and a shell process in the same orb can call it; the probe got `{threadID}` back in about 3 seconds.

## Lanes

### E. Bridge plugin (branch `th/e-bridge`)

Owns `skills/scoussens-skills/pstack-sync/adapters/amp/plugin/orchestrate-bridge/` (an Amp plugin: `index.ts`, `README.md`) and its test `adapters/amp/__tests__/bridge-plugin.test.ts`.

- [x] On `session.start`, start a loopback server on an ephemeral port with a random bearer token and write `{ url, token, thread, startedAt }` to `<working dir>/.orchestrate/bridge.json` (0600), where the working dir is `AMP_WORKING_DIRECTORY`, else the plugin system's `workspaceRoot`, else cwd. Remove the file and close the server on dispose. Never log the token.
- [x] `POST /spawn` with `{ name, prompt, project, mode, labels, parent? }`: validate every field (mode in low|medium|high|ultra, labels match the label pattern, project a non-empty string, prompt under 200 kB, parent defaults to the session thread and may only be a thread id), create the thread as a child of the parent with `executor: 'orb'` and private visibility, add labels, append the prompt, answer `{ threadID, parent }`. Reject a bad token with 401 and bad input with 400 and a reason, never with a stack. One request at a time per bridge is fine.
- [x] Test with a fake `PluginAPI` (a stub `getBuiltinAgent` returning a fake agent whose `createThread` records its options and returns a fake thread with `addLabels`, `append`, and `id`): the file is written and removed, a good request creates the child with the right options and order, bad token, bad label, bad mode, oversized prompt are refused with the right codes, and dispose closes the server.
- [x] README: what it does, where to install it (Workspace Plugins repository so every orb thread has it, or `.amp/plugins/` of a project), the file it writes, and the security model (loopback only, token, input validated, the project is whatever the caller names and the user can access).
- [x] Verify: `bun test` in `adapters/amp`, `npm run validate`, and a live check from this orb: write the plugin to `/tmp/<scratch>/.amp/plugins/`, run a vehicle thread `printf 'Run the shell command sleep 70 and then reply ok.' | amp -x --title probe --dangerously-allow-all &` from that directory with a chosen bridge path, POST a spawn for `https://github.com/IL-SCoussens/playgrounds` with labels `orchestrate` and `orch-probe`, and show `amp threads search "parent:<vehicle id>"` finding the child. Archive every thread the check creates and say which.

### F. Adapter: nested spawn, labels, titles, archive on handoff (branch `th/f-adapter`)

Owns `adapters/interface.ts`, `adapters/amp/agent-runtime.ts`, `adapters/amp/agent-runtime/scripts/core/agent-manager.ts`, the fake amp under `__tests__/fake-amp`, tests `agent-runtime.test.ts` and `gates.test.ts`, and the adapter `README.md` sections for spawn, wait, and the environment table.

- [x] `spawn` takes `labels?: string[]` and `title?: string` in addition to today's fields, and `nodeType?: 'planner' | 'subplanner' | 'worker' | 'verifier'`. When a bridge file exists (path from `ORCHESTRATE_AMP_BRIDGE`, else `<cwd>/.orchestrate/bridge.json`, else `$AMP_WORKING_DIRECTORY/.orchestrate/bridge.json`) and answers, spawn through it so the thread nests under the calling thread; otherwise `amp -ox` as today, followed by `amp threads label <id> <labels...>`. Either way record which path was used on the run (`via: 'bridge' | 'cli'`).
- [x] Titles: the first `wait` or `stream` poll that sees a message renames the thread to `<runTag> <name>` with `amp threads rename`; a rename failure is logged once and never fails the run. `runTag` is passed in by the manager.
- [x] Archive: a new runtime method `archive(agentId)` over `amp threads archive`. The manager calls it right after a handoff is written for a worker, verifier, or subplanner, never for the root planner, and records `archivedAt` on the task. `kill-tree` and `cancel` keep their current behaviour.
- [x] Wait rule: an archived thread whose export shows an assistant reply after the last user message and an idle state is `finished`; archived mid-turn stays `cancelled`.
- [x] Manager: `runTag` is the first six characters of a stable hash of `rootSlug` plus `plan.selfAgentId` (or `rootSlug` alone when unset), written to `state.json` as `runTag`; every spawn gets labels `orchestrate` and `run-<runTag>` and the title `<runTag> <task>`; the kickoff spawn (root planner) gets the same labels and title `<runTag> root` and `nodeType: 'planner'`.
- [x] Tests: fake amp learns `threads label`, `threads rename` (fails on an empty thread, like the real CLI), and `threads archive`; a fake bridge server in the test. Cover: spawn via bridge nests under the file's thread and labels, spawn via CLI labels afterwards, rename on first message and the empty-thread failure, archive after handoff for a worker and not for the root, archived-and-finished reads as finished, archived mid-turn as cancelled.
- [x] Verify: `bun test` in `adapters/amp`; `tsc --noEmit` in the installed layout with the port files copied in; `npm run validate`.

### G. Cleanup tool and the planner text (branch `th/g-cleanup`)

Owns `adapters/amp/agent-runtime/scripts/tools/cleanup.ts`, its test, the `scripts/tools/cleanup.ts` line in `sets/orchestrate/set.json`, a "Cleanup" README section, and `sets/orchestrate/transform.json`.

- [x] `bun tools/cleanup.ts <workspace> [--branches] [--repo-path <checkout>] [--dry-run]`: archive every thread in `state.json` whose task is terminal and is not the root planner and is not yet archived (one `amp threads archive` each, idempotent, with `--unarchive` never used), and with `--branches` delete each `orch/<rootSlug>/<task>` branch whose head commit is an ancestor of the integration branch (`git merge-base --is-ancestor`), keeping the integration branch and anything not contained. Print one line per action and one summary; `--dry-run` prints the plan only.
- [x] Transform text (Amp block, small anchored find/replace in the voice of the existing text): planner.md names the run tag, the `run-<tag>` label, and nesting under the dispatcher's thread as the way to find a run's threads, says workers are archived on handoff and the root stays open, and names `cleanup.ts` for an interrupted run; dispatcher.md says the root planner nests under the thread that ran kickoff when the bridge plugin is installed.
- [x] Tests with the fake amp and a scratch git repo: the archive set is exactly the terminal non-root tasks, the root is never archived, the branch rule keeps an uncontained branch, dry-run performs nothing.
- [x] Verify: `bun test` in `adapters/amp`; a scratch `sync --set orchestrate` into a clone of the workspace shows the new text; `npm run validate`.

## Integration and proof

- [x] Merge E, G, F into `thread-hygiene`; resolve README and set.json overlaps; full check set.
- [ ] Publish the bridge plugin to the Workspace Plugins repository and the pack to the workspace with `publish --push` (operator's go).
- [ ] Third real run with a small goal: confirm threads nest under the kickoff thread, carry `run-<tag>` labels and `<tag> <task>` titles, workers are archived on handoff, and the root stays open and awake until the PR is opened.
