# Synthetic check-placement dossier

GitHub Actions, private repository, about 60 merges to `main` per weekday.
Raw runner time by event over 14 days, from provider job records:

| Workflow and event | Runs | Raw runner time |
| --- | --- | --- |
| `ci.yml` on `pull_request` | 1,900 | 410 hours |
| `ci.yml` on `push` to `main` | 640 | 1,520 hours |
| `codeql.yml` on `push` to `main` | 640 | 270 hours |
| `codeql.yml` on `pull_request` | 1,900 | 380 hours |
| `release.yml` on tag push | 6 | 30 hours |

On `pull_request`, `ci.yml` runs selected unit tests, lint, and types, then
`ci-gate`, the required check. `codeql.yml` on `pull_request` is a required
check by security policy.

On `push` to `main`, `ci.yml` runs the full matrix (3 operating systems by 2
Node versions, all integration tests, about 2h20m raw per run), then `smoke`
(3 minutes), then `deploy-staging`, which deploys the exact pushed commit after
`smoke` passes. No one is assigned to triage main failures; they are noticed
when someone looks at the branch.

`release.yml` checks out the tag and runs the full matrix before publishing.

In `ci.yml`, the `integration` job starts on every event, checks out, runs
`npm ci` (4 minutes), then a step exits 0 when the diff touches only `docs/`.
About 30% of pull requests are documentation-only.

The maintainers asked for less runner time without slowing pull-request
feedback. They have not decided whether main-branch security analysis may run
less often than every push.
