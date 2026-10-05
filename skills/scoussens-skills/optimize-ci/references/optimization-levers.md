# CI optimization levers

Choose levers from evidence. The same change can reduce latency, increase runner
consumption, or weaken assurance depending on topology and provider billing.

## Ranking table

| Lever | Typical latency effect | Typical runner effect | Evidence required | Main risk |
| --- | --- | --- | --- | --- |
| Remove duplicate work | Lower | Lower | Same command or coverage repeated with no distinct consumer | Hidden report or deployment consumer |
| Remove ownerless advisory work | Lower | Lower | Result cannot affect merge, deploy, alert, or reviewed artifact | Quiet assurance reduction |
| Cache dependencies or build outputs | Lower | Lower or neutral | Stable input key and expensive reproducible output | Poisoning, stale keys, transfer overhead |
| Reduce repeated setup | Lower | Lower | Setup dominates multiple jobs | Coupling jobs and obscuring failures |
| Parallelize independent work | Lower | Higher or neutral | Serial work lies on critical path | More setup, rounding, and flake surface |
| Combine small jobs | Higher or neutral | Lower | Setup and billing floors dominate | Slower feedback and poorer diagnostics |
| Cancel superseded review runs | Lower queue time | Lower | Old review commits have no consumer | Cancelling an exact-commit deploy gate |
| Optimize test infrastructure | Lower | Lower | Fixtures, services, cleanup, or I/O dominate | Changed isolation or realism |
| Select tests or paths | Lower | Lower | Sound dependency mapping and fail-closed default | Skipped verification for new paths |
| Change runner size | Lower | Higher or lower | CPU, memory, or I/O saturation and pricing data | Paying more without speedup |
| Shard a test suite | Lower | Higher or neutral | Balanced tests dominate critical path | Imbalance and multiplied setup |
| Reduce matrices | Lower | Lower | Unsupported or redundant combinations | Lost platform compatibility |

## Delete duplicate and ownerless work first

Find repeated invocations of the native gate, test suite, build, dependency
installation, code generation, coverage, mutation tests, scans, and artifact
creation. For each invocation, name its consumer:

- required merge decision
- deployment gate
- reviewed report or artifact
- alert with an owner and response path
- compliance or security requirement

If two invocations answer the same question over the same inputs, keep the one
with the clearest contract. If an advisory result has no reader, threshold,
alert, or retention consumer, quantify its cost and propose deletion rather than
quietly retaining ritual work.

## Cache reproducible work, never verdicts

Good candidates include downloaded dependencies, compiler caches, immutable tool
downloads, generated clients, and content-addressed build intermediates.

A safe key includes every input that can change the output, such as lockfile,
toolchain, operating system, architecture, relevant configuration, and source
hash where appropriate. Use restore prefixes only when stale entries are safe to
consume and validate.

Do not cache “tests passed,” lint verdicts, security verdicts, or a whole workspace
whose provenance is unclear. Do not place credentials in caches. Protect trusted
branches from caches that untrusted changes can populate. Measure archive upload
and download time—a large low-hit cache can make CI slower.

## Tune topology against the chosen objective

For feedback latency, parallelize independent critical-path work after accounting
for repeated setup and queue capacity. For runner consumption, combine jobs when
startup, checkout, dependency installation, or billing floors dominate.

Keep required check names stable unless hosted branch rules are changed in the
same authorized operation. A prettier job graph is not an improvement if merge
protection waits forever for an old context.

Use concurrency cancellation for superseded pull-request commits when no consumer
needs them. Do not cancel default-branch runs when a deployment waits for the
exact commit's successful check suite.

## Optimize test infrastructure before reducing test scope

Profile test discovery, environment startup, migrations, fixture creation,
database cleanup, browser startup, external service emulation, and teardown.
Common high-leverage changes include:

- start an expensive service once per worker or project instead of once per test
- use transactions when every write shares the injectable connection
- truncate only when another handle escapes the transaction
- derive cleanup metadata once rather than rediscovering it per test
- use disposable in-memory filesystems or databases only when semantics match
- disable durability settings only for throwaway test databases
- split database-free tests from database tests with an explicit, validated list
- balance shards using measured duration rather than file count

Preserve constraints, migrations, query semantics, authorization seams, and
isolation. A faster fake that no longer exercises the failure class is an
assurance change, not an optimization.

## Select work only with a fail-closed design

Path filters and affected-test selection can save large amounts in monorepos,
but only if the dependency mapping is trustworthy.

- New or unclassified paths run the broader safe gate.
- Shared configuration, lockfiles, toolchain files, workflow files, and generated
  contracts invalidate all affected consumers.
- A selector validates that every known file belongs to a class.
- The full gate still runs on a cadence or protected branch appropriate to the
  repository's risk.
- The mechanism has tests that prove both skip and run decisions.

Documentation-only skipping is a product decision when repository instructions
define one canonical gate. Quantify the saving and propose the rule change; do
not silently contradict it.

## Treat matrices, runners, and billing as product choices

Remove a platform or version only with support-policy evidence. Test a larger
runner when CPU, memory, or I/O saturation explains the critical path, then
compare both elapsed and billed cost. A twice-as-expensive runner that finishes
slightly faster can be correct for latency and wrong for consumption.

For self-hosted runners, include idle capacity, autoscaling lag, maintenance,
image warmup, and queue saturation. “No billed minutes” does not mean no cost.

## Preserve supply-chain controls

Optimization must not weaken action pinning, package integrity, provenance,
artifact attestations, secret boundaries, fork isolation, or least-privilege
permissions. Faster dependency installation is not worth executing mutable or
untrusted code with broader credentials.

