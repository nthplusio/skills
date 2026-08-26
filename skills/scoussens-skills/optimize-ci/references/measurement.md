# Measuring CI

Use this reference to establish a baseline and compare changes. The method is
provider-neutral; adapt collection to the repository's CI system.

## Define the run class

Do not mix unlike runs. A run class should hold these dimensions constant:

- event type — pull request, default-branch push, schedule, manual, release
- operating system, architecture, runner size, and hosted or self-hosted status
- matrix shape and enabled feature set
- cold or warm dependency and build caches
- test scope and service dependencies
- branch protection and deployment behavior

Exclude cancelled runs from duration percentiles unless cancellation behavior is
the subject of the evaluation. Report failed and retried runs separately because
they contribute consumption even when they do not represent steady-state speed.

Match each run to the workflow revision under evaluation. If the checkout is
dirty or its workflow is newer than hosted history, report the mismatch and do
not attribute historical timings to the unrun topology.

## Use the right quantities

For a run with jobs `J`:

- **Feedback latency** is completion time minus trigger time. Split it into queue
  time and execution time when the provider exposes both.
- **Critical-path execution** is the longest dependency-respecting path through
  the job graph. It is not always the duration of the longest individual job.
- **Raw runner time** is the sum of execution durations across all jobs in `J`.
- **Billed consumption** applies provider rounding, operating-system or runner
  multipliers, included allowances, and self-hosted policy to raw runner time.
- **Reliability cost** includes time consumed by failures, retries, flakes, and
  abandoned superseded runs.

Never call raw runner time “billed minutes” unless the provider confirms that the
two are identical for the evaluated plan and runner types.

## Collect enough evidence

Prefer 20–50 recent successful runs per class for a baseline. Compute p50 and p90
for latency and raw runner time. Also report the number of runs, date range, and
cache classification.

When only one or two runs exist for the current topology, use all of them and
show their individual values. Do not label a single value as a median or infer a
p90 from a tiny sample. Keep older-topology runs in a separate baseline rather
than padding the sample.

For a small before-and-after implementation, aim for at least three comparable
runs on each side. Use more when variance is high. If the provider is expensive
or inaccessible, state that the result is a local or modeled estimate.

Capture one row per run:

| Run | Commit | Event | Started | Queue | Elapsed | Runner time | Cache | Result | Retries |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

Capture one row per job or important step:

| Run | Job or step | Depends on | Duration | Runner | Repeated work | Required consumer |
| --- | --- | --- | --- | --- | --- | --- |

Provider logs are preferred for hosted effects. Local timing is useful for test,
build, and setup changes when the machine, command, data, and cache state are held
constant.

Record cache state as `unknown` or `unclassified` when the provider exposes
timings but not cache logs. Do not infer a hit from a fast install.

## Discover the full system

Search beyond the obvious workflow file. Common sources include:

- `.github/workflows/`, `.gitlab-ci.yml`, `.circleci/`, `Jenkinsfile`,
  `.buildkite/`, `azure-pipelines.yml`, and provider-specific includes
- package scripts, task runners, Makefiles, hooks, and container build files
- test setup, global fixtures, coverage configuration, and service containers
- branch rules, required checks, merge queues, environment approvals, and hosted
  variables
- deployment integrations that subscribe to pushes, checks, artifacts, or tags

Treat workflow comments and documentation as claims to verify against hosted
settings and recent runs.

Public run visibility does not imply access to branch rules, secrets,
environments, billing, or deployment integrations. If authenticated inspection
fails, mark those facts unknown. Do not infer a required check from a job name.

## GitHub Actions specifics

`scripts/gh_ci_baseline.py` handles the first five of these. They are written
out so you can recognise them when you query by hand or read someone else's
numbers.

**Required checks live in two places, and each API is blind to the other.**
Rulesets are read with `gh api repos/{owner}/{repo}/rules/branches/{branch}`.
Classic protection is read with
`gh api repos/{owner}/{repo}/branches/{branch}/protection/required_status_checks`.
A repository can use either or both. `gh api repos/{owner}/{repo}/branches/{branch}`
can report `"protected": true` with an empty `required_status_checks`, because
a ruleset is what requires the check. Read both before saying a branch has no
required checks.

**A 404 from the classic endpoint is ambiguous.** The message `Branch not
protected` means no classic rule. A bare `Not Found` or a 403 means the token
cannot read protection, so the answer is unknown, not none.

**`strict` means a pull request must be up to date before it merges.** Under
it, every merge to the base branch makes open pull requests stale, and each one
reruns CI after its author updates it. That rerun is real consumption, and it
grows with merge frequency rather than with pipeline length.

**Run history outlives the workflow.** `gh run list` still prints runs of a
deleted or renamed workflow. Confirm what exists with
`gh api repos/{owner}/{repo}/actions/workflows`, which also reports each
workflow's `state` — `active`, `disabled_manually`, or `disabled_inactivity`.

**A skipped job reports equal start and end times.** A job skipped by an `if:`
on some events, such as a deploy-only job on a pull request, looks like a
zero-second job. Leave it out of durations, or its median collapses.

**The jobs API does not report `needs:`, but its timestamps do.** Each job's
`created_at` is when it became runnable. A job created the moment another
finished is waiting on it, so start and end offsets from the run's start
recover the serial chain. Confirm the chain against the workflow file before
you rely on it.

**`gh run watch --exit-status` exits 0 for a cancelled run.** Read the
conclusion with `gh run view <id> --json conclusion` instead of trusting the
exit code. The same applies to any wrapper that treats exit 0 as success.

**Billing rounds each job up to a whole minute.** Thirty 20-second jobs bill as
thirty minutes, not ten, so many small jobs can cost more than one long one.
Standard GitHub-hosted runners are free for public repositories; larger runners
are billed even there. Private repositories pay per-OS rates against the plan's
included minutes, so take rates from the account's current pricing rather than
from memory.

## Control benchmark noise

- Compare the same commit where possible.
- Separate cold and warm caches.
- Keep runner type, matrix, database image, dependency lockfile, and test scope
  constant.
- Record test file and test-case counts.
- Avoid comparing a local workstation directly with a hosted runner.
- Report medians and ranges; do not select the best run.
- Check whether queue time dominates before tuning execution.

## Bound each opportunity

For a stage consuming fraction `f` of the measured objective, deleting that stage
cannot save more than `f`. Optimizing it by fraction `r` has an upper bound of
`f × r` before secondary effects.

For parallel changes, calculate both objectives:

- Splitting a 20-minute serial job into two 11-minute jobs may cut feedback time
  by about 9 minutes while increasing raw runner time from 20 to 22 minutes.
- Combining two 8-minute independent jobs may reduce setup and billed rounding
  while increasing the critical path.

State which trade the user selected.

## Compare honestly

A result should name:

- before and after samples
- p50 and p90 feedback latency
- p50 and p90 raw runner time
- provider-billed change when available
- cache state
- test and check counts
- failures or retries
- confidence and remaining uncertainty

If only an upper bound is known, call it an upper bound. If the data comes from a
different run class, do not present it as a before-and-after comparison.
