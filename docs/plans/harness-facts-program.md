# Harness facts program plan

Harness knowledge in this pack is split into three layers with three homes. Shared harness facts move into a registry inside `harness-discovery`. Skill needs are declared in one vocabulary, the discovery schema. Install state and local choices stay in `.nthplusio-skills/` and never flow back into the pack. The consumer is any skill that must behave the same in Amp, Cursor, or Claude Code without re-deriving what the harness can do. The maintainer inherits one place to update when a harness changes. PR ids in order are HF-1, HF-2, HF-3, HF-4.

## How to read this

One box is one unit of work. Every box names the evidence that checks it. A nested box is a sub-step of the box above it. Check a box only when its evidence exists, a file, a log line, a screenshot, a test run, or a SHA. The body is a how-to. The appendices explain and record.

The program runs `pstack/skills/poteto-mode/playbooks/autopilot-stack.md`. The operator lands the stack. Every PR stops at STACK-READY. No PR is review-gated, because none changes an interactive surface.

Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

The surface for every PR is a command line script. A live lane is therefore a scripted run whose output is saved as a log, and the saved artifact named in each lane is that log, not a picture.

## Program checklist

### Arm the program

- [ ] State the protocol and this plan to the operator, then stop. Start execution only on the operator's explicit go.
- [ ] Read these from trunk at program start. Re-read them at every tick.
  - [ ] `git show origin/main:pstack/skills/poteto-mode/playbooks/autopilot-stack.md`
  - [ ] `git show origin/main:pstack/skills/swarm/SKILL.md`
  - [ ] `git show origin/main:pstack/skills/poteto-mode/playbooks/opening-a-pr.md`
  - [ ] `git show origin/main:skills/scoussens-skills/harness-discovery/SKILL.md`
  - [ ] `git show origin/main:skills/scoussens-skills/pstack-sync/SKILL.md`
- [ ] On the operator's go, arm the audit tick as an hourly thread schedule (the `building-schedules` skill) with the tick prompt below. Never leave the cadence to memory.
- [ ] Use this tick prompt, verbatim. "Re-read the execution playbook from trunk. Audit the operation against it and fix drift in this tick. Probe every active lane and judge progress by side effects only. Stand down a stuck lane and dispatch its replacement now. Then post a short status message to the operator in chat only when the audit found a tracked change that no earlier status message reported, such as a PR opened, a code-ready head, a round launched or closed, a verdict, a merge, a stuck agent and the action taken, a blocker added or cleared, or a decision only the operator can make. Name every such change and nothing else. Do not repeat a table, the merged list, or an unchanged blocker. If the audit found none, end the turn with no reply text. Either way, log this tick's row in your decision trail. The row names the items reported, or none."
- [ ] On the operator's hold or stand-down, send every owner a zero-writes order at once.

### Spawn owners

- [ ] Spawn one owner per PR with the full lifecycle the execution playbook names.
- [ ] Follow this dependency graph. Start dependent work only after its parent merges, or base it on the parent branch when the execution playbook stacks.
  - [ ] HF-1 and HF-2 are independent and first. Both branch from `main`.
  - [ ] HF-3 after HF-2, based on the HF-2 branch.
  - [ ] HF-4 after HF-3, based on the HF-3 branch.
- [ ] Hold the file boundaries. HF-1 touches only `skills/scoussens-skills/pstack-sync/**`. HF-2 touches only `skills/scoussens-skills/harness-discovery/**`. HF-3 touches `skills/scoussens-skills/harness-discovery/**` and `skills/scoussens-skills/pstack-sync/**`. HF-4 touches `scripts/validate-skills.mjs`, `skills/scoussens-skills/explain-to/**`, `skills/scoussens-skills/visualize-spec/SKILL.md`, `skills/scoussens-skills/harness-discovery/evals/**`, and `README.md`.
- [ ] Hold the review gate. No PR changes an interaction, so none waits for a chat review.

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

Each live lane runs in its own checkout at the PR head. Drive from the shell.

- [ ] `git fetch origin <head-branch> && git checkout <head SHA>`.
- [ ] `npm ci`. No server starts; the surface is the scripts.
- [ ] Deliver input only through `python3`, `node`, and `npm run` commands. Read-only diagnostics are `git status --short` and `cat` of the files a lane names.
- [ ] Save every log to `/tmp/swarm-<pr-id>/worker-<n>/<slug>.log` and return the paths with the report.

## Split pstack-sync state into shared and local (HF-1)

**Depends on.** None.

**Files.**

- [ ] Edit `skills/scoussens-skills/pstack-sync/scripts/sync.py`.
- [ ] Edit `skills/scoussens-skills/pstack-sync/evals/test_sync.py`.
- [ ] Edit `skills/scoussens-skills/pstack-sync/SKILL.md`.
- [ ] Edit `skills/scoussens-skills/pstack-sync/references/adapting.md`.

**Build.**

- [ ] Give each harness block in `transform.json` a `local` sub-block with the same `accept`, `global`, and `files` keys. `State.__init__` in `sync.py` reads both and builds `self.tf` as the merge, shared first, local second, so every marker and replay sees one combined view.
- [ ] Add `--local` to `cmd_record` in `sync.py`. With it, the recorded entry lands under `local.files`; without it, under `files`. A file recorded locally is removed from the shared block, and the reverse, so one file has one home.
- [ ] Read a second profile, `harness/<harness>.local.md`, in `State.__init__` when it exists. `parse_profile` runs on both texts and local rows override shared rows. `profile_text` becomes the concatenation so `dependency_report` still sees local companion mappings.
- [ ] Add `cmd_seed` in `sync.py`. `seed --out <dir>` writes `transform.json` without any `local` block and copies `harness/<harness>.md` without the local file into `<dir>`. This is the one lever that refreshes the pack's seeds.
- [ ] Teach `adopt_durable` to copy a shipped `harness/<harness>.md` only, never a `.local.md`, so a pack refresh cannot plant local rows.
- [ ] Rewrite the State section of `SKILL.md` and the profile section of `adapting.md` so that a seed holds only what is true of the harness itself; a companion mapping to a repository's own skill, an exclusion, or any row that names a repository goes in the local file or is recorded with `--local`.

**You see.**

- [ ] After `record --local ketchup/SKILL.md`, `transform.json` holds `"ketchup/SKILL.md"` under `"local": {"files": ...}` and not under `"files"`.
- [ ] After `seed --out /tmp/seed`, `/tmp/seed/transform.json` contains no `"local"` key and `/tmp/seed/harness/` contains no `*.local.md`.
- [ ] A `sync` run after a plain copy of the skill directory reports `local_drift: []` and keeps every local entry.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_sync.py` gains `test_record_local_keeps_the_entry_out_of_the_seed`, `test_local_profile_rows_override_shared_rows`, `test_seed_writes_shared_state_only`, and `test_a_plain_copy_keeps_local_entries`. Run `python3 -B -m unittest discover -s skills/scoussens-skills/pstack-sync/evals -v`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes at the PR head on the `swarm workers` line (`inherit`), per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the existing 21 `test_sync.py` cases at trunk and at head. Save `regression.log`. Pass when both runs print `OK` and head adds the four new cases.
- [ ] Lane 2. Clone the Intellilake workspace skills repository at its current head, replace its `pstack-sync/` with the PR's copy, run `sync`. Save `workspace-sync.log`. Pass when the report has `added`, `updated`, `removed`, `needs_adaptation`, and `local_drift` all empty.
- [ ] Lane 3. In that clone, run `record --local poteto-help/SKILL.md`, then `seed --out /tmp/seed`. Save `seed-excludes-local.log`. Pass when `grep -c poteto-help /tmp/seed/transform.json` prints `0` and `grep -c poteto-help .nthplusio-skills/pstack-sync/transform.json` prints at least `1`.
- [ ] Lane 4. In that clone, write `harness/amp.local.md` with a `companion-skills` row that maps `orchestrate` to `orchestration-run`, run `sync`. Save `local-profile.log`. Pass when the report's `dependencies.unresolved` is empty and `/tmp/seed/harness/amp.md` after `seed` does not contain `orchestration-run`.
- [ ] Lane 5. Delete the clone's `pstack-sync/` and copy the pack's seed copy in, as a refresh does, then run `sync`. Save `plain-copy.log`. Pass when `local` entries from lane 3 are still present in the durable `transform.json` and `local_drift` is empty.
- [ ] Lane 6. Run `seed --out /tmp/seed2` twice. Save `seed-idempotent.log`. Pass when `diff -r /tmp/seed /tmp/seed2` prints nothing.
- [ ] Lane 7. Run `record` without `--local` on a file previously recorded with `--local`. Save `record-moves-home.log`. Pass when the file key appears once in `transform.json`, under `files`.
- [ ] Lane 8. Run `status --since HEAD~1` after a commit that records one local and one shared entry. Save `status-counts.log`. Pass when the output lists both files under New adaptations.
- [ ] Lane 9. Start a fresh temp install with only the pack's seeds and run `sync`. Save `fresh-install.log`. Pass when the run completes with exit 0 and the durable `transform.json` has an empty `local` block.
- [ ] Lane 10. Run `npm run validate` and `npm run check:builder` at head. Save `gates.log`. Pass when both print a `✓` line and no `✗` line.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of `sync` on the workspace clone with a warm upstream cache, at trunk and at head.
- [ ] Probe. `time python3 pstack-sync/scripts/sync.py sync --repo <clone> --harness amp`, three runs each side, interleaved trunk, head, trunk, head, trunk, head.
- [ ] Baseline. Record the trunk median first.
- [ ] Rule. Head median is within 1.2 times the trunk median. A larger ratio fails.

**Review gate.** None. HF-1 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends HF-1 to the base-branch stack and the operator lands it.

## Seed harness facts from a registry (HF-2)

**Depends on.** None.

**Files.**

- [ ] Create `skills/scoussens-skills/harness-discovery/registry/amp.json`.
- [ ] Edit `skills/scoussens-skills/harness-discovery/scripts/state.py`.
- [ ] Edit `skills/scoussens-skills/harness-discovery/evals/test_state.py`.
- [ ] Edit `skills/scoussens-skills/harness-discovery/SKILL.md`.
- [ ] Edit `README.md`.

**Build.**

- [ ] Define the registry entry shape in `state.py` as `{"name", "fingerprint": {"command", "value"}, "entry"}` where `entry` is one discovery harness entry. The registry file name is the harness slug.
- [ ] Add `cmd_seed` to `state.py`. `seed --harness <name or slug>` loads `registry/<slug>.json`, creates `discovery.json` from the template's repository section when absent, inserts the entry under its name unless one exists, stamps `observed_at` and appends a registry source line. It runs the fingerprint command and prints one of `fresh`, `stale`, or `unverifiable` with the two values. `--force` replaces an existing entry.
- [ ] Add `cmd_export` to `state.py`. `export --harness <name>` writes the local entry back to `registry/<slug>.json` with the repository section dropped and every string that contains the repository root path removed, and refreshes the fingerprint value by running its command.
- [ ] Make `check` validate every registry file through `check_discovery` on a synthetic document, so a broken seed fails CI.
- [ ] Write `registry/amp.json` from the Amp entry observed on 2026-10-13, with the workspace repository URL removed from `skills.locations` and the fingerprint command `amp --version`.
- [ ] Rewrite step 1 of `SKILL.md` to run `seed` first. On `fresh`, reuse the registry's facts and inspect only fields the entry marks as limitations. On `stale`, re-inspect every field and `export` the result. On `unverifiable`, inspect as today. Add the registry row to the README state table.

**You see.**

- [ ] In an empty repository, `state.py seed --harness Amp` creates `.nthplusio-skills/discovery.json` and prints `fresh amp 0.0.<version>` when the installed CLI matches, or `stale` with both versions.
- [ ] `state.py resolve --harness amp` then prints the seeded entry with its `harness.slug`.
- [ ] `state.py export --harness Amp` rewrites `registry/amp.json` and `git diff` shows only fields that changed locally.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_state.py` gains `test_seed_creates_the_entry_from_the_registry`, `test_seed_does_not_replace_an_existing_entry_without_force`, `test_seed_reports_a_stale_fingerprint`, `test_export_strips_repository_facts_and_root_paths`, and `test_check_fails_on_a_broken_registry_file`. Run `python3 -B -m unittest discover -s skills/scoussens-skills/harness-discovery/evals -v`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes at the PR head on the `swarm workers` line (`inherit`), per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the existing `test_state.py` cases at trunk and at head. Save `regression.log`. Pass when both print `OK` and head adds five cases.
- [ ] Lane 2. In a fresh `git init` directory, run `seed --harness Amp` inside this orb. Save `seed-fresh.log`. Pass when the output starts with `fresh` and `check discovery` prints `PASS`.
- [ ] Lane 3. Edit the registry fingerprint value to `0.0.0` and run `seed` in another fresh directory. Save `seed-stale.log`. Pass when the output starts with `stale` and names both versions.
- [ ] Lane 4. Run `seed --harness Amp` with `PATH` emptied of `amp`. Save `seed-unverifiable.log`. Pass when the output starts with `unverifiable` and the entry is still written.
- [ ] Lane 5. Run `seed` twice without `--force`. Save `seed-idempotent.log`. Pass when the second run changes no bytes of `discovery.json`.
- [ ] Lane 6. Seed, then run the workspace's `pstack-sync sync --dry-run` against a fresh install directory that has only the pack's seeds. Save `pstack-uses-seed.log`. Pass when `profile_gaps` is empty.
- [ ] Lane 7. Seed, edit `skills.locations` to include the clone's absolute path, run `export`. Save `export-sanitizes.log`. Pass when `grep -c "$PWD" registry/amp.json` prints `0`.
- [ ] Lane 8. Corrupt `registry/amp.json` by deleting `owner_term`, run `check discovery`. Save `check-registry.log`. Pass when the output contains `FAIL` and names `registry/amp.json`.
- [ ] Lane 9. Run `migrate` on a repository that already has a hand-written Amp entry, then `seed`. Save `seed-keeps-existing.log`. Pass when the hand-written `context` text survives.
- [ ] Lane 10. Run `npm run validate` and `npm run check:builder` at head. Save `gates.log`. Pass when both print a `✓` line and no `✗` line.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of `state.py check discovery` at trunk and at head on the same repository, and the diff-added work, `seed`, with an absolute budget.
- [ ] Probe. `time python3 state.py check discovery`, three runs each side interleaved, and `time python3 state.py seed --harness Amp` three runs at head.
- [ ] Baseline. Record the trunk median for `check` first.
- [ ] Rule. Head `check` median within 1.2 times trunk. `seed` completes in under 1 second plus the measured wall time of the fingerprint command run alone, because that command is the harness CLI's startup and not this script's work; record both numbers. Either failing fails.

**Review gate.** None. HF-2 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends HF-2 to the base-branch stack and the operator lands it.

## Answer modes and custom subagents from discovery (HF-3)

**Depends on.** HF-2.

**Files.**

- [ ] Edit `skills/scoussens-skills/harness-discovery/assets/discovery.template.json`.
- [ ] Edit `skills/scoussens-skills/harness-discovery/scripts/state.py`.
- [ ] Edit `skills/scoussens-skills/harness-discovery/registry/amp.json`.
- [ ] Edit `skills/scoussens-skills/harness-discovery/SKILL.md`.
- [ ] Edit `skills/scoussens-skills/pstack-sync/needs.json`.
- [ ] Edit `skills/scoussens-skills/pstack-sync/harness/amp.md`.
- [ ] Edit `skills/scoussens-skills/pstack-sync/evals/test_sync.py`.

**Build.**

- [ ] Add two fields to the template and the checker. `skills.frontmatter` is text naming the frontmatter keys the harness reads and what it does with `mode`, and `helpers.definitions`, text or null describing named subagent definition files and how one is dispatched.
- [ ] In `needs.json`, give `modes` the discovery field `skills.frontmatter` and `custom-subagents` the discovery field `helpers.definitions`, so `harness_facts` answers them and the profile no longer has to.
- [ ] Fill both fields in `registry/amp.json`.
- [ ] Remove the `modes` and `custom-subagents` rows from the shipped `harness/amp.md`, because a row for a discovery-answered need only belongs there at `native` or `keep`.
- [ ] Update `ShippedStateTests` so the shipped profile rows match the needs without discovery fields, which the existing test already enforces.

**You see.**

- [ ] `sync` on a repository seeded from the registry reports `harness_facts.modes.skills.frontmatter` and `harness_facts.custom-subagents.helpers.definitions`, and `profile_gaps` stays empty with the two rows gone.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_sync.py` gains `test_modes_and_custom_subagents_are_answered_by_discovery`. `test_state.py` gains `test_check_accepts_frontmatter_and_definitions_fields`. Run both suites.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes at the PR head on the `swarm workers` line (`inherit`), per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run both suites at trunk and head. Save `regression.log`. Pass when both print `OK` on each side.
- [ ] Lane 2. Seed a fresh repository from the registry and run the workspace `pstack-sync sync --dry-run` against a fresh install. Save `facts-answer-needs.log`. Pass when `profile_gaps` is empty and `harness_facts` has keys `modes` and `custom-subagents`.
- [ ] Lane 3. Remove `skills.frontmatter` from the seeded entry and rerun. Save `missing-field-gap.log`. Pass when `profile_gaps` contains `modes`.
- [ ] Lane 4. Run `state.py check discovery` on the workspace clone's current `discovery.json`, which lacks the two fields. Save `old-entry-still-valid.log`. Pass when it prints `PASS`, because the fields are optional.
- [ ] Lane 5. Clone the workspace, apply the PR's `needs.json` and profile, keep its durable profile unchanged, run `sync`. Save `workspace-unchanged.log`. Pass when `needs_adaptation` is empty, because the durable rows still override.
- [ ] Lane 6. Same clone, delete the two rows from the durable profile, add the two fields to its discovery entry, run `sync`. Save `workspace-promoted.log`. Pass when `needs_adaptation` is empty and `harness_facts` lists both needs.
- [ ] Lane 7. Run `python3 -m json.tool` on the template and the registry file. Save `json-valid.log`. Pass when both parse.
- [ ] Lane 8. Grep the shipped `harness/amp.md` for `modes` and `custom-subagents` rows. Save `rows-removed.log`. Pass when neither appears as a table row.
- [ ] Lane 9. Run `ShippedStateTests` alone. Save `shipped-state.log`. Pass when it prints `OK`.
- [ ] Lane 10. Run `npm run validate` and `npm run check:builder` at head. Save `gates.log`. Pass when both print a `✓` line and no `✗` line.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of `sync --dry-run` on the workspace clone at trunk and at head.
- [ ] Probe. `time python3 pstack-sync/scripts/sync.py sync --dry-run --repo <clone> --harness amp`, three runs each side, interleaved.
- [ ] Baseline. Record the trunk median first.
- [ ] Rule. Head median within 1.2 times trunk.

**Review gate.** None. HF-3 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends HF-3 to the base-branch stack and the operator lands it.

## Declare skill needs in frontmatter and read facts in explain-to (HF-4)

**Depends on.** HF-3.

**Files.**

- [ ] Edit `scripts/validate-skills.mjs`.
- [ ] Create `skills/scoussens-skills/harness-discovery/evals/test_needs_declaration.py`.
- [ ] Edit `skills/scoussens-skills/explain-to/SKILL.md`.
- [ ] Edit `skills/scoussens-skills/explain-to/references/formats.md`.
- [ ] Edit `skills/scoussens-skills/explain-to/evals/evals.json`.
- [ ] Edit `skills/scoussens-skills/visualize-spec/SKILL.md`.
- [ ] Edit `README.md`.

**Build.**

- [ ] Accept `metadata.needs` in `validate-skills.mjs` as a comma-separated string of dotted paths. Resolve each against a harness entry of `harness-discovery/assets/discovery.template.json`. An unknown path is an error that names the skill and the path.
- [ ] Declare `needs: artifacts, skills.load, helpers.invoke` on `explain-to` and `needs: artifacts` on `visualize-spec`.
- [ ] Replace the Amp block in formats.md with one rule. Resolve the running harness's entry with `state.py resolve`, pick the artifact destination whose tool is in your tool list, and name that destination's present and update operations in the hand-off. Keep the no-page-tool fallback.
- [ ] Add an assertion to the explain-to HTML-page eval that the hand-off names the destination from the discovery entry rather than a harness skill by name.
- [ ] Document `metadata.needs` in the README skill-authoring section.

**You see.**

- [ ] `npm run validate` on a temporary skill with `needs: owners.nonexistent` prints `✗ ... unknown need owners.nonexistent` and exits 1.
- [ ] `npm run validate` on the repository prints `✓ 17 skill(s) valid`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_needs_declaration.py` builds a temp repository with the validator and one skill, runs `node scripts/validate-skills.mjs`, and asserts the error text for a bad path and exit 0 for a good one. Run `python3 -B -m unittest discover -s skills/scoussens-skills/harness-discovery/evals -v`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes at the PR head on the `swarm workers` line (`inherit`), per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `npm run validate` at trunk and head. Save `regression.log`. Pass when both print `✓ 17 skill(s) valid`.
- [ ] Lane 2. Add `needs: owners.nonexistent` to a copy of a skill and run the validator. Save `bad-need.log`. Pass when the output names the path and exits 1.
- [ ] Lane 3. Add `needs: artifacts` and run. Save `good-need.log`. Pass when exit 0.
- [ ] Lane 4. Add `needs: artifacts,,skills.load` and run. Save `empty-item.log`. Pass when the output reports the empty item.
- [ ] Lane 5. Run the explain-to HTML-page eval prompt cold against the head skill in this orb. Save `explain-to-handoff.log`. Pass when the reply names the destination from `state.py resolve --harness amp` and not the string `creating-artifacts` as a hand-off target.
- [ ] Lane 6. Run the same eval with `discovery.json` absent. Save `explain-to-no-discovery.log`. Pass when the reply falls back to a Markdown document and says what the page would have added.
- [ ] Lane 7. Run `npm run check:builder`. Save `builder.log`. Pass when it prints `✓`.
- [ ] Lane 8. Run `grep -rn "creating-artifacts\|creating-views" skills/scoussens-skills/explain-to/references/formats.md`. Save `no-hardcoded-names.log`. Pass when it prints nothing.
- [ ] Lane 9. Run `npm run test:skills`. Save `test-skills.log`. Pass when every suite passes.
- [ ] Lane 10. Run the validator on the workspace skills clone root after copying the head validator in. Save `workspace-validate.log`. Pass when no need error appears for the copied skills.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of `npm run validate` at trunk and head.
- [ ] Probe. `time npm run -s validate`, three runs each side, interleaved.
- [ ] Baseline. Record the trunk median first.
- [ ] Rule. Head median within 1.2 times trunk.

**Review gate.** None. HF-4 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends HF-4 to the base-branch stack and the operator lands it.

## Close the program

- [ ] Every box above is checked with its evidence.
- [ ] Reply to the operator with the report the execution playbook names.

## Appendix A. Prototype evidence

Three questions were settled by inspection in this orb on 2026-10-13, before this plan was written.

- Does a registry inside a skill directory ship with the pack? Yes. `scripts/lib/discover-skills.mjs` returns whole skill directories and the workspace copy of `harness-discovery` already carries its `scripts/` and `assets/`.
- Does the discovery checker reject new fields? No. `check_discovery` in `state.py` indexes known keys only, so HF-3's fields can be optional without breaking saved files.
- Is there a cheap fingerprint for Amp? Yes. `amp --version` printed `0.0.1791907253-g874296 (released 2026-10-13T16:00:53.000Z)` in this orb.

Unproven. The fingerprint commands for Cursor and Claude Code. HF-2 ships only the Amp registry entry; another harness adds its entry with its own command when first discovered there.

## Appendix B. Alternatives rejected

- A registry at the repository root, outside any skill. Lost because a skills.sh install ships skill directories only, so the registry would be absent exactly where it is needed.
- Marking local entries inline with a flag on each transform. Lost to a `local` sub-block, which keeps one file one home and lets `seed` drop a block instead of filtering rows.
- Promoting every pstack profile row to a discovery field. Lost because `role-model-config`, `companion-skills`, `cursor-product`, and `bugbot` are pstack substitutions, not harness facts, and `invocation-control` at `keep` must stay a row to keep auto-acceptance.
- A YAML list for `metadata.needs`. Lost because the validator requires string metadata values and a comma-separated string needs no new type rule.

## Appendix C. Risks

- HF-1. A durable `transform.json` from before the split has no `local` block. `State.__init__` tolerates its absence, and lane 5 proves the plain-copy path. The owner watches `local_drift` on the workspace clone.
- HF-2. The seeded Amp entry describes Amp as observed from a Claude Code session inside an orb, so `Task`, `oracle`, and `wait_for_threads` facts come from docs. The entry's limitations say so; the owner keeps that text in the registry.
- HF-3. The workspace durable profile keeps its `modes` and `custom-subagents` rows until someone removes them, and a row overrides discovery. Lanes 5 and 6 cover both states. The owner files the workspace follow-up.
- HF-4. A needs path that exists in the template but is null in a harness entry still validates. Validation checks the vocabulary, not support; the skill must handle null per its own text.

## Appendix D. Links and reading list

- `skills/scoussens-skills/harness-discovery/SKILL.md` and `scripts/state.py` before HF-2 and HF-3.
- `skills/scoussens-skills/pstack-sync/SKILL.md`, `references/adapting.md`, and `scripts/sync.py` before HF-1 and HF-3.
- `docs/writing-good-descriptions.md` and `README.md` state table before HF-4.
- HF-1 and HF-2 get `pstack/skills/how/SKILL.md` over their scripts. HF-3 gets `pstack/skills/interrogate/SKILL.md` because it changes a contract two skills share.
- The decision trail per `pstack/skills/show-me-your-work/SKILL.md` lives at `.amp/in/artifacts/harness-facts/decisions.tsv`, uncommitted.
