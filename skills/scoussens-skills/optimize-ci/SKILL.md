---
name: optimize-ci
description: >-
  Audit a repository's continuous integration for feedback time and runner
  minutes — baselined on comparable runs, every saving bounded by the share of
  the run it can touch, and every change checked against the required checks
  and deploy gates that depend on the pipeline — then recommend, design, or
  implement the changes, on GitHub Actions, GitLab CI, CircleCI, Buildkite,
  Jenkins, Azure Pipelines, or another provider. Load this only when the user
  asks to evaluate or speed up CI as a whole — "why is CI so slow", "audit our
  pipeline", "cut our Actions minutes", "our checks take twenty minutes",
  "speed up the PR build", "are we wasting runner time". Do not load it to
  debug one failing build, to fix a single flaky test, or to write a new
  workflow from scratch; answer those directly instead.
---

# Optimize CI

Treat CI as a measured system with two independent costs: elapsed feedback time
and consumed runner time. A change that improves one can make the other worse.
Preserve the repository's verification and deployment contracts while improving
the objective the user actually values.

## Choose the mode

Infer the mode from the request and state it before acting.

- **Evaluate** — inspect, measure, and recommend. Default to read-only commands.
  Do not modify workflows, provider settings, branch rules, deployment settings,
  the checkout, generated files, dependencies, or persistent caches. Ask before
  running native gates, installs, generators, `npx`, containers, or other commands
  that may write or start paid work.
- **Implement** — make the requested changes, validate them, and report measured
  results. Treat provider and repository settings as separate mutation scopes;
  repository edits do not authorize changing hosted settings.
- **Design** — produce a concrete target workflow when provider data or access is
  unavailable. Label every unmeasured estimate.

Ask only for decisions that repository and provider evidence cannot answer. For
a neutral evaluation, report both pull-request latency and total runner or billed
minutes. Ask the user to choose only when an implementation trades one objective
for the other. Do not ask the user to collect facts you can inspect.

## Step 1 — Read the contracts before the workflow

Read repository instructions, CI configuration, package or build manifests, test
configuration, hooks, deployment configuration, and documentation that names the
gate. Then inspect hosted settings when authenticated access permits it. Public
workflow history is not evidence of private branch rules or deployment settings;
report those contracts as unknown when they cannot be read.

Record these contracts explicitly:

- the canonical verification command and every required status check
- which events and branches must emit checks
- deployment systems that wait for a particular branch, commit, check suite, or
  artifact
- tests, security scans, generated-code checks, or platform matrices whose
  removal changes the assurance level
- runner constraints, secrets, service containers, and trusted or untrusted
  contribution paths

Do not assume that a green pull request is the only consumer. A production deploy
may require a second run on the exact commit at the default branch.

## Step 2 — Establish a comparable baseline

Read [references/measurement.md](references/measurement.md) before collecting or
comparing timings.

On GitHub Actions, start with the collector. It reads only, and it does the
parts that go wrong by hand: it reads required checks from both rulesets and
classic protection, keeps runs of an older workflow file out of the baseline,
separates events, excludes skipped jobs, and withholds percentiles from small
samples:

```bash
python3 scripts/gh_ci_baseline.py                      # list workflows and their state
python3 scripts/gh_ci_baseline.py --workflow ci.yml    # contracts, runs, baseline
python3 scripts/gh_ci_baseline.py --workflow ci.yml --json > baseline.json
```

Treat its output as the baseline's first draft, not its verdict. It cannot see
cache hits, `needs:` edges, or billing multipliers, and it says so.

Use 20–50 recent comparable successful runs when the provider exposes history.
Match history to the exact workflow revision being evaluated, and separate pull
requests, default-branch pushes, scheduled runs, cache-warm runs, and materially
different matrices. When the current topology has fewer runs, use every
comparable run, show the individual values or range, and do not claim p50 or p90
from one or two observations. If history is unavailable, measure the native gate
locally only with write authority, or use provider logs that the user supplies.
Say which evidence is missing and whether a dirty checkout differs from the
hosted revision.

Measure at least:

- end-to-end elapsed time and queue time
- critical-path job and step durations
- sum of runner time across all jobs
- install, generation, build, test, database, artifact, and teardown time
- cache hit rate and transfer time, or explicitly `unknown` when logs do not
  expose them
- failure, cancellation, and retry frequency
- test file and test-case counts where the framework reports them

Use p50 and p90 only for a run class with a meaningful sample. Do not present one
unusually warm run as the baseline. Distinguish provider-billed minutes from raw
runner time when rounding, platform multipliers, or self-hosted runners apply.

## Step 3 — Model the workflow before changing it

Build a compact inventory with one row per job:

| Job | Trigger | Depends on | Runner | p50 | Runner time | Gate or advisory | Output consumer |
| --- | --- | --- | --- | --- | --- | --- | --- |

Identify the critical path separately from total consumption. Quantify the
maximum possible saving from each independent candidate stage before proposing
work. A stage that occupies 8% of the run cannot explain a 50% improvement.
For overlapping setup or topology changes, provide a dependency-aware model and
label it as an estimate rather than adding stage bounds together.

Search first for:

1. full or partial verification repeated without an independent consumer
2. advisory work that cannot affect a decision
3. setup repeated across jobs or matrices
4. pathological test infrastructure, global setup, or per-test cleanup
5. cache misses, oversized cache transfers, and generated work with stable inputs
6. serial dependencies that do not need to be serial
7. excessive parallelism when runner minutes matter more than latency
8. stale matrices, artifacts, reports, or integrations with no owner

Read [references/optimization-levers.md](references/optimization-levers.md) when
ranking or implementing candidates.

## Step 4 — Produce an evidence-backed recommendation

For each recommendation, state:

| Change | Evidence | Feedback-time effect | Runner-minute effect | Assurance change | Risk | Confidence |
| --- | --- | --- | --- | --- | --- | --- |

Use ranges when run variance is material. Separate measured savings from an
upper bound and from an estimate. Recommend deletion only after naming the
consumer or decision that the work does—or does not—serve.

Prefer the smallest set of changes that captures most of the available saving.
Do not redesign the entire pipeline to optimize a minor stage.

## Step 5 — Preserve safety while optimizing

These constraints hold unless the user explicitly chooses a different assurance
level:

- Keep the canonical gate and test semantics intact. Record test counts before
  and after changes that alter test selection or topology.
- Do not rename, remove, or consolidate check-producing jobs when required-check
  settings are unavailable. A matching workflow job name is not proof of the
  hosted rule.
- Cache immutable inputs and reusable outputs, not pass or fail verdicts.
- Make selective execution fail closed. New or unclassified files take the safe,
  broader path until classified.
- Do not cancel default-branch runs when a deployment waits for that exact check
  suite. Cancellation is usually safe only for superseded review commits.
- Keep secrets out of caches and artifacts. Treat caches populated by untrusted
  changes as untrusted input.
- Preserve least-privilege permissions, version pinning policy, provenance, and
  required security scans.
- Do not replace realistic integration behavior with mocks solely for speed.
- Do not change branch rules, hosted settings, deployment settings, or billing
  plans without explicit authority for that scope.

When a repository rule blocks an optimization, present it as a decision with the
reason and expected saving. Do not silently route around it.

## Step 6 — Implement in reversible increments

For implementation mode:

1. Capture the baseline and current contracts in the work log.
2. Make one independently measurable class of change at a time.
3. Run the repository's native gate under comparable conditions.
4. Compare test counts, exit semantics, artifacts, and emitted check names.
5. Run syntax or provider validation for every changed workflow.
6. Inspect the diff for unrelated edits and secret exposure.
7. Use provider runs to confirm the effect when access exists.

Do not claim provider savings from local timing alone. Local benchmarks can prove
a code-level improvement; only provider evidence proves queue, cache, billing, or
hosted-runner effects.

## Step 7 — Validate the result

Prefer at least three before and three after runs from the same run class. If that
cost is disproportionate, run the smallest defensible sample and label the
confidence accordingly.

Validation must cover:

- the native verification gate passes
- the same intended tests and checks run
- required check names still match hosted protection rules
- required branch and event runs still occur
- deployment consumers still receive their expected commit, check, or artifact
- cold-cache behavior remains correct
- warm-cache behavior produces the expected saving
- cancellations, failures, and cleanup still report truthful conclusions

## Report the outcome

Lead with the decision and measured impact. Include:

1. **Verdict** — the dominant bottleneck and the recommended action
2. **Baseline** — run class, sample, p50/p90 elapsed time, runner time, and data
   limitations
3. **Contracts** — required checks, deployment coupling, and assurance preserved
4. **Opportunities** — ranked table with latency, consumption, risk, and confidence
5. **Changes and validation** — only in implementation mode
6. **Deferred decisions** — options that need authority or trade assurance for cost

## Do not use this skill for

- **Debugging one failing build.** Read its log and fix the cause. A baseline of
  thirty runs says nothing about why one of them went red.
- **Fixing a single flaky test.** Flakiness is a reliability cost this skill
  counts, but repairing one test is ordinary debugging.
- **Writing a new workflow from scratch.** With no runs to measure, there is
  nothing to baseline. Write the workflow, and come back once it has history.

It is invoked deliberately, by name or by an explicit request to evaluate or
speed up CI. A full audit reads dozens of runs and their job timings, which is
too much work to spend on a question that did not ask for it.

## Done when

- The baseline separates elapsed time from runner or billed consumption.
- Every recommendation points to observed evidence and a consumer or contract.
- Expected savings are measured, bounded, or clearly labeled as estimates.
- Implemented changes pass the native gate and preserve intended test counts and
  externally required check names.
- Hosted effects are confirmed with comparable provider runs or reported as
  unverified.
