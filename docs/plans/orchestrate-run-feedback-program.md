# Orchestrate run feedback program

What the first two real `/orchestrate` runs on the synced skill (IL-SCoussens/playgrounds PR #1 and PR #2, 2026-10-14) showed, and the seven changes that follow from it. Integration branch `run-feedback`, based on the hashed-cache fix (nthplusio/skills PR #72). Four lanes, each in its own worktree and branch, merged into `run-feedback`, then one PR to `main`.

## Evidence from the runs

| Observation | Cost | Lane |
| --- | --- | --- |
| Planner detached `run` as an orb service, its turn ended idle, nobody woke it when the verifier finished | 9 min and a manual nudge | A |
| Two failed loop starts, missing `bun install` and the hashed runtime path | 4 min | B |
| First kickoff found no skill because `node_modules` had been swept into the workspace commit | whole first run ran without the loop | C |
| Progress was watched by sending `/dashboard` into the planner thread and by polling thread exports | operator time | D |
| First planner, without the skill, used worktree subagents and finished faster than the loop did for a comparable scope | none, a data point | A |
| PR #1 carries `index-board/plan.json` | reviewer confusion | A |
| Six `orch/*` branches left behind, "no CI checks found" reported as a finding, `ORCHESTRATE_REPO_URL is unset` logged although the service command set it | noise | A, B |

## Lanes

### A. Planner liveness and the Amp planner text (branch `rf/a-liveness`)

Owns `skills/scoussens-skills/pstack-sync/sets/orchestrate/transform.json` and the port file `adapters/amp/agent-runtime/scripts/cli/task.ts`.

- [x] Amp transform for `references/planner.md`: run `run` in the foreground with `--max-runtime-sec` below the tool timeout, re-invoke on exit 100 until `tree` shows every task terminal, never as an orb service. Evidence: the adapted planner.md in a scratch sync shows the text.
- [x] Safety net in `cli/task.ts` `run`: when the loop exits with every task terminal and `plan.selfAgentId` names a thread whose last known state is idle, send one follow-up to it naming the terminal tasks. Never when the thread is working. Evidence: a bun test with the fake `amp` showing the follow-up on idle and none when working.
- [x] Amp transform for `references/dispatcher.md`: a goal with fewer than four independent tasks stays in the current thread with worktree subagents, otherwise kickoff; name the doctor (`bun <orchestrate>/scripts/tools/doctor.ts --repo <url>`) as the step before kickoff. Evidence: adapted dispatcher.md.
- [x] Amp transform for `references/planner.md`: keep state in `.orchestrate/<rootSlug>/` at the repository root, add `.orchestrate/` to `.git/info/exclude` unless `syncStateToGit` needs it tracked (read how the state sync commits before deciding), delete worker task branches after the integration branch holds them and list what remains in the PR body, report a repository without workflows as "no CI configured" once and do not subscribe to CI there, and name the dashboard (`bun <orchestrate>/scripts/tools/dashboard.ts <workspace>`) as the way to show progress. Evidence: adapted planner.md.
- [x] Verify: `python3 -I sync.py sync --set orchestrate --repo <scratch clone> --harness amp` reports no `needs_adaptation`, `local_drift`, or `profile_gaps`; `bun test` in `adapters/amp` passes; `npm run validate` passes.

### B. Doctor preflight (branch `rf/b-doctor`)

Owns `adapters/amp/agent-runtime/scripts/tools/doctor.ts`, its test, and its README section; adds the file to the `agent-runtime` port in `sets/orchestrate/set.json`.

- [x] `bun tools/doctor.ts [--repo <url>] [--workspace <dir>] [--json]` checks, each as a pass, warn, or fail line with the fix: scripts dependencies installed, Amp runtime resolves (`resolveRuntimeDir`), `amp` on PATH and signed in, the repository is an accessible Amp project, the repository accepts a push (dry run when a checkout is present, otherwise the API permission), `ORCHESTRATE_REPO_URL` set and matching `--repo`, Slack token present or absent (information only), plan.json valid when `--workspace` is given. Exit 1 on any fail. Evidence: a bun test with the fake `amp` covering a clean run and each failure, plus a log of a real run in this orb.
- [x] Find why `ORCHESTRATE_REPO_URL is unset` was logged when the planner started the loop with `amp orb service start --command 'ORCHESTRATE_REPO_URL=... bun ...'`. Test whether that service runner passes leading environment assignments; record the answer in the README and make the doctor warn about it when it matters. Evidence: the test command and its output in the lane log.
- [x] Verify: `bun test` in `adapters/amp`, `npm run validate`.

### C. Workspace publish (branch `rf/c-publish`)

Owns `pstack-sync/scripts/sync.py` `publish`, its tests in `evals/test_sync.py`, and the SKILL.md section.

- [x] `sync.py publish --pack <pack checkout> --repo <workspace clone> --harness amp [--push] [--verify]`: copy every pack skill over the workspace copy, remove skills the previous publish copied that the pack no longer has (tracked in `.nthplusio-skills/pack-manifest.json` with the pack commit and skill names), run `sync` for every set under the pack's `sets/`, append `profile_gaps_in_seed` rows to the durable profile, refuse to commit when a `node_modules` directory or a file over 2 MB would be added, commit `Refresh workspace skills from nthplusio/skills@<sha>`, push with `--push`, and with `--verify` run `amp skill info <skill>` for one skill from each set and report whether the index has it. Evidence: unit tests on temp pack and workspace repos for the copy, the removal, the refusal, and the manifest; a log of a real publish into a throwaway clone of the workspace repo.
- [x] Verify: `python3 -m unittest` for pstack-sync, `npm run validate`, `npm run check:private`.

### C2. Seed refresh (branch `rf/c-publish`, found while dogfooding)

- [x] Dogfooding `publish` into a fresh clone of the real workspace applied none of lane A's planner transforms, because `adopt_durable` copies the shipped `transform.json` only when no durable copy exists. Added a three-way seed refresh at the start of every sync: `sets/<set>/seed.json` records the shipped shared block as last adopted; an entry the install left unchanged takes the shipped change, an entry the install recorded stays, and an entry both changed stays and is reported under `seed_conflicts`. Evidence: 6 unit tests, and the live publish log showing planner.md and dispatcher.md in the clone gaining the new text.

### D. Dashboard producer (branch `rf/d-dashboard`)

Owns `adapters/amp/agent-runtime/scripts/tools/dashboard.ts`, its test, and its README section; adds the file to the `agent-runtime` port in `set.json`. Reads `dashboard/references/status-contract.md` and the producers table in `dashboard/SKILL.md` and follows them without extending the contract.

- [x] `bun tools/dashboard.ts <workspace> [--out <html>] [--hosted]` writes `<workspace>/status.json` from `plan.json`, `state.json`, `handoffs/`, and `attention.log`: one row per task with the thread as owner, agent status from the task state, evidence from the handoff status lines, decisions from the planner's plan notes when present, `updated_at` now. Then renders it with the dashboard skill's `render_dashboard.py`, found beside the orchestrate skill as `dashboard/` or the newest `dashboard@<hash>/`, the same lookup the runtime uses. Evidence: a bun test building a record from a fixture workspace that the renderer accepts (run the real renderer), and a rendered page from the sparkline run's recorded state if it can be reconstructed, otherwise from the fixture, inspected as a screenshot.
- [x] Verify: `bun test` in `adapters/amp`, dashboard's own `python3 -m unittest` still passes, `npm run validate`.

## Integration

- [x] Merge lanes into `run-feedback` in the order C, B, D, A; resolve `set.json` and README overlaps.
- [x] Run the full check set on the integration branch: `npm run validate`, `check:builder`, `check:private`, `test:skills`, `bun test` in `adapters/amp`, scratch `sync --set orchestrate`.
- [x] Open one PR to `main` with the evidence list; merging and the workspace publish wait for the operator.
