# Make each test earn its execution

## Question the suite before speeding it up

Faster runners and narrower selection still execute tests that protect nothing.
When test execution dominates the objective, or the suite grows faster than the
code it covers, audit what the tests protect before tuning how they run. Suites
grown by coding agents often accumulate tests that restate the implementation,
duplicate another owner's coverage, or assert facts a stronger assertion already
implies.

Deleting or consolidating a test changes assurance. Treat it as a contract
decision with evidence, not a cleanup chore or a timing fix. Never rank tests
for deletion by runtime alone; a fast test can protect nothing, and two similar
tests can protect different behavior.

## Audit one subsystem at a time

Read the production code before its tests. For each test or assertion, record:

| Question | Evidence that answers it |
| --- | --- |
| Which behavior contract does it protect? | Caller-visible behavior, error class, platform promise, or regression issue |
| Which plausible bug makes it fail? | A named mutation or a past defect, not "it covers this file" |
| Which other test owns the same contract? | The strongest retained test, located by name |
| Does it fail on harmless refactors? | Mocks of call order, private helpers, incidental formatting |
| Does it pass when the behavior is broken? | A planted fault the test misses |

Classify each candidate as keep, consolidate into a named owner, repair, or
delete. Repair a valuable flaky test rather than paying its retry cost. Keep
platform, integration, and end-to-end boundaries that protect distinct behavior
even when unit tests appear to cover the same code.

## Prove the retained owner still catches the bug

Before deleting or consolidating, plant the fault the removed test was meant to
catch and show that a retained test fails. Revert the fault afterward. When a
fault cannot be planted, keep the test or record the unproven gap as a risk.
Never delete the only useful regression guard to make a failure or a budget
problem disappear.

Report removed lines and files as maintenance evidence, not as a CI saving.
Measure execution time on the affected jobs before and after under comparable
conditions; a large line reduction can save little runtime, and the reverse.

## Limit growth with a visible budget

Without a counter-pressure, agents add tests for every change because adding
looks thorough and deleting needs proof. Recommend a test-growth guard only when
the repository's evidence shows sustained growth without matching contract
coverage. Make growth visible per change, allow a stated net amount, and require
a recorded justification for larger additions. Reward consolidation, but never
let a budget justify deleting an independent safety contract.

The guard is a new persistent mechanism. Give it an owner, an override path,
and a retirement condition per [simplicity and maintenance](simplicity-maintenance.md).

## Accept the cleanup

Accept a deletion or consolidation when its contract has a named retained owner,
a planted fault proved that owner fails, affected native checks pass, and the
removed coverage is listed in the report. Do not target a deletion percentage.
In evaluate and design modes, present candidates and their evidence; deletion
itself requires implement authority.
