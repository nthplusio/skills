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
