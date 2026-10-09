# Collect comparable evidence

## Define the population and clocks

Keep event, tested revision, runner type, matrix, test scope, services, and cache
state explicit. Separate pull requests, integration commits, main pushes,
schedules, and releases. Classify cache state as unknown when logs do not expose
it; a fast install is not proof of a hit.

Match effective configuration, including called workflows, scripts, manifests,
toolchains, and images. A matching top-level workflow blob is only a first filter.
Record local edits or hosted configuration changes that make history incomparable.

Use quantities with named origins:

| Quantity | Origin and endpoint |
| --- | --- |
| First useful feedback | Trigger to the first trustworthy, actionable result |
| Required-gate latency | Trigger to the required decision on the tested revision |
| Run completion latency | Trigger to the last completed job, including downstream work |
| Attempt elapsed | Attempt start to that attempt's last job completion |
| Time to green | Original trigger to successful decision, including retries and human delay |
| Job queue interval | Provider job creation to execution start; verify what creation means |
| Critical-path execution | Longest dependency-respecting execution path, without queue or approvals |
| Raw runner time | Sum of executed job durations across every attempt and conclusion |
| Rounded hosted minutes | Per-job rounding applied to hosted execution, before rates and allowances |

Run completion is not necessarily required-gate latency. The longest job queue
interval is not total queue delay. Do not sum overlapping queue and elapsed
intervals or subtract the longest queue from elapsed to invent execution time.
Creation-to-latest-attempt delay includes retry waits, not only initial queuing.

## Sample steady-state speed and total consumption separately

Prefer 20 to 50 comparable successful first attempts when available. Report sample
size, dates, individual values or ranges, and material workload differences.
With sparse history, show all observations rather than manufacture a stable tail
percentile. The collector's minimum sample thresholds prevent tiny-sample labels;
they do not establish statistical confidence.

Keep failed, cancelled, superseded, and repeated attempts out of ordinary
successful-run speed distributions unless those behaviors are the subject.
Keep their work in consumption totals. State the observation window and coverage
before extrapolating per-run savings to monthly consumption. Partial API reads
are missing evidence, not zero-cost runs.

Capture enough data to explain a result:

- run ID, event, tested revision, configuration revision, timestamps, and conclusion
- each attempt and job, runner labels, execution duration, and queue interval
- task and step durations, intended test identities, and reported test counts
- cache hits, transfer durations, services, and cleanup when logs expose them
- first-attempt failures, retry causes, cancellation reasons, and repair time

Read required-check settings and deployment consumers separately from timings.
Public run history does not establish private protection, secrets, or billing.

## Use the GitHub collector within its limits

Resolve `scripts/gh_ci_baseline.py` relative to the skill directory and run it
against the target repository. Use its JSON output for repeatable inspection.
It paginates workflow and job reads, accounts for attempts, and distinguishes
unknown workflow revisions and incomplete measurements.

The collector's `elapsed` is trigger-to-run-completion, not time to the required
gate. Inspect `attempt_elapsed`, `initial_delay`, job queues, and attempt coverage
before explaining delay. Read the output's completeness warnings and compare the
current workflow file with other configuration inputs yourself.

It does not infer cache hits, classify warm and cold workloads, expand expressions
or reusable workflows, inspect runner utilization, reconstruct `needs:`, or
calculate account charges. Read logs, configuration, and billing evidence for
those facts. Job timestamps suggest concurrency, not proof of a dependency.

## Bound and validate the improvement

Deleting a stage consuming fraction \(f\) of the chosen objective saves at most
\(f\). Reducing that stage by fraction \(r\) bounds direct savings at \(f r\).
For a job graph, recompute the critical path after the change. Competing paths
and shared resources can remove the expected benefit.

For example, replacing a 20-minute job with two 11-minute jobs can reduce elapsed
execution by 9 minutes while increasing raw runner time to 22 minutes. Repeated
setup, transfers, queues, and billing rounding can change both effects.

For a small implementation, aim for at least three comparable observations on
each side. Increase the sample when variance matters. Hold source, runner,
services, scope, and cache state constant where possible. Compare cold and warm
behavior separately, and verify the intended tasks actually ran.

Local probes support code-level claims only. Hosted evidence is needed for
queue, provider-cache, billing, and exact-commit deployment claims. State what
remains unverified and distinguish measured changes, bounds, and estimates.

## Accept the evidence

The baseline is usable when every included run has known scope and complete
timings, excluded consumption is disclosed, and the dominant constraint has
supporting observations. Missing provider access warrants a limited conclusion
or a design assumption, not an invented timing or hosted rule.
