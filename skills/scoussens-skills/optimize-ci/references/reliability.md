# Preserve trustworthy failure feedback

## Classify failures before hiding them

Separate product defects, test defects, infrastructure failures, external-service
failures, and unknown causes. Preserve first-attempt logs and test identities
even when a retry succeeds. Measure time to green, repair effort, and retry
consumption instead of reporting only successful-run latency.

Retry a known transient failure with bounded attempts and delay. Rerunning an
entire suite for one flaky test multiplies work and can delay genuine failures.
A successful retry does not establish that the first failure was harmless.

Quarantine needs an owner, reason, expiry or review date, continued visibility,
and restoration evidence. State the lost blocking coverage. Google's
[flaky-test account](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html)
describes these mitigation tradeoffs; its historical rates are not a baseline
for the target repository.

## Define the aggregate decision

Derive expected tasks from validated selection. A successful aggregate must
establish that every expected task completed successfully or reused a valid
native result. A task outside the selected set may be skipped only when the
selection itself succeeded and permits that skip.

| Observed state | Required decision |
| --- | --- |
| Every expected task succeeds | Success |
| Unselected task skipped with validated selection | Allowed if the contract permits it |
| Failed expected task | Failure |
| Cancelled expected task | Non-success |
| Missing task or output | Non-success |
| Missing or failed selection evidence | Broader work, never an empty green gate |
| Expected task skipped without a valid reuse decision | Non-success |

Scheduling an aggregate after failures makes it execute, not decide correctly.
Inspect its exit behavior and required check identity. Validate complete intended
task sets; equal test counts can hide both omission and duplication.

## Make cancellation and cleanup serve consumers

Cancel obsolete review commits only after naming consumers that no longer need
them. An exact-main-commit check, migration, or release artifact may remain needed
even when a newer run exists. Distinguish cancel-in-progress from serialization.

Ensure cleanup runs on relevant failure and cancellation paths and releases
temporary resources and shared locks. Preserve diagnostics before teardown.
Timeouts need a known owner and bounded resources, not silent infinite retries.

## Exercise the failure contract

Validate success, justified skip, invalid skip, selector failure, task failure,
cancellation, missing prerequisite, missing artifact, timeout, and cleanup for
the states the change affects. Inspect provider conclusions rather than assuming
a command wrapper's exit code means the run succeeded. Syntax-only validation
does not prove these decisions.
