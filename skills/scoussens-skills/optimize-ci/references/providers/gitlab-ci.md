# Apply GitLab CI contracts

## Resolve the effective configuration

Read `.gitlab-ci.yml`, includes, components, child pipelines, workflow rules,
job rules, runner tags, variables, protected branches, environments, and merge
settings. Record installed GitLab version, offering, and feature entitlement.
Syntax and available behavior can differ from GitLab.com.

Use [CI Lint](https://docs.gitlab.com/ci/yaml/lint/) to validate expanded
configuration when authorized. Its default-branch push simulation is not proof
of merge-request, scheduled, fork, or merge-train behavior.

## Separate pipeline creation from job selection

`workflow:rules` controls whether a pipeline exists. Job `rules` selects work
inside it. Both push and merge-request pipelines can run for one push unless
creation rules prevent duplication. Read [job-rule guidance](https://docs.gitlab.com/ci/jobs/job_rules/)
before attributing repeated execution to slow jobs.

`rules:changes` uses different comparison bases for branch and merge-request
pipelines. New branches and non-push events can match broadly without an
appropriate `compare_to`. Confirm the revision range and test schedules, manual
runs, shared inputs, renames, and missing history. Do not assume GitHub path-filter
semantics apply.

Ordinary merge-request pipelines test source content. Merged-results pipelines
test a temporary combined revision and can fall back on conflicts. Merge trains
include earlier queued changes and can regenerate later work after a failure.
Read [pipeline types](https://docs.gitlab.com/ci/pipelines/pipeline_types/) and
[merge trains](https://docs.gitlab.com/ci/pipelines/merge_trains/) before changing
integration assurance or estimating speculative consumption.

## Distinguish scheduling from artifact identity

`needs` can bypass unrelated stage barriers. `needs:artifacts` changes which
outputs download. A `needs:project` download can use the latest successful job
at a ref without waiting for its currently running pipeline. That is not proof
the intended current producer finished. Tie outputs to a pipeline, job, revision,
and digest rather than only a branch name.

[Resource groups](https://docs.gitlab.com/ci/resource_groups/) serialize jobs
across pipelines, separately from runner capacity. Mutual exclusion alone does
not prove deployment order. Some ordering modes need idempotent jobs. Inspect
consumers before using interruption or newer-first scheduling.

## Inspect effective trust and capacity

Parent-project execution of fork CI can use fork configuration with parent
resources. Inspect triggering identity, protected variable and runner settings,
and same-project restrictions using [fork pipeline guidance](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/).
Preserve protected-cache separation and verify who may read and write outputs.

For runner delays, inspect global concurrency, per-runner limits, job-request
concurrency, provisioning, and other projects sharing eligible runners. The
[runner configuration reference](https://docs.gitlab.com/runner/configuration/advanced-configuration/)
describes dispatch limits distinct from execution slots.

## Verify each affected pipeline type

Exercise relevant push, merge-request, combined-revision, train, schedule, manual,
fork, cancellation, and missing-output cases. Check reporting and artifact
consumers as well as successful commands. Use account-specific compute, storage,
and self-hosted cost evidence; do not translate GitHub minute policies.
