# Diagnose the measured constraint

## Choose a discriminating observation

| Suspected constraint | Evidence to gather | Candidate experiment |
| --- | --- | --- |
| Shared-runner queue | Eligible slots, ready-job backlog, arrival rate, pool limits, provisioning delay | Reduce obsolete demand or alter dispatch within authorized scope |
| Repeated setup | Checkout, image pull, toolchain, install, generation, service startup per job | Reuse valid outputs or consolidate jobs with the same contract |
| Computation | CPU saturation, task concurrency, compiler or test profiles | Tune workers or trial a runner size under comparable workloads |
| Memory or I/O | Memory pressure, swapping, disk wait, database and filesystem timing | Reduce contention or change disposable test infrastructure |
| Transfer or network | Cache and artifact size, hit rate, download, compression, upload | Compare uncached and cached end-to-end work |
| Uneven tests | Per-file or per-case durations, setup per worker, shard completion | Pack small shards, then balance measured work rather than file counts |
| Oversized runner | Peak CPU and memory against the runner class, billed units per job | Trial a smaller class on the identical workload |
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

## Pack work into jobs, then balance the jobs

Sharding divides work into jobs; parallelism decides how many run at once.
Treat them as separate decisions. Each job repeats queueing, startup, checkout,
install, and fixture setup, so more shards multiply that overhead and total
runner time even when wall time falls.

1. **Pack.** Measure each job's setup share. When setup rivals the useful work,
   merge shards that share a toolchain, services, and trust level until setup
   is a small share of each job. Keep apart suites that need isolation or
   distinct diagnostics.
2. **Balance.** Assign work by measured per-file or per-case duration, not by
   file count, so jobs finish together. A job that finishes early cannot help
   the straggler that owns the remaining work. Balancing can justify more jobs
   when one straggler sets the critical path.

Report both effects for any sharding change: critical-path time and total
runner time, including billing rounding per job. Fewer jobs is not the
objective, and neither is more.

## Size runners to the work in both directions

Reject a larger runner recommendation without evidence of the resource it fixes.
Question oversized runners the same way: a job that cannot use its cores or
memory pays for idle capacity. Trial a smaller class on the identical workload
and record elapsed time, peak memory, out-of-memory events, and billed units on
both classes. A smaller runner can cut cost and lengthen the wait; report the
tradeoff against the stated objective rather than either number alone.

Qualify runner classes per job class. Serial tooling and lint often fit small
runners; memory-heavy builds and analysis may need to stay large. Watch billing
rounding: a small overhead that crosses a billed-minute boundary can erase a
saving. Include prices, rounding, idle fleet cost, warmup, and maintenance from
the account's actual policy. No provider bill for self-hosted execution does
not mean free capacity.

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

## Catch cheap failures before the push

A formatting or lint failure found in CI costs a runner, its setup, and a
round trip for the author or agent. When first-attempt failures are often
deterministic and cheap to detect, recommend a local path: formatting, lint,
and a focused test command, plus type checking where its latency fits. Make the
path one native command that people and agents both run, such as a pre-commit
or pre-push hook. Keep the same checks required in CI; a skipped hook proves
nothing.

On the checks authors wait for, a faster equivalent tool can cut the wait.
Qualify it against the canonical tool on the same inputs, keep the canonical
tool at release or scheduled validation, and fall back to it where the faster
tool lacks support.

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
