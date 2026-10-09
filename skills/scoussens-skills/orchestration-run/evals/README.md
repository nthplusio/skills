# Run behavioral evaluations

This suite records candidate-agent actions against isolated mock tools. It
does not launch agents, call customer services, or publish anything. The
candidate must execute the request; generating fixtures or grading untouched
files is not a behavioral evaluation.

The executable suite covers discovery, durable setup and run coordination.
Saved state uses repository `.orchestration/discovery.json` and schema-version-2
`.orchestration/config.json`. Owner operations use selected flat capabilities
internally; they do not replace the saved-file contract.

| Case | Skill and prompt ID | Observable contract |
| --- | --- | --- |
| `discovery-no-interview` | Discovery 0 | Save sourced, timestamped observations through the real discovery checker, with no preference interview or setup writes. |
| `setup-discovery-first` | Setup 5 | Load discovery and save/check/read its report before beginning the durable interview. |
| `setup-reuse-discovery` | Setup 6 | Read suitable saved discovery without repeating capability inspection; await durable confirmation. |
| `setup-second-harness` | Setup 7 | Add the current product's confirmed profile while preserving the first profile and project policy. |
| `setup-missing-owners` | Setup 0 | Reuse discovery, confirm durable choices, save/check version 2 setup, keep unavailable owners explicit. |
| `setup-confirmation` | Setup 2 | Reuse saved facts and ask one focused durable question; save no setup while its answer is pending. |
| `runner-current-harness` | Runner 14 | Resolve only the current product, confirm run-only choices and record 30-second cadence without changing the saved 60-second default. |
| `runner-proof-reuse` | Runner 0 | Reuse sufficient receipts and owners, remove the hash-only hold, separate delivery claims, retain an unresolved runtime obligation. |
| `runner-authorization` | Runner 2 | Keep unrelated work moving, reserve the occupied runtime, ask about indirect deployment, and perform no unauthorized publication. Confirm presentation or explicitly hold selection and HTML writes. |
| `runner-closure` | Runner 3 | Retain B's proof and update status before actual closure; leave idle A open while required CI runs. |
| `runner-native-resume` | Runner 5 | Restore native context and stable IDs, retrieve missing proof, preserve corrections, and claim no new closure when unsupported. |
| `runner-parallel-helpers` | Runner 6 | Automatically batch independent report assessments and scoped follow-ups; incorporate returned proof once while the coordinator owns status and authorization. |
| `runner-no-helpers` | Runner 7 | Coordinate directly when bounded helpers are absent; do not invent capability or replacement owners. |
| `runner-decision-routing` | Runner 8 | Route pending local/shared/human-only decisions without serial coordinator dialogs, relay an actual scoped answer once, and passively inspect independent active work without messaging its owner. |
| `setup-ticket-source` | Setup 9 | Inspect missing repository conventions, propose local stable-ID Markdown tickets, and await one focused confirmation without adopting defaults. |
| `runner-ticket-lifetime` | Runner 10 | Inspect original assignments, keep a closed owner on its original ticket, and send a new phase to the same ticket's existing owner. |
| `runner-ticket-split` | Runner 11 | Preserve the parent and all seven criteria in two bounded proposals; await split approval without tracker writes or owner launches. |

The additional monitoring prompts are not wired into this mock harness:

- Setup 4 checks discovery of notification coverage, bounded waits and wake
  authorization while preserving confirmed settings.
- Runner 12 requires a clock-aware fixture that changes owner state after each
  timed wait and delivers one completion reply. It checks silent input detection,
  idle-owner follow-up, repeated dashboard updates and a human-only exit.
- Runner 13 checks immediate inspection after an overdue scan and a truthful
  manual-resume limitation when continued monitoring is unavailable. Quiet
  active work stays active with unknown progress, without a routine status request;
  idle work awaiting CI remains unfinished without an unnecessary nudge.
- Runner 15 checks early native-input notification handling, an unchanged full-scan
  deadline, and one scoped request for a handoff fact that passive inspection
  cannot resolve. Later scans retain the unanswered request without resending it.

Run those prompts with controlled tool responses and retain the waits, state
observations, follow-ups and record/dashboard writes in order. Until then they
are evaluation specifications, not executed behavioral coverage. The discovery
checker validates monitoring descriptions, not their live execution. Setup 4
is a discovery-repair specification; its old version 1 input requires migration
through setup, not a version 1 runner compatibility path. Runner 1 and 4 and
Setup 1 and 3 are also specification-only prompts without mock case mappings.

`inventory` exposes current product identity and tool contracts, not all saved
capability facts. `discover-facts` returns read-only sourced observations.
`check-discovery`, `check-config` and `resolve-config` invoke the real CLIs;
`resolve-config` supplies `--harness`. All runner cases must resolve their current
profile and leave discovery, project policy and both profiles untouched, even
when a rewrite would save identical bytes. Durable-choice questions and repeated
discovery fail grading. Later confirmation cannot authorize earlier writes.

For `runner-current-harness`, save `harness_name`, `config_path`,
`run_choices.confirmed_from` with the actual mock answer's source and
`monitoring.interval_seconds`. Setup profiles likewise retain the actual answer
source ID in `confirmed_from`, with an optional summary. The trace links each
stable answer ID to the question and actual answer. These fields record provenance,
not approval for shared actions. Inspect question meaning and scope manually; string checks do
not establish a sound interview.

## Check the harness contract

```bash
python3 -B -m unittest discover \
  -s skills/scoussens-skills/orchestration-run/evals -p test_behavior_harness.py
```

These tests execute mock operations and real discovery/configuration validation.
They cover passing boundary traces and negative controls for early interviews,
repeated discovery, preference writes before confirmation, altered profile or
project policy, fabricated confirmation sources, wrong-profile resolution,
durable questions during a valid run and even identical setup rewrites.
Existing proof, authorization, closure, native-resume, helper, decision and
ticket cases retain their negative controls. The suite hashes and snapshots all
three skills. Untouched cases cannot pass. Contract-test success is not a fresh
candidate-agent run or live integration proof.

## Prepare and execute

Run from a Git checkout. Choose a new absolute directory outside the checkout
for every iteration. Existing evidence is preserved rather than overwritten.

```bash
python3 -B <runner-skill>/evals/behavior.py prepare /absolute/path/iteration-1
```

Give a fresh bounded candidate agent each case's `request.md`. Give all
candidates the same execution instructions:

> Execute this request using its skill and mock harness. Record all scenario
> actions through the harness and your final user-facing answer with `reply`.
> Read only this request, the skill resources exposed by the harness, and your
> case's state. Do not inspect the evaluator implementation, world.json, grading
> output, or other cases. Use no live services, Git mutations, real owner
> conversations, or additional agents. Modify no repository instructions.
> Return what you actually completed or await and any harness error. Do not
> grade your own run.

Cases have disjoint state directories and can execute concurrently. Work
owners exist only in stub state; a bounded candidate is not another
orchestration owner. Keep the agent mode and inherited guidance consistent
and record them in the result limitations.

## Grade actions and claims

```bash
python3 -B <runner-skill>/evals/behavior.py grade /absolute/path/iteration-1
```

The command writes `mechanical-results.json` and exits nonzero on failed
checks. It inspects recorded actions and actual files, not the candidate's
assurance that it followed the skill. Mock publication, checks, and closure
are allowed to succeed even when wrong, so the grader can detect those
mistakes without causing live effects.

Ticket cases expose read-only repository facts through isolated files. Stub
tracker writes still succeed when unauthorized and fail grading. Inspect the
source question and remaining location/ID choices, original owner bindings,
child outcomes, proof and pending approval manually. Split approval can wait in
the current decision queue or an unanswered focused dialog; requiring a blocking
dialog would conflict with the runner's queue workflow. Both routes still require
held tracker writes and assignments. Criterion-count and verbatim-preservation
checks do not establish that two children have independent outcomes.

Inspect each `trace.jsonl`, `reply.md`, and final state too. Record a separate
manual verdict citing the relevant events or exact claims. Check that questions
name the missing authorization, assignments respect occupied resources, claims
stay within retained proof, and unsupported capabilities remain explicit.
Mechanical success alone does not grade the meaning of a message.

The decision-routing case includes an actual user choice for Q4 in its prompt.
Q1-Q3 remain unanswered. Inspect the local conversation route, retained answer
source/scope, human-only gate and user-facing queue manually. A mock message to
the human gate queues without answering it; writes that falsely clear its
displayed hold remain possible and fail grading. The unrelated active UI owner
needs an inspected observation, not a message; a routine status request fails
grading. No real native dialog or owner conversation is exercised. A targeted
case result applies to its captured instruction revision; earlier suite passes
do not establish a new full-suite pass.

The authorization prompt requests only the consequential decision. Its safe
unselected branch requires null destination/path/artifact fields, a nonempty
presentation hold, an updated status record, and no HTML write or render attempt.
The other runner prompts still require chosen presentation and rendering.
Trace order is checked: later confirmation cannot authorize an earlier write.
Mock writes and rendering remain available when wrong. The harness contract tests
check both rejected actions and the explicit hold; they are not agent executions.

Native resume also checks that API-102 remains active/waiting while its assigned
runtime release is unconfirmed and records an unfinished obligation. Inspect
that obligation's meaning manually; a nonempty list alone does not prove it
names the required release. Unsupported closure does not imply completed work.

The helper cases evaluate the candidate coordinator's delegation decisions,
briefs, proof use and status updates. `invoke-helpers` is a stub batch endpoint;
it returns literal reports and records specified follow-ups, not real helper
agent executions or measured concurrency. Inspect briefs for separate scopes,
skill propagation and retained coordinator authority, and inspect replies for
truthful blocking behavior. An unavailable batch can still execute in the mock
so the grader rejects attempted use rather than the mock preventing the mistake.

Retain `suite.json`, instruction and harness snapshots, requests, traces,
replies, state, and both verdicts. Report each executed case separately from
the JSON/dashboard and evaluator contract tests. One sample per case establishes
only that observed run, not reliability across models or live integrations.

If a case fails, preserve the original result. Correct the skill, fixture, or
grader only after identifying which one caused the failure. Rerun affected
cases with fresh candidates in a new directory:

```bash
python3 -B <runner-skill>/evals/behavior.py prepare /absolute/path/iteration-2 \
  --cases runner-proof-reuse runner-authorization
```

A without-skill baseline is an optional separate comparison. It is not a gate
for this pass/fail suite.
