# Design the task and artifact graph

## Gather the contracts beneath jobs

Expand includes, reusable workflows, matrices, task-runner commands, and downstream
pipelines. Use native graph exports when available. For each task, identify
declared inputs, outputs, toolchain, resource requirements, trust level, owner,
and verification consumer.

For each event, record a contract row:

| Event | Tested revision | Required decision | Task set | Allowed skips | Artifact consumer |
| --- | --- | --- | --- | --- | --- |

Distinguish source-branch checks from combined integration revisions and release
commits. Include hosted check-source restrictions and approval dependencies.

Draw task dependencies and artifact transfers separately. Label service locks
and environment serialization explicitly. A job that starts after another ends
may be queued or blocked by an approval, not dependent on that job's output.

## Choose boundaries that serve decisions

Start a new pipeline with existing native verification and build commands.
Resolve each proposed invocation against the manifest or command definition.
Keep descriptive task labels separate from executable script names; a matrix
label such as `unit` does not imply that `npm run unit` exists.
Separate tasks when they require different trust, platforms, services, artifacts,
or useful failure diagnosis. Parallelize independent decisions only when capacity
permits it. Avoid serial stage barriers that have no ordering or data reason.

Remove duplicate work only when the inputs, assurance, and consumers are the same.
An exact-main-commit deployment check is not automatically redundant with a
pull-request result. Cheap early checks can save failed-run consumption, but a
serial lint barrier can delay successful critical-path tests. Use observed failure
patterns and the chosen feedback objective to decide.

For matrices, connect each dimension to a support promise or an observed defect
class. For sharding, validate complete non-overlapping task assignment, shared
setup cost, and diagnostic artifacts. Removing a supported platform changes
assurance even when another platform passes.

## Place each check at the stage that needs its answer

Ask which decision consumes a check's result, then run it at the earliest
event that decision needs and no more often. A typical split:

| Stage | Answer it owes | Typical work |
| --- | --- | --- |
| Pull request or merge queue | Is this change safe to merge? | Selected tests, lint, types, required security checks |
| Push to the default branch | Did the merge break something immediately? | Small regression and protocol guards, exact-commit deploy checks |
| Scheduled validation | Does a named recent revision pass the broad suite? | Full matrix, slow integration, broad security analysis |
| Release | Does the shipped version pass its release gates? | Release qualification on the exact release revision |

Moving broad work from every main push to a schedule removes whole runs, but it
creates obligations. The scheduled job must test a named revision, retain its
results, and route failures to an owner who repairs them. An older green run is
not proof for a newer commit. Keep release gates bound to the shipped revision.
Moving a check changes when its answer arrives; it must not make a required
answer optional. Name the defect-detection delay this introduces and who
accepts it.

For a schedule, reuse an unchanged prior result only when its inputs match and
its writer is trusted, and expire it after a stated age. When superseding pushes
are frequent, a short admission delay or concurrency group can cancel work
before a runner starts. Apply it only to runs whose consumers no longer need
them, per [reliability](reliability.md).

Automated reviewers, maintenance bots, and agents that push are CI consumers
too. Count their runs and pushes in the event inventory. Prefer one automatic
review per pull request with later reviews on request, and a debounce or
concurrency group for agents that push repeatedly. A requested review is not a
passing review, and required review rules stay in place.

## Decide skips before paying for the runner

A skip decided at pipeline or job creation saves the runner, its startup, and
its setup. A skip decided inside a step has already paid for all three. For each
conditional task, record where its skip decision runs and move it to the
earliest point that has enough information to decide correctly. A cheap
planning job that emits the selection can gate many expensive jobs.

Moving a skip earlier can change required-check behavior. A job skipped by its
condition and a workflow or pipeline that never starts report differently. Read
the provider reference before moving a decision that a required check depends on.

## Make selection depend on declared inputs

Use changed inputs and transitive consumers, not only directory prefixes. Inspect
the event's base and head revisions, available history, generated contracts,
shared configuration, lockfiles, and toolchains. Unknown inputs take the broader
safe route. Prefer the repository's task graph over a second manually maintained
dependency map.

Exercise additions, deletions, renames, unknown files, broad diffs, and missing
comparison history. Prove both narrow and broad selection. Compare task identities
with the full gate before relying on a selector; shadow runs find omissions but
do not prove graph completeness. Retain full verification at an appropriate
integration point or cadence. See [Nx affected execution](https://nx.dev/docs/features/ci-features/affected)
for one native implementation, not a requirement to adopt Nx.

Before a selector may skip work, require these rollout gates:

- **Backtest against real regressions.** Replay the revision before each past
  fix through the selector. Confirm it selects the test that exposed the bug,
  then run that test and see it fail. Include deleted files, shared helpers,
  fixtures, and renames, not only sibling-test cases. A miss is a rule to
  repair or a reason to widen the fallback.
- **Record the prediction before the run.** In shadow mode, save the selected
  set before any test starts and run the full set independently. A failure
  outside the prediction is a miss. Nothing from the run may flow back into
  that prediction.
- **Size the evidence.** Zero misses across \(N\) independent faulty changes
  still allows a miss rate near \(3/N\) at 95% confidence; for small \(N\),
  report the exact bound \(1 - 0.05^{1/N}\). Count revisions from
  one regression episode once. State the accepted miss budget before enabling
  skips.
- **Reject incomplete plans.** When a selected test has no known owner, shard,
  or runtime, reject the narrowed plan and run the broader set. An empty
  narrowed plan is never a successful test run.
- **Keep a switch.** One setting, such as a repository variable, must restore
  full selection without editing tests or workflows.

A learned or model-ranked selector follows the same gates and has no skip
authority until it beats the deterministic dependency graph on the same
backtest.

## Bind artifacts to their consumers

For each transferred output, name producer, source revision, build inputs,
platform, digest, access policy, retention, and consumer. A best-effort cache
is not the sole delivery channel for a required output.

Promote the tested artifact when the release contract permits it. Rebuilding
for a different target or authorized source revision may require another build
and verification decision. A matching branch name, upload, or checksum alone
does not establish trusted provenance. Cross-project "latest successful" outputs
may belong to an older pipeline.

## Verify the proposed graph

Check that every required event emits its expected decision on the intended
revision. Exercise unknown selection, empty selection, failed prerequisites,
cancelled work, missing artifacts, approvals, and shared-resource ordering.
Use the provider references for skip and artifact semantics, and
[reliability](reliability.md) for aggregate decisions.

Accept the design when each task and edge has a consumer, each consumer receives
the intended verified inputs, and each unsupported assumption has a validation
plan. A syntax-valid graph alone does not meet those conditions.
