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
