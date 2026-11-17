# CI architecture eval results

Run date: 2026-10-09. These are synthetic behavior evaluations, not CI benchmarks.
The source checkout started at
[`1175987`](https://github.com/nthplusio/skills/commit/1175987a3a96614345ef5cb930ca1ed5b504e56c).
Changes remain local and uncommitted.

## Coverage and method

27 independent samples completed: two nine-case with-skill rounds, four extra
with-skill economics samples, and five no-skill samples. No samples errored or
were abandoned. Assertions and expected answers were withheld from workers.
Graders received response files without configuration labels; the parent
inspected their evidence and corrected unsupported grades. Raw responses,
original grades, and corrections were exported as review evidence in the thread.

The no-skill samples cover cases 0, 2, 3, and 7, with two fixture versions for
case 2. This is not a full paired comparison or evidence of a general skill
advantage. Old Iteration 1 scores use different fixtures and are not comparable.

The suite has 51 assertions after adding native-command and checkout-revision
checks. The final full round preceded a reporting clarification and the case 2
provider correction. Only case 2 was rerun afterward; do not report these samples
as a full-suite run of the final revision.

## Decisions observed

| Case | Reviewed evidence |
| --- | --- |
| 0, latency | Preserved the ruleset check, migration edge, and exact-main deploy consumer; separated PR evidence and bounded savings. Absence of hosted actions was self-reported, not independently audited. |
| 1, consumption | Counted 992 raw minutes; rejected two five-minute shards as a 25% work increase; left actual charges and rerun savings unquantified. |
| 2, no worthwhile change | Every sample retained the three jobs. On the corrected provider-specific fixture, one of two with-skill samples explicitly recognized free standard public runner execution; the other and the baseline omitted it. Billing reporting remains inconsistent. |
| 3, initial design | The first answer generated nonexistent `unit` and `integration` scripts and mislabelled default Actions PR checkout as head-only. The next answer used `test:unit` and `test:integration` and explicitly deferred revision semantics until provider selection. |
| 4, shared capacity | Diagnosed the shared queue constraint and rejected blind sharding or larger runners. |
| 5, selection | Selected broadly for unknown inputs and rejected failed, cancelled, missing, or unjustifiably skipped expected work. |
| 6, trust | Rejected fork artifacts and writable caches reaching privileged release execution; required producer, revision, digest, and trust controls. |
| 7, native cache | Accepted qualified Bazel reuse, rejected a saved pass flag, and addressed GitLab events, artifact identity, and the temporary source-plus-target revision. |
| 8, implementation | The parent executed the copied gate checker successfully and verified unchanged source hashes. No hosted-action claim was independently audited. |

## Eval corrections and remaining uncertainty

The original case 2 fixture said "public repository" and "standard hosted
runners" without naming a provider. Four with-skill samples and one no-skill
sample omitted GitHub's billing exemption or treated billing as unknown. That
assertion was under-specified: GitHub's exemption does not follow from generic
public visibility. Those economics grades are invalidated. The corrected fixture
names GitHub Actions and standard GitHub-hosted Linux runners, and removes the
sentence that supplied the desired no-change verdict. Compare only samples
using the same fixture version. The corrected 1/2 recognition result is a
reporting limitation, not a claim that the rule itself is uncertain.

The parent also corrected two grader errors. The revision assertion expressly
allows deferral while provider choice is unresolved. The GitLab answers define
the merged revision as source plus target, not merely a "combined" keyword;
the baseline additionally says not to treat it as the source branch alone.
Response evidence does not prove a worker made no hosted calls. Keep those
authority assertions unverified rather than converting self-reports to passes.

## Cases 9 to 11 (2026-11-17)

These cases cover test value, packing and runner sizing, and check placement.
One with-skill and one no-skill sample ran per case against the same fixture
revision, with assertions withheld from workers. The parent graded them
without blinding, so treat these as indicative, not a blind comparison.

| Case | With skill | No skill | Assertions the baseline missed |
| --- | --- | --- | --- |
| 9, test value | 8/8 | 7/8 | `planted_fault_proof`: asked for a mutation check only on the retry test, not before each removal or consolidation |
| 10, sharding and size | 7/7 | 6/7 | `trial_smaller_runner`: compared times on smaller runners without recording peak memory or billed units |
| 11, stage placement | 8/8 | 7/8 | `schedule_named_revision`: scheduled main HEAD without recording the tested commit or retaining results |

Both configurations rejected 40 shards, kept the sole webhook guard, and kept
the required PR CodeQL check, so those assertions do not discriminate. The
differences sit in proof and evidence requirements, not in the headline verdict.
One sample per configuration cannot establish a general skill advantage.

## Case 12 (2026-11-17)

Case 12 covers selector rollout gates. The first fixture, with a prediction
written after the run and one PR pushed 31 times, did not discriminate: one
sample per configuration, both 7/7. That baseline also reported the exact
zero-miss bound, about 26% for 10 episodes, where the with-skill sample used
3/N; the reference now names the exact bound for small N.

The fixture was rewritten with subtler traps: 95 bot PRs that share one root
cause, a backtest of sibling-test fixes only, shard-less tests dropped with a
warning, a count-based gate, a nightly backstop with no owner, and a model
compared only on planted mutations. The pre-run prediction, unmapped-file
fallback, and switch are adequate, and one assertion penalizes flagging them.
Two samples per configuration ran; the parent graded them without blinding.

| Sample | Score | Missed |
| --- | --- | --- |
| With skill A | 8/8 | none |
| With skill B | 8/8 | none |
| No skill A | 7/8 | `model_same_backtest`: excluded the model but never required it to beat the graph |
| No skill B | 7/8 | `model_same_backtest`: same |

Both baselines deduplicated the bot episode, computed the exact 4.1% and 6.3%
bounds, and caught the shard drop, count gate, and nightly gaps from the
evidence alone. The one discriminating assertion does not change the verdict.
With-skill samples also added release gates on the shipped revision, failure
states to exercise, and a benefit check, which no assertion covers.

The fixture was then rewritten a second time around GitHub Actions semantics,
with adequate statistics and controls: `ci-gate` without `if: always()`, a
required check behind a `paths` filter, a `HEAD~1` diff on the PR head, a
skipped `merge_group`, and a shadow comparison that trusts
`gh run watch --exit-status`. Two samples per configuration, graded without
blinding:

| Sample | Score | Missed |
| --- | --- | --- |
| With skill A | 6/6 | none |
| With skill B | 6/6 | none |
| No skill A | 5/6 | `cancelled_counts_as_pass`: proposed testing a cancelled run, but did not identify the exit-code flaw |
| No skill B | 5/6 | `cancelled_counts_as_pass`: said the exit code treats cancellations as failures, the opposite risk |

Both baselines caught the skipped gate, the pending paths-filtered check, the
last-commit diff, and the merge-queue skip. The only discriminating assertion
restates a quirk documented in the GitHub provider reference. The fixture YAML
also has unintended defects that samples found: no job passes `plan.json` or
test IDs to `unit` and `ci-gate`, and `vars.TEST_SELECTION` is never passed to
the planner. Both baselines flagged the plan wiring and one flagged the
variable; both with-skill samples flagged the plan wiring. The fixture was
corrected after grading: artifacts now carry the plan and executed IDs, and the
planner receives the variable. The samples above ran against the uncorrected
fixture. Treat case 12 as a regression guard, not evidence of skill advantage.

## Collector `--by-workflow` (2026-11-17)

Nine collector tests passed, three of them new. Three planted faults each
failed a new test: reading attempt clocks in the fleet view, counting a run
twice when it shifts across pages, and counting skipped jobs as executed. A
read-only run against this repository over 14 days read 11 of 11 runs, split
8 `push` and 3 `pull_request`, matching an independent `gh run list` count. That
checks API compatibility and grouping, not cost.

## Executable validation

- Collector unittest discovery: six tests passed.
- `npm run validate`: all 14 skills valid, including bundled text assets.
- `npm run check:builder`: all 14 skills discovered by the builder.
- `git diff --check`: passed.
- The source gate checker failed as intended on `invalid skip`; both fixed
  disposable copies passed `aggregate gate checks passed`. Source fixture hashes
  were unchanged; the parent also compared each copied checker with the source.
- A read-only collector smoke against five real GitHub runs returned five
  complete measurements with three jobs each. It checked API compatibility,
  not speed, cost, cache effectiveness, or deployment behavior.

Final execution-doc SHA-256: `28a4a9eaeccd1226847cf4558f3ded197fed424fec4f613e07c90c5fb8a73db6`.
Final fixture SHA-256: `dc24ae5665fdb04796869bbb928c31a534a2546cc6e6be77eaf560988a552d22`.
Each hashes sorted skill-relative paths and contents, separated by NUL bytes.
Execution docs include `SKILL.md` followed by sorted `references/**/*.md`;
fixtures include sorted regular files under `evals/fixtures/`.
