# CI architecture methods beyond latency optimization

Research date: 2026-10-09. Scope: primary-source research for improving
`skills/scoussens-skills/optimize-ci`, not an audit of this repository's CI.
The coverage and collector findings below describe the pre-change skill at
[`1175987`](https://github.com/nthplusio/skills/commit/1175987a3a96614345ef5cb930ca1ed5b504e56c),
including its original `optimization-levers.md`. The proposed split records the
research recommendation; subsequent implementation and evals may refine it.

## Preserve the measurement method and add an architecture model

The skill already distinguishes feedback latency from runner consumption,
requires comparable samples, bounds savings by affected work, discovers merge
and deployment contracts, and protects selective execution and credentials.
Those are useful foundations. A repository-specific CI architect also needs to
explain which work must happen, which artifact each decision verifies, who can
influence that work, and who maintains it.

Recommendation: extend the method with task and artifact dependency graphs,
capacity analysis, executable gate contracts, and reliability and maintenance
policies. Choose the depth from repository risk and observed constraints. This
does not justify imposing a monorepo build tool or redesigning every pipeline.

## Source-linked claims

The facts column reports source-owned behavior. The final column contains
recommendations derived from those facts, not provider requirements.

| ID | Source-owned fact and precise source | Recommended repository use |
| --- | --- | --- |
| C1 | [Bazel trace profiles](https://bazel.build/advanced/performance/json-trace-profile) expose action concurrency, CPU use, garbage collection, and the critical path. They distinguish slow actions from idle workers and analysis overhead. | Profile inside the slow job. Wall time alone cannot identify CPU, I/O, dependency, or setup constraints. Use the repository's build-tool equivalent. |
| C2 | [Google SRE overload analysis](https://sre.google/sre-book/handling-overload/#the-pitfalls-of-queries-per-second-bEsQiL) favors resource-based capacity over request-count proxies and discusses retry budgets. This source describes services, not CI. [GitLab Runner configuration](https://docs.gitlab.com/runner/configuration/advanced-configuration/#long-polling-issues) distinguishes global `concurrent`, per-runner `limit`, and job-request `request_concurrency`. Long polling can delay dispatch despite available execution capacity. | Adapt resource and retry analysis to runner pools. Separate dependency waiting, dispatch delays, occupied slots, provisioning, and actual resource saturation before adding workers. |
| C3 | [Bazel performance metrics](https://bazel.build/advanced/performance/build-performance-metrics) distinguish target, configured-target, and action graphs through `query`, `cquery`, and `aquery`. Execution-graph logs support critical-path drag analysis, the time potentially saved by removing a node. | Distinguish package dependencies, executable tasks, and CI scheduling. Recompute competing paths after a topology change rather than treating a critical node's duration as guaranteed savings. |
| C4 | [Nx affected execution](https://nx.dev/docs/features/ci-features/affected) combines changed files, a project graph, and dependent projects. Its recommended CI base is the last successful main-branch commit. Lockfile changes affect all projects by default. Widely used projects can still affect most of a repository. | Validate the graph and comparison commits before selecting work. A path-to-job map is insufficient for transitive consumers. Last-successful baselines matter when earlier default-branch changes failed or never ran. |
| C5 | [GitHub dependency caching](https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching#artifacts-versus-dependency-caching) and [GitLab caching](https://docs.gitlab.com/ci/caching/#how-cache-is-different-from-artifacts) distinguish optional reusable caches from artifacts that transfer job outputs. Both require correctness without a cache hit. | Give artifacts producer, consumer, commit, digest, retention, and access contracts. Do not use a best-effort cache as the only transfer channel for a required build output. |
| C6 | [GitLab `needs`](https://docs.gitlab.com/ci/yaml/needs/) bypasses unrelated stage barriers. [`needs:artifacts`](https://docs.gitlab.com/ci/yaml/#needsartifacts) limits downloads to listed dependencies. [`needs:project`](https://docs.gitlab.com/ci/yaml/#needsproject) downloads the latest successful specified job at a ref without waiting for a pipeline already running at that ref. | Model ordering and artifact identity separately. Replacing stages with a DAG can change downloads. A cross-project artifact fetch is not proof that the current producer completed. |
| C7 | [GitHub required-check troubleshooting](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks#handling-skipped-but-required-checks) distinguishes filtered-out workflows, whose checks remain pending, from conditionally skipped jobs, which report success. Failed prerequisites can skip dependent jobs without blocking a merge. | A stable aggregate gate must execute on required events and inspect expected task conclusions. Adding `always()` makes the gate run, but does not make its decision correct. |
| C8 | [GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#git-diff-comparisons) uses different diff comparisons for pushes and pull requests. Changed-file limits can prevent a filtered workflow from running. Diff timeouts and sufficiently large commit histories cause it to run instead. | Do not equate native path filters with a fail-closed dependency selector. Test broad diffs, additions, deletions, renames, shared configuration, and missing comparison history. Check limits for the deployed provider version. |
| C9 | [GitHub merge queues](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue) validate temporary combined commits through `merge_group`. Required Actions workflows need that trigger. Failed entries can cause later combined branches to rebuild. Build concurrency is separate from merge limits, which do not combine builds. | Verify required check identity on the combined commit. Include speculative builds and invalidation in capacity and consumption estimates. Do not assume larger merge groups imply fewer CI builds. |
| C10 | [GitLab job rules](https://docs.gitlab.com/ci/jobs/job_rules/#avoid-duplicate-pipelines) can create both push and merge-request pipelines for one push. `workflow:rules` controls pipeline creation. [`rules:changes`](https://docs.gitlab.com/ci/yaml/#ruleschanges) compares merge requests with the target branch and branch pipelines with the previous commit. It evaluates true for new branches and non-push pipelines without `compare_to`. | Analyze event creation before individual job filters. Make comparison bases explicit where needed, without blindly applying one base to every event. |
| C11 | [GitLab merge-request pipelines](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/) test source-branch content. [Merged-results pipelines](https://docs.gitlab.com/ci/pipelines/merged_results_pipelines/) test a temporary source-plus-target commit and fall back to ordinary merge-request pipelines on conflicts. `compare_to` can include target-branch changes. [Merge trains](https://docs.gitlab.com/ci/pipelines/merge_trains/) test cumulative queued changes in parallel and regenerate later pipelines when an earlier entry fails. | Distinguish source-only feedback from integration assurance. A merge train is not interchangeable with an ordinary merged-results pipeline. Record the tested revision and pipeline type. |
| C12 | [John Micco's Google testing account](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html) describes targeted retries and quarantine. Retries delay discovery of genuine failures. Quarantine removes critical-path work but can mask real races. This is a 2016 engineering account, not a current universal flake-rate benchmark. | Preserve first-attempt failures and classify their causes. Use bounded targeted retries, ownership, quarantine expiry, continued non-blocking execution, and explicit restoration criteria. |
| C13 | [GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use) recommends least privilege and full-SHA action pinning. Privileged `pull_request_target` and `workflow_run` processing of untrusted code creates compromise paths. Persistent self-hosted runners can retain compromise. [OIDC](https://docs.github.com/en/actions/concepts/security/openid-connect) exchanges workflow identity claims for short-lived cloud credentials under configured trust conditions. | Trace untrusted code and data to credential-bearing jobs, writable caches, artifact consumers, and runner networks. OIDC requires restrictive trust policies and permissions, not merely removal of stored keys. |
| C14 | [GitLab fork pipeline documentation](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/#use-with-forked-projects) says parent-project runs can use fork-branch CI configuration with parent resources and variables. Protected-resource access has additional same-project, branch, permission, and setting conditions. | Treat running a fork pipeline in the parent as a trust transition. Inspect actual variable protection, triggering identity, runner isolation, and installed GitLab version. |
| C15 | [GitHub cache security](https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching#cache-security) treats restored contents as untrusted and warns that forks can read caches. [GitLab cache separation](https://docs.gitlab.com/ci/caching/#use-the-same-cache-for-all-branches) is a security feature, not just a hit-rate setting. | Separate readers from writers and trusted from untrusted execution. Hashing content or using a lockfile key does not establish who produced it. Inspect effective scopes and overrides. |
| C16 | [SLSA v1.1 build requirements](https://slsa.dev/spec/v1.1/requirements) distinguish provenance integrity from isolation. Build L3 addresses cross-build influence, signing-secret access, and cache poisoning. [Artifact verification](https://slsa.dev/spec/v1.1/verifying-artifacts) checks artifact digest, trusted builder, canonical source, build type, and expected parameters. | Choose controls from a threat model. An uploaded attestation is not an enforced consumer policy or automatic proof of a SLSA level. |
| C17 | [Reproducible Builds definitions](https://reproducible-builds.org/docs/definition/) require bit-identical specified artifacts under the same source, environment, and instructions. [Bazel hermeticity](https://bazel.build/basics/hermeticity) discusses host tools, timestamps, source-tree writes, and undeclared dependencies. SLSA v1.1 isolation explicitly does not require hermeticity. | Test repeatability and environmental variance separately from provenance. A pinned container is useful but does not by itself prove declared inputs or reproducible output. |
| C18 | [Bazel `--cache_test_results` reference](https://bazel.build/docs/user-manual#cache-test-results) deliberately reuses test results. Its `auto` policy reruns changed tests or dependencies, external tests, repeated-run requests, and previously failed tests. [Remote caching](https://bazel.build/remote/caching) documents explicit action inputs and warns about untracked host tools. | Qualify the skill's blanket ban on verdict caching. Arbitrary pass flags are unsafe. Build-tool result reuse needs complete inputs, appropriate test semantics, trusted cache writers, and an uncached validation path. |
| C19 | [GitHub reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows) have explicit inputs and secret propagation, and nested calls cannot elevate token permissions. [GitLab components](https://docs.gitlab.com/ci/components/#write-a-component) recommend few dependencies, pinned revisions, updates, and component tests. Component configuration merges with callers and can collide on names. | Reuse cohesive responsibilities with versioned contracts. Count update effort and cross-repository blast radius. Small duplication can cost less than a dependency chain. |
| C20 | [GitLab CI Lint](https://docs.gitlab.com/ci/yaml/lint/) validates included configuration and can simulate `rules` and `needs`. The documented UI simulation uses a default-branch push, not every event. [GitHub matrix fail-fast](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstrategyfail-fast) cancels queued and running matrix jobs after relevant failures. | Syntax validation is necessary but not an event-state test. Exercise cancellation, reporting, cleanup, and integration events separately. |
| C21 | [GitLab resource groups](https://docs.gitlab.com/ci/resource_groups/#process-modes) serialize matching jobs across project pipelines. Default `unordered` mode does not guarantee execution order. Newest-first modes require idempotent jobs. | Model environment locks separately from runner capacity. Mutual exclusion does not establish deploy ordering or authorize dropping an exact-commit consumer. |
| C22 | [DORA CI guidance](https://dora.dev/capabilities/continuous-integration/) calls for authoritative repeatable packages used downstream and prompt broken-build repair. [DORA delivery metrics](https://dora.dev/guides/dora-metrics/) define change lead time, deployment frequency, failed deployment recovery time, change fail rate, and deployment rework rate. They recommend application-level context and warn against metric targets and disparate comparisons. | Track trustworthy feedback, repair effort, and delivery effects alongside runtime. A faster successful pipeline alone does not prove faster or safer software delivery. |
| C23 | [GitHub event semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request) set `GITHUB_SHA` and default checkout to the test merge revision for an open, mergeable pull request. Checking out `github.event.pull_request.head.sha` instead tests the head. `merge_group` supplies the merge-group revision. | Verify design prose against event and checkout behavior. A configuration that tests the merge revision must not label its result head-only. This fact was checked while investigating an initial-design eval failure. |
| C24 | [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) makes standard GitHub-hosted runner usage free in public repositories. Larger runners are charged even for public repositories. Storage has separate billing rules. | Identify provider and runner class before applying an exemption. Public visibility alone does not establish another provider's billing policy. An eval that expects this exemption must name GitHub Actions and standard runners. |

## An actionable repository-analysis method

The following procedure is a recommendation. It extends the skill's measured,
reversible workflow rather than replacing its baseline or authorization rules.

1. **Define decisions and assurance.** Inventory review, integration, release,
   deployment, security, and compliance consumers. Record required events,
   tested revisions, task identities, check sources, artifact identities,
   owners, and permissible skip conditions. Produce an event-to-gate contract
   matrix, including forks and merge queues or trains. Mark unreadable hosted
   settings unknown. Ask for objectives only when evidence cannot resolve them.

2. **Build task and artifact graphs.** Expand matrices, includes, reusable
   workflows, task-runner commands, generated inputs, and downstream pipelines.
   Annotate each task with inputs, outputs, toolchain, resource needs, gate role,
   and owner. Label edges as scheduling dependencies, data transfers, or shared
   resource locks. Overlay trust boundaries and credential access. Use native
   graph exports where available. Timestamps alone do not prove dependency
   correctness. The output is a graph with every edge justified by a consumer.

3. **Diagnose execution and shared capacity.** Keep the skill's comparable run
   classes. Include unsuccessful attempts in consumption and reliability data.
   Record event, workflow revision, queue timestamps, ready-job backlog, eligible
   runners, pool limits, startup delay, resource profiles, and transfers.
   Distinguish dependency wait from runner queue wait and human approval wait.
   For fixed task durations on identical execution slots, a derived execution
   lower bound is \(\max(P, W/C)\), where \(P\) is the critical path, \(W\) is
   total work, and \(C\) is slot capacity. This is not a prediction for
   heterogeneous runners, contention, locks, or autoscaling. Replay observed
   arrivals and job durations when shared-pool contention could reverse a local
   speedup. Produce a bottleneck explanation, not just a slow-job list. [C1-C3]

4. **Prove selection and gates.** Derive affected work from declared inputs and
   transitive consumers. Validate comparison commits and available Git history.
   Construct a truth table for ordinary, shared-config, unknown-file, large-diff,
   source-only, merged, fork, and missing-history cases. Missing information
   takes the broader path. Check task identities and intended partitions,
   not only counts. An aggregate gate accepts skipped work only when a valid
   selection decision justifies it. Exercise failure, cancellation, empty
   selection, and missing expected jobs. Shadow a proposed selector against the
   full gate before relying on it. Shadow coverage reduces uncertainty but
   does not prove graph completeness. [C4, C7-C11, C20]

5. **Specify reliability and artifact trust.** Classify failures as product,
   test, infrastructure, external dependency, or unknown. Keep first-attempt
   diagnostics and repair time. Define retry budgets and quarantine ownership,
   review dates, coverage loss, and restoration evidence. For release builds,
   connect the authorized source revision to the tested artifact and deployed
   digest. Promote that artifact where the release contract permits it, rather
   than rebuilding per environment. Verify provenance policy at consumption.
   Test cold-cache recovery, clean rebuilds, and relevant environmental
   variations. Produce failure and trust-boundary policies. [C5-C6, C12-C18, C22]

6. **Compare target designs and maintenance cost.** Compare the smallest viable
   topology with selective execution, sharding, or distributed builds only
   where evidence supports them. State latency, total attempt consumption,
   capacity, assurance, artifact transfer, isolation, and operating-cost effects.
   Name owners for runner images, reusable components, pins, selectors,
   quarantine, and retention. Include update and rollback procedures. Provider
   configuration validation and representative event-state tests are required.
   Keep hosted-setting changes separately authorized. [C19-C21]

7. **Measure net impact and keep the result reviewable.** Change one causal
   class at a time. Record comparable before and after samples and uncertainty.
   Measure trigger-to-first trustworthy feedback, trigger-to-required-gate
   completion, time to green across retries, first-attempt reliability, total
   runner consumption, queue delay, and maintenance effort. Exclude superseded
   runs from latency distributions when appropriate, but retain their resource
   cost and cancellation rate. Check lost verification, deploy failures, and
   rollback criteria. Relate results to DORA delivery outcomes only over a
   suitable observation period. CI latency is not commit-to-production lead
   time, and correlation does not attribute a delivery change to CI alone. [C22]

## Tradeoffs that require repository evidence

| Technique | Benefit to test | Cost or rejection condition |
| --- | --- | --- |
| More workers or shards | Lower dependency-respecting execution time | Repeated setup, transfer, memory contention, or a saturated shared pool can increase consumption and queue delay. Balance measured durations rather than file counts. |
| Affected execution and result caching | Avoid unchanged work | Incomplete dependencies or wrong comparison commits lose verification. Broadly shared changes limit savings. External-state tests may require fresh execution. |
| Merge queues or trains | Validate concurrent changes against integration state | Speculation, flakes, and invalidation consume extra work. Low merge contention may not justify added configuration or entitlement requirements. |
| Fast review checks and deeper release checks | Earlier actionable feedback | Moving a check changes when defects become visible. Preserve each required decision's assurance and exact artifact contract. |
| Build once and promote | Keep tested and deployed artifact identity consistent | Packaging differences, platform targets, or authorized revision changes can require distinct builds. Do not promote an unrelated review artifact. |
| Retries and quarantine | Reduce false blocking failures | Retries increase detection delay. Quarantine removes blocking coverage. Neither is evidence that a race or product bug is harmless. |
| Ephemeral isolated runners and scoped credentials | Reduce persistence and credential exposure | Provisioning and cache warmup add cost. Assess network reachability, cache writers, and artifact consumers even with clean runners. |
| Shared workflow components | Centralize policy and updates | Deep nesting, mutable references, secret propagation, and naming collisions increase debugging and rollout cost. Test consumer contracts. |

No prices or savings are asserted here. Capacity, storage, network, idle fleet,
maintenance, and incident costs belong in an implementation's account-specific
measurement. Provider limits and GitLab features depend on version, offering,
and entitlement. Recheck the linked documentation before applying a design.

## Gaps relative to the reviewed skill

| Priority | Existing coverage | Addition worth considering |
| --- | --- | --- |
| High | Baseline collector and read-only evals | Explicit metric origins, complete pagination, all-attempt accounting, completeness warnings, and fixtures that detect truncation and pre-start delays. Cover implementation behavior and refresh stale scenario expectations. See supplied local evidence below. |
| High | Job inventory, critical path, and output consumers | A normalized task graph plus artifact graph, resource locks, and trust-boundary annotations. Model target topology rather than optimizing only job durations. |
| High | Required checks and fail-closed selection | Event-state contract tests, tested revision identity, task identity coverage, provider skip semantics, and explicit combined-commit validation. |
| High | Queue time and runner constraints | Shared-pool demand, dispatch and provisioning limits, resource profiles, speculative merge work, and contention-aware estimates. |
| High | Failure and retry frequency | First-attempt evidence, failure taxonomy, time to repair, bounded retry policy, and owned quarantine with restoration criteria. |
| High | Least privilege, pinning, and provenance preservation | Concrete untrusted-to-privileged data paths, cache writer policy, artifact verification at consumption, and isolated runner lifecycle. |
| Medium | Reproducible cache inputs and cold-cache validation | Clean-build and environmental-variance probes. Distinguish reproducibility, hermeticity, isolation, and provenance. Qualify verdict-caching guidance for sound native test-result caches. |
| Medium | Ownerless-work deletion and reversible implementation | Versioned reusable-component contracts, image and pin updates, ownership, retention, and recurring maintenance cost. |
| Medium | Latency and consumption comparisons | Trustworthy feedback and time-to-green measures that include failures. Use application-level delivery outcomes as guardrails, not CI optimization targets. |

Local evidence collected in the [source thread](https://ampcode.com/threads/T-01a11e8f-5606-71ac-902d-cff71b7a20e5)
through direct inspection and a synthetic fixture in its `nthplusio/skills` checkout:

- `scripts/gh_ci_baseline.py` under the skill fetches at most 100 jobs without
  pagination, fetches only the latest retry attempt, and measures elapsed time
  from `startedAt`, not `createdAt`. Therefore complete runner consumption and
  trigger-to-completion latency need additional collection or explicit limits.
- A synthetic metric-definition fixture has trigger 00:00, attempt start 00:05,
  job start 00:07, and completion 00:09. It reports elapsed 240 seconds and
  longest job queue 120 seconds. Trigger-to-completion is 540 seconds. These
  quantities have different origins. Do not add the queue to elapsed, because
  it overlaps that interval. This is not a real CI benchmark or speedup claim.
- All three existing evals are read-only. Eval 2 expects two jobs, while the
  source thread's local `.github/workflows/validate.yml` has `validate`,
  `plugins`, and `builder-agrees`. These findings identify incomplete mode
  coverage and a stale fixture, not evidence that repository CI is unhealthy.

Recommendation: preserve the short measured-optimization entry point. Put these
methods in a deeper architecture reference and provider-specific references,
invoked when contracts, shared capacity, reliability, or cross-pipeline artifacts
make a local optimization unsafe or incomplete. If the skill expands to new
pipeline design, make that scope explicit. Its present exclusion of new-workflow
creation is consistent with requiring observed baselines, so architecture design
without history must keep estimates labeled and define a validation plan.

## Proposed reference structure

This is a proposal, not an implemented split. Keep scope, authority, repository
profile, mandatory contract discovery, evidence limits, and completion criteria
in `SKILL.md`. Make design a deliberate mode, including repositories without
run history, rather than only a fallback when provider access is missing.

Load references at the decision they support. Redistribute the current
`optimization-levers.md` into the relevant references instead of maintaining
duplicate rules and ranking tables.

| Proposed path under `references/` | Decision and load condition |
| --- | --- |
| `measurement.md` | How to collect and compare evidence. Load when analyzing history or validating an improvement. Define timestamp origins, all-attempt consumption, incomplete data, workload classes, and uncertainty. |
| `architecture.md` | What runs on each event and which artifact it verifies. Load for pipeline design or changes to job boundaries, dependencies, selection, concurrency, matrices, or artifact flow. |
| `performance.md` | Which measured constraint to change. Load for queue, setup, compute, I/O, network, cache, transfer, or test bottlenecks. Require an observation that discriminates between competing explanations. |
| `simplicity.md` | Whether a structural change earns its complexity. Load when proposing components, generated matrices, selectors, custom scripts, or workflow consolidation. Compare the current design, the smallest change, and a larger redesign. |
| `maintenance.md` | Who operates and updates the design. Load when introducing persistent images, self-hosted runners, shared workflows, caches, retained artifacts, or new external dependencies. Require owners and update, recovery, and retirement procedures. |
| `reliability.md` | Whether failures remain useful and truthful. Load for retries, flakes, quarantine, cancellations, aggregate gates, external dependencies, or cleanup. Require failure-state validation. |
| `security.md` | Which trust boundary a change crosses. Load when changing credential-bearing jobs, fork execution, runner isolation, cache writers, artifacts, or provenance. Keep the mandatory trust check in the main skill. |
| `impact.md` | Whether an improvement is worth delivering. Load when ranking candidates and accepting results. Compare latency, consumption, run frequency, assurance, maintenance effort, implementation cost, uncertainty, and rollback criteria. |
| `providers/<detected-provider>.md` | How the provider implements the contract. Load only the detected provider's reference. Start with GitHub Actions and GitLab. Cover hosted rules, event and diff semantics, skips, includes, concurrency, artifacts, validation, and current documentation links. |

Each reference should contain evidence to gather, decisions to make, rejection
conditions, and verification cases. Avoid a general CI textbook or copied
provider documentation. If simplicity and maintenance remain short and have no
distinct execution branches, combine them into one reference.

The repository profile should name the deliverables, supported platforms,
build and test tools, external services, contribution model, release cadence,
change volume, risk requirements, CI owners, and practical budgets. Mark unknown
inputs rather than deriving a policy from the programming language alone.

## Evaluate architecture behavior as well as optimization reports

Preserve the existing blinded, with-skill versus baseline evaluation method.
Use versioned fixtures or pin real-repository scenarios to revisions so workflow
changes do not silently invalidate expected behavior. Add scenarios that expose
plausible wrong decisions:

- A repository with no CI history needs a justified design and validation plan,
  not invented measurements or a refusal to design.
- A shared runner pool is saturated, so more shards increase queue pressure.
- An unknown file or shared lockfile invalidates an otherwise narrow selector.
- A failed or cancelled prerequisite must not produce a green aggregate gate.
- Fork inputs reach a privileged cache or artifact consumer.
- A release consumer requires the tested artifact's digest and exact revision.
- Native dependency-aware test-result caching is appropriate, while an ad hoc
  pass flag is not.
- A small pipeline has no worthwhile improvement and should remain unchanged.
- A GitLab scenario requires different event and artifact semantics from GitHub.

Keep collector checks separate from agent evaluations. Collector fixtures should
detect truncated job lists, missing permissions, unknown revisions, initial
queue delays, multiple attempts, and incomplete API responses. Agent evaluations
should grade observable gate correctness, evidence quality, design justification,
and mutation authority rather than the number of recommendations produced.

Source limitations: the Google testing page's Markdown conversion omitted the
article body. The claim above uses the retrieved HTML article body, not its
comment thread. Google's historical percentages are deliberately not
generalized. Apart from the explicitly attributed local evidence, no repository
CI, hosted settings, benchmark, deployment, or billing data was collected for
this research.
