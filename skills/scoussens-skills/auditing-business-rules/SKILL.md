---
name: auditing-business-rules
description: >-
  Audits business-rule consistency, code conformance, and proposed changes against
  a versioned policy registry, with evidence and explicit gaps. Use when asked to
  audit business rules, assess a specification's policy impact, or review a code
  change against approved rules. Does not approve policy or claim unexamined code
  conforms.
compatibility: Requires maintaining-business-rules. Executable registry audits also require its pinned Python 3.9+ validator, Git, and a POSIX filesystem.
---

# Auditing business rules

Compare approved intent with observed behavior without changing either to erase
the disagreement. Separate findings about policy, code, and architecture.

## 1. Select the question and pin the inputs

Choose the requested mode:

- **Consistency:** inspect rules, proposals, exceptions, and dependencies for
  contradictions, missing decisions, and inconsistent terminology.
- **Conformance:** trace accepted policy through code, configuration, and entry
  points at a named revision.
- **Change impact:** compare a specification or code change with accepted policy
  and proposed policy amendments.

Load `maintaining-business-rules` for its shared contract. If unavailable, stop
the executable audit and name that dependency; do not recreate its schemas.

For a proposal-only consistency review without a registry, identify the supplied
statements, scope, provenance, and missing ownership or effectivity decisions.
Keep proposals distinct from approved policy. No executable validator, registry,
or code snapshot is required. Continue with the semantic checks in step 3 and
the conversational report in step 4; leave code conformance not assessed.

For registry-backed audits, resolve the maintenance scripts directory as
`RULES_TOOL` and use the version pinned by that registry. Read project guidance,
domain owners, scope, glossary, and external registry pins. Run `rules.py validate`;
for a PR, include the trusted base commit. Choose an explicit policy as-of time.
For a whole-repository snapshot, use the same commit as base and head. For a
specification or uncommitted change, inspect it read-only and provide a provisional
assessment; commit-based reports require immutable snapshots. Do not commit user
work merely to satisfy the report tool.

**Done when:** mode, supplied evidence, examined domains, and inaccessible sources
are explicit; registry-backed audits also identify registry/code revisions or
provisional inputs and the policy as-of time. Unavailable facts remain unknown.

## 2. Determine affected rules and surfaces

Inspect the actual diff or specification, not only its stated intent. Use bindings
as starting points; also inspect changed code with no bindings. Trace callers,
data/configuration dependencies, API routes, UI validation, jobs, queries, schema
constraints, migrations, and reference data that can change the outcome.

For fresh discovery, load `business-rules-catalogue` and preserve its independent
checking contract. For existing snapshots, verify source freshness and select
the relevant binding explicitly. Reused display IDs and old Correct reviews do
not establish a match or approval. Report skipped surfaces and incomplete traces.

**Done when:** every changed policy-bearing area has a rule mapping or an explicit
unrecorded-behavior finding; scope exclusions are named rather than treated as passes.

## 3. Investigate findings at the appropriate strength

Read [audit judgments](references/judgments.md). For every claimed conflict, give
a concrete input/context in which rules demand incompatible outcomes. Examine
both sides of thresholds, actor/scope differences, effective dates, precedence,
and partial-failure or retry guarantees. A suspected conflict is not a proof.

For code conformance, execute established contract tests or targeted scenarios
when practical. Derive expected outcomes from approved policy, not the code under
test. Retain the command, code revision, environment, and decisive output. Source
review can establish a specific path, not universal enforcement across unseen paths.

For PRs, assess base code/base policy, head code/base policy, and head code/head
effective approved policy. Check approval evidence for every changed rule and
owner designation. Proposed amendments cannot justify a mismatch. A legitimate
replacement keeps the old-policy discrepancy visible while identifying approval
and head conformance. Never rewrite a rule to make the report pass.

**Done when:** each conclusion names its rule revision, scenario, evidence, method,
and limitation. Missing evidence remains not assessed or potential, not confirmed.

## 4. Produce the artifact and route decisions

For committed local-registry audits, use the shared tool:

```bash
python3 -B "$RULES_TOOL/rules.py" audit-context --repo "$REPO" \
  --base "$BASE" --head "$HEAD" --as-of "$AS_OF" > context.json
```

Use `selected_policies` to identify exact comparisons, then remove that helper
field when preparing the input matching the `audit` schema definition. Fill scope,
exclusions, limitations, assessments, and unrecorded behavior. Set `binding_ids`
to the snapshots actually used, or leave it empty when investigating code directly.
Aggregate scenarios for a rule/comparison in one assessment; include all relevant
evidence. The tool fills omitted accepted-rule comparisons as not assessed.

```bash
python3 -B "$RULES_TOOL/rules.py" report --repo "$REPO" \
  --base "$BASE" --head "$HEAD" --as-of "$AS_OF" \
  --input audit-input.json --out "$RUN/report"
```

Deliver `audit.json` and `audit.md`. For semantic review of proposals or a design
without code snapshots, report the same distinctions in the conversation or a
requested document; do not manufacture commit IDs or approved-policy assessments.
Report generation validates context and evidence shape, not the truth of evidence.

Route proven violations to a fix, approved amendment, or scoped owner waiver.
Send policy ambiguity to the designated owner through maintenance. Keep unmapped
behavior unratified. Deterministic validation and established contract tests are
the initial CI gates; semantic findings require review. Posting PR comments,
opening tickets, changing code, or publishing artifacts needs the applicable
authorization; an audit request alone is read-only apart from its local reports.

**Done when:** the reader can distinguish must-resolve findings, approved policy
changes, waivers, suspected conflicts, and uncovered behavior; code/policy freshness,
audience, verification limits, and actual delivery state are explicit. Never infer
production conformance without deployment and configuration evidence.
