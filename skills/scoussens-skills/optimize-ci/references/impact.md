# Decide whether the change earns its cost

## Compare benefits and obligations

Rank candidates against the user's objective and the repository's risk. Include
the current design as an option. For a new pipeline, compare a simple initial
design with the additional mechanisms proposed.

| Candidate | Evidence | Latency | Total consumption | Assurance | Effort and owner | Risk and confidence |
| --- | --- | --- | --- | --- | --- | --- |

Distinguish measured benefit, a theoretical bound, and an estimate. Include run
frequency, retries, superseded work, storage, transfer, idle fleet cost, and
maintenance where evidence permits. A faster individual run may raise monthly
consumption. Unbilled runner savings can still improve feedback or capacity;
evaluate that benefit separately from monetary savings.

Do not monetize developer waiting with invented salaries or assume that every
saved minute becomes productive work. Report observed waiting and diagnosis
cost, or label an agreed valuation as an assumption. Use actual account prices
and billing policies for monetary conclusions.

## Prefer changes with evidence and low operating cost

Delete redundant work after checking its consumer. Tune a measured dominant
stage before adding mechanisms to minor stages. Consider uncertain benefits,
cross-repository blast radius, update effort, and assurance losses when ranking
selectors, runner fleets, reusable workflows, and new services.

Recommend no change when benefit does not justify churn. If a contract blocks
an otherwise useful improvement, state the contract and estimated benefit as a
decision requiring authority. Do not quietly weaken it.

## Define acceptance and rollback before rollout

Name the expected result, comparable workload, observation period, assurance
checks, and rejection condition. Separate first useful feedback, required-gate
completion, and release readiness. Track first-attempt reliability, retry cost,
queue delay, and time to green alongside successful-run duration.

Specify how to restore the previous behavior and how exact-revision or artifact
consumers stay served during transition. A selector can first run in shadow
mode against the full gate; treat its added consumption as experiment cost.
Hosted experiments require authority for the affected settings and paid work.

Accept the improvement when observed outcomes meet the agreed criteria without
unapproved assurance or maintenance changes. State unverified provider effects.
[DORA delivery outcomes](https://dora.dev/guides/dora-metrics/) can provide longer-term
guardrails for the same application, but CI timing alone does not establish
commit-to-production improvement or causal delivery impact.
