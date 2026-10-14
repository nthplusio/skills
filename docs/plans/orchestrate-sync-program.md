# Orchestrate sync program plan

One coordinator instead of two. Cursor's `orchestrate` plugin becomes an upstream set that the sync installs and adapts per harness, the way pstack is today, with tickets as optional inputs the root planner reads. The dashboard leaves `orchestration-run` as its own skill behind a data contract any producer can feed. pstack-sync becomes a sync for any skill set from any repository, with ports for code the harness must replace. Retirement of `orchestration-run` and `orchestration-setup` waits for a side-by-side run the operator judges. PR ids in order are OS-1, OS-2, OS-3, OS-4, OS-5.

## How to read this

One box is one unit of work. Every box names the evidence that checks it. A nested box is a sub-step of the box above it. Check a box only when its evidence exists, a file, a log line, a screenshot, a test run, or a SHA. The body is a how-to. The appendices explain and record.

The program runs `pstack/skills/poteto-mode/playbooks/autopilot-stack.md`. The operator lands the stack. Every PR stops at STACK-READY. OS-4 is gated on the prototype in Appendix A and does not start until it proves a round trip. OS-5 is the operator's own item and stops at a report.

Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

The surface for every PR is a command line script or a rendered page. A live lane is a scripted run whose output is saved as a log, or a page capture, and the artifact named in each lane is that log or capture.

## Program checklist

### Arm the program

- [ ] State the protocol and this plan to the operator, then stop. Start execution only on the operator's explicit go.
- [ ] Read these from trunk at program start. Re-read them at every tick.
  - [ ] `git show origin/main:pstack/skills/poteto-mode/playbooks/autopilot-stack.md`
  - [ ] `git show origin/main:pstack/skills/swarm/SKILL.md`
  - [ ] `git show origin/main:pstack/skills/poteto-mode/playbooks/opening-a-pr.md`
  - [ ] `git show origin/main:skills/scoussens-skills/pstack-sync/SKILL.md`
  - [ ] `git show origin/main:skills/scoussens-skills/orchestration-run/SKILL.md`
- [ ] On the operator's go, arm the audit tick as an hourly thread schedule (the `building-schedules` skill) with the tick prompt below. Never leave the cadence to memory.
- [ ] Use this tick prompt, verbatim. "Re-read the execution playbook from trunk. Audit the operation against it and fix drift in this tick. Probe every active lane and judge progress by side effects only. Stand down a stuck lane and dispatch its replacement now. Then post a short status message to the operator in chat only when the audit found a tracked change that no earlier status message reported, such as a PR opened, a code-ready head, a round launched or closed, a verdict, a merge, a stuck agent and the action taken, a blocker added or cleared, or a decision only the operator can make. Name every such change and nothing else. Do not repeat a table, the merged list, or an unchanged blocker. If the audit found none, end the turn with no reply text. Either way, log this tick's row in your decision trail. The row names the items reported, or none."
- [ ] On the operator's hold or stand-down, send every owner a zero-writes order at once.

### Spawn owners

- [ ] Spawn one owner per PR with the full lifecycle the execution playbook names.
- [ ] Follow this dependency graph. Start dependent work only after its parent merges, or base it on the parent branch when the execution playbook stacks.
  - [ ] OS-1 and OS-2 are independent and first. Both branch from `main`.
  - [ ] OS-3 after OS-2, based on the OS-2 branch.
  - [ ] OS-4 after OS-3 and after the Appendix A prototype passes, based on the OS-3 branch.
  - [ ] OS-5 after OS-1 and OS-4 merge; it is a run, not a code change.
- [ ] Hold the file boundaries. OS-1 touches `skills/scoussens-skills/dashboard/**`, `skills/scoussens-skills/orchestration-run/**`, `skills/scoussens-skills/orchestration-setup/scripts/state.py`, `skills/scoussens-skills/harness-discovery/scripts/state.py`, and `README.md`. OS-2 touches `skills/scoussens-skills/pstack-sync/**` only. OS-3 touches `skills/scoussens-skills/pstack-sync/sets/**`, `skills/scoussens-skills/pstack-sync/dialects/**`, and the workspace install. OS-4 touches `skills/scoussens-skills/pstack-sync/adapters/**` and the orchestrate set's port files.
- [ ] Hold the review gate. OS-1 changes a rendered page and is review-gated. The others change no interaction.

### PR mechanics, for every PR

- [ ] Resolve the forge once. Default to `gh`; if `command -v origin` succeeds and Origin can resolve the repository, use `origin pr` for every PR operation. Record any fallback to `gh`. Never require `gt`.
- [ ] Open the PR ready, never draft, per **Opening a PR**. Use `gh pr create --base <base-branch>`. A stack child targets its parent branch.
- [ ] Run `npm run validate`, `npm run check:builder`, and `npm run test:skills` once before the PR-facing push. Push with hooks on.
- [ ] Run a slop-strip pass over the diff before each commit and `/no-comments` before review.
- [ ] Triage every Bugbot and security-reviewer comment per `../references/bugbot-triage.md`.
- [ ] Rebase onto current trunk before the code-ready report and babysit. Keep that merge base in fix rounds. Rebase again only at merge prep, on a `git merge-tree` conflict with trunk, or on a CI failure that comes from a change on trunk.

### Verdict and merge, for every PR

- [ ] At the code-ready head SHA and at each later push that changes the patch, run the swarm per `pstack/skills/swarm/SKILL.md`. One gates lane. The ten live lanes from the PR's **Verify, live** block. The perf lane from its **Verify, perf** block. Two or more audit lanes, each with its own focus, that read the diff and the receipts and distrust the PR body. The root audits the receipts in the merge-ready report before the verdict.
- [ ] Clean only when every lane is `PASS`. Findings go back to the owner, including a defect that a lane filed as a note. A new head gets a fresh swarm and a fresh verdict, except for results that stay valid under the patch-id rule in `playbooks/shipping.md`.
- [ ] On a clean verdict the root appends the PR to the one linear base-branch stack. The operator lands the stack bottom-up. A rebase that keeps the patch-id keeps the verdict.

### Boot recipe, for every live lane

Each live lane runs in its own checkout at the PR head. Drive from the shell, and capture pages with `agent-browser`.

- [ ] `git fetch origin <head-branch> && git checkout <head SHA>`.
- [ ] `npm ci`. For OS-4 lanes, `bun install` inside the orchestrate set's `scripts/`.
- [ ] Deliver input only through `python3`, `node`, `bun`, `amp`, and `npm run` commands. Read-only diagnostics are `git status --short` and `cat` of the files a lane names.
- [ ] Save every log or capture to `/tmp/swarm-<pr-id>/worker-<n>/<slug>.log` or `.png` and return the paths with the report.

## Extract the dashboard behind a status contract (OS-1)

**Depends on.** None.

**Files.**

- [ ] Create `skills/scoussens-skills/dashboard/SKILL.md`.
- [ ] Create `skills/scoussens-skills/dashboard/references/status-contract.md`.
- [ ] Create `skills/scoussens-skills/dashboard/scripts/render_dashboard.py`, moved from `orchestration-run/scripts/`.
- [ ] Create `skills/scoussens-skills/dashboard/scripts/check_served.py`, moved.
- [ ] Create `skills/scoussens-skills/dashboard/assets/dashboard-template.html`, moved.
- [ ] Create `skills/scoussens-skills/dashboard/references/dashboard-layout.md`, moved.
- [ ] Create `skills/scoussens-skills/dashboard/evals/test_dashboard.py` with `DashboardTests` and the `check_served` test, and `evals/dashboard-preview.json`, moved.
- [ ] Create `skills/scoussens-skills/orchestration-run/scripts/validate_run.py`, holding `check_lifecycle` and the task proof checks.
- [ ] Edit `skills/scoussens-skills/orchestration-run/SKILL.md`, `references/dashboard-data.md`, `evals/test_dashboard.py`, `evals/behavior.py`, `evals/test_behavior_harness.py`, `evals/test_chain_contract.py`.
- [ ] Edit `skills/scoussens-skills/harness-discovery/scripts/state.py` and its two copies, so `STAGES` and `COORDINATOR_SKILLS` include the dashboard.
- [ ] Edit `README.md`.

**Build.**

- [ ] Split `render_dashboard.py` into display (stays in `render()`) and lifecycle rules (`check_lifecycle` and the task checks at the renderer's lines 188 to 389 move to `validate_run.py`). The renderer rejects unknown top-level keys and bad value sets only; it no longer enforces approval expiry, idle scans, or closed-run cleanliness.
- [ ] Write `status-contract.md` from the display parts of `dashboard-data.md`, namely run fields, task fields, work status, the eight stages, evidence, presentation, monitoring. Give the contract its own `contract_version`, separate from `skill_version`, which stays with orchestration-run and hashes its own folder.
- [ ] Write `dashboard/SKILL.md` as a producer-neutral skill, where input is one status file per the contract, output is one page at a destination chosen through explain-to's settings sheet from the harness entry's `artifacts`, refreshed in place at an interval the producer names. Document three producers in one table, an orchestration run, a single task with subagents, a thread with child threads, each with the minimal status file it writes.
- [ ] Rewrite orchestration-run's section 5 so that it writes `status.json` per the contract, runs `validate_run.py`, then calls the dashboard skill's renderer and `check_served.py`. Keep the presentation-hold and destination-choice rules.
- [ ] Read `STAGES` in `state.py` from the contract file instead of the copied tuple; add `dashboard` to `COORDINATOR_SKILLS`; add `dashboard` to the chain test's `NAMES`.

**You see.**

- [ ] `python3 skills/scoussens-skills/dashboard/scripts/render_dashboard.py <status.json> <out.html>` renders the preview file to the same page bytes as before the move, except the version comment.
- [ ] `python3 skills/scoussens-skills/orchestration-run/scripts/validate_run.py <status.json>` prints the lifecycle findings the renderer used to print.
- [ ] A status file with only `schema_version`, `run_id`, `title`, `tasks`, and `presentation` renders a page, which proves a producer that is not an orchestration run can feed it.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `dashboard/evals/test_dashboard.py` keeps every `DashboardTests` case and gains `test_minimal_status_renders`. `orchestration-run/evals/test_dashboard.py` keeps `LifecycleTests` against `validate_run.py`. Run `npm run test:skills`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes at the PR head on the `swarm workers` line (`inherit`), per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Render `evals/dashboard-preview.json` at trunk and head, strip the version comment, diff. Save `regression.log`. Pass when the diff is empty.
- [ ] Lane 2. Render the preview at head and capture the page at 1280 by 720 at 2x. Save `preview.png`. Pass when the overview, task cards, and evidence render with nothing clipped.
- [ ] Lane 3. Render the minimal status file. Save `minimal.png`. Pass when the page shows the tasks and no error.
- [ ] Lane 4. Run `validate_run.py` on a status file with an expired approval. Save `lifecycle.log`. Pass when it reports the expiry and the renderer alone does not.
- [ ] Lane 5. Run orchestration-run's `evals/behavior.py` scenario that writes a dashboard. Save `behavior.log`. Pass when `dashboard.html` is written through the new path.
- [ ] Lane 6. Run `check_served.py` against a page served by `python3 -m http.server`. Save `served.log`. Pass when it prints PASS.
- [ ] Lane 7. Run the chain contract test. Save `chain.log`. Pass when the three `state.py` copies match and `dashboard` is in `NAMES`.
- [ ] Lane 8. Render a status file with an unknown top-level key. Save `unknown-key.log`. Pass when the renderer rejects it by name.
- [ ] Lane 9. Capture the page at 390 wide. Save `narrow.png`. Pass when cards stack and nothing overflows.
- [ ] Lane 10. Run `npm run validate` and `npm run check:builder` at head. Save `gates.log`. Pass when both print a `✓` line and no `✗` line.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time to render the preview file, trunk renderer against head renderer plus `validate_run.py`.
- [ ] Probe. `time python3 <renderer> preview.json out.html`, three runs each side, interleaved; head adds `time python3 validate_run.py preview.json`.
- [ ] Baseline. Record the trunk median first.
- [ ] Rule. Head render plus validate median within 1.2 times the trunk median.

**Review gate.** The operator reviews before merge.

- [ ] Copy lane 2 and lane 9 captures into `.amp/in/artifacts/orchestrate-sync/OS-1-review-preview.png` and `OS-1-review-narrow.png`.
- [ ] Record a 30 to 60 second video of the page refreshing in place while a status file changes. Save it as `.amp/in/artifacts/orchestrate-sync/OS-1-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends OS-1 to the base-branch stack and the operator lands it.

## Generalize the sync to sets, dialects, and ports (OS-2)

**Depends on.** None.

**Files.**

- [ ] Create `skills/scoussens-skills/pstack-sync/sets/pstack.json`.
- [ ] Create `skills/scoussens-skills/pstack-sync/dialects/cursor.json`, moved from `needs.json` minus the set-specific rows.
- [ ] Edit `skills/scoussens-skills/pstack-sync/scripts/sync.py`.
- [ ] Edit `skills/scoussens-skills/pstack-sync/evals/test_sync.py`.
- [ ] Edit `skills/scoussens-skills/pstack-sync/SKILL.md` and `references/adapting.md`.
- [ ] Delete `skills/scoussens-skills/pstack-sync/needs.json`.

**Build.**

- [ ] Replace the module constants `UPSTREAM`, `ROOT_PLUGIN`, `SUBDIR`, `AGENTS`, and the `pstack-` collision prefix with a `SetConfig` loaded from `sets/<set>.json`, selected by `--set` (default `pstack`). Keep the module aliases so the test API holds.
- [ ] Split `needs.json` so that the Cursor rows go to `dialects/cursor.json`; `role-model-config`, `bugbot`, and the pstack wording of `custom-subagents` go to the set's `extra_needs`. `load_needs` merges dialect plus set.
- [ ] Key durable state per set under `.nthplusio-skills/pstack-sync/sets/<set>/manifest.json`, `transform.json`, `LICENSE-*`. `adopt_durable` moves today's pstack state into `sets/pstack/` once. The harness profile and local profile stay shared.
- [ ] Add every set's managed directories to `available`, so a dependency one set installs shows as `existing` to another set.
- [ ] Add ports to the transform model. A `ports` block per set names upstream files that the harness replaces as a unit, each with the adapter path that provides them. `sync` installs the adapter in place of the port's files, hashes the upstream files, and reports `stale_ports` when upstream changes them.
- [ ] Write the per-set file shape and the port rule into `SKILL.md` and `adapting.md`; the commit subject becomes `<set>: sync to <repo>@<short-sha>`.

**You see.**

- [ ] `sync --set pstack` on the workspace clone reports `unchanged_count: 58` and moves the state under `sets/pstack/` with no other change.
- [ ] `sync --set <unknown>` fails naming the missing `sets/<unknown>.json`.
- [ ] A test set with one port installs the adapter file and reports `stale_ports` when the upstream port file changes.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_sync.py` keeps all 29 cases and gains `test_state_moves_under_the_set_directory`, `test_two_sets_share_one_dependency`, `test_a_port_installs_its_adapter_and_reports_upstream_changes`, and `test_dialect_and_set_needs_merge`. Run `python3 -B -m unittest discover -s skills/scoussens-skills/pstack-sync/evals -v`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes at the PR head on the `swarm workers` line (`inherit`), per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the existing 29 tests at trunk and at head. Save `regression.log`. Pass when both print `OK`.
- [ ] Lane 2. Clone the workspace, replace `pstack-sync/` with head, run `sync --set pstack`. Save `workspace-migrate.log`. Pass when `sets/pstack/manifest.json` exists, the old files are gone, and the report has no `added`, `updated`, `removed`, `needs_adaptation`, or `local_drift`.
- [ ] Lane 3. Run `sync` with no `--set`. Save `default-set.log`. Pass when it behaves as `--set pstack`.
- [ ] Lane 4. Run `sync --set nosuch`. Save `unknown-set.log`. Pass when it exits 1 naming `sets/nosuch.json`.
- [ ] Lane 5. In a temp install, define a second set from the test upstream that depends on `deslop`, sync both. Save `two-sets.log`. Pass when `deslop` is installed once and the second set lists it under `existing`.
- [ ] Lane 6. Define a port in the test set, sync, change the upstream port file, sync again. Save `port-stale.log`. Pass when the second run lists the port under `stale_ports`.
- [ ] Lane 7. Run `seed --out` and diff against the pack seeds. Save `seed.log`. Pass when only the expected set layout differs.
- [ ] Lane 8. Run `status --since HEAD~1` after the migration commit. Save `status.log`. Pass when it reports the set name and no changed adaptations.
- [ ] Lane 9. Run `record --local` on one file in the pstack set. Save `record.log`. Pass when the entry lands under `sets/pstack/transform.json` local block.
- [ ] Lane 10. Run `npm run validate` and `npm run check:builder` at head. Save `gates.log`. Pass when both print a `✓` line and no `✗` line.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of `sync --dry-run` on the workspace clone at trunk and at head.
- [ ] Probe. Three runs each side, interleaved.
- [ ] Baseline. Record the trunk median first.
- [ ] Rule. Head median within 1.2 times trunk.

**Review gate.** None. OS-2 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends OS-2 to the base-branch stack and the operator lands it.

## Sync the orchestrate set's text and declare its ports (OS-3)

**Depends on.** OS-2.

**Files.**

- [ ] Create `skills/scoussens-skills/pstack-sync/sets/orchestrate.json`.
- [ ] Edit `skills/scoussens-skills/pstack-sync/dialects/cursor.json` with the constructs the plugin adds, namely Cursor agent URLs, `cursor-sdk`, `AwaitShell`, `ManagePullRequest`, Cursor model ids, `:rotating_light:`.
- [ ] Edit `skills/scoussens-skills/pstack-sync/harness/amp.md` with rows for the new needs.
- [ ] Workspace install, the `orchestrate/` skill directory and `.nthplusio-skills/pstack-sync/sets/orchestrate/`.

**Build.**

- [ ] Write `sets/orchestrate.json` with upstream `cursor/plugins`, root plugin `orchestrate`, skills subdir `orchestrate/skills`, dialect `cursor`, agents dir none, ports listing `scripts/core/agent-manager.ts` spawn, wait, stream, cancel, list, and follow-up as one `agent-runtime` port, `scripts/models.ts` as a `models` port, and `scripts/tools/nudge-root.ts` and `probe-models.ts` as parts of the same port.
- [ ] Sync the set into the workspace clone. Adapt the Markdown, meaning SKILL.md, the four references, the ten prompts, the README. Replace Cursor URLs and tool names with the Amp facts from discovery; replace the `cursor-sdk` hand-off with a pointer to the Amp adapter's documentation; fix the stale `/orchestrate` prefix claim; say that tickets, when the user names any, are inputs the root planner reads into `plan.json` tasks and are otherwise absent.
- [ ] Record the adaptations; mark the port files as pending the OS-4 adapter so `sync` reports them under `ports_pending` rather than installing Cursor code that cannot run.

**You see.**

- [ ] `sync --set orchestrate` reports the Markdown installed and `ports_pending: ["agent-runtime", "models"]`.
- [ ] `grep -rn "cursor.com\|cursor-sdk\|AwaitShell\|ManagePullRequest" orchestrate/` in the workspace prints nothing.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_sync.py` gains `test_pending_ports_are_reported_and_not_installed`. Run the suite.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes at the PR head on the `swarm workers` line (`inherit`), per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the pstack set sync at trunk and head on the workspace clone. Save `regression.log`. Pass when both report nothing to adapt.
- [ ] Lane 2. Run `sync --set orchestrate` on a clone. Save `orchestrate-sync.log`. Pass when the Markdown files are added and the two ports are pending.
- [ ] Lane 3. Grep the installed Markdown for Cursor constructs. Save `no-cursor.log`. Pass when it prints nothing.
- [ ] Lane 4. Read the adapted `references/planner.md` with a cold agent and ask it which commands it would run to spawn a worker. Save `planner-read.log`. Pass when it names the adapter, not the Cursor SDK.
- [ ] Lane 5. Run `status --since HEAD~1`. Save `status.log`. Pass when it lists the orchestrate set separately from pstack.
- [ ] Lane 6. Run the pstack set sync after the orchestrate set is installed. Save `pstack-after.log`. Pass when nothing changes and no `existing` collisions appear.
- [ ] Lane 7. Change one upstream prompt file in a test upstream and sync. Save `prompt-stale.log`. Pass when the stale transform is reported with its upstream diff.
- [ ] Lane 8. Validate `sets/orchestrate.json` against the set schema in the script. Save `set-schema.log`. Pass when it loads.
- [ ] Lane 9. Security review log of every installed text file. Save `security.log`. Pass when no network call, credential read, or install step is found in Markdown.
- [ ] Lane 10. Run `npm run validate` and `npm run check:builder` at head. Save `gates.log`. Pass when both print a `✓` line and no `✗` line.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of `sync --set orchestrate --dry-run` with a warm cache, and of the pstack set at trunk and head.
- [ ] Probe. Three runs each, interleaved.
- [ ] Baseline. Record the trunk pstack median first.
- [ ] Rule. The pstack median at head within 1.2 times trunk; the orchestrate dry run under 10 seconds.

**Review gate.** None. OS-3 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends OS-3 to the base-branch stack and the operator lands it.

## Provide the Amp agent runtime adapter (OS-4)

**Depends on.** OS-3, and the Appendix A round-trip prototype.

**Files.**

- [ ] Create `skills/scoussens-skills/pstack-sync/adapters/amp/agent-runtime.ts`.
- [ ] Create `skills/scoussens-skills/pstack-sync/adapters/amp/models.ts`.
- [ ] Create `skills/scoussens-skills/pstack-sync/adapters/amp/README.md`.
- [ ] Create `skills/scoussens-skills/pstack-sync/adapters/amp/__tests__/agent-runtime.test.ts`.
- [ ] Create `skills/scoussens-skills/pstack-sync/adapters/interface.ts`, the `AgentRuntime` interface.

**Build.**

- [ ] Define `AgentRuntime` with spawn, getRun, wait, stream, cancel, list, sendFollowUp, agentUrl, and models, with the same result shapes `core/handoff.ts` and `core/loop.ts` consume.
- [ ] Implement the Amp adapter over the `amp` CLI, with spawn as `amp -ox` on a repository and ref, identity from the thread ID it prints, status and final message from `amp threads export`, follow-up with `amp threads continue <id> -ox`, cancel by archiving, and the thread URL as `agentUrl`. Stream is a poll over export deltas.
- [ ] Carry a refactor patch for upstream `agent-manager.ts` that routes its SDK calls through the interface, stored as the port's adapter so `sync` applies it and reports when upstream moves the seam.
- [ ] Record Amp model handling, where `models()` returns Amp agent modes from `amp` where the CLI exposes them, otherwise the single `inherit` entry.

**You see.**

- [ ] `bun test` in the adapter folder passes against a fake `amp` on `PATH`.
- [ ] `bun scripts/cli.ts kickoff "<small goal>" --repo <this repo>` from the workspace's orchestrate skill starts an orb thread, the root planner writes `plan.json`, one worker thread runs, and a handoff file appears.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `agent-runtime.test.ts` covers spawn, wait with a finished thread, wait with a dropped stream, cancel, and follow-up, each against the fake CLI. Run `bun test`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes at the PR head on the `swarm workers` line (`inherit`), per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Trunk lacks the feature; record that, and gate the round trip, a kickoff of a one-task goal and get one handoff file. Save `roundtrip.log`. Pass when the handoff has the header and a `## Branch` line.
- [ ] Lane 2. A two-task plan with `dependsOn`. Save `depends.log`. Pass when the second task's prompt contains the first handoff.
- [ ] Lane 3. A verifier task. Save `verifier.log`. Pass when the verdict lands on the target's state row.
- [ ] Lane 4. Cancel a running worker. Save `cancel.log`. Pass when state shows `cancelled` and the thread is archived.
- [ ] Lane 5. Kill the loop mid-run and restart with `run`. Save `recover.log`. Pass when the running task is reattached and finishes.
- [ ] Lane 6. Raise Andon through the file source and confirm no spawn happens. Save `andon.log`. Pass when the sweep logs the hold.
- [ ] Lane 7. A ticket passed to kickoff appears in `plan.json` as a task's brief. Save `ticket-input.log`. Pass when the brief quotes the ticket ID and title.
- [ ] Lane 8. `tail` on a running worker. Save `tail.log`. Pass when it shows assistant text within one poll interval.
- [ ] Lane 9. Render the run's state through the dashboard skill. Save `dashboard.png`. Pass when every task appears with its status.
- [ ] Lane 10. Run `npm run validate`, `npm run check:builder`, and `bun test`. Save `gates.log`. Pass when all are green.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Trunk lacks the feature. Measure the diff-added work, the time from spawn to first assistant text, and time from worker completion to handoff file written.
- [ ] Probe. Three one-task kickoffs, recording both intervals from the loop log.
- [ ] Baseline. Record the first run's values as the baseline.
- [ ] Rule. Spawn to first text under 120 seconds; completion to handoff under one poll interval plus 10 seconds.

**Review gate.** None. OS-4 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends OS-4 to the base-branch stack and the operator lands it.

## Run one milestone both ways and decide (OS-5)

**Depends on.** OS-1, OS-4.

**Files.**

- [ ] Create `.amp/in/artifacts/orchestrate-sync/comparison.md`, uncommitted.

**Build.**

- [ ] Pick one real milestone of three to five tickets. Run it under orchestration-run with the dashboard skill, then under the adapted orchestrate with tickets as kickoff inputs and the dashboard fed from `state.json`.
- [ ] Record for each run the wall time, human turns, tickets landed, defects found by verifiers, and what each coordinator could not do.

**You see.**

- [ ] One comparison file with both columns filled from receipts, and a recommendation line the operator can accept or reject.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] No code changes. The unit box is the receipts list in the comparison file; every number links a log.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes at the PR head on the `swarm workers` line (`inherit`), per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Trunk is orchestration-run; record its run as the baseline. Save `baseline-run.log`. Pass when the milestone closes with receipts.
- [ ] Lane 2. The orchestrate run. Save `candidate-run.log`. Pass when the same milestone closes with receipts.
- [ ] Lane 3. Dashboard from the orchestration run. Save `dashboard-run.png`. Pass when it renders through the dashboard skill.
- [ ] Lane 4. Dashboard from the orchestrate state. Save `dashboard-orchestrate.png`. Pass when it renders through the dashboard skill.
- [ ] Lane 5. Ticket binding in the candidate. Save `tickets.log`. Pass when every ticket appears in a task brief and in a handoff.
- [ ] Lane 6. Human turns counted from both threads. Save `turns.log`. Pass when both counts come from the thread exports.
- [ ] Lane 7. Verifier findings in the candidate. Save `verifiers.log`. Pass when each finding links a handoff.
- [ ] Lane 8. Approval gate in the baseline, Andon in the candidate, each exercised once. Save `gates.log`. Pass when both held the line and resumed.
- [ ] Lane 9. Code landed, both runs, from `git log`. Save `landed.log`. Pass when each ticket maps to a merged PR or a recorded reason.
- [ ] Lane 10. The comparison file. Save `comparison.log`. Pass when every cell cites a lane log.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time to close the milestone, baseline against candidate, and human turns.
- [ ] Probe. One run each, same tickets, same week, logged.
- [ ] Baseline. The orchestration-run values.
- [ ] Rule. No pass or fail; the operator decides on the table. The program records both.

**Review gate.** None. OS-5 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The operator decides retirement; a yes becomes a separate removal PR outside this plan.

## Close the program

- [ ] Every box above is checked with its evidence.
- [ ] Reply to the operator with the report the execution playbook names.

## Appendix A. Prototype evidence

One question gates OS-4 and is settled by running, not by reading, namely whether an orb thread can be spawned, watched, and read back from a shell with the `amp` CLI alone, with its final message returned verbatim. Settled on 2026-10-14. `amp -ox "<task>" --visibility private --no-archive-after-execute` returns in about 3 seconds with the thread URL; `amp threads export <id>` polled every 15 seconds reaches `idle` in about 47 seconds and returns the final assistant message verbatim; `amp threads continue <id> -ox` delivers a follow-up reply within one poll tick; `amp threads archive <id>` closes it. Mode listing is partial, since no command lists agent modes, so the `models` port returns `inherit` plus whatever `amp plugins show-agent-options` names. Evidence in `.amp/in/artifacts/orchestrate-sync/prototype-roundtrip.log`. The prototype runs `amp -ox` with a one-line task against this repository, records the thread ID it prints, polls `amp threads export` until the thread is idle, and reads the final assistant message. It keeps the commands and output under `.amp/in/artifacts/orchestrate-sync/prototype-roundtrip.log`. Unproven until that log exists is whether a follow-up through `amp threads continue` wakes a paused orb within the loop's 60 second watchdog, and whether the CLI exposes agent modes for the `models` port.

Settled by inspection on 2026-10-14. The plugin's Slack layer already sits behind an interface, so Slack stays optional; `AndonSource.snapshot()` is an interface, so a file-based stop signal fits without Slack; about 900 of 8,000 lines touch the Cursor SDK and they concentrate in one 270-line method, so the refactor patch is bounded.

## Appendix B. Alternatives rejected

- Adapting `cli.ts` with find-and-replace transforms. Lost because the SDK calls are interleaved with handoff and state logic in one method, so text edits would break on every upstream change; a port behind an interface moves with the seam instead.
- Keeping `orchestration-run` and only adding orchestrate alongside. Lost because two coordinators with two state shapes double every dashboard and gate change; the plan keeps both only for the one comparison run.
- Making tickets the unit of work in orchestrate. Lost by the operator's decision, which makes tickets optional inputs to the planner, which keeps the upstream planner prompt intact and the adaptation thin.
- Rewriting the loop in Python to match the rest of the pack. Lost because it forks the whole plugin; the adapter keeps upstream's loop and tests.

## Appendix C. Risks

- OS-1. The renderer enforces lifecycle rules today; moving them to `validate_run.py` can silently drop a check. Lane 4 and the kept `LifecycleTests` guard it. The owner watches for any rule that has no test.
- OS-2. Two sets sharing one transform namespace can collide on a skill name. Per-set durable directories remove the collision; the owner watches `existing` in reports.
- OS-3. Adapted prose that tells a planner to run commands the adapter does not yet provide. Ports stay pending until OS-4, and lane 4 reads the prose cold.
- OS-4. The `amp` CLI may not expose what the loop needs, above all a reliable finished signal and agent modes. The Appendix A prototype decides before any code is written; a miss turns OS-4 into a request for a CLI feature and stops the program at OS-3.
- OS-4. The security review of the installed scripts (`.amp/in/artifacts/orchestrate-sync/os-3-security-review.md`) found three things the adapter must settle before a real run. The measurement runner executes a command string from `plan.json` through `bash -c`, so measurements stay off unless the plan opts in. The measurement clone accepts any repository URL, so the adapter refuses a URL that is not the configured origin. Operator mode lifts the workspace confinement on Slack file uploads and the orb user can enable it, so the Amp port keeps the confinement on. The owner also drops `@cursor/sdk` from the carried `package.json`, which pulls a native sqlite3 build and telemetry the ports no longer need.
- OS-4. The refactor patch on `agent-manager.ts` must be re-applied when upstream edits that method. The port hash reports it; the owner budgets a re-carry per upstream release.
- OS-5. A single milestone is one sample. The comparison file says so, and the operator weighs it as such.

## Appendix D. Links and reading list

- `skills/scoussens-skills/orchestration-run/references/dashboard-data.md` and `scripts/render_dashboard.py` before OS-1.
- `skills/scoussens-skills/pstack-sync/scripts/sync.py` and `references/adapting.md` before OS-2 and OS-3.
- Upstream `orchestrate/skills/orchestrate/references/{planner,spawning,handoffs}.md` and `scripts/core/{loop,agent-manager,handoff}.ts` at cursor/plugins c86f349 before OS-3 and OS-4.
- OS-1 and OS-2 get `pstack/skills/how/SKILL.md` over their scripts. OS-4 gets `pstack/skills/interrogate/SKILL.md` because it carries a patch on upstream code.
- The decision trail per `pstack/skills/show-me-your-work/SKILL.md` lives at `.amp/in/artifacts/orchestrate-sync/decisions.tsv`, uncommitted.
