# Diagnose the measured constraint

## Choose a discriminating observation

| Suspected constraint | Evidence to gather | Candidate experiment |
| --- | --- | --- |
| Shared-runner queue | Eligible slots, ready-job backlog, arrival rate, pool limits, provisioning delay | Reduce obsolete demand or alter dispatch within authorized scope |
| Repeated setup | Checkout, image pull, toolchain, install, generation, service startup per job | Reuse valid outputs or consolidate jobs with the same contract |
| Computation | CPU saturation, task concurrency, compiler or test profiles | Tune workers or trial a runner size under comparable workloads |
| Memory or I/O | Memory pressure, swapping, disk wait, database and filesystem timing | Reduce contention or change disposable test infrastructure |
| Transfer or network | Cache and artifact size, hit rate, download, compression, upload | Compare uncached and cached end-to-end work |
| Uneven tests | Per-file or per-case durations, setup per worker, shard completion | Balance measured work rather than file counts |
| External dependency | Service wait, throttling, transient errors, image and registry location | Isolate the dependency cost without changing integration semantics |

Profile inside a dominant command before changing the graph around it. Native
build-tool traces can separate analysis, actions, idle workers, and critical-path
work. [Bazel performance metrics](https://bazel.build/advanced/performance/build-performance-metrics)
illustrate this method. Use the repository's equivalent tool rather than adding
Bazel merely to collect profiles.

## Check capacity before increasing parallelism

Account for other repositories using the same pool, eligible runner labels,
slot limits, container startup, and nested test-worker concurrency. More CI jobs
do not create more capacity. A saturated pool can convert shorter jobs into
longer queues and multiply setup.

With fixed durations and identical slots, execution cannot beat
\(\max(P, W/C)\), where \(P\) is the dependency critical path, \(W\) is total
work, and \(C\) is slot capacity. This lower bound is not a prediction for
heterogeneous runners, locks, autoscaling, or resource contention. Use observed
arrival and duration distributions when shared demand matters.

Reject a larger runner recommendation without evidence of the resource it fixes.
Include prices, rounding, idle fleet cost, warmup, and maintenance from the
account's actual policy. No provider bill for self-hosted execution does not
mean free capacity.

## Reuse work with complete inputs

Measure both cache-hit rate and transfer cost. A large low-hit cache can lose to
a clean install. Keys must cover relevant source, lockfiles, configuration,
toolchain, operating system, architecture, and environment inputs. Restore
prefixes are appropriate only when consuming stale contents remains correct.

Native dependency-aware test-result caching can be valid. For example,
[Bazel's result cache](https://bazel.build/docs/user-manual#cache-test-results)
reruns changed tests and dependencies, external tests, repeated tests, and failed
tests under its `auto` policy. Assess declared inputs, external state, trust in
writers, and uncached validation. Never substitute an arbitrary saved "passed"
flag for a gate. Move cache trust decisions to [security](security.md).

## Improve test infrastructure without removing realism

Profile discovery, service startup, migrations, fixtures, browser startup,
cleanup, and teardown separately from test assertions. Useful candidates include
one service per worker, reusable cleanup metadata, and balanced worker assignment.
Transactions work only when all test writes use the injected connection. A write
through another handle requires another isolation mechanism.

Use in-memory databases or reduced durability only when relevant semantics remain
equivalent and data is disposable. Preserve migrations, constraints, authorization,
query behavior, isolation, and expected failure classes. Replacing realistic
integration with a faster fake is an assurance decision, not a timing fix.

## Verify the explanation

Run the smallest authorized experiment whose result separates competing causes.
Check intended work, resource use, cold and warm behavior, setup duplication,
and both latency and consumption. Keep measured savings separate from the upper
bound in [measurement](measurement.md). Reject an optimization when it moves the
constraint or loses assurance without achieving the chosen objective.
