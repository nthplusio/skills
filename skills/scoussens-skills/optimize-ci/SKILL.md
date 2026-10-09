---
name: optimize-ci
description: >-
  Evaluates, designs, and improves a repository's CI architecture for trustworthy
  feedback, runner cost, and maintainability while preserving merge and release
  contracts. Use when the user asks to audit or speed up CI, reduce CI cost,
  redesign a pipeline, or design CI for a repository without an existing pipeline.
  Supports GitHub Actions, GitLab CI, and other providers. Do not load for one
  failing build, one flaky test, or a narrow workflow syntax question.
---

# Optimize CI

Design CI around the target repository's verification decisions. Improve the
chosen objective without quietly changing what a successful gate guarantees.

## Choose the mode and authority

Infer the mode from the request and state it before acting.

- **Evaluate** inspects evidence and recommends. Keep the target repository and
  hosted settings unchanged. Ask before installs, generators, native gates,
  containers, or paid runs that inspection would require.
- **Design** proposes an initial or replacement architecture. History is optional.
  Label assumptions and estimates, and specify how to validate them. Proposal
  authority does not authorize applying the design.
- **Implement** makes authorized local changes and verifies them. Branch rules,
  hosted settings, deployments, and paid experiments remain separate scopes.

For a neutral audit, consider latency, total consumption, reliability, and
maintenance. Infer priorities from the request and repository evidence. Ask only
when a consequential tradeoff remains unresolved or an action needs authority.
Keep a narrow request narrow; escalate to redesign only when its cause demands it.

## Step 1: Identify the repository and its contracts

Read repository instructions, manifests, native verification commands, test
configuration, CI includes, release configuration, and relevant history. Inspect
hosted protection and deployment settings when readable.

Build a compact profile of deliverables, supported platforms, build and test
tools, external services, contribution trust, release cadence, change volume,
owners, runner classification, billing policy, and practical budgets. Mark
missing facts unknown.

Map every relevant event to its tested revision, required checks, permitted
skips, artifact consumer, and deployment dependency. Include merge queues or
trains, forks, schedules, and releases when the repository uses them. Read the
detected provider's semantics in
[GitHub Actions](references/providers/github-actions.md) or
[GitLab CI](references/providers/gitlab-ci.md). For another provider, consult its
official documentation for these contracts rather than translating GitHub rules.

**Complete when** every existing gate and downstream consumer has an evidence
source or an explicit unknown, and the design objective fits this repository.

## Step 2: Establish evidence, or state the design assumptions

For measured analysis, read [measurement](references/measurement.md). Collect
comparable run classes, unsuccessful attempts, queue delays, task timings, and
cache evidence. On GitHub Actions, run the bundled read-only collector against
the target repository, resolving its path relative to this skill:

```bash
python3 <skill-directory>/scripts/gh_ci_baseline.py --repo owner/repo
python3 <skill-directory>/scripts/gh_ci_baseline.py --repo owner/repo --workflow ci.yml --json
```

The collector is evidence, not a verdict. Inspect its completeness indicators.
It does not classify cache state, resolve the full effective workflow, reconstruct
task dependencies, or establish actual billed cost.

For a repository without history, use its profile and native commands to design
an initial pipeline. Record unmeasured task durations, capacity, and hosted rules
as assumptions. Include a first-run measurement plan instead of inventing a baseline.

**Complete when** each quantitative claim names its population and clock, or is
explicitly an assumption, estimate, or unknown.

## Step 3: Explain the work and its limiting constraint

Map commands beneath jobs, generated inputs, artifacts, and shared resources.
Distinguish ordering edges from data transfers and resource locks. Name the
consumer that justifies each task and dependency.

Read [architecture](references/architecture.md) when designing or changing job
boundaries, events, selection, matrices, concurrency, or artifact flow. Read
[performance](references/performance.md) when queue, setup, computation, I/O,
network, transfer, or test infrastructure limits the requested objective.

For an audit, explain why the observed constraint dominates and what observation
would disprove that explanation. For initial design, identify likely constraints
and the measurements that will decide whether to change the starting topology.

**Complete when** the graph accounts for every proposed task and artifact, and
the recommendation follows from a constraint rather than a generic best practice.

## Step 4: Compare worthwhile designs

Compare keeping the current design with the smallest useful change. Add a larger
redesign only when it solves an observed constraint or a stated new requirement.
For a new pipeline, compare a simple native-command design with any proposed
selector, sharding, or reusable component.

Read [simplicity and maintenance](references/simplicity-maintenance.md) before
adding selectors, custom orchestration, shared workflows, persistent images,
self-hosted runners, or external dependencies. Read [impact](references/impact.md)
when ranking candidates or accepting results.

For each candidate, state evidence, feedback-time effect, total consumption,
assurance change, implementation effort, ongoing ownership, risk, and confidence.
Bound savings by the work it can remove; recompute overlapping critical paths.
State whether the benefit is measured, bounded, or estimated.

**Complete when** the selected design earns its complexity, rejected alternatives
have reasons, cost conclusions respect known billing policy, and "no worthwhile
change" remains an acceptable verdict.

## Step 5: Check safety and failure behavior

These checks apply in every mode. Preserve existing contracts unless the user
explicitly authorizes changing them:

- Keep canonical verification semantics, supported platforms, security controls,
  and externally required check identities. Unknown hosted rules block renaming
  or removing check producers, not further analysis.
- Make selection take the broader safe path for unknown files, missing history,
  or incomplete dependency information. Validate intended task identities and
  partitions, not only unchanged test counts.
- Ensure aggregate gates reject failed, cancelled, or missing required work.
  Accept a skipped task only when a validated selection decision permits it.
- Preserve exact-revision and artifact consumers. Cancel only runs whose
  consumers no longer need them, not main runs that a deployment waits on.
- Keep untrusted code, cache writers, and artifacts outside privileged execution
  unless the consumer verifies the required identity and trust policy. Keep
  secrets out of caches and reports, and preserve least privilege and pinning.
- Reuse native task results only with complete inputs, suitable test semantics,
  and trusted writers. An arbitrary cached "passed" flag is not verification.

Read [reliability](references/reliability.md) for retries, flakes, quarantine,
aggregate gates, cancellation, cleanup, or external-service failures. Read
[security](references/security.md) when a proposal changes credentials, fork
execution, cache access, runner isolation, artifact consumption, or provenance.

**Complete when** every changed decision has failure-state checks, every trust
transition has a control, and remaining risks or authority limits are explicit.

## Step 6: Deliver or implement the design

Evaluate mode delivers a verdict, baseline limits, preserved contracts, and
ranked options. Design mode delivers an event-to-gate matrix, task and artifact
graph, native commands, required hosted configuration, assumptions, owners,
validation plan, and rollback criteria. Show enough concrete configuration to
make the proposal implementable without implying that it has been applied.
Check proposed command names against the repository's native commands and
revision claims against the configured event and checkout behavior. Mark
unresolved configuration inputs explicitly instead of assuming a match.

In implement mode:

1. Capture evidence and contracts before editing.
2. Change one independently verifiable class of behavior at a time.
3. Run native verification and provider syntax validation.
4. Exercise affected events and failure states, including unknown selection,
   cancellation, missing outputs, cleanup, and cold-cache recovery.
5. Compare intended task coverage, check identities, artifact lineage, and
   consumers. Confirm hosted effects only through authorized provider evidence.
6. Record measured results, limitations, ownership, and rollback conditions.

**Complete when** local behavior is verified, unchanged contracts still hold,
and unverified hosted behavior is named rather than claimed.

## Report the decision and delivery state

Lead with the chosen action and why it fits this repository. Include the evidence
and its limits, contract and assurance effects, worthwhile alternatives, and
validation appropriate to the mode. Distinguish proposed, locally verified,
committed, pushed, and hosted-verified work. A local speedup does not establish
queue, billing, or deployment improvements.

For cost conclusions, state the known billing basis even when recommending no
change. Unbilled execution has no direct runner-charge saving; missing prices
do not erase a known billing exemption.

## Scope

Use this skill for repository-level CI analysis and architecture. Debugging one
failure or repairing one flaky test uses ordinary diagnosis; summarize its
pipeline impact here only when it explains the broader constraint. Repository
redesign does not authorize infrastructure changes or production operations.
