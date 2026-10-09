# Apply GitHub Actions contracts

## Read both protection sources

Inspect rulesets through `repos/{owner}/{repo}/rules/branches/{branch}` and
classic required checks through
`repos/{owner}/{repo}/branches/{branch}/protection/required_status_checks`.
The collector reads both. Empty classic protection does not mean no required
ruleset checks. A plain 403 or 404 is unknown access, not proof of no protection;
an explicit "Branch not protected" response identifies absent classic protection.

Record the required context and any expected GitHub App, not only job names.
Inspect strict up-to-date requirements and merge-queue policy. Strict updates can
create consumption as main advances; count actual reruns before claiming their
impact. Public history does not establish private rules or deployment settings.

## Validate events and verdicts

Required checks must report on the intended revision and supported event.
For an open, mergeable `pull_request`, the default `GITHUB_SHA` and checkout
refer to its test merge revision, not its head. Explicitly checking out
`github.event.pull_request.head.sha` changes that assurance. Match the reported
revision to the actual checkout, and use the merge-group revision for
`merge_group`. Confirm these mappings in the
[event reference](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request).

[Required-check troubleshooting](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)
distinguishes pending checks from filtered-out workflows, successful conditional
job skips, and skipped dependents after a prerequisite fails. Stable aggregate
gates must run after failure and explicitly inspect expected conclusions.

[Merge queues](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)
need `merge_group` in required Actions workflows. The combined revision differs
from the pull-request head. Count speculative builds and invalidated queue work;
merge limits do not themselves combine CI builds. A manual run on a PR branch
is not automatically an eligible required PR check.

Native path filters use event-dependent diff comparisons and have changed-file
limits. They are not a fail-closed dependency selector. Exercise broad diffs,
new files, shared inputs, and missing history. Read current
[workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
before relying on filters, expressions, matrices, or cancellation behavior.

## Treat collection as partial evidence

List active workflows instead of treating old run history as current topology.
Paginate job lists, account for every run attempt, and distinguish skipped jobs
from executed jobs. The attempt endpoint and its job list can establish attempt
timing; job timestamps do not reconstruct `needs:`.

Check emitted context names against the relevant revision and event, not the
union of all historical job names. Reusable workflows, local actions, scripts,
manifests, and image changes can alter effective work without changing the
top-level workflow blob. Inspect them separately.

Read provider conclusions when watching runs. In particular, a successful
`gh run watch --exit-status` exit does not distinguish every cancelled outcome.
Use `gh run view <id> --json conclusion` before reporting success.

## Preserve cache, artifact, and credential boundaries

[Caching](https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching)
is optional reuse; artifacts transfer specific outputs. Confirm cache branch and
writer scope, artifact source and digest, and retention. Assume restored contents
can be untrusted. Forks can read accessible base-branch caches.

Privileged `pull_request_target` and `workflow_run` consumers must not execute
untrusted checked-out code or artifacts with release credentials. Inspect runner
isolation, explicit permissions, pinned actions, and OIDC trust claims using
[secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use).

## Validate without overstating hosted effects

Use an installed Actions-aware validator such as `actionlint` when available.
Exercise aggregate scripts and selection locally. Hosted checks, environment
approvals, and deployment integrations require authorized provider evidence;
local YAML validation alone cannot confirm them.

Per-job rounded minutes are not the bill. Standard hosted execution in public
repositories is free; larger runners are charged even in public repositories.
Use [GitHub's billing policy](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
and current account rates, rounding, allowances, storage, and runner
classification before quoting cost. Do not infer a runner is billable from its
label alone.
