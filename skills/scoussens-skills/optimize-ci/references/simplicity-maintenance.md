# Make the design worth operating

## Compare complexity against a named benefit

Compare the current design, a native-command change, and any proposed custom
selector, reusable component, generated matrix, or orchestration script. Name
the measured duplication or requirement that the extra mechanism solves.

Count places a maintainer must inspect to answer what runs and why, hidden defaults,
configuration overrides, copied dependency maps, and cross-repository callers.
Keep business verification in native commands that developers can run locally.
Keep provider configuration responsible for events, permissions, scheduling,
and transfer rather than a second implementation of application checks.

Shared workflows earn their place when they centralize a cohesive policy or
remove costly drift. A few repeated commands may be cheaper than nested workflows
with many inputs and overrides. Make caller inputs, outputs, permissions, and
secret propagation explicit. Pin revisions and test representative consumers.

Delete advisory work only after checking for a reader, threshold, merge decision,
deployment, alert response, retained artifact, or compliance consumer. A report
being non-blocking is not proof that it is unused.

## Assign the operating work

For each new persistent mechanism, identify owner, update source, expected
maintenance effort, failure diagnosis, and retirement condition:

| Mechanism | Operating decisions |
| --- | --- |
| Runner fleet or image | Patching, capacity, provisioning, isolation, stale image recovery |
| Shared workflow or action | Revision updates, consumer tests, rollout and rollback |
| Selector or shard map | Input coverage, dependency changes, imbalance, broader fallback |
| Cache | Trusted writers, invalidation, eviction, cold recovery, quotas |
| Artifacts and reports | Consumers, retention, access, storage growth, deletion policy |
| External service | Availability, credentials, throttling, replacement and failure visibility |

Use existing ownership and dependency-update mechanisms. Do not create a new
service or platform merely to maintain a small pipeline. Unowned maintenance
is a cost to resolve or a reason to reject the proposed mechanism.

## Verify update and recovery behavior

Test a dependency or toolchain update, unavailable cache, missing artifact,
and configuration change where the mechanism can be invalidated. Ensure a
maintainer can reproduce the failing native command and locate its diagnostics.
Check that shared-component updates preserve consumer contracts before rollout.

Accept the design when its owner can explain, update, recover, and retire it
without reconstructing undocumented state. If expected benefit is negligible,
keep the simpler pipeline. Rank the net value using [impact](impact.md).

Provider examples include [GitHub reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)
and [GitLab components](https://docs.gitlab.com/ci/components/). Recheck their
version, permission, and configuration-merging constraints for the target system.
