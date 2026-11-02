# Audit judgments

## Consistency is not schema validity

Start with scope: two rules can differ without conflicting when they govern
different actors, products, jurisdictions, periods, or states. Check the glossary
before treating similar words as equivalent. A pinned `exception_to` relationship
is explicit context; hierarchy membership is not inherited precedence.

For a suspected conflict, identify both exact rule revisions or quote the supplied
unversioned proposals. Construct a scenario that satisfies both sets of conditions
and state the incompatible required outcomes.
If scope or meaning is unresolved, classify it potential and name the missing
decision. If conditions cannot overlap, explain why the apparent conflict dissolves.

Distinguish:

- Confirmed conflict: the reviewed scoped rules demand incompatible outcomes in
  the supplied scenario. This is not a proof over every possible input.
- Potential conflict: meaning, applicability, or evidence remains uncertain.
- Not assessed: the rule, dependency, or surface was not examined sufficiently.

Look for unreachable decisions, missing cases, duplicate decisions with divergent
thresholds, stale exception targets, and undefined ordering. The shared validator
checks references and cycles, not these semantic properties. Use a domain checker
for exact range/table reasoning only when its semantics and actual execution are
known; never describe a model's prose assessment as a solver result.

## Code evidence

Inspect the deciding condition and paths reaching it. A function named `authorize`
or a passing happy-path test is not proof of authorization on every entry point.
Trace bypasses, UI/backend duplication, batch jobs, database defaults, and policy
configuration. Repeat deliveries and failures can change business outcomes too.

Evidence identifies its source revision and method: executed test, source review,
or semantic review. For execution, retain actual input, independently derived
expected result, output, command, and relevant environment. A mocked fixture only
establishes its own contract. For external services or production-only configuration,
state what was inaccessible and what conclusion depends on it.

An architectural duplication finding is not itself a business-rule violation.
Show differing behavior or a missing required enforcement boundary before making
that stronger claim. Tests and implementation bindings are evidence, never policy
approval. Do not derive expected results by running the same production function
that the test is meant to challenge.

## Report semantics

The shared `audit` input contains exact base/head code and registry digests,
as-of time, scope, exclusions, limitations, assessments, and unrecorded behavior.
An assessment identifies one selected rule revision and code/policy comparison,
an outcome, method, evidence list, scenario, and optional waiver decision ID.

Outcomes are `conforms`, `violation`, `confirmed-conflict`, `potential-conflict`,
or `not-assessed`. `conforms` means the supplied evidence supports the examined
scope; method and exclusions remain visible. A violation or conflict requires a
concrete scenario. A proposal-only conflict belongs in the semantic review, not
an assessment falsely presenting the proposal as selected approved policy.

The report derives disposition separately:

- `must-resolve`: a reader-reported violation or confirmed conflict.
- `advisory`: conformance, incomplete assessment, or potential conflict.
- `resolved-in-head`: base code violated a rule, but head code has reported
  conformance against that same base-policy rule revision. The historical outcome,
  scenario, and evidence remain unchanged; missing head/base assessment or
  conformance only against a different policy cannot establish a repair.
- `approved-policy-change`: head differs from base policy, but a different
  effective approved revision of the same rule has reported head conformance.
- `waived`: an owner-approved waiver covers this finding and exact rule revision,
  has not expired, and its pinned source matches the assessed code.

Recording a waiver changes Git HEAD. The tool allows registry-metadata-only
differences from its `code_commit`, but no application source/configuration/test
changes. A waiver covers one finding ID and target revision; it does not authorize
unrelated findings or an indefinite exception. The report verifies recorded scope,
not the human identity behind the owner's attestation.

Retirements, cross-ID splits/merges, and external dependency changes need explicit
review of their consequences. The tool does not automatically clear their old-policy
findings. Preserve the discrepancy and cite the approved transition in the review.

Summary `reported-conformance-within-scope` is not an automatic CI pass. Empty
policy, omitted comparisons, stale binding source, external dependencies, excluded
scope, named limitations, or resolved historical violations require review.
Report exit 0 means generation succeeded;
`ci_gate: not-evaluated` remains explicit. The report does not execute reader-supplied
commands. Only independently executed checks establish their claimed results.

Keep changed behavior and required decisions first in the PR summary. Include
rule IDs/revisions, counterexamples, source citations, and commands with decisive
output. Preserve inaccessible evidence as a limitation. Rebuild the report after
either head code or the registry changes; stale context is rejected. Publishing
source material or a review page beyond its permitted audience needs approval.
